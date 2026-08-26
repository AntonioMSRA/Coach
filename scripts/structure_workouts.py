#!/usr/bin/env python3
"""
Converte as descricoes em texto livre dos treinos de bike/corrida em
plan/plan.json para a sintaxe de treino estruturado do intervals.icu, para
que o relogio consiga guiar o atleta durante o treino (avisos por troço,
zonas alvo), em vez de mostrar so um titulo/duracao.

So mexe em sport in ("run", "bike", "swim") -- forca/mobilidade/PT ficam
como texto livre (nao sao "zone-based"). Sintaxe
confirmada manualmente num treino real (ver commits "Retry structured
workout..." e "Add blank lines between workout sections..."):

  Warmup
  - 20m Z2 HR

  Main Set 4x
  - 5m Z3 HR
  - 2m Z1 HR

  Cooldown
  - 10m Z1 HR

Regras chave (aprendidas por tentativa/erro + docs da comunidade, ja que o
intervals.icu esta bloqueado neste ambiente):
  - Cabecalhos de seccao (Warmup / Main Set Nx / Cooldown) NAO levam "-" e
    precisam de uma linha em branco antes, senao colam-se ao passo anterior.
  - Cada passo leva "-", duracao (h/m/s) e alvo.
  - Zonas (Z1..Z7) precisam de sufixo explicito "HR" ou "Power", senao a
    API assume potencia por omissao (mesmo em corrida).
  - Repeticoes: "<Nome da seccao> Nx" antes do bloco a repetir.

Idempotente: salta treinos cuja descricao ja parece estruturada (contem uma
linha a comecar por "- ").

Requer ANTHROPIC_API_KEY. Uso:
  python3 scripts/structure_workouts.py            # aplica
  python3 scripts/structure_workouts.py --dry-run   # so mostra
  python3 scripts/structure_workouts.py --limit 5   # so os primeiros N (testar)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(__file__)
PLAN_PATH = os.path.join(HERE, "..", "plan", "plan.json")

ZONE_TARGET = {"run": "HR", "bike": "Power", "swim": "HR"}
SPORT_NAME_PT = {"run": "corrida", "bike": "bicicleta", "swim": "natação"}

SYNTAX_RULES = """Sintaxe de treino estruturado do intervals.icu (CONFIRMADA a funcionar):

- Um treino tem seccoes: "Warmup", "Main Set" (ou "Main Set Nx" se repetir),
  "Cooldown". Nomes de seccao NAO levam "-" a frente, e tem de haver uma
  LINHA EM BRANCO antes de cada cabecalho de seccao (senao cola-se ao passo
  anterior e nao funciona).
- Cada passo dentro de uma seccao comeca com "- " e tem EXATAMENTE UMA
  quantidade (duracao OU distancia) + alvo. Pode ter texto livre curto em
  portugues ANTES dessa quantidade, como pista/legenda (ex:
  "- aquecimento 10m Z1 HR").
- CUIDADO CRITICO: no intervals.icu, um numero colado a "m" (ex: "200m",
  "400m") e SEMPRE lido como MINUTOS, nunca como metros -- e isto aplica-se
  a QUALQUER numero+"m" na linha do passo, incluindo dentro do texto livre
  da legenda, nao so no valor "oficial" do passo (ex: "- 200m forte 30s Z5
  HR" e uma ARMADILHA: o parser le tanto os "200m" da legenda como MINUTOS
  como os "30s" -- resultando num passo de duracao absurda). Regras:
    * Para uma distancia em metros, usa SEMPRE o sufixo "mtr", nunca "m"
      sozinho (ex: "- 200mtr Z5 HR", nunca "- 200m Z5 HR").
    * Se precisares de mencionar uma distancia em metros dentro do texto
      livre da legenda (ex: repeticoes de pista "200m forte / 200m leve"),
      escreve por extenso "200 metros" (com espaco, nunca "200m" colado) ou
      usa "mtr" -- nunca deixes um numero colado a "m" em lado nenhum da
      linha, mesmo que nao seja o valor do passo.
    * Cada passo tem UM SO numero de quantidade (a duracao real do passo,
      em h/m/s, OU a distancia em mtr/km) -- nao repitas a mesma
      informacao (distancia e duracao) duas vezes no mesmo passo.
- Alvo: usa zonas "Z1" a "Z7" SEMPRE seguidas de "{zone_suffix}" (ex: "Z3 {zone_suffix}"),
  nunca uma zona sozinha (fica ambiguo/errado).
- Repeticao: escreve o cabecalho da seccao como "Main Set Nx" (ex:
  "Main Set 4x") e por baixo os passos que compoem UMA repeticao (a API
  repete-os N vezes sozinha - nao repitas tu os passos no texto).
- Nao uses ranges tipo "Z1-Z2" num so passo -- usa "ramp Z1-Z2" se for
  mesmo uma rampa gradual, ou escolhe uma zona so.

Exemplo real validado (corrida, 20' aquecimento + 4x(5' zona3 / 2' zona1) + 10' cooldown):

Warmup
- 20m Z2 HR

Main Set 4x
- 5m Z3 HR
- 2m Z1 HR

Cooldown
- 10m Z1 HR

Exemplo real validado (corrida em pista, repeticoes por distancia -- repara
que a legenda usa "200 metros" por extenso e o passo usa a duracao real do
esforco em segundos, NUNCA "200m"):

Warmup
- aquecimento 15m Z2 HR

Main Set 10x
- 200 metros forte 40s Z5 HR
- recuperacao 60s Z1 HR

Cooldown
- 5m Z1 HR
"""


def already_structured(description):
    return any(line.strip().startswith("- ") for line in (description or "").splitlines())


def build_prompt(workout):
    sport = workout["sport"]
    zone_suffix = ZONE_TARGET[sport]
    swim_note = (
        "\nEste treino e de natacao: os passos sao normalmente por distancia "
        "em vez de duracao, porque e assim que a descricao original os da "
        "(series de piscina). CUIDADO: no intervals.icu \"m\" significa "
        "MINUTOS, nao metros -- para distancia em metros tens de usar "
        "\"mtr\" (ex: \"- 100mtr Z2 HR\", \"- 50mtr Z4 HR\"), NUNCA \"100m\" "
        "(isso seria lido como 100 minutos!). Repeticoes de series (ex: "
        "\"8x50\") continuam a usar \"Main Set 8x\" + um passo "
        "\"- 50mtr Z_ HR\" por baixo, tal como nos outros desportos.\n"
        if sport == "swim" else ""
    )
    return f"""{SYNTAX_RULES.format(zone_suffix=zone_suffix)}
{swim_note}
Converte este treino de {SPORT_NAME_PT[sport]}
para essa sintaxe, usando SEMPRE "{zone_suffix}" depois de cada zona (nunca
outro tipo de alvo). A duracao/distancia total dos passos deve somar
aproximadamente o total dado.

Titulo: {workout['title']}
Duracao total: {workout['duration_h']} horas
{"Distancia total: " + str(workout['distance_m']) + " metros" if workout.get('distance_m') else ""}
Descricao original: {workout['description'] or '(sem descricao -- usa o titulo e o teu bom senso de treinador para decidir a zona, ex: "Regenerativo"/"Zn1"=Z1, "LSD"/"Base"=Z2, "Tempo"=Z3, "Threshold"/"Limiar"=Z4, "VO2"=Z5+)'}

Responde APENAS com o texto estruturado (sem explicacoes, sem markdown ```,
sem comentarios). Se o treino for um esforco continuo sem intervalos, usa
so uma seccao "Warmup" com um unico passo cobrindo a duracao/distancia toda
-- nao inventes uma estrutura que a descricao original nao tem.
"""


def call_claude(prompt):
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    # tira eventuais vedacoes de codigo, por seguranca
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("text"):
            text = text[4:].strip()
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sport", action="append", choices=sorted(ZONE_TARGET),
                     help="restringe a um ou mais desportos (repete a opcao para varios); por omissao todos")
    ap.add_argument("--force", action="store_true",
                     help="reconverte mesmo treinos que ja parecem estruturados (ignora already_structured)")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERRO: define ANTHROPIC_API_KEY no ambiente.", file=sys.stderr)
        sys.exit(1)

    with open(PLAN_PATH, encoding="utf-8") as f:
        plan = json.load(f)

    sports = set(args.sport) if args.sport else set(ZONE_TARGET)
    targets = [
        w for w in plan
        if w["sport"] in sports and (args.force or not already_structured(w["description"]))
    ]
    if args.limit:
        targets = targets[:args.limit]

    print(f"{len(targets)} treinos a estruturar (de um total de {len(plan)}).")

    converted, failed = 0, 0
    for w in targets:
        prompt = build_prompt(w)
        try:
            structured = call_claude(prompt)
        except Exception as e:  # noqa: BLE001 -- reportar e continuar os outros
            print(f"FALHOU: {w['date']} - {w['title']}: {e}", file=sys.stderr)
            failed += 1
            continue
        if not structured:
            print(f"vazio, a saltar: {w['date']} - {w['title']}")
            continue
        print(f"--- {w['date']} - {w['title']} ({w['sport']}) ---")
        print(structured)
        print()
        if not args.dry_run:
            w["description"] = structured
        converted += 1

    print(f"\nResumo: {converted} convertidos, {failed} falharam.")

    if not args.dry_run and converted:
        with open(PLAN_PATH, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print("plan.json atualizado.")


if __name__ == "__main__":
    main()
