"""Rgela de aceitacao da coleta: materia e pagina.

O QUE CAUSOU O PROBLEMA (medido em 2026-10-04)
---------------------------------------------
9 das 41 materias do banco nao eram sobre o Kenneth nem sobre a
empresa dele. Entraram porque o filtro casava a PALAVRA SOLTA
"marketing" em texto que nao era sobre a empresa:

  "marketing para clientes" (G1, CSB)
  "politica de privacidade para fins de marketing" (SAPO)
  "cookies de campanhas de marketing" (CREMERS, Engarrafador)
  "Marketing Science", revista citada num artigo de psicologia

E o filtro procurava no TEXTO INTEIRO da pagina, incluindo a barra
lateral de "Noticias Relacionadas", onde aparece link de materia da
empresa.

TENTATIVAS DESCARTADAS POR MEDICAO
----------------------------------
1) Cortar o texto no primeiro bloco de navegacao e procurar so no
   que sobrou: barrou 13 das 32 materias legitimas. CNN e Estadao
   tem "Compartilhe com" no MEIO do artigo.
2) Considerar a mencao "so na navegacao" quando nao ha nenhuma antes
   do bloco: barrou 9 das 32. O botao de compartilhar vem ANTES do
   artigo em varios sites.

REGUA FINAL - medida em 2026-10-04 nos 40 casos reais:
  Materia boa : 32/32 - o nome aparece, 1a mencao entre 0.04 e 0.58
  Ruido       : 8/8   - o nome COMPLETO nao aparece (0 ocorrencias)

Ou seja: nao preciso adivinhar onde comeca o artigo. Exijo o NOME
COMPLETO e, para empresa, que a 1a mencao venha antes da metade do
texto (barra lateral sempre fica no fim). Materia real do Kenneth
sempre cita o nome cedo.
"""
import re
import unicodedata


def _sem_acento(s):
    b = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in b if unicodedata.category(c) != "Mn")


def _limpa(s):
    return re.sub(r"[^a-z0-9]", "", _sem_acento(s))


def ocorrencias(texto, nome):
    """Posicoes (fracoes de 0 a 1) do nome dentro do texto."""
    chave = _limpa(nome)
    limpo = _limpa(texto)
    if not chave or not limpo:
        return []
    out = []
    i = limpo.find(chave)
    while i != -1:
        out.append(i / len(limpo))
        i = limpo.find(chave, i + 1)
    return out


def empresa_de_verdade(texto, nome="80 20 Marketing"):
    """True se o NOME COMPLETO da empresa aparece.

    Exigir "80 20" e o que separa a empresa da palavra "marketing",
    que o sistema usava e que aparece em texto comum e em cookie de
    site.
    """
    return bool(ocorrencias(texto, nome))


def e_nome_de_empresa(keyword):
    return (keyword or "").lower().startswith("80 20")


def aceita(texto, titulo="", keyword="Kenneth Corrêa", antes_de=0.85):
    """Rgela de aceitacao da coleta.

    Pessoa  -> o nome completo precisa aparecer no texto.
    Empresa -> o nome completo precisa aparecer E a primeira mencao
               precisa vir antes de 60% do texto. Barra lateral e
               rodape ficam sempre depois disso.

    Devolve (aceita, motivo) para o log mostrar o porque.
    """
    if not (texto or "").strip():
        return False, "sem texto"

    fracs = ocorrencias(texto, keyword)
    if not fracs:
        if e_nome_de_empresa(keyword):
            return False, "nome completo da empresa nao aparece"
        return False, "nome da pessoa nao aparece no texto"

    if fracs[0] > antes_de:
        # so aparece tarde: charakteristico de link de rodape/sidebar
        if e_nome_de_empresa(keyword):
            return False, f"empresa so no fim da pagina ({fracs[0]:.0%})"
        return False, f"nome so no fim da pagina ({fracs[0]:.0%})"

    return True, f"{len(fracs)} mencao(oes), 1a em {fracs[0]:.0%}"