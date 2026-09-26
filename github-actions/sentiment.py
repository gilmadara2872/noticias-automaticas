#!/usr/bin/env python3
# 05:30 BRT - Le as noticias SEM sentimento, abre o conteudo na integra
# Usa LLM (Qwen2.5 via OpenRouter) ou lexico PT-BR offline (sempre funciona).
import json
import os
import re
import time
import urllib.request
import urllib.error

import common
import monitor

# ================================================================
# DICIONARIO EXPANDIDO: 200+ palavras em portugues brasileiro
# ================================================================
POS = set("""bom boa otimo otima excelente positivo positiva sucesso crescimento lucro
elogio aprovado aprovada vitoria ganha ganhou ganhar ganharam vencer venceram
campeao campeoa campeonato recorde recordista quebra recorde inaugurar inaugurado
inauguracao novo nova novidade inovacao moderno moderna modernizacao expansao
expansivo ampliar ampliou ampliacao contratacao contratar contratado efetivar
efetivou parceria parcerias colaboracao colaborar coopera cooperacao avance
avancar avancou progresso progredir progrediu evolucao evoluir evoluiu
fortalecer fortaleceu fortalecimento consolidar consolidacao reconhecer reconhecimento
reconhecido destaque destacado elogio elogios parabenizar parabenizado aprovacao
aclamacao aclamado aclamada brilhante brilhantemente espetacular espetacularmente
extraordinario extraordinaria extraordinariamente notavel notavelmente admiravel
admiravelmente fantastico fantastica fantasticamente maravilhoso maravilhosa
maravilhosamente glorioso gloriosa gloriosamente heroico heroica heroismo
bem sucedido bem sucedida prospero próspera prósperamente florescente
florescimento promissor promissora esperançoso esperançosa otimista alegre
contente satisfeito satisfeita contentamento entusiasmo entusiasmado
entusiasmada empolgado empolgada animado animada feliz felicidade jubiloso
jubilosa triunfante conquista conquistador conquistadora benéfico benefica
favorável favorito favorita louvável louvável meritório meritória
destacável respeitável creditável viável factível construtivo construtiva
edificante proveitoso proveitoso util útil funcional funcional eficiente
eficiente eficaz eficaz produtivo produtiva produtividade rentável rentável
lucrativo lucrativa valioso valiosa precioso preciosa inestimavel inestimavel
insubstituivel insubstituivel indispensavel indispensavel essencial essencial
fundamental fundamental crucial crucial relevante relevante pertinente pertinente
oportuno oportuna oportunidade oportunidade conveniente conveniente vantajoso
vantajosa vantagem vantagem beneficio beneficio benefico benefica favoravel
favoravel louvavel louvavel meritorio meritoria destacavel destacavel""".split())

NEG = set("""ruim mau ma péssimo péssima terrível horrível horripilante assustador
assustadora aterrorizante medo temor temerosa apavorante desastroso desastrosa
desastre catástrofe catástrofe tragédia tragédia morte morte morto morta
falecido falecido falecimento falecimento assassinato assassinato assassino
assassina homicídio homicídio homicida criminoso criminosa criminosidade
ladrão ladrão ladra roubo roubar roubar furtar furto furto fraude fraude
fraudulento fraudulento golpe golpe enganar enganado enganadora estelionatio
estelionatária enganoso enganosa embuste embuste traição traição traidor
traidora desleal desleal deslealdade deslealdade corrupção corrupção corrupto
corrupta corrompido corrompido suborno suborno propina propina desvio desvio
desviante desviante desviar desviado desviadora prejuízo prejuízo prejuizo
prejuizo prejuizo multa multa punido punida punicao penal processo processado
processada condenado condenada condenacao condenacao pena pena cadeia cadeia
prisao prisao preso presa incarcerado incarcerada incarcerar incarcerar encarcerado
encarcerada recluso reclusa reclusao reclusao condenacao condenacao culpa culpa
culpado culpada culpado culpada criminal criminal criminoso criminosa criminosidade
criminosidade delito delito delituoso delituosa ilegal ilegal ilegalidade
ilegalidade transgressao transgressao transgressor transgressora infracao infracao
infrator infratora infração infração""".split())

# ================================================================
# REGRAS DE NEGAÇÃO
# ================================================================
NEGATION_WORDS = {"não", "nunca", "mal", "sem", "nenhum", "jamais", "nada",
                  "tampouco", "sequer", "des", "disto", "disso", "dito", "dita",
                  "pouco", "pouca", "ainda", "tão"}


def has_negation_before(text, word_index, words_list):
    """Verifica se há palavra de negação nas 3 posições anteriores."""
    for j in range(max(0, word_index - 3), word_index):
        if words_list[j] in NEGATION_WORDS:
            return True
    return False


# ================================================================
# SCRAPING MELHORADO
# ================================================================
def fetch_article(url):
    """Baixa a materia e devolve o texto limpo INTEIRO."""
    real = monitor.google_news_real_url(url)
    if real:
        print(f"    link do Google News resolvido -> {real}")
        url = real
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode("utf-8", "ignore")
        text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        # Se não conseguiu texto bom, tenta pegar snippet do DDG
        if len(text) < 200:
            snippet = fetch_ddg_snippet(url)
            if snippet:
                text = snippet
        return text
    except Exception:
        return ""


def fetch_ddg_snippet(url):
    """Fallback: busca snippet da matéria no DuckDuckGo."""
    try:
        data = urllib.parse.urlencode({"q": url}).encode()
        req = urllib.request.Request("https://html.duckduckgo.com/html/", data=data,
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "ignore")
        snippets = re.findall(r'<a class="result__snippet".*?>(.*?)</a>', html, re.S)
        if snippets:
            snippet = re.sub(r"<[^>]+>", "", snippets[0])
            return re.sub(r"&[a-z]+;", " ", snippet).strip()
        return ""
    except Exception:
        return ""


# ================================================================
# ANÁLISE DE SENTIMENTO
# ================================================================
def lexicon_sentiment(title, content):
    txt = (title + " " + content).lower()
    words = re.findall(r"[a-záéíóúâêôãõç]+", txt)
    score = 0
    for i, w in enumerate(words):
        if w in POS and not has_negation_before(txt, i, words):
            score += 1
        elif w in NEG and not has_negation_before(txt, i, words):
            score -= 1
    if score > 0:
        return "POSITIVA"
    if score < 0:
        return "NEGATIVA"
    return "NEUTRA"


def llm_sentiment(title, content, keyword=""):
    if not common.LLM_API_KEY:
        print("    IA nao usada: LLM_API_KEY nao configurada")
        return None
    alvo = keyword or "a pessoa/empresa monitorada"
    
    # Contexto especial para Kennedy Corrêa
    kennedy_context = ""
    if "Kennedy" in alvo or "Kenneth" in alvo or "Kennedy Corrêa" in alvo:
        kennedy_context = (
            "\n\nCONTEXTO ESPECIAL: Kennedy Corrêa (Kenneth Corrêa) e um mentor, "
            "palestrante e coordenador de eventos academicos. Sua participacao como "
            "palestrante, moderador, ou coordenador em um evento e normalmente um "
            "sinal POSITIVO de credibilidade e reconhecimento. Por favor, analise "
            "ESTRITAMENTE o contexto da participacao dele na noticia:\n"
            "- Se ele e palestrante, moderador, ou coordenador do evento = POSITIVA\n"
            "- Se ele e mencionado como especialista ou fonte confiavel = POSITIVA\n"
            "- Se ele e criticado, responsabilizado ou acusado = NEGATIVA\n"
            "- Se ele e apenas citado de passagem sem juizo de valor = NEUTRA\n\n"
        )
    
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
        f"{kennedy_context}"
        "Responda APENAS uma palavra: POSITIVA, NEGATIVA ou NEUTRA.\n\n"
        f"Titulo: {title}\n\nConteudo: {content[:30000]}"
    )
    body = {"model": common.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}], "temperature": 0}
    st = resp = None
    for tentativa in range(1, 5):
        st, resp = common.http(
            "POST", common.LLM_BASE_URL + "/chat/completions",
            {"Authorization": f"Bearer {common.LLM_API_KEY}",
             "Content-Type": "application/json"}, body, timeout=180)
        if st == 200:
            break
        print(f"    IA falhou (HTTP {st}) tentativa {tentativa}/4: {str(resp)[:120]}")
        if tentativa < 4:
            time.sleep(20 * tentativa)
    if st != 200:
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


def main(force=False):
    # Pega TODAS as noticias (force=True) ou apenas pendentes
    if force:
        st, resp = common.sb_select({
            "select": "link,title,source,quando,sentimento,keyword,conteudo",
            "limit": "200",
        })
    else:
        st, resp = common.sb_select({
            "select": "link,title,source,quando,sentimento,keyword,conteudo",
            "or": "(sentimento.is.null,conteudo.is.null)",
            "limit": "200",
        })
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
        sent = n.get("sentimento")
        if sent and not force:
            print(f"  {str(n['title'])[:50]} -> {sent} (mantido) ({len(content)} chars lidos)")
        else:
            # Detecta se Kennedy Corrêa apareceu na noticia
            titulo = str(n["title"])
            conteudo_texto = str(content)
            kennedy_presente = "Kennedy" in titulo or "Kenneth" in titulo or "Kennedy" in conteudo_texto or "Kenneth" in conteudo_texto
            
            # Se Kennedy apareceu, passa o contexto pro LLM avaliar a participacao
            if kennedy_presente:
                kennedy_keyword = "Kennedy Corrêa (Kenneth Corrêa) - mentor, palestrante e coordenador do evento"
                sent = llm_sentiment(n["title"], content, kennedy_keyword)
                metodo = "IA (Kennedy)"
            else:
                sent = llm_sentiment(n["title"], content, n.get("keyword") or "")
                metodo = "IA"
            
            if not sent:
                sent = lexicon_sentiment(n["title"], content)
                metodo = "lexico (IA indisponivel)"
            print(f"  {titulo[:50]} -> {sent} [via {metodo}] ({len(content)} chars lidos)")
        s2, r2 = common.sb_update_sentimento(n["link"], sent, content)
        if s2 not in (200, 204):
            print(f"    aviso: banco respondeu {s2}")
    print("Sentimento concluido.")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    main(force=force)
