#!/usr/bin/env python3
# 05:30 BRT - Le as noticias SEM sentimento, abre o conteudo na integra
# e classifica com LLM (OpenRouter). O lexico PT-BR so entra como rede de
# seguranca e NUNCA em silencio: se a IA falhar, o sistema avisa no Telegram.
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

import common
import monitor

# ================================================================
# DICIONARIO EXPANDIDO: 200+ palavras em portugues brasileiro
# Usado SO como rede de seguranca quando a IA esta indisponivel.
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
        req = urllib.request.Request(url, headers={"User-Agent": monitor.UA})
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
# SAUDE DA IA  (novo)
# ================================================================
# Por que isto existe: em 26/09 a reclassificacao rodou com o secret
# LLM_API_KEY VAZIO. As 37 noticias cairam no lexico e o workflow
# reportou "success". Ninguem percebeu que a IA nunca rodou.
# Agora a chave e o modelo sao testados ANTES de classificar qualquer coisa.
def checa_llm():
    """Retorna (ok, mensagem). Testa a chave e o modelo de verdade."""
    if not common.LLM_API_KEY:
        return False, ("LLM_API_KEY vazia - o secret nao esta cadastrado "
                       "ou esta vazio no GitHub (Settings > Secrets)")
    st, resp = common.http("GET", common.LLM_BASE_URL + "/key", headers={
        "Authorization": f"Bearer {common.LLM_API_KEY}"}, timeout=30)
    if st != 200:
        return False, f"chave rejeitada pelo OpenRouter (HTTP {st})"
    st, resp = common.http("POST", common.LLM_BASE_URL + "/chat/completions", {
        "Authorization": f"Bearer {common.LLM_API_KEY}",
        "Content-Type": "application/json"},
        {"model": common.LLM_MODEL,
         "messages": [{"role": "user", "content": "Responda apenas: OK"}],
         "max_tokens": 60}, timeout=150)
    if st != 200:
        return False, (f"modelo '{common.LLM_MODEL}' recusado (HTTP {st}): "
                       f"{str(resp)[:220]}")
    return True, f"chave e modelo OK ({common.LLM_MODEL})"


# ================================================================
# ANALISE DE SENTIMENTO
# ================================================================
def lexicon_sentiment(title, content):
    """Rede de seguranca. So entra se a IA falhar - e nesse caso o sistema
    AVISA no Telegram. Nunca classifica em silencio."""
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


# A REGRA QUE VOCÊ PEDIU: o que importa e o PAPEL que o Kenneth DESEMPENHA
# na noticia, e nao o tema dela. Noticia pesada (deepfake, crime, IA) em que
# ele aparece como especialista/palestrante = POSITIVA; so citado de
# passagem = NEUTRA; acusado ou criticado = NEGATIVA.
PROMPT_REGRAS = (
    "Voce avalia a REPUTACAO de uma pessoa especifica em uma noticia. "
    "O que importa e o PAPEL que essa pessoa DESEMPENHA na noticia, e NAO "
    "o tema dela.\n\n"
    "Procure a FRASE em que o nome aparece e leia o que essa frase faz:\n"
    "  1) A pessoa e O ASSUNTO da materia, ou e elogiada, criticada ou "
    "acusada -> POSITIVA ou NEGATIVA.\n"
    "  2) A pessoa da uma OPINAO sobre o tema (explica, avalia, analisa, "
    "comenta, recomenda) e e apresentada como fonte -> POSITIVA, porque a "
    "reputacao dela esta em jogo e ela se posiciona.\n"
    "  3) A pessoa e so um NOME EM LISTA (palestrantes confirmados, "
    "participantes, lista de presentes, rodape, tag, link relacionado, "
    "assuntos relacionados) -> NEUTRA. Nao ha juzo nenhum sobre ela.\n"
    "  4) A materia nao e sobre ela e o nome so aparece como mencao "
    "incidental -> NEUTRA.\n"
    "  5) A pessoa e acusada, criticada, vitima de violencia, ou aparece em "
    "contexto de crime, denuncia ou processo -> NEGATIVA.\n\n"
    "REGRA QUE RESOLVE O ERRO MAIS COMUM:\n"
    "Ser citado como especialista NAO e automaticamente positivo. Boa parte "
    "dessas materias e factual, e citar o nome so diz de onde veio a "
    "informacao.\n\n"
    "Exemplos do caso 3, que e o que mais se repete:\n"
    "  'Entre os palestrantes confirmados estao A, B e Kenneth Correa' -> NEUTRA\n"
    "  'Assuntos Relacionados: Kenneth Correa' -> NEUTRA\n"
    "Exemplo do caso 2:\n"
    "  'Para Kenneth Correa, professor da FGV, os modelos chineses passaram "
    "a ocupar posicao relevante' -> POSITIVA\n"
    "  'Segundo o especialista Kenneth Correa, enviar foto para uma IA traz "
    "risco' -> POSITIVA (ele da a opiniao; o risco e do servico, nao dele)\n"
    "Exemplo do caso 5:\n"
    "  'Advogado afirma que Kenneth Correa participava do esquema' -> NEGATIVA\n\n"
    "NUNCA responda POSITIVA apenas porque o tema da noticia e positivo ou "
    "porque a pessoa e citada. Responda POSITIVA apenas nos casos 1 e 2.\n\n"
    "Responda com UMA PALAVRA: POSITIVA, NEGATIVA ou NEUTRA."
)


def llm_sentiment(title, content, keyword=""):
    if not common.LLM_API_KEY:
        print("    IA nao usada: LLM_API_KEY nao configurada")
        return None
    alvo = keyword or "a pessoa/empresa monitorada"
    prompt = (PROMPT_REGRAS + f"\n\nPessoa avaliada: {alvo}\n\n"
              f"Titulo: {title}\n\nConteudo: {content[:30000]}\n\n"
              "Responda APENAS uma palavra.")
    body = {"model": common.LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            # Modelos :free com raciocinio (ex: qwen3.8-27b) gastam tokens
            # pensando e devolvem content=null se max_tokens for baixo.
            # 1500 evita a resposta vazia.
            "max_tokens": 1500, "temperature": 0}
    st = resp = None
    for tentativa in range(1, 4):
        st, resp = common.http(
            "POST", common.LLM_BASE_URL + "/chat/completions",
            {"Authorization": f"Bearer {common.LLM_API_KEY}",
             "Content-Type": "application/json"}, body, timeout=240)
        if st == 200:
            break
        print(f"    IA falhou (HTTP {st}) tentativa {tentativa}/3: {str(resp)[:150]}")
        if tentativa < 3:
            time.sleep(15 * tentativa)
    if st != 200:
        return None
    try:
        txt = (resp["choices"][0]["message"].get("content") or "").strip().upper()
    except Exception as e:
        print(f"    IA respondeu em formato inesperado: {e} | {str(resp)[:120]}")
        return None
    for s in ("POSITIVA", "NEGATIVA", "NEUTRA"):
        if s in txt:
            return s
    print(f"    IA respondeu sem classificacao clara: {txt[:80]!r}")
    return None


def main(force=False, lote=None):
    # ---------------------------------------------------------------
    # 1. SAUDE DA IA - antes de tudo.
    # Sem isto, chave vazia ou modelo renomeado = workflow "success"
    # e 100% das classicoes caindo no lexico sem ninguem ver.
    # ---------------------------------------------------------------
    ok_llm, msg_saude = checa_llm()
    print(f"Saude da IA: {'OK - ' + msg_saude if ok_llm else 'FALHOU - ' + msg_saude}")

    # 2. Consulta no banco
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

    # ---------------------------------------------------------------
    # 2b. LOTE. A OpenRouter da 50 requisicoes/dia no tier gratuito, e
    # uma reclassificacao das 47_noticias consome 49 delas. Isso impede
    # de refazer tudo duas vezes no mesmo dia. Com --lote, processa
    # apenas os links informados e economiza cota para o restante.
    # ---------------------------------------------------------------
    if lote and isinstance(resp, list) and resp:
        avisos = {l.strip() for l in lote if l.strip()}
        antes = len(resp)
        resp = [r for r in resp if r.get("link") in avisos]
        print(f"Lote: {len(resp)} de {antes} noticia(s) selecionadas "
              f"({antes - len(resp)} fora do lote foram ignoradas).")
        if not resp:
            print("  nenhum link do lote existe no banco.")
            return

    if not isinstance(resp, list) or not resp:
        print(f"select status={st}; nada p/ analisar ou erro.")
        if not ok_llm:
            print("  aviso: IA fora do ar (sera classificado por lexico quando "
                  "houver noticia nova).")
            avisa_telegram(
                "SISTEMA DE SENTIMENTO FORA DO AR\n\n"
                f"Motivo: {msg_saude}\n\n"
                "Sem a IA, toda noticia sera classificada por uma lista de "
                "palavras (reserva), o que da resultados ruins. "
                "Ajuste os secrets LLM_API_KEY e LLM_MODEL no GitHub.")
        return

    print(f"{len(resp)} noticias para processar. Analisando...")
    n_ia = n_lex = n_neutra = 0
    falhas = []
    sem_texto = []

    for n in resp:
        content = fetch_article(n["link"])
        sent = n.get("sentimento")
        if sent and not force:
            print(f"  {str(n['title'])[:50]} -> {sent} (mantido) ({len(content)} chars)")
            continue

        titulo = str(n["title"])
        # A palavra-chave do banco vem do monitor; e ela quem define quem
        # esta sendo avaliado. Nao ha mais caso especial "Kennedy": a regra
        # de participacao vale para qualquer pessoa monitorada.
        alvo = n.get("keyword") or ""

        # ---------------------------------------------------------- PORTÃO
        # Se o download falhou (paywall, JS, site fora do ar), `content`
        # fica vazio/curto. Classificar nesse estado e inventar: o modelo
        # so ve o titulo e quase tudo vira POSITIVA. Foi assim que 7
        # noticias sem o nome no texto acabaram classificadas.
        if len(content) < 300:
            print(f"  {titulo[:50]} -> SEM TEXTO ({len(content)} chars) "
                  f"[IGNORADA - sem corpo nao da para classificar]")
            falhas.append(f"{titulo[:50]} (download falhou)")
            n_lex += 0          # nao conta como lexico: nem chegou a tentar
            sem_texto.append(titulo[:60])
            continue

        # Se o nome nao aparece no corpo, esta noticia nao e sobre a pessoa.
        if alvo and not monitor.cita(content, alvo):
            print(f"  {titulo[:50]} -> NEUTRA [IGNORADA - nome ausente no corpo]")
            common.sb_update_sentimento(n["link"], "NEUTRA", content)
            n_neutra += 1
            continue

        sent = llm_sentiment(titulo, content, alvo) if ok_llm else None
        if sent:
            metodo = "IA"
            n_ia += 1
        else:
            sent = lexicon_sentiment(titulo, content)
            metodo = "LEXICO"
            n_lex += 1
            falhas.append(titulo[:60])
        print(f"  {titulo[:50]} -> {sent} [{metodo}] ({len(content)} chars lidos)")

        s2, r2 = common.sb_update_sentimento(n["link"], sent, content)
        if s2 not in (200, 204):
            print(f"    aviso: banco respondeu {s2}")
        time.sleep(2)

    print(f"\nRESUMO: {n_ia} classificada(s) por IA | {n_lex} pelo lexico de "
          f"reserva | {n_neutra} neutra(s) sem o nome no corpo | "
          f"{len(sem_texto)} sem texto")

    # ---------------------------------------------------------------
    # 3. ALARME. Se qualquer coisa caiu no lexico, o cliente e avisado.
    # Silencio aqui e o que fez o sistema parecer funcionar sem funcionar.
    # ---------------------------------------------------------------
    if n_lex > 0:
        lista = "\n".join(f"- {t}" for t in falhas[:8])
        mais = f"\n... e mais {len(falhas)-8}" if len(falhas) > 8 else ""
        avisa_telegram(
            "ATENCAO: ANALISE DE SENTIMENTO PARCIAL\n\n"
            f"Por IA: {n_ia} noticia(s)\n"
            f"Pelo LEXICO de reserva: {n_lex} noticia(s)\n\n"
            "As noticias abaixo foram classificadas por lista de palavras, "
            "nao por leitura do texto - o resultado delas e pouco confiavel:\n"
            f"{lista}{mais}\n\n"
            f"Motivo: {msg_saude}")

    # Alarme separado para download quebrado: e falha do scraper, nao da
    # IA. Sem este aviso o cliente acha que a materia foi analisada.
    if sem_texto:
        lista = "\n".join(f"- {t}" for t in sem_texto[:6])
        mais = f"\n... e mais {len(sem_texto)-6}" if len(sem_texto) > 6 else ""
        avisa_telegram(
            "AVISO: MATERIA SEM TEXTO NAO FOI ANALISADA\n\n"
            f"{len(sem_texto)} noticia(s) entraram no banco mas o corpo nao "
            "pode ser baixado (paywall, pagina em JavaScript ou site fora "
            "do ar). Sem texto nao da para classificar com precisao, entao "
            "foram deixadas sem sentimento.\n\n"
            f"{lista}{mais}")

    print("Sentimento concluido.")


def avisa_telegram(texto):
    """Envia alerta e nunca quebra o pipeline por causa disso.

    Se o proprio alerta falha, diz no console E writes no banco seria
    demais; aqui o ponto e nao deixar o aviso morrer em silencio: um
    404 aqui significa que o workflow nao passou TG_TOKEN/TG_CHAT_ID.
    """
    if not common.TG_TOKEN or not common.TG_CHAT_ID:
        print("  AVISO: Telegram nao configurado (TG_TOKEN/TG_CHAT_ID faltando). "
              "O alerta abaixo NAO foi enviado:")
        print("  " + texto.replace("\n", "\n  "))
        return
    try:
        st, r = common.tg_send(texto)
        print(f"  Telegram alerta: status={st}")
        if st != 200:
            print("  ALERME NAO ENTREGUE. Confira os secrets TG_TOKEN/TG_CHAT_ID.")
    except Exception as e:
        print(f"  falha ao enviar alerta: {e}")


if __name__ == "__main__":
    force = "--force" in sys.argv

    # --lote <arquivo>: um link por linha, para processar so um pedaco e
    # economizar cota da OpenRouter (50 req/dia no tier gratuito).
    lote = None
    if "--lote" in sys.argv:
        i = sys.argv.index("--lote")
        if i + 1 < len(sys.argv):
            try:
                with open(sys.argv[i + 1], encoding="utf-8") as fh:
                    lote = [ln.strip() for ln in fh if ln.strip()]
            except OSError as e:
                print(f"nao consegui ler o lote {sys.argv[i+1]}: {e}")
        else:
            print("--lote precisa do caminho de um arquivo")

    main(force=force, lote=lote)
