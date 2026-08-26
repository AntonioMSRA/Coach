"""Cliente minimo para a API do intervals.icu, partilhado pelos scripts de sync."""
import base64
import json
import urllib.error
import urllib.request

API_BASE = "https://intervals.icu/api/v1"

# Acrescentado a toda a descricao de eventos criados por nos, para os
# distinguirmos de eventos que o proprio atleta cria a mao no intervals.icu.
# scripts/sync_to_intervals.py so atualiza/apaga eventos que tenham esta marca.
MARKER = "\n\n_(plano automatico -- Coach)_"


def api_request(method, path, api_key, body=None):
    url = f"{API_BASE}{path}"
    token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}") from e


def fetch_events(athlete_id, api_key, oldest, newest):
    path = f"/athlete/{athlete_id}/events?oldest={oldest}&newest={newest}"
    return api_request("GET", path, api_key) or []


def fetch_activities(athlete_id, api_key, oldest, newest):
    path = f"/athlete/{athlete_id}/activities?oldest={oldest}&newest={newest}"
    return api_request("GET", path, api_key) or []
