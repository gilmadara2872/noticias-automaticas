#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coleta em 2 CAMADAS.

O PROBLEMA QUE RESOLVE
----------------------
Buscar so pelo nome nao pega materia de veiculo grande (O Globo, Estadão).
Medido: '"Kenneth Corrêa" when:365d' devolve 30 resultados e NENHUM e a
materia do O Globo, porque o paywall impede o Google de indexar o corpo -
e no O Globo o nome esta no MEIO do artigo. O filtro do monitor.py aceitaria
a materia (o nome aparece 6 vezes no texto), mas ela nunca chega ate ele.

A CAMADA 2 (por TEMA) resolve. Descoberta medida: com 1 termo o Google News
satura em 100 itens e a materia escorre; com 2 termos volta completa e ela
aparece no TOPO:
    '"inteligência artificial" viagem when:7d'      -> 37 itens, materia #1
    '"inteligência artificial" restaurante when:7d' -> 55 itens, materia #1
    '"inteligência artificial" when:7d'  -> 100 itens (saturado), materia some

PORTANTO: as consultas de tema usam SEMPRE 2+ termos, e o filtro de corpo
(cita()) continua sendo o portao final nas duas camadas.
"""
import sys
import time
import urllib.parse
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone

import monitor
import filtro_pagina

# import tardio: collect e importado por monitor, entao importar common no
# topo criaria ciclo. Dentro da funcao resolve na hora do uso.
def _common():
    import common
    return common

BRT = timezone(timedelta(hours=-3))

# ---------------------------------------------------------------- CAMADA 1
# Busca pelo nome. Barata e precisa. Janelas de 7 e 30 dias porque 'when:2d'
# provou ser insuficiente: a materia do O Globo ja tinha 32h quando o monitor
# rodou e nao apareceu.
BUSCAS_NOME = [
    '"Kenneth Corrêa" when:7d',
    '"Kenneth Corrêa" when:30d',
    'Kenneth Correa when:30d',
]

# ---------------------------------------------------------------- CAMADA 2
# Busca por TEMA. Sempre 2+ termos (ver docstring). Os termos sao os temas que
# o Kenneth efetivamente cobre: IA aplicada, eventos, mercado, viagens.
BUSCAS_TEMA = [
    '"inteligência artificial" viagem when:7d',
    '"inteligência artificial" restaurante when:7d',
    '"inteligência artificial" especialista when:7d',
    '"inteligência artificial" professor when:7d',
    '"inteligência artificial" palestra when:7d',
    '"inteligência artificial" keynote when:7d',
    '"inteligência artificial" evento when:7d',
    '"inteligência artificial" convite when:7d',
    'IA inteligencia artificial profissional when:7d',
]

# ---------------------------------------------------------------- CAMADA 3
# Busca por VEICULO, em vez de por assunto.
#
# Por que: as consultas de tema sao uma lista adivinhada. Um veiculo grande
# publica materia sobre QUALQUER assunto - seguranca, dados, educacao,
# economia digital - e o nome do Kenneth no meio do texto. Busca por
# assunto so acha se o titulo usar aquele assunto; busca por veiculo pega
# tudo que aquele veiculo publicou na janela.
#
# A lista de veiculos e FINITA e CONHECIDA. Nao e adivinhacao.
# O filtro de corpo (cita) continua decidindo o que e dele.
VEICULOS = [
    # SEM 'when:' de proposito - medido: o operador zera estas consultas.
    #   site:folha.uol.com.br "Kenneth Corrêa"   -> 2 itens sem when, 0 com
    #   site:folha.uol.com.br Kenneth Correa    -> 100 itens sem when, 1 com
    # A janela de data nao se perde: avaliar() descarta em Python o que for
    # mais velho que dias_janela. Filtrar duas vezes so custava materia.
    'site:folha.uol.com.br "Kenneth Corrêa"',
    'site:uol.com.br "Kenneth Corrêa"',
    'site:oglobo.globo.com "Kenneth Corrêa"',
    'site:estadao.com.br "Kenneth Corrêa"',
    'site:cnnbrasil.com.br "Kenneth Corrêa"',
    'site:valor.globo.com "Kenneth Corrêa"',
    # sem acento: veiculo grande costuma publicar "Correa"
    'site:folha.uol.com.br Kenneth Correa',
    'site:oglobo.globo.com Kenneth Correa',
    'site:estadao.com.br Kenneth Correa',
    'site:cnnbrasil.com.br Kenneth Correa',
    'site:valor.globo.com Kenneth Correa',
    # fonte nomeada (source: tambem funciona no RSS)
    'source:Estadão "Kenneth Corrêa"',
    # veiculo como termo solto: pega republicacao em portal agregador
    '"Kenneth Corrêa" folha',
    '"Kenneth Corrêa" oglobo',
    '"Kenneth Corrêa" valor',
]


# Teto de downloads por consulta de tema. O ganho marginal cai muito depois
# das primeiras e o custo e tempo de rede (rate limit do veiculo).
MAX_DOWNLOADS_POR_TEMA = 20

# Pausa entre downloads, para o veiculo nao bloquear por rapido demais.
PAUSA = 1.2


def _rss(q):
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
           + "&hl=pt-BR&gl=BR&ceid=BR:pt-419")
    try:
        return monitor.parse_items(monitor.fetch_rss(url))
    except Exception as e:
        print(f"    RSS falhou ({q}): {e}")
        return []


def _dt_brt(e):
    try:
        dt = parsedate_to_datetime(e["pubDate"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BRT)
    except Exception:
        return None


def textos_publicados():
    """Materias ja no banco, com titulo e corpo.

    A comparacao de republicacao usa o CORPO, porque so o titulo nao
    distingue 'mesma materia, titulo variado' de 'assunto parecido,
    materia diferente' - erro que uma versao anterior cometia nos dois
    sentidos.
    """
    st, resp = _common().sb_select({
        "select": "title,conteudo,source,link", "limit": "300"})
    if not isinstance(resp, list) or not resp:
        return []
    return [{"title": r.get("title") or "", "conteudo": r.get("conteudo") or "",
             "source": r.get("source") or "", "link": r.get("link") or ""}
            for r in resp if r.get("conteudo")]


def coletar(keyword, dias_janela=14, verbose=True):
    """Devolve lista de dicts no mesmo formato que o monitor.py grava."""
    vistos = set()      # titulos aceitos
    testados = set()    # titulos ja baixados: evita refazer o mesmo download
    saida = []

    ja_publicadas = textos_publicados()
    if verbose:
        print(f"  {len(ja_publicadas)} materia(s) com texto ja no banco "
              f"(base para detectar republicacao)")

    def _link_ja_no_banco(link):
        """True se este endereco ja foi gravado.

        Sem isso, uma materia apagada do banco pela limpeza volta na
        coleta seguinte: em 2026-10-05 a materia do riobrilhante
        voltou do mesmo jeito que tinha sido removida.
        """
        alvo = (link or "").split("?")[0].rstrip("/")
        if not alvo:
            return False
        for pub in ja_publicadas:
            ja = (pub.get("link") or "").split("?")[0].rstrip("/")
            if ja and ja == alvo:
                return True
        return False

    def _titulo_igual_ao_do_banco(titulo, fonte_novo=""):
        """Mesmo titulo (sem acento, sem pontuacao) ja guardado.

        So com fonte diferente: no mesmo veiculo, titulo igual pode ser
        materia nova da secao de resumo.

        `fonte_novo` e PARAMETRO de proposito: antes esta funcao lia a
        variavel `fonte`, que so existe dentro de avaliar(). Escopo irmao
        nao enxerga escopo irmao - era NameError garantido no primeiro
        registro com titulo repetido, e derrubava o monitor inteiro.
        """
        def chave(s):
            s = __import__("unicodedata").normalize("NFD", (s or "").lower())
            s = "".join(c for c in s if __import__("unicodedata").category(c) != "Mn")
            return __import__("re").sub(r"[^a-z0-9]+", " ", s).strip()[:60]

        alvo = chave(titulo)
        if not alvo:
            return False
        for pub in ja_publicadas:
            if fonte_novo and pub.get("source") == fonte_novo:
                continue
            if chave(pub.get("title")) == alvo:
                return True
        return False

    def avaliar(e):
        """Verifica e devolve o dict pronto, ou None se nao serve."""
        dt = _dt_brt(e)
        if dt is None:
            return None
        if dt.timestamp() < (datetime.now(BRT) - timedelta(days=dias_janela)).timestamp():
            return None

        t = e["title"].strip()
        fonte = e.get("source") or ""
        if " - " in t:
            t, talvez = t.rsplit(" - ", 1)
            if not fonte:
                fonte = talvez
        chave = t.lower()[:80]
        if chave in vistos or chave in testados:
            return None

        def pronto(url, checagem):
            vistos.add(chave)
            return {"keyword": keyword, "title": t, "link": url,
                    "source": fonte, "dia": dt.strftime("%Y-%m-%d"),
                    "quando": dt.strftime("%d/%m/%Y %H:%M"),
                    "ts": int(dt.timestamp() * 1000),
                    "checagem": checagem}

        # Republicacao: mesma materia em outro portal. So e decidido
        # DEPOIS de baixar o corpo, porque a comparacao e de texto e nao
        # de titulo. O titulo sozinho erra nos dois sentidos - deixa
        # passar republicacao e barra materia nova sobre o mesmo tema.
        def checa_republicacao(txt):
            # Evidencia dupla: titulo (pega reescrita local) + corpo
            # (pega quando o titulo foi muito mexido).
            for p in ja_publicadas:
                if monitor.e_republica(t, fonte, ja_publicadas, txt):
                    print(f"    [dup] '{t[:40]}' = republicacao de "
                          f"'{p['title'][:34]}' ({p['source'][:14]})")
                    return True
            return False

        # Link ja no banco = mesma materia, com certeza. Checagem mais
        # barata que qualquer comparacao de texto.
        if _link_ja_no_banco(e["link"]):
            print(f"    [dup] '{t[:40]}' = link ja esta no banco")
            return None

        # Nome no TITULO = o nome esta no titulo, mas a MATERIA pode
        # ser republicacao de outra ja guardada. Antes esta checagem
        # nao existia aqui e a materia voltava pro banco duplicada.
        if monitor.cita(t, keyword):
            if _titulo_igual_ao_do_banco(t, fonte):
                print(f"    [dup] '{t[:40]}' = mesmo titulo ja no banco")
                return None
            url = monitor.google_news_real_url(e["link"]) or e["link"]
            return pronto(url, "titulo")

        # Nao esta no titulo: so vale conferir baixando o corpo.
        url = monitor.google_news_real_url(e["link"])
        if not url:
            return None
        testados.add(chave)      # ja verificado; nao repetir em outra consulta
        txt = monitor.baixa_texto(url)
        if txt:
            #Rgela de materia x pagina. O filtro antigo casava a
            # palavra solta "marketing" e procurava no texto INTEIRO
            # da pagina, incluindo a barra lateral de "Noticias
            # Relacionadas". Em 2026-10-04 isso deixou 9 de 41
            # materias no banco sem serem sobre o Kenneth nem sobre a
            # empresa dele. Ver filtro_pagina.py para a medicao.
            ok, motivo = filtro_pagina.aceita(txt, t, keyword)
            if not ok:
                if verbose:
                    print(f"    [filtro] '{t[:40]}' descartada: {motivo}")
                return None
            # Mesmo titulo (normalizado) de OUTRO veiculo = mesma materia.
            #
            # Esta checagem so existia no caminho do TITULO. Quando o nome
            # nao esta no titulo - caso de "Evento gratuito reune
            # empresarios..." -, o caminho do CORPO nao a rodava e a
            # duplicata entrava. Medido em 2026-10-06: a mesma materia
            # entrou 2x (riobrilhante em 05/10, diariodigital em 24/09),
            # porque e_republica exige corpo >= 800 chars no registro
            # ANTIGO - e o corpo so e gravado pelo sentiment.py, que ainda
            # nao tinha rodado para a materia antiga.
            if _titulo_igual_ao_do_banco(t, fonte):
                print(f"    [dup] '{t[:40]}' = mesmo titulo ja no banco (via corpo)")
                return None
            # Ultima chance: e republicacao de algo ja no banco?
            if checa_republicacao(txt):
                return None
            return pronto(url, "corpo")
        return None

    # ------------------------------------------------ CAMADA 1: por nome
    for q in BUSCAS_NOME:
        for e in _rss(q):
            r = avaliar(e)
            if r:
                saida.append(r)
                if verbose:
                    print(f"    [nome] {r['title'][:58]} ({r['checagem']})")
            time.sleep(0.4)

    # ------------------------------- CAMADAS 2 e 3: tema e veiculo
    # Mesmo algoritmo para os dois, so muda a lista de consultas e o rotulo.
    # A CAMADA 3 e a que fecha a lacuna de assunto: um veiculo grande publica
    # sobre qualquer tema, e o nome do Kenneth esta no meio do texto.
    for rotulo, consultas in (("TEMA", BUSCAS_TEMA), ("VEICULO", VEICULOS)):
        for q in consultas:
            baixados = achou = 0
            for e in _rss(q):
                if baixados >= MAX_DOWNLOADS_POR_TEMA:
                    break
                titulo = e["title"].strip().lower()[:80]
                if titulo in vistos or titulo in testados:
                    continue
                baixados += 1
                r = avaliar(e)
                if r:
                    saida.append(r)
                    achou += 1
                    if verbose:
                        print(f"    [{rotulo:7}] {r['title'][:58]} ({r['checagem']})")
                time.sleep(PAUSA)
            if verbose:
                print(f"  {rotulo:7} {q[:44]:44} baixados={baixados:3} novos={achou}")

    # dedup final por titulo
    unicos, vistos2 = [], set()
    for r in saida:
        k = r["title"].lower()[:80]
        if k in vistos2:
            continue
        vistos2.add(k)
        unicos.append(r)
    return unicos


if __name__ == "__main__":
    import os
    os.environ.setdefault("KEYWORDS", "Kenneth Corrêa")
    from common import KEYWORDS
    kw = sys.argv[1] if len(sys.argv) > 1 else KEYWORDS[0]
    res = coletar(kw)
    print(f"\nTOTAL: {len(res)} materia(s)")
    for r in res:
        print(f"  [{r['checagem']:12}] {r['title'][:62]}")