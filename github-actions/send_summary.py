#!/usr/bin/env python3
# 06:00 BRT - Le do Supabase as noticias do DIA ALVO (com sentimento) e envia
# o resumo via Telegram para TG_CHAT_ID. E a UNICA mensagem do dia.
#
# O resumo cobre TODAS as palavras-chave monitoradas: as que tiveram noticia
# aparecem detalhadas; as que nao tiveram sao listadas como "sem noticias",
# para o cliente saber que o robo olhou e nao achou (silencio nunca e omissao).
import os
from datetime import datetime, timedelta, timezone

import common

BRT = timezone(timedelta(hours=-3))

# Mesma lista que o monitor coleta: fonte unica em common.py.
KEYWORDS = common.KEYWORDS

# Janela do resumo: quantas horas para tras olhar a COLETA (created_at).
#
# POR QUE NAO POR DATA DE PUBLICACAO (era o que estava, e estava errado):
# o monitor coleta com atraso - a janela dele e de 14 dias, entao materia
# publicada em 23/09 foi coletada em 05/10. Preso a "publicado ontem", o
# resumo desses dias dava 0 e o cliente recebia "nenhuma noticia" mesmo
# havendo materia nova no banco (medido em 2026-10-06: os 4 dias anteriores
# deram 0 noticias, com 34 materias no banco). Ancorar na COLETA faz toda
# materia entrar em um resumo.
#
# 26h = um pouco mais que 24h, para absorver o atraso do cron do GitHub.
# Limite conhecido: se o resumo rodar 2x dentro da janela (dispatch manual),
# a materia repete - nao existe marcador de "ja reportado" no banco.
RESUMO_HORAS = int(os.environ.get("RESUMO_HORAS", "26"))

MAX = 4000


def main():
    desde = datetime.now(timezone.utc) - timedelta(hours=RESUMO_HORAS)
    corte = desde.strftime("%Y-%m-%dT%H:%M:%S")
    dia = datetime.now(BRT).strftime("%d/%m/%Y")
    st, resp = common.sb_select({
        "select": "keyword,title,source,link,quando,sentimento,checagem",
        "created_at": "gte." + corte,
        "sentimento": "not.is.null",
        "order": "ts.desc",
        "limit": "50",
    })
    # a coluna 'checagem' e opcional: se ainda nao existe, refaz sem ela
    if common.coluna_ausente(st, resp, "checagem"):
        st, resp = common.sb_select({
            "select": "keyword,title,source,link,quando,sentimento",
            "created_at": "gte." + corte,
            "sentimento": "not.is.null",
            "order": "ts.desc",
            "limit": "50",
        })
    if not isinstance(resp, list):
        print(f"select status={st}; erro ao ler o banco: {resp}")
        common.tg_send(f" RESUMO DIARIO ({dia})\n\n"
                       "Nao foi possivel ler o banco de noticias hoje. "
                       "O monitoramento precisa de atencao.")
        return

    # agrupa por palavra-chave, preservando a ordem monitorada
    por_kw = {k: [] for k in KEYWORDS}
    for n in resp:
        por_kw.setdefault(n.get("keyword", "?"), []).append(n)

    com, sem = [], []
    n_total = 0
    for kw in por_kw:
        itens = por_kw[kw]
        if not itens:
            sem.append(kw)
            continue
        linhas = [f"* {kw} - {len(itens)} noticia(s)"]
        for n in itens:
            n_total += 1
            s = (n.get("sentimento") or "NEUTRA").upper()
            aviso = ""
            if n.get("checagem") == "nao_conferida":
                aviso = "\n   (!) nao foi possivel confirmar a citacao - confira a materia"
            linhas.append(
                f"\n{n_total}. {n.get('title','')}\n"
                f" Veiculo: {n.get('source','') or 'desconhecido'}\n"
                f" {n.get('quando','')}\n"
                f" URL: {n.get('link','')}\n"
                f"[{s}] Sentimento: {s}{aviso}"
            )
        com.append("\n".join(linhas))

    cab = (f" RESUMO DIARIO DE NOTICIAS ({dia})\n"
           f" Total: {n_total} noticia(s) em {len(KEYWORDS)} termo(s) monitorado(s)\n")
    # Se nada foi coletado hoje, avisa explicitamente. Antes o sistema ficava
    # em silencio e era impossivel saber se "nenhuma noticia" era verdade ou
    # se a coleta tinha falhado.
    if n_total == 0:
        cab += (" ATENCAO: nenhuma noticia coletada hoje. Se ontem houve "
                "noticias, a coleta pode estar falhando - verifique o log "
                "do workflow 'Monitorar' no GitHub Actions.\n")
    partes_txt = [cab]
    if com:
        partes_txt.append("\n\n------------------------\n\n".join(com))
    if sem:
        partes_txt.append("SEM NOTICIAS HOJE:\n" +
                          "\n".join(f"- {k}: nenhuma noticia encontrada" for k in sem))
    if not com:
        partes_txt.append("Nenhuma noticia nova encontrada hoje "
                          "para os termos monitorados.")
    texto = "\n\n".join(partes_txt)

    partes, resto = [], texto
    while len(resto) > MAX:
        cut = resto.rfind("\n", 0, MAX)
        if cut < 0:
            cut = MAX
        partes.append(resto[:cut])
        resto = resto[cut:].lstrip("\n")
    partes.append(resto)

    for p in partes:
        s, r = common.tg_send(p)
        mid = r.get("result", {}).get("message_id") if isinstance(r, dict) else r
        print("envio status", s, "msg_id", mid)
    print(f"Enviadas {len(partes)} parte(s) para {common.TG_CHAT_ID}.")


if __name__ == "__main__":
    main()
