#!/usr/bin/env python3
# 05:00 BRT - Monitora Google News (palavras-chave) e salva no Supabase.
# Busca com when:2d e MANTE no banco todas as noticias dos ultimos N dias
# (acumula para graficos; nunca apaga). Dedup por link (nao repete).
import json
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import common

# Palavras-chave NA ORDEM EXATA pedida. As duas grafias de Kenneth sao
# monitoradas separadamente de proposito. Aspas = frase exata (menos ruido).
KEYWORDS = ["Kenneth Corrêa", "Kenneth Correa", "MedGuias", "80 20 Marketing"]

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
            coletados.append({
                "keyword": kw,
                "title": t,
                "link": e["link"],
                "source": fonte,
                "dia": dt.strftime("%Y-%m-%d"),
                "quando": dt.strftime("%d/%m/%Y %H:%M"),
                "ts": int(ts * 1000),
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
