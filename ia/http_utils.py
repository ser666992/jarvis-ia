"""
ia/http_utils.py
==================
Helper HTTP mínimo baseado em `urllib` (stdlib) para os provedores de
IA em `ia/providers/`. Propositalmente NÃO depende de `requests`, para
que nenhum provedor externo exija instalar nada além do Python padrão.
"""

import json
import urllib.error
import urllib.request


def post_json(url: str, payload: dict, headers: dict = None, timeout: int = 30):
    """POST com corpo JSON. Retorna (ok: bool, status_ou_None, data: dict)."""
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    req_headers.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return True, resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"erro": str(e)}
        return False, e.code, body
    except urllib.error.URLError as e:
        return False, None, {"erro": str(e.reason)}
    except Exception as e:
        return False, None, {"erro": str(e)}


def get_json(url: str, headers: dict = None, timeout: int = 10):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return True, resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        return False, e.code, {}
    except Exception as e:
        return False, None, {"erro": str(e)}
