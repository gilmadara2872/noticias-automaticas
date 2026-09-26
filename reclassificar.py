#!/usr/bin/env python3
# Script para reclassificar TODAS as noticias no banco de dados
# Zera sentimento e conteudo para que sentiment.py analise tudo com o novo modelo Qwen.
# NAO APAGA NADA - somente reclassifica os registros que ja existem.
import os, json, urllib.request, urllib.error

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uirvzlxhuyaentizyden.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TABLE = "monitored_news"

def _hdr():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Prefer": "return=representation"}

# Zera sentimento e conteudo de TODAS as noticias
url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
hdr = _hdr()
body = json.dumps({"sentimento": None, "conteudo": None}).encode()
req = urllib.request.Request(url, data=body, method="PATCH", headers=hdr)
try:
    r = urllib.request.urlopen(req, timeout=30)
    print("SUCCESS: Todas as noticias tiveram sentimento e conteudo zerados.")
    print("O pipeline do sentiment.py vai reclassificar tudo no proximo ciclo (05:30 BRT).")
    print("Nenhuma noticia foi apagada - apenas reclassificada.")
except urllib.error.HTTPError as e:
    print(f"ERRO: HTTP {e.code} - {e.read().decode()[:300]}")
    print("Verifique se SUPABASE_KEY e uma service_role key (nao anon).")
except Exception as e:
    print(f"ERRO: {e}")
