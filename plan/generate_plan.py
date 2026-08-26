#!/usr/bin/env python3
"""
Gera o plano de treino de triatlo (hoje -> 31/dez) a partir do historico real
de treinos (history_workouts.csv, export TrainingPeaks) e escreve:
  - plan/plan.json   (fonte de verdade, consumido por scripts/sync_to_intervals.py)
  - plan/plan.csv     (leitura humana)
  - plan/PLAN.md       (resumo por fase)

Logica geral:
  1. O bloco "build + taper + corrida" de 27/ago/2025 -> 17/out/2025 (a prova do
     ano passado, exatamente 52 semanas / 364 dias antes da prova deste ano) e
     copiado e deslocado +364 dias. Como 364 e multiplo de 7, os dias da semana
     mantem-se identicos (treino longo continua ao sabado, etc.) e a "semana de
     prova" cai exatamente na semana da prova de 2026.
  2. O dia da corrida antiga (18/out/2025, splits de bike/swim/run) e substituido
     por um unico evento de prova: "IronMan 70.3 Cascais".
  3. As 4 semanas seguintes (18/out -> 15/nov) sao uma progressao de recuperacao
     escrita de raiz (o historico nao tem dados aqui - o atleta parou por completo
     no ano passado; desta vez o objetivo e continuar a treinar).
  4. O bloco de manutencao/pre-epoca de 17/nov/2025 -> 31/dez/2025 e copiado e
     deslocado da mesma forma (+364 dias) para cobrir 16/nov -> 30/dez/2026.
  5. E acrescentada 1x/semana uma sessao de "Mobilidade / Rolo de espuma"
     (ausente no historico) e mantido o padrao existente de Forca 1-2x/semana e
     "Treino com a PT".
"""
import csv
import datetime
import json
import pathlib

HERE = pathlib.Path(__file__).parent
CSV_PATH = HERE / "history_workouts.csv"
TODAY = datetime.date(2026, 8, 26)
RACE_DATE = datetime.date(2026, 10, 17)
PLAN_END = datetime.date(2026, 12, 31)

OLD_RACE_DATE = datetime.date(2025, 10, 18)
SHIFT_DAYS = (RACE_DATE - OLD_RACE_DATE).days  # 364 -> preserves weekday
assert SHIFT_DAYS % 7 == 0, "shift must preserve weekday alignment"

# Titulos de linhas administrativas do CSV original que nao sao treinos
ADMIN_TITLES = {"Data limite pagamento Coach"}

TYPE_MAP = {
    "Run": "run",
    "Bike": "bike",
    "Swim": "swim",
    "Strength": "strength",
    "Custom": "pt",          # "Treino com a PT"
    "Day Off": "rest",
    "Other": "other",
    "Rowing": "other",
}


def load_history():
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


DEFAULT_DURATION_H = {
    "run": 0.75, "bike": 1.5, "swim": 0.75, "strength": 0.75,
    "pt": 1.0, "other": 0.5, "mobility": 0.4,
}


def estimate_duration(title, sport):
    """Quando o CSV nao tem duracao planeada, estima um valor razoavel."""
    import re
    m = re.search(r"(\d+)\s*kms?", title, re.IGNORECASE)
    if m and sport == "run":
        km = int(m.group(1))
        return round(km * 6.0 / 60.0, 2)  # ~6'/km, conservador para LSD
    return DEFAULT_DURATION_H.get(sport)


def to_workout(row, new_date):
    dur = row["PlannedDuration"]
    try:
        duration_h = round(float(dur), 3) if dur else None
    except ValueError:
        duration_h = None
    dist = row["PlannedDistanceInMeters"]
    try:
        distance_m = float(dist) if dist else None
    except ValueError:
        distance_m = None
    sport = TYPE_MAP.get(row["WorkoutType"], "other")
    if duration_h is None and sport != "rest":
        duration_h = estimate_duration(row["Title"], sport)
    return {
        "date": new_date.isoformat(),
        "title": row["Title"],
        "sport": sport,
        "description": row["WorkoutDescription"],
        "duration_h": duration_h,
        "distance_m": distance_m,
        "source": "history",
    }


def copy_block(rows, start, end):
    """Copy rows with start <= date <= end (inclusive), shifted by SHIFT_DAYS."""
    out = []
    for row in rows:
        d = row["WorkoutDay"]
        if not d:
            continue
        date = datetime.date.fromisoformat(d)
        if not (start <= date <= end):
            continue
        if row["Title"] in ADMIN_TITLES:
            continue
        new_date = date + datetime.timedelta(days=SHIFT_DAYS)
        out.append(to_workout(row, new_date))
    return out


def build_block1(rows):
    """Build + taper, dia seguinte a hoje ate ao dia antes da prova."""
    start = datetime.date(2025, 8, 28)  # -> 2026-08-27 (amanha)
    end = datetime.date(2025, 10, 17)   # -> 2026-10-16 (vespera da prova)
    return copy_block(rows, start, end)


def build_race_event():
    return {
        "date": RACE_DATE.isoformat(),
        "title": "IronMan 70.3 Cascais",
        "sport": "race",
        "description": "Prova: 1.9km natacao + 90km bike + 21.1km corrida.",
        "duration_h": None,
        "distance_m": None,
        "source": "race",
    }


def build_recovery_block():
    """18/out -> 15/nov/2026: 4 semanas de progressao pos-prova (sem historico)."""
    out = []

    def add(date, title, sport, desc, dur):
        out.append({
            "date": date.isoformat(), "title": title, "sport": sport,
            "description": desc, "duration_h": dur, "distance_m": None,
            "source": "recovery-plan",
        })

    d0 = RACE_DATE  # sabado da prova

    # Semana 1 (18-24 out): recuperacao total, so aerobio muito leve
    add(d0 + datetime.timedelta(days=1), "Recovery Day", "rest",
        "Recuperacao pos-prova: pernas para cima, hidratar, sem treino.", None)
    add(d0 + datetime.timedelta(days=2), "Caminhada + Mobilidade", "mobility",
        "Caminhada leve 20-30' + mobilidade articular suave.", 0.5)
    add(d0 + datetime.timedelta(days=3), "Swim muito leve", "swim",
        "Nadar solto sem intensidade, foco em soltar os ombros.", 0.4)
    add(d0 + datetime.timedelta(days=4), "Recovery Day", "rest",
        "Descanso total.", None)
    add(d0 + datetime.timedelta(days=5), "Zn1 - Bike regenerativa", "bike",
        "Rolar muito facil em Zn1, percurso plano.", 0.75)
    add(d0 + datetime.timedelta(days=6), "Mobilidade / Rolo de espuma", "mobility",
        "Rolo de espuma + alongamentos 20-25'.", 0.4)
    add(d0 + datetime.timedelta(days=7), "AE1 - Run muito leve", "run",
        "Corrida muito leve em Zn1, piso macio, sem pressa nenhuma.", 0.4)

    # Semana 2 (25-31 out): reintroducao leve
    w2 = d0 + datetime.timedelta(days=7)
    add(w2 + datetime.timedelta(days=1), "Zn1/2 - Bike facil", "bike",
        "Rolar facil Zn1/Zn2, percurso plano.", 1.0)
    add(w2 + datetime.timedelta(days=2), "Swim tecnica", "swim",
        "Foco 100% em tecnica, sem intensidade. Drills.", 0.5)
    add(w2 + datetime.timedelta(days=3), "Strength - retoma leve", "strength",
        "Forca funcional leve, foco em mobilidade e core, cargas baixas.", 0.75)
    add(w2 + datetime.timedelta(days=4), "Recovery Day", "rest", "Descanso.", None)
    add(w2 + datetime.timedelta(days=5), "30' Run - Zn2", "run",
        "Corrida facil em Zn2, piso soft.", 0.5)
    add(w2 + datetime.timedelta(days=6), "Mobilidade / Rolo de espuma", "mobility",
        "Rolo de espuma + alongamentos 20-25'.", 0.4)
    add(w2 + datetime.timedelta(days=7), "Base Builder (Heart Rate)", "bike",
        "Rolar Zn2, percurso plano a ondulado, minimo 50% do tempo em Zn2.", 1.5)

    # Semana 3 (1-7 nov): a construir a base de novo
    w3 = w2 + datetime.timedelta(days=7)
    add(w3 + datetime.timedelta(days=1), "Base Builder (Heart Rate)", "bike",
        "Rolar Zn2, percurso plano a ondulado, minimo 50% do tempo em Zn2.", 1.5)
    add(w3 + datetime.timedelta(days=2), "Swim Z2", "swim",
        "Series de 100-200 em Zn2, tecnica limpa.", 0.75)
    add(w3 + datetime.timedelta(days=3), "Treino com a PT", "pt",
        "Sessao com o personal trainer.", 1.0)
    add(w3 + datetime.timedelta(days=4), "40' Run @Zn2", "run",
        "Corrida em Zn2, piso soft e cadencia +88.", 0.67)
    add(w3 + datetime.timedelta(days=5), "Base Builder (Power)", "bike",
        "Rolar Zn2, minimo 50% do tempo em zona 2 de potencia.", 1.75)
    add(w3 + datetime.timedelta(days=6), "Mobilidade / Rolo de espuma", "mobility",
        "Rolo de espuma + alongamentos 20-25'.", 0.4)
    add(w3 + datetime.timedelta(days=7), "50' Run - Zn2", "run",
        "Corrida em Zn2 com piso soft.", 0.83)

    # Semana 4 (8-15 nov): aproximacao ao volume de manutencao
    w4 = w3 + datetime.timedelta(days=7)
    add(w4 + datetime.timedelta(days=1), "Base Builder (Heart Rate)", "bike",
        "Rolar Zn2, minimo 50% do tempo em zona 2.", 1.75)
    add(w4 + datetime.timedelta(days=2), "Swim - palas", "swim",
        "Aquecimento + 20' Zn2 com palas + easy.", 0.6)
    add(w4 + datetime.timedelta(days=3), "Strength", "strength",
        "Forca geral, retoma de cargas normais.", 0.75)
    add(w4 + datetime.timedelta(days=4), "Recovery Day", "rest", "Descanso.", None)
    add(w4 + datetime.timedelta(days=5), "Base Builder (Power)", "bike",
        "Rolar Zn2, minimo 50% do tempo em zona 2 de potencia.", 1.75)
    add(w4 + datetime.timedelta(days=6), "Mobilidade / Rolo de espuma", "mobility",
        "Rolo de espuma + alongamentos 20-25'.", 0.4)
    add(w4 + datetime.timedelta(days=7), "60' Run - Zn2", "run",
        "Corrida em Zn2 com piso soft.", 1.0)

    return out


def build_block2(rows):
    start = datetime.date(2025, 11, 17)
    end = datetime.date(2025, 12, 31)
    return copy_block(rows, start, end)


def add_weekly_mobility(workouts, start, end):
    """Garante 1x/semana Mobilidade/Rolo aos domingos onde ainda nao exista."""
    have_sundays = {
        w["date"] for w in workouts
        if w["sport"] == "mobility"
    }
    d = start
    while d <= end:
        if d.weekday() == 6 and d.isoformat() not in have_sundays:  # domingo
            workouts.append({
                "date": d.isoformat(),
                "title": "Mobilidade / Rolo de espuma",
                "sport": "mobility",
                "description": "Rolo de espuma + alongamentos, 20-25'.",
                "duration_h": 0.4,
                "distance_m": None,
                "source": "added-mobility",
            })
        d += datetime.timedelta(days=1)


def build_year_end_tail():
    return [{
        "date": PLAN_END.isoformat(),
        "title": "Descanso - Fim de ano",
        "sport": "rest",
        "description": "Fecho do plano de 2026. Descanso.",
        "duration_h": None,
        "distance_m": None,
        "source": "recovery-plan",
    }]


def dedupe_titles(workouts):
    """scripts/sync_to_intervals.py identifica cada treino por (data, titulo) --
    se dois treinos no mesmo dia tiverem o mesmo titulo generico (ex: duas
    entradas "Running" no historico original, que eram treinos diferentes mas
    ficaram com o mesmo nome), o sync nao os consegue distinguir e cria
    duplicados. Aqui desambiguamos, acrescentando " (2)", " (3)", etc.
    """
    from collections import Counter
    seen = Counter()
    for w in workouts:
        key = (w["date"], w["title"])
        seen[key] += 1
        if seen[key] > 1:
            w["title"] = f"{w['title']} ({seen[key]})"


def main():
    rows = load_history()

    workouts = []
    workouts += build_block1(rows)
    workouts.append(build_race_event())
    workouts += build_recovery_block()
    workouts += build_block2(rows)

    # o bloco 2 termina em 2026-12-30; garante que 31/dez fica coberto
    covered_dates = {w["date"] for w in workouts}
    if PLAN_END.isoformat() not in covered_dates:
        workouts += build_year_end_tail()

    add_weekly_mobility(workouts, datetime.date(2026, 8, 27), PLAN_END)

    # so o intervalo pedido: amanha -> 31/dez, sem duplicar o dia de hoje
    workouts = [w for w in workouts if TODAY < datetime.date.fromisoformat(w["date"]) <= PLAN_END]
    workouts.sort(key=lambda w: (w["date"], w["sport"] != "rest"))
    dedupe_titles(workouts)

    HERE.mkdir(exist_ok=True)
    with open(HERE / "plan.json", "w", encoding="utf-8") as f:
        json.dump(workouts, f, ensure_ascii=False, indent=2)

    with open(HERE / "plan.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "title", "sport", "description", "duration_h", "distance_m"])
        for wk in workouts:
            w.writerow([wk["date"], wk["title"], wk["sport"], wk["description"],
                        wk["duration_h"] or "", wk["distance_m"] or ""])

    write_markdown(workouts)

    print(f"Gerados {len(workouts)} treinos: {workouts[0]['date']} -> {workouts[-1]['date']}")


PHASES = [
    (datetime.date(2026, 8, 27), datetime.date(2026, 9, 20), "Build/Especifico"),
    (datetime.date(2026, 9, 21), datetime.date(2026, 10, 16), "Taper"),
    (datetime.date(2026, 10, 17), datetime.date(2026, 10, 17), "PROVA - IronMan 70.3 Cascais"),
    (datetime.date(2026, 10, 18), datetime.date(2026, 11, 15), "Recuperacao pos-prova"),
    (datetime.date(2026, 11, 16), PLAN_END, "Manutencao / base sem objetivo definido"),
]


def phase_for(date):
    for start, end, name in PHASES:
        if start <= date <= end:
            return name
    return "?"


def write_markdown(workouts):
    from collections import defaultdict
    weekly = defaultdict(lambda: defaultdict(float))
    weekly_phase = {}
    for w in workouts:
        d = datetime.date.fromisoformat(w["date"])
        wk = d.isocalendar()[:2]
        weekly[wk][w["sport"]] += w["duration_h"] or 0.0
        weekly_phase[wk] = phase_for(d)

    lines = [
        "# Plano de treino - ate 31/dez/2026",
        "",
        f"Gerado a partir do historico real de treinos e da prova "
        f"**IronMan 70.3 Cascais em {RACE_DATE.isoformat()}**.",
        "",
        "## Fases",
        "",
    ]
    for start, end, name in PHASES:
        lines.append(f"- **{name}**: {start.isoformat()} -> {end.isoformat()}")
    lines += ["", "## Volume semanal planeado (horas)", "",
              "| Semana | Fase | Bike | Run | Swim | Forca | PT | Mobilidade | Total |",
              "|---|---|---|---|---|---|---|---|---|"]
    for wk in sorted(weekly.keys()):
        s = weekly[wk]
        total = sum(s.values())
        lines.append(
            f"| {wk[0]}-W{wk[1]:02d} | {weekly_phase[wk]} | {s.get('bike',0):.1f} | "
            f"{s.get('run',0):.1f} | {s.get('swim',0):.1f} | {s.get('strength',0):.1f} | "
            f"{s.get('pt',0):.1f} | {s.get('mobility',0):.1f} | {total:.1f} |"
        )
    (HERE / "PLAN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
