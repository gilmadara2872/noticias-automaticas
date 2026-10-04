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
import collect

# Palavras-chave monitoradas: fonte unica em common.py (segredo KEYWORDS).
KEYWORDS = common.KEYWORDS

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def normaliza(s):
    """minusculas sem acento, para casar 'Correa' com 'Correa'."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def cita(texto, keyword):
    """True se o texto cita a keyword (todas as palavras dela, sem acento).

    ATENCAO - por que isto NAO e um simples 'all(p in t for p in palavras)':
    esse teste dava FALSO POSITIVO grave. "Kenneth Correa" (2 palavras)
    era satisfeita por um texto sobre o jogador "John Kennedy": as duas
    palavras aparecem, so que em outra ordem e separadas. Com as consultas
    por veiculo, que trazem 100 itens, isso encheva o banco de materia de
    futebol e de politica.

    Por isso exigimos o NOME INTEIRO como sequencia, com espaco em volta:
    ' kenneth correa ' ou ' kenneth  correa ' (espaco duplo quando o
    original trazia <strong>). Isso mantem o match no meio da frase e
    descarta quem tem so o sobrenome em outro contexto.
    """
    t = normaliza(texto)
    partes = normaliza(keyword).split()
    if not partes:
        return False
    nome = " ".join(partes)
    # aceita espacos extras entre as palavras (marcacao HTML bold)
    if re.search(r"\b" + r"\s+".join(re.escape(p) for p in partes) + r"\b",
                 t):
        return True
    return f" {nome} " in f" {t} "


# Palavras que mudam o sentido ou o contexto. Na hora de comparar dois
# titulos para ver se sao a mesma materia, estas nao podem ser ignoradas.
STOP_REPUBLICA = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do", "das",
    "dos", "em", "no", "na", "nos", "nas", "por", "para", "pela", "pelo",
    "com", "sem", "sob", "sobre", "entre", "apos", "apos", "ate", "ja",
    "e", "ou", "mas", "que", "se", "como", "quando", "onde", "qual", "quais",
    "e", "the", "of", "and", "to", "in", "for", "on",
}


def titulo_chave(titulo):
    """Reduz o titulo a uma forma comparavel: sem acento, minusculo,
    sem pontuacao e sem as palavras que nao carregam sentido.

    'iPhone 18, IA e pressão de Trump: o que esperar da Apple' e
    'iPhone 18 IA e pressao de Trump - o que esperar da Apple'
    viram a MESMA chave. Noticias diferentes sobre o mesmo assunto
    continuam com chaves diferentes, porque as palavras que definem
    o assunto sao justamente as que sobram.
    """
    t = normaliza(titulo)
    t = re.sub(r"[^\w\s]", " ", t)
    partes = [p for p in t.split() if p not in STOP_REPUBLICA]
    return " ".join(partes)[:120]


def _bigramas(texto):
    """Conjunto de pares de palavras consecutivas.

    Ordem importa: e a SEQUENCA que distingue duas materias sobre o mesmo
    tema. 'OpenAI adia IPO por seguranca' e 'OpenAI lanca modelo para
    programadores' tem as mesmas palavras soltas, mas nada em comum
    quando olhamos os pares.
    """
    limpo = re.sub(r"[^\w\s]", " ", (texto or "").lower())
    palavras = [p for p in limpo.split() if len(p) > 2]
    if len(palavras) < 2:
        return set(palavras)
    return set(zip(palavras, palavras[1:]))


def corpo_similar(a, b, corte=0.55):
    """0.0 a 1.0. Serve para dizer se dois textos sao a MESMA materia.

    Medido com o caso real do banco (mesma noticia em varios portais):
    pares de materia diferente ficaram entre 0,00 e 0,20; o mesmo texto
    republicado fica acima de 0,50. O corte de 0,55 fica no meio, com
    folga dos dois lados.
    """
    A, B = _bigramas(a), _bigramas(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def _recontido(a, b):
    """0.0 a 1.0: quanto do texto A esta dentro do texto B (ou vice-versa).

    DIFFERENTE do Jaccard, que se mede contra a UNIAO. Aqui a pergunta e
    'um dos dois cabe dentro do outro?', e isso e o que identifica
    republicacao: um portal publica o comunicado e outro publica uma
    versao menor ou reescrita do MESMO texto.

    Calibrado nos pares do banco:
      mesma materia (comunicado reescrito)  -> 1.00, 1.00, 0.56
      materias diferentes                   -> 0.68, 0.34, 0.12
    O Jaccard NAO separa (0.35 para o mesmo e 0.51 para diferentes -
    invertido). O recontido separa.
    """
    A, B = _bigramas(a), _bigramas(b)
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return inter / min(len(A), len(B))


def e_republica(titulo_novo, fonte_nova, ja_publicadas, txt_novo,
                 corte=0.55):
    """True se e a MESMA materia ja publicada em OUTRO veiculo.

    Calibrado nos 903 pares do banco. Medir antes foi o que salvou este
    filtro: duas versoes anteriores (por titulo e por Jaccard de corpo)
    erraram nos dois sentidos porque foram escritas no chute.

    O que os dados mostram (recontido do corpo):

      republicacao entre veiculos distintos:
        0.73, 0.70, 0.68, 0.65, 0.59, 0.56
      materia diferente DENTRO do mesmo veiculo:
        0.74, 0.68, 0.63, 0.54, 0.53

    Os intervalos se cruzam, entao so o recontido nao decide. A evidencia
    que separa e o VEICULO: materia publicada duas vezes no mesmo site
    nao e republicacao, e outra materia da secao "Resumo do dia".

    Regra: recontido >= 0.55 E veiculo diferente. O mesmo comunicado em
    4 portais da cidade passa; os 'Resumo do OD' do Olhar Digital nao.
    """
    if not txt_novo:
        return False          # sem corpo nao da para decidir com seguranca

    for outro in ja_publicadas:
        corpo_antigo = outro.get("conteudo") or ""
        if not corpo_antigo or len(corpo_antigo) < 800:
            continue           # texto curto demais para comparar

        if fonte_nova and outro.get("source") == fonte_nova:
            continue           # mesmo veiculo: materia nova da mesma secao

        if _recontido(txt_novo, corpo_antigo) >= corte:
            return True
    return False


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

# Janela de data. Antes era 7 dias, o que faz o monitor perder materia:
# uma materia so seria coletada 7 dias depois de publicada, e o cliente
# ja teria visto o assunto em outro lugar.
#
# 14 dias e um meio-termo. Para a CAMADA 3 (busca por veiculo) a janela
# e maior: como o filtro por data e feito em Python, aumenta-la nao custa
# requisição - só evita que materia valida do mes passado passe batido.
LAST_N_DAYS = 14

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
        # A coleta em 2 camadas vive em collect.py. Ela existe porque buscar
        # SO pelo nome perde materia de veiculo grande: o paywall do O Globo
        # impede o Google de indexar o nome, que esta no meio do artigo. A
        # camada 2 busca por TEMA e o filtro cita() (aqui mesmo, no monitor)
        # continua decidindo o que e do cliente. Ver collect.py.
        novos = collect.coletar(kw, dias_janela=LAST_N_DAYS, verbose=True)
        for c in novos:
            if c["ts"] / 1000 < limite_ts:
                continue          # fora da janela de gravacao
            coletados.append(c)

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
