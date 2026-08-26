# Coach — plano de treino para o IronMan 70.3 Cascais 2026

Plano de triatlo gerado a partir do teu histórico real de treinos, cobrindo
**27 de agosto até 31 de dezembro de 2026**, com o **IronMan 70.3 Cascais a
17 de outubro de 2026** como objetivo principal, seguido de manutenção/base
sem objetivo definido até ao fim do ano.

Ficheiros:

- `plan/history_workouts.csv` — o teu export com o histórico de treinos (usado como referência/template).
- `plan/generate_plan.py` — gera o plano a partir do histórico.
- `plan/plan.json` — **fonte de verdade** do plano (o que vai ser sincronizado com o intervals.icu).
- `plan/plan.csv` — o mesmo plano em CSV, para leres/editares facilmente numa folha de cálculo.
- `plan/PLAN.md` — resumo das fases e do volume semanal planeado.
- `scripts/sync_to_intervals.py` — sincroniza `plan/plan.json` com o calendário do intervals.icu.
- `.github/workflows/sync-intervals.yml` — corre esse script automaticamente todas as segundas-feiras (e sempre que fazes push a `plan/plan.json`).

## Como foi feito o plano

- **27/ago → 16/out**: é uma cópia (com as datas ajustadas) do bloco de build +
  taper que já fizeste entre 27/ago/2025 e 17/out/2025 — exatamente 52 semanas
  antes da tua última prova, por isso os dias da semana coincidem
  perfeitamente (treino longo ao sábado continua ao sábado, etc.). É um plano
  que já foi validado pelo teu treinador no ano passado para o mesmo tipo de
  objetivo.
- **17/out**: dia da prova.
- **18/out → 15/nov**: 4 semanas de recuperação progressiva escritas de raiz
  (o ano passado simplesmente pararam de treinar depois da prova; desta vez
  disseste que queres continuar, por isso construí uma rampa de volta ao
  treino em vez de um vazio).
- **16/nov → 31/dez**: cópia do bloco de manutenção/pré-época que fizeste em
  Nov-Dez 2025 — foi exatamente a mesma situação (sem objetivo definido logo
  a seguir a uma prova), com força 1-2x/semana e sessões com a PT.
- Em todo o plano foi acrescentada **1x/semana uma sessão de Mobilidade / Rolo
  de espuma** (20-25'), que não existia no teu histórico e que disseste sentir
  falta.

Vê `plan/PLAN.md` para o detalhe fase a fase e o volume semanal.

**O plano é só o ponto de partida — edita `plan/plan.json` ou `plan/plan.csv`
à vontade.** Sempre que fizeres push de uma alteração a esse ficheiro, o
workflow sincroniza automaticamente as diferenças para o intervals.icu.

---

## Passo a passo para automatizar tudo

### 1. Criar conta no intervals.icu

1. Vai a [intervals.icu](https://intervals.icu) e cria uma conta (podes usar
   login Google/Strava/Garmin).
2. Em **Settings → Connections**, liga a tua conta **Garmin Connect**
   (autoriza o acesso). Isto é o que permite ao intervals.icu ler as tuas
   atividades do Garmin e, mais importante para ti, **enviar os treinos
   planeados de volta para o calendário do teu relógio Garmin**.
3. Ainda em **Settings**, confirma que a opção de sincronizar/enviar treinos
   planeados para o Garmin está ativa (normalmente chamada algo como *"Push
   workouts to Garmin"* / sincronização de calendário). Sem isto os treinos
   ficam só no site, não chegam ao relógio.

### 2. Obter a tua API Key e Athlete ID

1. Em **Settings → Developer Settings** no intervals.icu, gera uma **API
   Key**.
2. O teu **Athlete ID** aparece no URL do teu perfil (algo como
   `i123456`) ou nas mesmas Developer Settings.
3. Guarda os dois — vais precisar deles no próximo passo. Nunca os partilhes
   nem os cometas no código.

### 3. Configurar os secrets no GitHub

No repositório GitHub (`AntonioMSRA/Coach`):

1. **Settings → Secrets and variables → Actions → New repository secret**
2. Cria dois secrets:
   - `INTERVALS_API_KEY` → a API key do passo 2.
   - `INTERVALS_ATHLETE_ID` → o teu athlete id (ex: `i123456`).

Estes valores ficam encriptados pelo GitHub e só são visíveis dentro das
Actions deste repositório — não aparecem em lado nenhum do código.

### 4. Testar manualmente antes de confiares na automação

O script nunca foi corrido contra a API real neste ambiente (não tinha
acesso de rede ao intervals.icu para verificar), por isso o primeiro teste
deve ser feito por ti, com cuidado:

1. No GitHub, vai a **Actions → Sync training plan to intervals.icu → Run
   workflow**.
2. Corre primeiro com **dry_run = true** — isto só mostra nos logs o que
   *seria* criado, sem tocar em nada.
3. Confirma nos logs que as datas e os nomes fazem sentido.
4. Corre de novo com **dry_run = false**. Isto vai criar os ~172 treinos no
   teu calendário do intervals.icu.
5. Vai ao intervals.icu → Calendar e confirma que os treinos aparecem nos
   dias certos.
6. Confirma no teu Garmin Connect / relógio que os treinos planeados chegaram
   (pode demorar alguns minutos a sincronizar).

Se algum passo falhar, os logs da Action mostram o erro exato devolvido pela
API (por exemplo um campo com nome diferente) — nesse caso confirma o nome
certo do campo em https://intervals.icu/api-docs.html e ajusta
`scripts/sync_to_intervals.py`.

### 5. Automação recorrente

Depois do primeiro teste manual correr bem, já não precisas de fazer nada:

- O workflow corre **automaticamente todas as segundas-feiras às 6h UTC**.
- Também corre sempre que fizeres `git push` a uma alteração em
  `plan/plan.json`.
- É idempotente: nunca duplica treinos (verifica o que já existe por
  data+nome antes de criar) e nunca mexe em dias passados.

### 6. Como ajustar o plano no futuro

- Para pequenos ajustes (mudar um treino, mover um dia): edita
  `plan/plan.json` diretamente (ou `plan/plan.csv` numa folha de cálculo e
  depois converte) e faz commit/push — a sincronização atualiza-se sozinha.
- Para regenerar tudo de raiz (ex: mudar a data da prova): edita as
  constantes no topo de `plan/generate_plan.py` (`RACE_DATE`, `PLAN_END`) e
  corre `python3 plan/generate_plan.py`, depois faz commit dos ficheiros
  gerados.
- Se quiseres analisar como estás a treinar de facto e ajustar o plano com
  base nisso (o que fizeste vs. o que estava planeado), pede-me nesta
  conversa — o intervals.icu também expõe as tuas atividades reais pela
  mesma API (`GET /athlete/{id}/activities`), o que dá para comparar carga
  planeada vs. executada e adaptar as próximas semanas.
