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
- `plan/athlete_input.md` — **escreve aqui** notas para o coach automático (dores, viagens, cansaço, boa forma). É lido todos os dias antes de qualquer ajuste.
- `plan/CHANGELOG.md` — criado automaticamente na primeira vez que o coach ajustar algo. Histórico, dia a dia, do que mudou e porquê.
- `scripts/adapt_plan.py` — todos os dias, compara o que treinaste de facto (via intervals.icu) com o que estava planeado + as tuas notas, e propõe pequenos ajustes às próximas ~2 semanas usando a API da Anthropic (Claude). Tem regras fixas (guardrails) que travam qualquer alteração fora do razoável — ver secção "Como funciona o ajuste automático" abaixo.
- `scripts/sync_to_intervals.py` — sincroniza `plan/plan.json` (já ajustado) com o calendário do intervals.icu — cria, atualiza e remove eventos conforme necessário.
- `.github/workflows/sync-intervals.yml` — corre os dois scripts acima automaticamente todos os dias de manhã (e sempre que fazes push a `plan/plan.json`).

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

## Como funciona o ajuste automático

Todos os dias de manhã, antes de sincronizar com o intervals.icu, o
workflow corre `scripts/adapt_plan.py`, que:

1. Vai buscar ao intervals.icu o que treinaste **de facto** nos últimos 7
   dias e compara com o que estava planeado.
2. Vai buscar também os teus registos de **Wellness** (fadiga, sono, stress,
   motivação, dores) que preenches diretamente no site/telemóvel do
   intervals.icu — é aí que deves registar "como te sentes", não precisas de
   nenhuma app nova.
3. Lê as tuas notas em `plan/athlete_input.md`.
4. Pede a Claude (a IA da Anthropic) para propor ajustes pequenos e
   conservadores às **próximas ~2 semanas** — nunca ao plano todo.
5. Cada proposta passa por regras fixas antes de ser aceite: no máximo 10
   alterações por corrida do ajuste, nunca em datas passadas, nunca durante o taper /
   semana de prova / primeira semana pós-prova (17/set → 24/out fica sempre
   intocável), nunca no próprio dia da prova, e a duração de qualquer treino
   tem um teto razoável por modalidade. Se não houver motivo para mudar
   nada — que vai ser a maioria dos dias — a lista de alterações fica
   vazia, e é suposto ser assim.
6. Escreve sempre uma entrada em `plan/CHANGELOG.md` a explicar o que
   mudou (ou que não mudou nada) e porquê, para leres quando quiseres.
   Se discordares de um ajuste, o histórico do Git permite reverter
   (`git revert`) o commit desse dia.

Isto é heurístico, não uma bola de cristal — para qualquer coisa fora do
comum (lesão a sério, mudança de objetivo, etc.) fala comigo diretamente
nesta conversa.

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

### 2. Obter a tua API Key e Athlete ID do intervals.icu

1. Em **Settings → Developer Settings** no intervals.icu, gera uma **API
   Key**.
2. O teu **Athlete ID** aparece no URL do teu perfil (algo como
   `i123456`) ou nas mesmas Developer Settings.
3. Guarda os dois — vais precisar deles no próximo passo. Nunca os partilhes
   nem os cometas no código.

### 2b. Obter uma API Key da Anthropic (para o ajuste automático)

Isto é o que permite ao robô "pensar" sobre os teus dias em vez de só copiar
um plano fixo.

1. Vai a [console.anthropic.com](https://console.anthropic.com), cria conta
   se ainda não tiveres, e em **Settings → API Keys** cria uma nova chave.
2. Vais precisar de ter crédito associado à conta (a Anthropic pede cartão
   ou compra de crédito pré-pago). O custo real disto é muito baixo — cada
   ajuste diário usa poucos milhares de tokens, tipicamente cêntimos por
   mês, não euros.
3. Guarda a chave — só é mostrada uma vez.

### 3. Configurar os secrets no GitHub

No repositório GitHub (`AntonioMSRA/Coach`):

1. **Settings → Secrets and variables → Actions → New repository secret**
2. Cria três secrets:
   - `INTERVALS_API_KEY` → a API key do passo 2.
   - `INTERVALS_ATHLETE_ID` → o teu athlete id (ex: `i123456`).
   - `ANTHROPIC_API_KEY` → a chave do passo 2b.

Estes valores ficam encriptados pelo GitHub e só são visíveis dentro das
Actions deste repositório — não aparecem em lado nenhum do código.

### 4. Testar manualmente antes de confiares na automação

**Já testado e confirmado a funcionar (26/ago/2026): os 172 treinos foram
criados com sucesso no intervals.icu.** Passos que qualquer pessoa deve
repetir se recriar isto de raiz:

1. No GitHub, vai a **Actions → Sync training plan to intervals.icu → Run
   workflow**.
2. Liga **dry_run = true** e **skip_adapt = true**, corre. Isto só mostra
   nos logs o que *seria* criado, sem tocar em nada.
3. Confirma nos logs que as datas e os nomes fazem sentido.
4. Corre de novo com **dry_run = false** (mantém skip_adapt = true). Isto
   vai criar os ~172 treinos no teu calendário do intervals.icu.
5. Vai ao intervals.icu → Calendar e confirma que os treinos aparecem nos
   dias certos.
6. Confirma no teu Garmin Connect / relógio que os treinos planeados chegaram
   (pode demorar alguns minutos a sincronizar).

Passada esta primeira vez, o cron diário já corre com o ajuste automático
ligado (não precisas de marcar skip_adapt outra vez — isso é só para hoje).

**Marcar o dia da prova como "corrida":** a API do intervals.icu recusou
tanto `type: "Triathlon"` como `category: "RACE"` (erro 400 "JSON parse
error" nos dois), por isso o evento "IronMan 70.3 Cascais" (17/out) foi
criado como um treino normal, sem a marcação especial de prova. Para
ativares isso: no intervals.icu → Calendar → abre o evento do dia 17/out →
deve haver uma opção tipo "This is a race" / categoria — ativa-a e guarda.
É um ajuste manual único, só para esse dia.

### 5. Automação recorrente

Depois do primeiro teste manual correr bem, já não precisas de fazer nada:

- O workflow corre **automaticamente todos os dias às 5h UTC**: primeiro
  ajusta o plano (`adapt_plan.py`), depois sincroniza
  (`sync_to_intervals.py`).
- Também corre sempre que fizeres `git push` a uma alteração em
  `plan/plan.json`.
- É seguro correr repetidamente: nunca duplica treinos, nunca mexe em dias
  passados, e só atualiza/apaga eventos que ele próprio criou (nunca toca
  em algo que tu adiciones manualmente no calendário do intervals.icu).

### 6. Como ajustar o plano no futuro

- **Para o dia a dia, tudo no mesmo sítio (o telemóvel, dentro do
  intervals.icu)**: preenche o **Wellness** todos os dias (fadiga, sono,
  stress, motivação, dores) e usa o campo de texto livre **"Comments"** do
  próprio Wellness para qualquer nota específica ("amanhã tenho mais
  disponibilidade", "dores no joelho esquerdo", viagens, etc.) — o ajuste
  automático diário lê **todos** os campos do Wellness, incluindo esse
  texto livre, não só os números. Não precisas de tocar no GitHub nem de
  vir a este chat para o dia a dia — o campo Comments substitui, no
  telemóvel, o que `plan/athlete_input.md` fazia só no computador.
- `plan/athlete_input.md` continua a existir como alternativa (ex: se
  preferires escrever algo mais longo num computador), mas deixou de ser
  necessário no uso diário — o Comments do Wellness já chega a Claude da
  mesma forma.
- **Para pedidos que precisam de resposta imediata/no próprio dia** (ex:
  "hoje afinal vou correr em vez de nadar") em vez de esperar pelo ajuste
  automático da manhã seguinte: manda mensagem aqui mesmo, no chat com o
  Claude — também dá para usar a partir do telemóvel (app do Claude ou
  claude.ai no browser), por isso continua a ser "um sítio só" mesmo para
  isto.
- Para pequenos ajustes manuais e imediatos (mudar um treino, mover um dia):
  edita `plan/plan.json` diretamente (ou `plan/plan.csv` numa folha de
  cálculo e depois converte) e faz commit/push — a sincronização
  atualiza-se sozinha.
- Para regenerar tudo de raiz (ex: mudar a data da prova): edita as
  constantes no topo de `plan/generate_plan.py` (`RACE_DATE`, `PLAN_END`) —
  e também `LOCK_START`/`LOCK_END`/`RACE_DATE` no topo de
  `scripts/adapt_plan.py`, que têm de ficar em sincronia — corre
  `python3 plan/generate_plan.py` e faz commit dos ficheiros gerados.
- Para qualquer coisa fora do comum — lesão a sério, mudar de objetivo,
  dúvidas sobre o plano — fala comigo diretamente nesta conversa.

## Notas técnicas (problemas já resolvidos)

Se algum dia isto voltar a falhar, começa por aqui:

- **HTTP 403 "error code: 1010"** → bloqueio da Cloudflare por causa do
  User-Agent por omissão do Python. Resolvido em `scripts/intervals_client.py`
  ao enviar um `User-Agent` normal.
- **HTTP 401 "Auth failed"** → API key ou Athlete ID errados/copiados com
  espaços. Confirma os secrets no GitHub.
- **HTTP 400 "JSON parse error"** → a API tem enums estritos nalguns campos.
  Confirmado que `type: "Triathlon"` e `category: "RACE"` não são aceites;
  usa sempre valores já comprovados (`Run`, `Ride`, `Swim`, `WeightTraining`,
  `Yoga`, `Other` para type; `WORKOUT` ou `NOTE` para category).
- Se os runs do GitHub Actions ficarem presos em "queued" sem nenhum job:
  confirma em `Settings → Billing and licensing → Budgets and alerts` que o
  orçamento de Actions não está a 0€, e que há um método de pagamento
  associado à conta.
- **Treino de natação com duração absurda (ex: horas em vez de minutos)** →
  na sintaxe de treino estruturado do intervals.icu, `m` significa
  **minutos**, não metros. Um passo de piscina tem de usar `mtr` (ex:
  `- 100mtr Z2 HR`), nunca `100m`. Corrigido em
  `scripts/structure_workouts.py`; se acontecer de novo num treino
  específico, corre o workflow **Structure workout descriptions (one-off)**
  com `sport = swim` e `force = true` para reconverter só a natação.
