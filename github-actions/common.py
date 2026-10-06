#!/usr/bin/env python3
# Helpers compartilhados (stdlib only) para os 3 scripts do Missao Gilberto.
# Tudo vem de variaveis de ambiente (segredos do GitHub) - nada hardcoded.
import os
import json
import urllib.parse
import urllib.request
import urllib.error

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uirvzlxhuyaentizyden.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
# O modelo principal anterior (qwen/qwen3.8-27b:free) saiu do ar gratuito
# em 2026-10-05. O novo principal e o nvidia/nemotron-3-super-120b-a12b:free,
# que e o maior modelo gratuito disponivel e tem bom desempenho em
# classificacao de texto. O tier gratuito do OpenRouter da 50 requisicoes/dia
# por conta, e o sistema usa cerca de 5 por dia.
LLM_MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

TABLE = "monitored_news"

DEFAULT_KEYWORDS = ["Cliente Nome", "Marca A", "Empresa B"]
KEYWORDS = [k.strip() for k in os.environ.get("KEYWORDS", "").split(";") if k.strip()] or DEFAULT_KEYWORDS


def http(method, url, headers=None, body=None, timeout=40):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers or {})
    if data is not None and "Content-Type" not in h:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", "ignore")
            return r.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")[:500]
    except Exception as e:
        return None, str(e)


# ---------- Supabase REST ----------
def _hdr(**extra):
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", **extra}


def coluna_ausente(st, resp, coluna):
    s = str(resp)
    return st in (400, 404) and coluna in s and ("PGRST204" in s or "42703" in s)


def sb_select(params: dict):
    q = urllib.parse.urlencode(params)
    return http("GET", f"{SUPABASE_URL}/rest/v1/{TABLE}?{q}", _hdr())


def sb_upsert(rows: list):
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?on_conflict=link"
    hdr = _hdr(Prefer="resolution=ignore-duplicates,return=minimal")
    st, resp = http("POST", url, hdr, rows)
    if coluna_ausente(st, resp, "checagem"):
        print("  aviso: coluna 'checagem' ainda nao existe no banco; gravando sem ela (rode o ALTER TABLE para ativar o aviso).")
        limpo = [{k: v for k, v in r.items() if k != "checagem"} for r in rows]
        st, resp = http("POST", url, hdr, limpo)
    return st, resp


def sb_update_sentimento(link: str, sentimento: str, conteudo: str = None):
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?link=eq.{urllib.parse.quote(link, safe='')}"
    hdr = _hdr(Prefer="return=representation")
    body = {"sentimento": sentimento}
    if conteudo is not None:
        body["conteudo"] = conteudo
    st, resp = http("PATCH", url, hdr, body)
    if conteudo is not None and coluna_ausente(st, resp, "conteudo"):
        print("  aviso: coluna 'conteudo' ainda nao existe no banco; gravando so o sentimento (rode o ALTER TABLE para guardar o texto).")
        st, resp = http("PATCH", url, hdr, {"sentimento": sentimento})
    return st, resp


# ---------- Telegram ----------
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    body = {"chat_id": TG_CHAT_ID, "text": text, "disable_web_page_preview": True}
    return http("POST", url, {}, body)
