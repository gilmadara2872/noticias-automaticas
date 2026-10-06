#!/usr/bin/env python3
"""
Compara a classificacao de sentimento entre o modelo principal e os modelos
de reserva do OpenRouter. Usa as frases que o Kenneth definiu como regras
de classificacao e mostra onde os modelos discordam.

O prompt vem DIRETO do sentiment.py (PROMPT_REGRAS), para o teste medir
exatamente a regra que roda em producao - nao uma copia que pode divergir.

Uso:
    LLM_API_KEY=... python3 compara_modelos.py
"""
import json
import sys
import time
import urllib.request
import urllib.error

import common
import sentiment  # PROMPT_REGRAS e MODELOS_RESERVA vem daqui

LLM_API_KEY = common.LLM_API_KEY
LLM_BASE_URL = common.LLM_BASE_URL

if not LLM_API_KEY:
    print("ERRO: LLM_API_KEY nao configurada. Defina a variavel de ambiente.")
    sys.exit(1)

MODELO_PRINCIPAL = common.LLM_MODEL
MODELOS_RESERVA = sentiment.MODELOS_RESERVA

# As frases que definem a regra. As 3 primeiras sao os casos que o Kenneth
# explicou em 2026-10-05 (neutra / negativa / positiva).
FRASES_TESTE = [
    {
        "frase": "Kenneth Correa foi citado na materia sobre o evento do setor",
        "esperado": "NEUTRA",
        "regra": "1. Citado, mas nada errado nem autoridade",
    },
    {
        "frase": "Investigacao sobre desvio de verbas cita Kenneth Correa entre os nomes apurados",
        "esperado": "NEGATIVA",
        "regra": "2. Perto de crime, mesmo sem acusacao direta",
    },
    {
        "frase": ("Para Kenneth Correa, especialista em tecnologia, os modelos de IA "
                  "mudaram o jogo; ele explicou como os sensores decidiram os lances"),
        "esperado": "POSITIVA",
        "regra": "3. Autoridade tecnica, mesmo em assunto de futebol",
    },
    {
        "frase": "Para Kenneth Correa, professor da FGV, os modelos chineses passaram a ocupar posicao relevante",
        "esperado": "POSITIVA",
        "regra": "Opiniao como especialista",
    },
    {
        "frase": "Entre os palestrantes confirmados estao A, B e Kenneth Correa",
        "esperado": "NEUTRA",
        "regra": "Nome em lista",
    },
    {
        "frase": "Assuntos Relacionados: Kenneth Correa",
        "esperado": "NEUTRA",
        "regra": "Mencao incidental",
    },
    {
        "frase": "Kenneth Correa foi assaltado na avenida XYZ",
        "esperado": "NEUTRA",
        "regra": "Vitima de violencia",
    },
    {
        "frase": "Advogado afirma que Kenneth Correa participava do esquema",
        "esperado": "NEGATIVA",
        "regra": "Acusado",
    },
    {
        "frase": "Kenneth Correa recebeu premio de empreendedor do ano",
        "esperado": "POSITIVA",
        "regra": "Elogiado/premio",
    },
]


def classificar(modelo, frase):
    """Classifica uma frase usando o mesmo formato do sentiment.py."""
    prompt = (sentiment.PROMPT_REGRAS + "\n\nPessoa avaliada: Kenneth Correa\n\n"
              f"Titulo: {frase}\n\nConteudo: {frase}\n\n"
              "Responda APENAS uma palavra.")
    body = json.dumps({
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        f"{LLM_BASE_URL}/chat/completions", data=body,
        headers={"Authorization": f"Bearer {LLM_API_KEY}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            resp = json.loads(r.read().decode())
            content = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip().upper()
            for s in ("POSITIVA", "NEGATIVA", "NEUTRA", "NEUTRO"):
                if s in content:
                    return "NEUTRA" if s == "NEUTRO" else s
            return f"?({content[:30]!r})" if content else "?(vazio)"
    except urllib.error.HTTPError as e:
        return f"ERRO HTTP {e.code}"
    except Exception as e:
        return f"ERRO {type(e).__name__}"


def main():
    print("=" * 78)
    print("COMPARACAO DE MODELOS DE CLASSIFICACAO DE SENTIMENTO")
    print("=" * 78)
    print(f"Modelo principal : {MODELO_PRINCIPAL}")
    print(f"Reservas         : {', '.join(MODELOS_RESERVA)}")
    print()

    modelos_todos = [MODELO_PRINCIPAL] + MODELOS_RESERVA
    resultados = {}

    for i, teste in enumerate(FRASES_TESTE, 1):
        print(f"--- Frase {i}/{len(FRASES_TESTE)}: {teste['regra']} ---")
        print(f"    {teste['frase'][:90]}")
        print(f"    Esperado: {teste['esperado']}")
        for modelo in modelos_todos:
            r = classificar(modelo, teste["frase"])
            resultados[(i, modelo)] = r
            marca = "OK " if r == teste["esperado"] else "XX "
            print(f"    {marca}{modelo:48s} -> {r}")
            time.sleep(1)
        print()

    print("=" * 78)
    print("RESUMO")
    print("=" * 78)
    for modelo in modelos_todos:
        acertos = sum(1 for (i, m), r in resultados.items()
                      if m == modelo and r == FRASES_TESTE[i - 1]["esperado"])
        papel = "PRINCIPAL" if modelo == MODELO_PRINCIPAL else "reserva"
        print(f"  {modelo:48s} {acertos}/{len(FRASES_TESTE)}  ({papel})")

    print()
    print("=== DISCORDANCIAS COM O PRINCIPAL (candidatas a sair da reserva) ===")
    alguma = False
    for i, teste in enumerate(FRASES_TESTE, 1):
        principal = resultados.get((i, MODELO_PRINCIPAL))
        for modelo in MODELOS_RESERVA:
            reserva = resultados.get((i, modelo))
            if reserva != principal:
                alguma = True
                print(f"  Frase {i} ({teste['regra']}):")
                print(f"    principal -> {principal}")
                print(f"    {modelo} -> {reserva}")
    if not alguma:
        print("  nenhuma: todas as reservas concordam com o principal.")


if __name__ == "__main__":
    main()
