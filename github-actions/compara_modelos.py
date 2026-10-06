#!/usr/bin/env python3
"""
Compara a classificação de sentimento entre o modelo principal e os modelos
de reserva do OpenRouter. Usa as 7 frases que o Kenneth definiu como regras
de classificação e mostra onde os modelos discordam.

Uso: python3 compara_modelos.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

# Configuração - via variáveis de ambiente (GitHub Secrets)
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")

if not LLM_API_KEY:
    print("ERRO: LLM_API_KEY não configurada. Defina a variável de ambiente.")
    sys.exit(1)

MODELO_PRINCIPAL = "nvidia/nemotron-3-super-120b-a12b:free"
MODELOS_RESERVA = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "dots-studio/dots-3-note-preview:free",
    "liquid/lfm-2.5-2.6b:free",
    "cohere/north-mini-code:free",
    "inclusionai/ling-3.0-flash-sante:free",
]

# As 7 frases que o Kenneth definiu como regras de classificação
# Baseado no PROMPT_REGRAS do sentiment.py
FRASES_TESTE = [
    {
        "frase": "Para Kenneth Correa, professor da FGV, os modelos chineses passaram a ocupar posicao relevante",
        "esperado": "POSITIVA",
        "regra": "Opinião como especialista"
    },
    {
        "frase": "Entre os palestrantes confirmados estao A, B e Kenneth Correa",
        "esperado": "NEUTRA",
        "regra": "Nome em lista"
    },
    {
        "frase": "Assuntos Relacionados: Kenneth Correa",
        "esperado": "NEUTRA",
        "regra": "Menção incidental"
    },
    {
        "frase": "Kenneth Correa foi assaltado na avenue XYZ",
        "esperado": "NEUTRA",
        "regra": "Vítima de violência"
    },
    {
        "frase": "Advogado afirma que Kenneth Correa participava do esquema",
        "esperado": "NEGATIVA",
        "regra": "Acusado"
    },
    {
        "frase": "Investigacao cita o nome de Kenneth Correa",
        "esperado": "NEGATIVA",
        "regra": "Perto de crime"
    },
    {
        "frase": "Kenneth Correa recebeu premio de empreendedor do ano",
        "esperado": "POSITIVA",
        "regra": "Elogiado/prêmio"
    },
]

PROMPT_REGRAS = (
    "Voce avalia a REPUTACAO de uma pessoa especifica em uma noticia. "
    "O que importa e o PAPEL que essa pessoa DESEMPENHA na noticia, e NAO "
    "o tema dela. Um acidente climatico e negativo, mas se a pessoa "
    "explicou o acidente como especialista, isso e POSITIVA para ela.\n\n"
    "Procure a FRASE em que o nome aparece e leia o que essa frase faz:\n"
    "  1) A pessoa da uma OPINIAO como especialista (explica, avalia, "
    "analisa, comenta, recomenda, e citada como fonte) -> POSITIVA. "
    "Vale mesmo que o assunto da materia seja negativo ou sem relacao "
    "com ela, como um jogo de futebol: se ela explicou a tecnologia "
    "usada, a opiniao dela agregou e e POSITIVA.\n"
    "  2) A pessoa e so um NOME EM LISTA (palestrantes confirmados, "
    "participantes, lista de presentes, rodape, tag, link relacionado, "
    "assuntos relacionados) -> NEUTRA. Nao ha opiniao nenhuma dela.\n"
    "  3) A materia nao e sobre ela e o nome so aparece como mencao "
    "incidental -> NEUTRA.\n"
    "  4) A pessoa e VITIMA de violencia (assalto, roubo, agressao, "
    "sequestro, acidente sofrido por ela) -> NEUTRA. Ser vitima nao e "
    "culpa dela e nao diz nada sobre a reputacao dela.\n"
    "  5) A pessoa e atacada, acusada, criticada ou tratada como "
    "problema (crime, denuncia, processo, investigacao, escandalo, "
    "'bandido', 'faz tudo errado') -> NEGATIVA. Aqui entra tanto "
    "quando ela e ACOUSADA quanto quando apenas APARECE PERTO de um "
    "crime ou investigacao, mesmo sem acusacao direta.\n"
    "ATENCAO: o juzo negativo tem de ser SOBRE A PESSOA. Se a materia "
    "acusa a EMPRESA, o CLIENTE, o GOVERNO ou o ASSUNTO, isso NAO e "
    "NEGATIVA para a pessoa - ela e citada para ANALISAR, e isso e "
    "POSITIVA pela regra 1.\n"
    "  6) A pessoa e elogiada ou recebe premio -> POSITIVA.\n\n"
    "Responda com UMA PALAVRA: POSITIVA, NEGATIVA ou NEUTRA."
)


def classificar(modelo, frase):
    """Classifica uma frase usando o modelo especificado."""
    prompt = f"{PROMPT_REGRAS}\n\nPessoa avaliada: Kenneth Correa\n\nFrase: {frase}\n\nResponda APENAS uma palavra."
    body = json.dumps({
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500,
        "temperature": 0
    }).encode()
    req = urllib.request.Request(
        f"{LLM_BASE_URL}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            resp = json.loads(r.read().decode())
            content = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip().upper()
            for s in ("POSITIVA", "NEGATIVA", "NEUTRA"):
                if s in content:
                    return s
            return f"?({content[:30]})"
    except urllib.error.HTTPError as e:
        return f"ERRO HTTP {e.code}"
    except Exception as e:
        return f"ERRO: {e}"


def main():
    print("=" * 80)
    print("COMPARAÇÃO DE MODELOS DE CLASSIFICAÇÃO DE SENTIMENTO")
    print("=" * 80)
    print()
    print(f"Modelo principal: {MODELO_PRINCIPAL}")
    print(f"Modelos de reserva: {', '.join(MODELOS_RESERVA)}")
    print()
    
    # Testar cada frase em cada modelo
    resultados = {}
    modelos_todos = [MODELO_PRINCIPAL] + MODELOS_RESERVA
    
    for i, teste in enumerate(FRASES_TESTE, 1):
        frase = teste["frase"]
        esperado = teste["esperado"]
        regra = teste["regra"]
        
        print(f"--- Frase {i}/{len(FRASES_TESTE)}: {regra} ---")
        print(f"  Frase: {frase[:80]}")
        print(f"  Esperado: {esperado}")
        print()
        
        for modelo in modelos_todos:
            resultado = classificar(modelo, frase)
            resultados[(i, modelo)] = resultado
            status = "✓" if resultado == esperado else "✗"
            print(f"  {status} {modelo:50s} -> {resultado}")
            time.sleep(1)  # Respeitar rate limit
        
        print()
    
    # Resumo
    print("=" * 80)
    print("RESUMO")
    print("=" * 80)
    print()
    
    for modelo in modelos_todos:
        acertos = sum(1 for (i, m), r in resultados.items() if m == modelo and r == FRASES_TESTE[i-1]["esperado"])
        total = len(FRASES_TESTE)
        print(f"  {modelo:50s} {acertos}/{total} acertos")
    
    print()
    
    # Mostrar discordâncias com o principal
    print("=== DISCORDÂNCIAS COM O PRINCIPAL ===")
    print()
    for i, teste in enumerate(FRASES_TESTE, 1):
        principal = resultados.get((i, MODELO_PRINCIPAL))
        for modelo in MODELOS_RESERVA:
            reserva = resultados.get((i, modelo))
            if reserva != principal:
                print(f"  Frase {i} ({teste['regra']}):")
                print(f"    Principal: {principal}")
                print(f"    Reserva ({modelo}): {reserva}")
                print()


if __name__ == "__main__":
    main()
