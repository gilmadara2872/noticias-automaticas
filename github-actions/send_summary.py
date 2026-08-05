#!/usr/bin/env python3
# 06:00 BRT - Le do Supabase as noticias do DIA ALVO (com sentimento) e envia
# o resumo via Telegram para TG_CHAT_ID. E a UNICA mensagem do dia.
#
# O resumo cobre TODAS as palavras-chave monitoradas: as que tiveram noticia
# aparecem detalhadas; as que nao tiveram sao listadas como "sem noticias",
# para o cliente saber que o robo olhou e nao achou (silencio nunca e omissao).
from datetime import datetime, timedelta, timezone

import common

BRT = timezone(timedelta(hours=-3))

# Mesma lista que o monitor coleta: fonte unica em common.py.
KEYWORDS = common.KEYWORDS

# Dia alvo do resumo:
#   1 = ONTEM (dia anterior a execucao)  -> digest do dia que fechou
#   0 = HOJE
# Cliente quer "somente as noticias que sairam no dia" (estritamente esse dia).
RESUMO_DIAS_ATRAS = 1

MAX = 4000


def main():
    alvo = datetime.now(BRT).replace(hour=0, minute=0, second=0, microsecond=0) \
        - timedelta(days=RESUMO_DIAS_ATRAS)
    dia = alvo.strftime("%Y-%m-%d")
    st, resp = common.sb_select({
        "select": "keyword,title,source,link,quando,sentimento,checagem",
        "dia": "eq." + dia,
        "sentimento": "not.is.null",
        "order": "ts.desc",
        "limit": "50",
    })
    # a coluna 'checagem' e opcional: se ainda nao existe, refaz sem ela
    if common.coluna_ausente(st, resp, "checagem"):
        st, resp = common.sb_select({
            "select": "keyword,title,source,link,quando,sentimento",
            "dia": "eq." + dia,
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
