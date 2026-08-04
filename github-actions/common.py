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
LLM_MODEL = os.environ.get("LLM_MODEL", "tencent/hy3:free")

TABLE = "monitored_news"


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
    except Exception as e:  # noqa
        return None, str(e)


# ---------- Supabase REST ----------
def sb_select(params: dict):
    q = urllib.parse.urlencode(params)
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?{q}"
    return http("GET", url, {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})


def sb_upsert(rows: list):
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?on_conflict=link"
    return http(
        "POST",
        url,
        {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
         "Prefer": "resolution=ignore,return=minimal"},
        rows,
    )


def sb_update_sentimento(link: str, sentimento: str):
    enc = urllib.parse.quote(link, safe="")
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}?link=eq.{enc}"
    return http(
        "PATCH",
        url,
        {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
         "Prefer": "return=representation"},
        {"sentimento": sentimento},
    )


# ---------- Telegram ----------
def tg_send(text: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    body = {"chat_id": TG_CHAT_ID, "text": text, "disable_web_page_preview": True}
    return http("POST", url, {}, body)
