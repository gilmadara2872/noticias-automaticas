#!/usr/bin/env python3
# 05:30 BRT - Le as noticias SEM sentimento, abre o conteudo na integra
# (best-effort) e classifica POSITIVA / NEGATIVA / NEUTRA.
# Usa LLM (Hy3 free via OpenRouter) SE LLM_API_KEY estiver setada;
# caso contrario, cai num lexico PT-BR offline (sempre funciona).
import json
import os
import re
import urllib.request
import urllib.error

import common

POS = set("bom boa otimo otima otima excelente positivo positiva positiva sucesso "
          "crescimento lucro elogio aprovado vitoria ganha ganhou avanco record "
          "parceria expande contrata".split())
NEG = set("ruim mau ma medo crime prisao preso condenado denunciado investigado "
          "fraude processo prejuizo queda perda criticado reclamacao revolta morto "
          "morre morreu acidente escandalo demissao falencia processado multa".split())


def fetch_article(url):
    """Baixa a materia e devolve o texto limpo INTEIRO (sem corte).
    Antes cortava em 4000 caracteres e perdia o final das materias longas."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "ignore")
        text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception:
        return ""


def lexicon_sentiment(title, content):
    txt = (title + " " + content).lower()
    words = set(re.findall(r"[a-záéíóúâêôãõç]+", txt))
    score = len(words & POS) - len(words & NEG)
    if score > 0:
        return "POSITIVA"
    if score < 0:
        return "NEGATIVA"
    return "NEUTRA"


def llm_sentiment(title, content, keyword=""):
    """Classifica pela IA. Devolve None se nao der - mas NUNCA em silencio:
    todo motivo de falha e impresso, senao a queda para o lexico passa
    despercebida e o resultado parece pior sem explicacao."""
    if not common.LLM_API_KEY:
        print("    IA nao usada: LLM_API_KEY nao configurada")
        return None
    # O modelo tem limite de tamanho no pedido, entao aqui vai um recorte
    # generoso (30 mil caracteres cobre materia jornalistica inteira).
    # No BANCO o texto e gravado completo, sem corte.
    alvo = keyword or "a pessoa/empresa monitorada"
    prompt = (
        "Voce e um analista de reputacao. Avalie o sentimento da noticia "
        f"ESTRITAMENTE em relacao a {alvo}.\n\n"
        "REGRA PRINCIPAL: classifique o TOM DA PARTICIPACAO OU MENCAO de "
        f"{alvo}, e NAO o tema da noticia.\n"
        "- Se o tema for pesado/negativo (crime, golpe, deepfake, fraude, "
        f"tragedia) mas {alvo} aparece como especialista, fonte, autoridade, "
        "vitima defendida, quem alerta, explica, ajuda ou combate o problema, "
        "a classificacao e POSITIVA.\n"
        f"- Só use NEGATIVA se {alvo} for acusado, criticado, responsabilizado, "
        "ridicularizado ou prejudicado na propria reputacao.\n"
        f"- Use NEUTRA se {alvo} for apenas citado de passagem, sem juizo de "
        "valor sobre ele.\n\n"
        "Responda APENAS uma palavra: POSITIVA, NEGATIVA ou NEUTRA.\n\n"
        f"Titulo: {title}\n\nConteudo: {content[:30000]}"
    )
    body = {"model": common.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}], "temperature": 0}
    st, resp = common.http(
        "POST", common.LLM_BASE_URL + "/chat/completions",
        {"Authorization": f"Bearer {common.LLM_API_KEY}",
         "Content-Type": "application/json"}, body, timeout=180)
    if st != 200:
        print(f"    IA falhou (HTTP {st}): {str(resp)[:150]}")
        return None
    try:
        txt = resp["choices"][0]["message"]["content"].strip().upper()
    except Exception as e:
        print(f"    IA respondeu em formato inesperado: {e} | {str(resp)[:120]}")
        return None
    for s in ("POSITIVA", "NEGATIVA", "NEUTRA"):
        if s in txt:
            return s
    print(f"    IA respondeu sem classificacao clara: {txt[:80]!r}")
    return None


def main():
    # Pega as noticias que faltam analisar. Tambem repesca as que ja tem
    # sentimento mas ainda estao sem o texto guardado (coluna 'conteudo'),
    # para que o acervo do banco fique completo.
    st, resp = common.sb_select({
        "select": "link,title,source,quando,sentimento,keyword",
        "or": "(sentimento.is.null,conteudo.is.null)",
        "limit": "200",
    })
    # se a coluna 'conteudo' ainda nao existe, volta ao criterio antigo
    if common.coluna_ausente(st, resp, "conteudo"):
        st, resp = common.sb_select({
            "select": "link,title,source,quando,sentimento",
            "sentimento": "is.null",
            "limit": "200",
        })
    if not resp:
        print(f"select status={st}; nada p/ analisar ou erro.")
        return
    print(f"{len(resp)} noticias para processar. Analisando...")
    for n in resp:
        content = fetch_article(n["link"])
        # Noticia repescada so para guardar o texto: mantem o sentimento que
        # ja foi decidido antes. Nunca reescreve classificacao existente.
        sent = n.get("sentimento")
        if sent:
            print(f"  {str(n['title'])[:50]} -> {sent} (mantido) "
                  f"({len(content)} chars lidos)")
        else:
            sent = llm_sentiment(n["title"], content, n.get("keyword") or "")
            metodo = "IA"
            if not sent:
                sent = lexicon_sentiment(n["title"], content)
                metodo = "lexico (IA indisponivel)"
            print(f"  {str(n['title'])[:50]} -> {sent} [via {metodo}] "
                  f"({len(content)} chars lidos)")
        # grava o sentimento E o texto integral da materia no banco
        s2, r2 = common.sb_update_sentimento(n["link"], sent, content)
        if s2 not in (200, 204):
            print(f"    aviso: banco respondeu {s2}")
    print("Sentimento concluido.")


if __name__ == "__main__":
    main()
