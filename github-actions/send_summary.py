#!/usr/bin/env python3
# 06:00 BRT - Le do Supabase as noticias do DIA ALVO (com sentimento) e envia
# o resumo via Telegram para TG_CHAT_ID. E a UNICA mensagem do dia.
from datetime import datetime, timedelta, timezone

import common

BRT = timezone(timedelta(hours=-3))

# Dia alvo do resumo:
#   1 = ONTEM (dia anterior a execucao)  -> digest do dia que fechou
#   0 = HOJE
# Kenneth quer "somente as noticias que sairam no dia" (estritamente esse dia).
RESUMO_DIAS_ATRAS = 1

MAX = 4000


def main():
    alvo = datetime.now(BRT).replace(hour=0, minute=0, second=0, microsecond=0) \
        - timedelta(days=RESUMO_DIAS_ATRAS)
    dia = alvo.strftime("%Y-%m-%d")
    st, resp = common.sb_select({
        "select": "keyword,title,source,link,quando,sentimento",
        "dia": "eq." + dia,
        "sentimento": "not.is.null",
        "order": "ts.desc",
        "limit": "50",
    })
    if not resp:
        print(f"select status={st}; sem noticias de {dia} ou erro.")
        msg = (f" RESUMO DIARIO DE NOTICIAS ({dia})\n\n"
               "Nenhuma noticia nova com analise de sentimento hoje.")
        s, r = common.tg_send(msg)
        print("envio status", s, r)
        return

    blocos = []
    for i, n in enumerate(resp, 1):
        s = (n.get("sentimento") or "NEUTRA").upper()
        emoji = {"POSITIVA": "[POSITIVA]", "NEGATIVA": "[NEGATIVA]", "NEUTRA": "[NEUTRA]"}.get(s, "[NEUTRA]")
        # mostra a URL de forma clara (rotulo + link). Tenta extrair a fonte
        # real do Google News (parametro url=) quando existir.
        link = n.get("link", "") or ""
        real = ""
        if "url=" in link:
            import urllib.parse as _up
            try:
                real = _up.unquote(link.split("url=", 1)[1].split("&")[0])
            except Exception:
                real = ""
        url_mostrar = real or link
        blocos.append(
            f"{i}. {n.get('title','')}\n"
            f" Veiculo: {n.get('source','') or 'desconhecido'}\n"
            f" {n.get('quando','')}\n"
            f" URL: {url_mostrar}\n"
            f"{emoji} Sentimento: {s}"
        )
    cab = f" RESUMO DIARIO DE NOTICIAS ({dia})\n Total: {len(resp)} noticia(s)\n"
    corpo = "\n\n------------------------\n\n".join(blocos)
    texto = cab + "\n" + corpo

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
