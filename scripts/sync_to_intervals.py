#!/usr/bin/env python3
"""
Sincroniza plan/plan.json com o calendario do intervals.icu.

So mexe em datas de hoje em diante - nunca toca em dias passados. Tem duas
partes:

  1. Cria os eventos que ainda nao existem, em todo o plano futuro
     (comparando por data+nome).
  2. Nos proximos RECONCILE_WINDOW_DAYS dias (onde o scripts/adapt_plan.py
     pode ter mudado coisas), tambem ATUALIZA eventos que mudaram e APAGA
     eventos que deixaram de estar no plano - mas só os que TEM a marca
     MARKER na descricao (ou seja, só eventos que este script criou). Nunca
     mexe num evento que tu proprio tenhas criado a mao no intervals.icu.

Requer duas variaveis de ambiente:
  INTERVALS_API_KEY      a tua API key (Settings > Developer no intervals.icu)
  INTERVALS_ATHLETE_ID   o teu id de atleta, formato "i123456"

Uso:
  python3 scripts/sync_to_intervals.py            # cria/atualiza o que for preciso
  python3 scripts/sync_to_intervals.py --dry-run   # so mostra o que faria

Nota: os nomes exatos dos campos da API (start_date_local, moving_time, etc.)
seguem a documentacao publica em https://intervals.icu/api-docs.html. Este
script nao foi corrido contra a API ao vivo neste ambiente (sem acesso de
rede a intervals.icu) - corre primeiro `--dry-run` e depois uma vez a serio
manualmente (workflow_dispatch) antes de confiares no cron semanal.
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import json as _json  # noqa: E402
from intervals_client import MARKER, api_request, fetch_events  # noqa: E402

RECONCILE_WINDOW_DAYS = 21

SPORT_MAP = {
    "run":      ("Run", "WORKOUT"),
    "bike":     ("Ride", "WORKOUT"),
    "swim":     ("Swim", "WORKOUT"),
    "strength": ("WeightTraining", "WORKOUT"),
    "pt":       ("WeightTraining", "WORKOUT"),
    "mobility": ("Yoga", "WORKOUT"),
    "other":    ("Other", "WORKOUT"),
    "rest":     ("Other", "NOTE"),
    # "Triathlon" nao e um "type" valido na API (HTTP 400 "JSON parse error" --
    # provavelmente um enum estrito do lado do servidor). "Other" e um type
    # generico que ja confirmamos funcionar; o que distingue este evento como
    # a prova e o category="RACE".
    "race":     ("Other", "RACE"),
}


def to_event_body(workout):
    sport_type, category = SPORT_MAP.get(workout["sport"], ("Other", "WORKOUT"))
    body = {
        "category": category,
        "start_date_local": f"{workout['date']}T00:00:00",
        "type": sport_type,
        "name": workout["title"],
        "description": (workout.get("description") or "") + MARKER,
    }
    if workout.get("duration_h"):
        body["moving_time"] = int(round(workout["duration_h"] * 3600))
    return body


def needs_update(existing, desired_body):
    for key in ("name", "type", "category", "description", "moving_time"):
        if str(existing.get(key) or "") != str(desired_body.get(key) or ""):
            return True
    return False


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
        plan = _json.load(f)

    today = datetime.date.today()
    today_s = today.isoformat()
    reconcile_end = (today + datetime.timedelta(days=RECONCILE_WINDOW_DAYS)).isoformat()
    future = [w for w in plan if w["date"] >= today_s]
    if not future:
        print("Nada para sincronizar (plano sem treinos futuros).")
        return

    oldest, newest = future[0]["date"], future[-1]["date"]
    print(f"Plano: {len(future)} treinos futuros entre {oldest} e {newest}.")
    print(f"Janela de reconciliacao (update/delete): {today_s} -> {reconcile_end}")

    if args.dry_run:
        existing_events = []
    else:
        existing_events = fetch_events(athlete_id, api_key, oldest, newest)
        print(f"Ja existem {len(existing_events)} eventos nesse intervalo no intervals.icu.")

    # indexar eventos existentes por (data, nome) -> evento
    existing_by_key = {}
    for ev in existing_events:
        date = (ev.get("start_date_local") or "")[:10]
        existing_by_key[(date, ev.get("name") or "")] = ev

    created, updated, deleted, skipped, failed = 0, 0, 0, 0, 0

    for w in future:
        key = (w["date"], w["title"])
        body = to_event_body(w)
        existing = existing_by_key.pop(key, None)

        if existing is None:
            if args.dry_run:
                print(f"[dry-run] criaria: {w['date']} - {w['title']} ({w['sport']})")
                created += 1
                continue
            try:
                api_request("POST", f"/athlete/{athlete_id}/events", api_key, body)
                print(f"criado: {w['date']} - {w['title']}")
                created += 1
            except RuntimeError as e:
                print(f"FALHOU (criar): {w['date']} - {w['title']}: {e}", file=sys.stderr)
                failed += 1
            continue

        # ja existe um evento com a mesma data+nome
        if w["date"] > reconcile_end:
            skipped += 1  # fora da janela de reconciliacao, nao mexer
            continue
        if MARKER not in (existing.get("description") or ""):
            print(f"aviso: evento manual em {w['date']} - {w['title']} ignorado (nao foi criado por nos).")
            skipped += 1
            continue
        if not needs_update(existing, body):
            skipped += 1
            continue
        if args.dry_run:
            print(f"[dry-run] atualizaria: {w['date']} - {w['title']}")
            updated += 1
            continue
        try:
            api_request("PUT", f"/athlete/{athlete_id}/events/{existing['id']}", api_key, body)
            print(f"atualizado: {w['date']} - {w['title']}")
            updated += 1
        except RuntimeError as e:
            print(f"FALHOU (atualizar): {w['date']} - {w['title']}: {e}", file=sys.stderr)
            failed += 1

    # o que sobrou em existing_by_key, dentro da janela de reconciliacao e
    # com a nossa marca, ja nao esta no plano -> apagar
    for (date, name), ev in existing_by_key.items():
        if date > reconcile_end:
            continue
        if MARKER not in (ev.get("description") or ""):
            continue
        if args.dry_run:
            print(f"[dry-run] apagaria: {date} - {name}")
            deleted += 1
            continue
        try:
            api_request("DELETE", f"/athlete/{athlete_id}/events/{ev['id']}", api_key)
            print(f"apagado: {date} - {name}")
            deleted += 1
        except RuntimeError as e:
            print(f"FALHOU (apagar): {date} - {name}: {e}", file=sys.stderr)
            failed += 1

    print(f"\nResumo: {created} criados, {updated} atualizados, {deleted} apagados, "
          f"{skipped} sem alteracao, {failed} falharam.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
