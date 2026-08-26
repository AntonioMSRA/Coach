#!/usr/bin/env python3
"""
Sincroniza plan/plan.json com o calendario do intervals.icu.

E idempotente: antes de criar, verifica os eventos ja existentes no
intervalo de datas (por data + nome) e salta os que ja la estao. So mexe
em datas de hoje em diante - nunca toca em dias passados.

Requer duas variaveis de ambiente:
  INTERVALS_API_KEY      a tua API key (Settings > Developer no intervals.icu)
  INTERVALS_ATHLETE_ID   o teu id de atleta, formato "i123456"

Uso:
  python3 scripts/sync_to_intervals.py            # cria o que faltar
  python3 scripts/sync_to_intervals.py --dry-run   # so mostra o que faria

Nota: os nomes exatos dos campos da API (start_date_local, moving_time, etc.)
seguem a documentacao publica em https://intervals.icu/api-docs.html. Este
script nao foi corrido contra a API ao vivo neste ambiente (sem acesso de
rede a intervals.icu) - corre primeiro `--dry-run` e depois uma vez a serio
manualmente (workflow_dispatch) antes de confiares no cron semanal. Se algum
campo tiver mudado de nome, o erro da API costuma dizer exatamente qual.
"""
import argparse
import base64
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = "https://intervals.icu/api/v1"

SPORT_MAP = {
    "run":      ("Run", "WORKOUT"),
    "bike":     ("Ride", "WORKOUT"),
    "swim":     ("Swim", "WORKOUT"),
    "strength": ("WeightTraining", "WORKOUT"),
    "pt":       ("WeightTraining", "WORKOUT"),
    "mobility": ("Yoga", "WORKOUT"),
    "other":    ("Other", "WORKOUT"),
    "rest":     ("Other", "NOTE"),
    "race":     ("Triathlon", "RACE"),
}


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


def fetch_existing(athlete_id, api_key, oldest, newest):
    path = f"/athlete/{athlete_id}/events?oldest={oldest}&newest={newest}"
    events = api_request("GET", path, api_key) or []
    existing = set()
    for ev in events:
        date = (ev.get("start_date_local") or "")[:10]
        name = ev.get("name") or ""
        existing.add((date, name))
    return existing


def to_event_body(workout):
    sport_type, category = SPORT_MAP.get(workout["sport"], ("Other", "WORKOUT"))
    body = {
        "category": category,
        "start_date_local": f"{workout['date']}T00:00:00",
        "type": sport_type,
        "name": workout["title"],
        "description": workout.get("description") or "",
    }
    if workout.get("duration_h"):
        body["moving_time"] = int(round(workout["duration_h"] * 3600))
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--plan", default=os.path.join(os.path.dirname(__file__), "..", "plan", "plan.json"))
    args = ap.parse_args()

    api_key = os.environ.get("INTERVALS_API_KEY")
    athlete_id = os.environ.get("INTERVALS_ATHLETE_ID")
    if not args.dry_run and (not api_key or not athlete_id):
        print("ERRO: define INTERVALS_API_KEY e INTERVALS_ATHLETE_ID no ambiente.", file=sys.stderr)
        sys.exit(1)

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    today = datetime.date.today().isoformat()
    future = [w for w in plan if w["date"] >= today]
    if not future:
        print("Nada para sincronizar (plano sem treinos futuros).")
        return

    oldest, newest = future[0]["date"], future[-1]["date"]
    print(f"Plano: {len(future)} treinos futuros entre {oldest} e {newest}.")

    if args.dry_run:
        existing = set()
    else:
        existing = fetch_existing(athlete_id, api_key, oldest, newest)
        print(f"Ja existem {len(existing)} eventos nesse intervalo no intervals.icu.")

    created, skipped, failed = 0, 0, 0
    for w in future:
        key = (w["date"], w["title"])
        if key in existing:
            skipped += 1
            continue
        body = to_event_body(w)
        if args.dry_run:
            print(f"[dry-run] criaria: {w['date']} - {w['title']} ({w['sport']})")
            created += 1
            continue
        try:
            api_request("POST", f"/athlete/{athlete_id}/events", api_key, body)
            print(f"criado: {w['date']} - {w['title']}")
            created += 1
        except RuntimeError as e:
            print(f"FALHOU: {w['date']} - {w['title']}: {e}", file=sys.stderr)
            failed += 1

    print(f"\nResumo: {created} criados, {skipped} ja existiam, {failed} falharam.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
