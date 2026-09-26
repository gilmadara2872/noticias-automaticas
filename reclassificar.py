#!/usr/bin/env python3
# Script para reclassificar TODAS as notícias no banco de dados
# Zera o sentimento para que o sentiment.py analise tudo novamente
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import common

# Zera o sentimento de todas as notícias
url = f"{common.SUPABASE_URL}/rest/v1/{common.TABLE}"
hdr = common._hdr(Prefer="return=representation")
body = {"sentimento": None, "conteudo": None}

st, resp = common.http("PATCH", url, hdr, body)
if st in (200, 204):
    print("SUCCESS: Todas as notícias tiveram sentimento e conteúdo zerados.")
    print("O pipeline do sentiment.py vai reclassificar tudo no próximo ciclo.")
else:
    print(f"ERRO: status={st}, resposta={resp}")
    print("Verifique suas credenciais do Supabase.")
