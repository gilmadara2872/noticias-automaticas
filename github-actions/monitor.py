#!/usr/bin/env python3
# 05:00 BRT - Monitora Google News (palavras-chave) e salva no Supabase.
# Busca com when:2d e MANTE no banco todas as noticias dos ultimos N dias
# (acumula para graficos; nunca apaga). Dedup por link (nao repete).
import json
import urllib.request
import urllib.parse
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import common

# Palavras-chave monitoradas: fonte unica em common.py (segredo KEYWORDS).
KEYWORDS = common.KEYWORDS

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def normaliza(s):
    """minusculas sem acento, para casar 'Correa' com 'Correa'."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def cita(texto, keyword):
    """True se o texto cita a keyword (todas as palavras dela, sem acento)."""
    t = normaliza(texto)
    return all(p in t for p in normaliza(keyword).split())


def ddg_urls(query):
    """Busca no DuckDuckGo HTML e devolve as URLs reais dos resultados."""
    try:
        data = urllib.parse.urlencode({"q": query}).encode()
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/", data=data,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                                   "AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception:
        return []
    out = []
    for h in re.findall(r'href="([^"]+)"', html):
        if h.startswith("//duckduckgo.com/l/?uddg="):
            h = urllib.parse.unquote(re.search(r"uddg=([^&]+)", h).group(1))
        if h.startswith("http") and "duckduckgo.com" not in h:
            if h not in out:
                out.append(h)
    return out[:6]


def google_news_real_url(gurl):
    """Traduz o link opaco do Google News (news.google.com/rss/articles/...)
    na URL real do veiculo, usando a mesma API interna que o navegador chama.

    Sem isso, quando o DuckDuckGo nao achava a materia pelo titulo, o link
    opaco ia parar no banco e o texto NUNCA era baixado (11 caracteres),
    fazendo a IA classificar so pelo titulo e devolver NEUTRA falso.
    """
    if "news.google.com" not in gurl or "/articles/" not in gurl:
        return None
    try:
        aid = gurl.split("/articles/")[1].split("?")[0]
        req = urllib.request.Request(gurl, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
        sg = re.search(r'data-n-a-sg="([^"]+)"', html)
        ts = re.search(r'data-n-a-ts="([^"]+)"', html)
        if not (sg and ts):
            return None
        inner = json.dumps(["garturlreq",
                            [["X", "X", ["X", "X"], None, None, 1, 1, "US:en",
                              None, 1, None, None, None, None, None, 0, 1],
                             "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                            aid, int(ts.group(1)), sg.group(1)])
        data = urllib.parse.urlencode(
            {"f.req": json.dumps([[["Fbv4je", inner, None, "generic"]]])}).encode()
        req = urllib.request.Request(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute", data=data,
            headers={"User-Agent": UA,
                     "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
        resp = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
        m = re.search(r'\[\\"garturlres\\",\\"(.*?)\\"', resp)
        return m.group(1) if m else None
    except Exception:
        return None


def resolve_url(titulo, fonte, link_google=""):
    """O link do Google News nao expoe a URL do veiculo (pagina JS).
    1o) traduz o proprio link opaco pela API do Google (exato e confiavel);
    2o) so entao cai na busca por titulo no DuckDuckGo (aproximada)."""
    real = google_news_real_url(link_google) if link_google else None
    if real:
        return real
    res = ddg_urls(titulo)
    if not res:
        return None
    dom = normaliza(fonte).replace(" ", "")
    for u in res:
        if dom and dom.split(".")[0] in normaliza(u):
            return u
    return res[0]


def baixa_texto(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception:
        return ""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", html)


def triagem(titulo, keyword, fonte="", link_google=""):
    """FILTRO. Devolve (aceita, url_real, checagem).

    'checagem' diz COMO a noticia entrou, para o resumo poder avisar o
    cliente quando algo entrou sem confirmacao:
      'titulo'      - keyword no titulo (certeza, sem precisar de rede)
      'corpo'       - keyword confirmada no texto da materia (certeza)
      'nao_conferida' - nao deu pra abrir a materia (captcha/timeout)

    Corpo baixado e NAO cita -> descarta (era a origem das aleatorias).
    Corpo inacessivel -> ACEITA e MARCA. Fail-open, mas nunca silencioso:
    e melhor uma noticia a mais, sinalizada, do que um monitoramento que
    emudece sozinho quando a rede aperta."""
    url = resolve_url(titulo, fonte, link_google)
    if cita(titulo, keyword):
        return True, url, "titulo"
    if not url:
        return True, None, "nao_conferida"
    texto = baixa_texto(url)
    if not texto:
        return True, url, "nao_conferida"
    return cita(texto, keyword), url, "corpo"

# Janela do FILTRO em dias: noticias publicadas ate N dias atras sao salvas.
# (O Google com when:2d so devolve ~2 dias, mas o filtro garante o acumulo
#  caso o feed traga mais. Aumente se quiser janela maior.)
LAST_N_DAYS = 7

BRT = timezone(timedelta(hours=-3))  # Brasil sem DST desde 2019 -> sempre UTC-3


def fetch_rss(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")


def parse_items(xml_text):
    out = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate") or ""
        src = (it.findtext("source") or "").strip()
        out.append({"title": title, "link": link, "pubDate": pub, "source": src})
    return out


def main():
    limite = datetime.now(BRT) - timedelta(days=LAST_N_DAYS)
    limite_ts = limite.timestamp()
    coletados = []
    for kw in KEYWORDS:
        q = '"' + kw + '" when:2d'
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
               "&hl=pt-BR&gl=BR&ceid=BR:pt-419")
        try:
            xml = fetch_rss(url)
        except Exception as e:
            print(f"  RSS falhou para {kw}: {e}")
            continue
        for e in parse_items(xml):
            try:
                dt = parsedate_to_datetime(e["pubDate"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(BRT)
            except Exception:
                continue
            ts = dt.timestamp()
            # so aceita dentro da janela dos ultimos N dias
            if ts < limite_ts:
                continue
            t = e["title"]
            fonte = e["source"]
            if " - " in t:
                t, talvez_fonte = t.rsplit(" - ", 1)
                if not fonte:
                    fonte = talvez_fonte
            # FILTRO DE RELEVANCIA: descarta noticia que nao cita a keyword.
            # Resolve tambem a URL real do veiculo (o link do Google e opaco).
            aceita, real, checagem = triagem(t, kw, fonte, e["link"])
            time.sleep(2)  # gentileza com o DuckDuckGo (evita rate-limit)
            if not aceita:
                print(f"  [descartada] {t[:60]}")
                continue
            if checagem == "nao_conferida":
                print(f"  [NAO CONFERIDA] {t[:55]} (materia inacessivel)")
            coletados.append({
                "keyword": kw,
                "title": t,
                "link": real or e["link"],
                "source": fonte,
                "dia": dt.strftime("%Y-%m-%d"),
                "quando": dt.strftime("%d/%m/%Y %H:%M"),
                "ts": int(ts * 1000),
                "checagem": checagem,
            })

    # dedup por link (nao repete nem no proprio lote)
    vistos, unicos = set(), []
    for c in coletados:
        if c["link"] in vistos:
            continue
        vistos.add(c["link"])
        unicos.append(c)
    unicos.sort(key=lambda x: x["ts"], reverse=True)

    print(f"Coletadas {len(unicos)} noticias (janela {LAST_N_DAYS} dias).")
    if unicos:
        # on_conflict=link + resolution=ignore => nao insere duplicado,
        # e NAO sobrescreve o sentimento que ja foi gravado antes.
        st, resp = common.sb_upsert(unicos)
        print(f"Supabase upsert status={st}")
        if st and st >= 400:
            print("  erro:", resp)
    with open("monitor_out.json", "w") as f:
        json.dump(unicos, f, ensure_ascii=False, indent=1)
    print("Pronto (nenhum dado apagado).")


if __name__ == "__main__":
    main()
