#!/usr/bin/env python3
"""
Ajusta as proximas ~2 semanas de plan/plan.json com base em:
  - o que foi realmente treinado na ultima semana (via API do intervals.icu)
  - as notas que tu escreveste em plan/athlete_input.md
  - o que estava planeado

Usa a API da Anthropic (Claude) para propor ajustes, mas nunca aplica nada
as cegas: cada alteracao proposta passa por um conjunto de regras fixas
(guardrails) antes de ser aceite. Corre uma vez por semana, antes do
scripts/sync_to_intervals.py, dentro do workflow do GitHub Actions.

Nunca mexe:
  - em dias de hoje para tras
  - na fase de taper / semana de prova / primeira semana pos-prova
    (LOCK_START -> LOCK_END, ver abaixo - mantem-se em sincronia manual com
    as fases definidas em plan/generate_plan.py)
  - no proprio dia da prova

Cada corrida escreve um registo em plan/CHANGELOG.md a explicar porque
mudou (ou nao mudou) alguma coisa - para poderes rever ou reverter
(`git revert`) se discordares.

Requer:
  ANTHROPIC_API_KEY
  INTERVALS_API_KEY, INTERVALS_ATHLETE_ID   (para ler o que treinaste)

Uso:
  python3 scripts/adapt_plan.py            # aplica os ajustes validados
  python3 scripts/adapt_plan.py --dry-run   # so mostra o que proporia
"""
import argparse
import datetime
import json
import os
import sys
from typing import List, Literal, Optional

sys.path.insert(0, os.path.dirname(__file__))
from intervals_client import fetch_activities  # noqa: E402

HERE = os.path.dirname(__file__)
PLAN_PATH = os.path.join(HERE, "..", "plan", "plan.json")
NOTES_PATH = os.path.join(HERE, "..", "plan", "athlete_input.md")
CHANGELOG_PATH = os.path.join(HERE, "..", "plan", "CHANGELOG.md")

# Tem de ficar em sincronia com as fases em plan/generate_plan.py.
LOCK_START = datetime.date(2026, 9, 21)   # inicio do taper
LOCK_END = datetime.date(2026, 10, 24)    # fim da 1a semana pos-prova
RACE_DATE = datetime.date(2026, 10, 17)

ADAPT_WINDOW_DAYS = 14
MAX_CHANGES = 10
MAX_ADD = 3
MAX_REMOVE = 5
DURATION_CEILING_H = {
    "run": 3.0, "bike": 6.0, "swim": 2.5, "strength": 1.5,
    "pt": 1.5, "mobility": 0.75, "other": 2.0,
}
ALLOWED_SPORTS = set(DURATION_CEILING_H) | {"rest"}


def is_locked(date):
    return LOCK_START <= date <= LOCK_END


class ChangeOp:
    def __init__(self, d):
        self.action = d.get("action")
        self.index = d.get("index")
        self.date = d.get("date")
        self.title = d.get("title")
        self.sport = d.get("sport")
        self.description = d.get("description")
        self.duration_h = d.get("duration_h")


def build_prompt(upcoming, adherence_text, notes_text, today):
    upcoming_json = json.dumps(
        [{"index": i, **{k: w[k] for k in ("date", "title", "sport", "description", "duration_h")}}
         for i, w in enumerate(upcoming)],
        ensure_ascii=False, indent=2,
    )
    return f"""Es um treinador de triatlo a rever o plano de um atleta amador que se
esta a preparar para o IronMan 70.3 Cascais (17/out/2026) e depois vai
continuar a treinar em manutencao, sem objetivo definido, ate 31/dez/2026.

Hoje e {today.isoformat()}.

## O que estava planeado vs. o que foi feito na ultima semana
{adherence_text}

## Notas recentes do atleta (podem nao ter nada de relevante)
{notes_text or "(sem notas novas)"}

## Proximas ~2 semanas atualmente planeadas
Cada item tem um "index" - usa esse numero para te referires a ele.
{upcoming_json}

## O que te peco
Propoe ajustes PEQUENOS e conservadores a este plano, so onde a evidencia
justifique (fadiga a acumular, treinos falhados repetidamente, dor
mencionada nas notas, ou o oposto - sinais claros de estar a sobrar
capacidade). Se nao houver nada que justifique mudar, propoe uma lista de
alteracoes vazia - isso e o resultado normal e esperado a maioria das
semanas.

Regras:
- No maximo {MAX_CHANGES} alteracoes.
- "modify" e "remove" tem de referir um "index" da lista acima.
- "add" cria um item novo (usa para substituir um treino por algo mais
  leve num dia especifico, ex: trocar corrida por mobilidade se ha dor).
- sport tem de ser um destes: {sorted(ALLOWED_SPORTS)}.
- duration_h dentro do razoavel para o sport (nunca inventes volumes altos).
- Nunca proponhas nada para datas fora da janela mostrada acima.
- Se so quiseres reduzir intensidade/volume sem mudar o dia, usa "modify".
- O campo "reasoning" deve ser uma explicacao curta, em portugues, que o
  atleta vai ler diretamente - escreve para ele, nao para um sistema.
"""


def call_claude(prompt):
    import anthropic
    from pydantic import BaseModel

    class Change(BaseModel):
        action: Literal["modify", "remove", "add"]
        index: Optional[int] = None
        date: Optional[str] = None
        title: Optional[str] = None
        sport: Optional[str] = None
        description: Optional[str] = None
        duration_h: Optional[float] = None

    class WeeklyAdaptation(BaseModel):
        reasoning: str
        changes: List[Change]

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model="claude-opus-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        output_format=WeeklyAdaptation,
    )
    return response.parsed_output


def summarize_adherence(activities, upcoming, today):
    """Compara o planeado dos ultimos 7 dias com o que foi de facto feito."""
    past_start = (today - datetime.timedelta(days=7)).isoformat()
    past_end = (today - datetime.timedelta(days=1)).isoformat()
    with open(PLAN_PATH, encoding="utf-8") as f:
        full_plan = json.load(f)
    planned_last_week = [w for w in full_plan if past_start <= w["date"] <= past_end]

    lines = []
    for w in planned_last_week:
        lines.append(f"- {w['date']} planeado: {w['title']} ({w['sport']}, "
                      f"{w['duration_h'] or '?'}h)")
    if not planned_last_week:
        lines.append("(sem treinos planeados nos ultimos 7 dias)")

    lines.append("\nAtividades reais registadas no intervals.icu na ultima semana:")
    if not activities:
        lines.append("(nenhuma atividade encontrada)")
    for act in activities:
        date = (act.get("start_date_local") or "")[:10]
        name = act.get("name") or act.get("type") or "?"
        moving = act.get("moving_time")
        h = f"{moving / 3600:.1f}h" if moving else "?"
        lines.append(f"- {date}: {name} ({act.get('type', '?')}, {h})")
    return "\n".join(lines)


def validate_and_apply(full_plan, upcoming, changes, today):
    applied, rejected = [], []
    n_add = n_remove = 0

    # indice upcoming -> posicao no full_plan (por identidade de objeto)
    id_to_pos = {id(w): pos for pos, w in enumerate(full_plan)}

    for ch in changes:
        if len(applied) >= MAX_CHANGES:
            rejected.append((ch, "limite de alteracoes atingido"))
            continue

        if ch.action in ("modify", "remove"):
            if ch.index is None or not (0 <= ch.index < len(upcoming)):
                rejected.append((ch, "index invalido")); continue
            target = upcoming[ch.index]
            target_date = datetime.date.fromisoformat(target["date"])
            if is_locked(target_date) or target_date <= today:
                rejected.append((ch, "data bloqueada (taper/prova/passado)")); continue
            if target["sport"] == "race":
                rejected.append((ch, "nunca mexer no dia da prova")); continue
            pos = id_to_pos[id(target)]

            if ch.action == "remove":
                if n_remove >= MAX_REMOVE:
                    rejected.append((ch, "limite de remocoes atingido")); continue
                full_plan[pos] = None  # marca para remover depois
                n_remove += 1
                applied.append((ch, f"removido: {target['date']} - {target['title']}"))
                continue

            # modify
            sport = ch.sport or target["sport"]
            if sport not in ALLOWED_SPORTS:
                rejected.append((ch, f"sport invalido: {sport}")); continue
            dur = ch.duration_h if ch.duration_h is not None else target["duration_h"]
            if dur is not None and sport in DURATION_CEILING_H and dur > DURATION_CEILING_H[sport]:
                rejected.append((ch, f"duracao acima do razoavel para {sport}")); continue
            before = f"{target['title']} ({target['duration_h'] or '?'}h)"
            full_plan[pos] = {
                **target,
                "title": ch.title or target["title"],
                "sport": sport,
                "description": ch.description or target["description"],
                "duration_h": dur,
                "source": "adapted",
            }
            applied.append((ch, f"modificado {target['date']}: {before} -> "
                                 f"{full_plan[pos]['title']} ({full_plan[pos]['duration_h'] or '?'}h)"))

        elif ch.action == "add":
            if n_add >= MAX_ADD:
                rejected.append((ch, "limite de adicoes atingido")); continue
            if not ch.date:
                rejected.append((ch, "sem data")); continue
            try:
                d = datetime.date.fromisoformat(ch.date)
            except ValueError:
                rejected.append((ch, "data invalida")); continue
            if is_locked(d) or d <= today or d > today + datetime.timedelta(days=ADAPT_WINDOW_DAYS):
                rejected.append((ch, "data fora da janela permitida")); continue
            sport = ch.sport or "other"
            if sport not in ALLOWED_SPORTS:
                rejected.append((ch, f"sport invalido: {sport}")); continue
            dur = ch.duration_h
            if dur is not None and sport in DURATION_CEILING_H and dur > DURATION_CEILING_H[sport]:
                rejected.append((ch, f"duracao acima do razoavel para {sport}")); continue
            full_plan.append({
                "date": ch.date, "title": ch.title or "Ajuste do coach",
                "sport": sport, "description": ch.description or "",
                "duration_h": dur, "distance_m": None, "source": "adapted",
            })
            n_add += 1
            applied.append((ch, f"adicionado {ch.date}: {ch.title or 'Ajuste do coach'}"))
        else:
            rejected.append((ch, "accao desconhecida"))

    new_plan = [w for w in full_plan if w is not None]
    new_plan.sort(key=lambda w: (w["date"], w["sport"] != "rest"))
    return new_plan, applied, rejected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    today = datetime.date.today()

    with open(PLAN_PATH, encoding="utf-8") as f:
        full_plan = json.load(f)

    window_end = (today + datetime.timedelta(days=ADAPT_WINDOW_DAYS)).isoformat()
    upcoming = [w for w in full_plan if today.isoformat() < w["date"] <= window_end]
    upcoming = [w for w in upcoming if not is_locked(datetime.date.fromisoformat(w["date"]))]

    if not upcoming:
        print("Janela de adaptacao inteiramente bloqueada (taper/prova/recuperacao) - nada a fazer.")
        return

    notes_text = ""
    if os.path.exists(NOTES_PATH):
        notes_text = open(NOTES_PATH, encoding="utf-8").read()

    activities = []
    api_key = os.environ.get("INTERVALS_API_KEY")
    athlete_id = os.environ.get("INTERVALS_ATHLETE_ID")
    if api_key and athlete_id:
        oldest = (today - datetime.timedelta(days=7)).isoformat()
        activities = fetch_activities(athlete_id, api_key, oldest, today.isoformat())
    else:
        print("aviso: sem INTERVALS_API_KEY/INTERVALS_ATHLETE_ID - a adaptar sem dados reais de execucao.")

    adherence_text = summarize_adherence(activities, upcoming, today)
    prompt = build_prompt(upcoming, adherence_text, notes_text, today)

    if not os.environ.get("ANTHROPIC_API_KEY") and not args.dry_run:
        print("ERRO: define ANTHROPIC_API_KEY no ambiente.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[dry-run] sem ANTHROPIC_API_KEY definido - a mostrar so o prompt que seria enviado:\n")
        print(prompt)
        return

    result = call_claude(prompt)
    changes = [ChangeOp(c.model_dump()) for c in result.changes]

    new_plan, applied, rejected = validate_and_apply(full_plan, upcoming, changes, today)

    print(f"Raciocinio do coach: {result.reasoning}\n")
    print(f"{len(applied)} alteracoes aceites, {len(rejected)} rejeitadas pelas guardrails.")
    for ch, msg in applied:
        print(f"  OK: {msg}")
    for ch, msg in rejected:
        print(f"  rejeitado ({msg}): {ch.action} index={ch.index} date={ch.date}")

    if args.dry_run:
        print("\n[dry-run] plan.json e CHANGELOG.md nao foram escritos.")
        return

    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(new_plan, f, ensure_ascii=False, indent=2)

    entry = [f"## {today.isoformat()}", "", result.reasoning, ""]
    if applied:
        entry.append("Alteracoes aplicadas:")
        entry += [f"- {msg}" for _, msg in applied]
    else:
        entry.append("Sem alteracoes esta semana.")
    if rejected:
        entry.append("")
        entry.append("Propostas rejeitadas pelas guardrails (para auditoria):")
        entry += [f"- {msg}" for _, msg in rejected]
    entry.append("")

    prior = ""
    if os.path.exists(CHANGELOG_PATH):
        prior = open(CHANGELOG_PATH, encoding="utf-8").read()
    else:
        prior = "# Historial de ajustes automaticos ao plano\n\n"
    with open(CHANGELOG_PATH, "w", encoding="utf-8") as f:
        f.write(prior + "\n".join(entry) + "\n")


if __name__ == "__main__":
    main()
