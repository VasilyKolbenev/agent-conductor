# Public alpha scope — finish V1, then use it to build V2

**Owner decision, 2026-09-05:** close the nine findings from the `8dec0e4` review,
prove one useful independently checked result, and pass final review and owner
acceptance. This is the current delivery boundary, not another platform roadmap.
Nothing here declares a release, a green remote run, or completed manual acceptance.

## Owner clarification, 2026-10-21: the core product contract

December Command orchestrates complete, existing vendor coding harnesses that the user
accesses through paid subscriptions: Grok, Claude Code, Codex, Kimi and DeepSeek.
The user assigns each harness roles and tasks, connects them into execution/review loops,
and collects independently checked results. Each harness retains its own agent execution
loop and tools; December Command supplies the workflow and coordination above that layer.

The default workflow is Ray Dalio's five-step cycle: goals, identify problems, diagnose,
design and do. Workflow Studio must also let users create and edit their own cycles
without code; the default cycle is not the only supported topology.

**Owner clarification, 2026-11-10:** The primary scenario is prolonged autonomous work
on large, compound tasks by complete harnesses. A Dalio action contains a harness's own
agent and tool loop; five workflow actions do not mean five internal model turns.
The five-action / 600-second rehearsal does not set a universal product ceiling.
Duration, workflow attempts, protocol envelopes and durable results need separate
budgets, presented for approval with the task. Local capture tests do not establish
long-duration execution, token renewal or recovery; those need their own real evidence.

The product must show each configured harness's subscription usage, remaining allowance,
and reset time for the windows the vendor actually reports, including daily, weekly and
five-hour windows where applicable. Distinguish measured values, stale observations and
unavailable data. Do not invent missing limits, equate local action counts with vendor
usage, or promise access that a particular vendor/account has not demonstrated.

Subscription access is part of V1's core acceptance, not a V2 improvement. API access may
remain optional, but an API-only rehearsal does not establish this product outcome and
API keys must not be required as a substitute for the owner's paid subscriptions.
This supersedes the earlier recovery decision H5-V1 and API-based R5-keys plan.

Claude Code 2.1.239 executing and Codex 0.112.0 checking is the first end-to-end proof,
not a reduction of the five-harness product scope. Record each remaining harness's actual
support and evidence separately. Native subscription execution inside the product's
boundary is still unfinished; this requirement does not claim the current wheel supports it.
Preserve the independent checker, explicit budgets, human gates and original-project safety.

**Owner decision, 2026-10-28 (V1-HARNESS):** V1 acceptance requires Claude Code and Codex
to execute and check tasks through their subscriptions, and shows the subscription limits
of Claude Code, Codex and Grok. Grok and Kimi as executors, and DeepSeek, are marked "not
yet supported" in V1 and form the next slice. The five harnesses remain the product goal.

**Public alpha decision, 2026-11-02 (ALPHA-FOUR):** Finish first-run UX first. Before public
distribution a new user must be able to connect their own Claude Code, Codex, Grok Build and
Kimi Code subscriptions and obtain a real task result with each. Record the version, result
and source of any quota readings per harness. Also complete the default Dalio cycle with
Codex and Grok, its human gates and independent result check. A scripted adapter only proves
local integration. DeepSeek remains in the product roadmap. The three-run concurrency target
belongs to the second stage. The earlier acceptance steps below are retained as milestones.

**Owner decision, 2026-10-30 (V1-GROK-ROLE):** Grok also takes one minimal role in the V1
Dalio v6 run, to show it working: role-diagnostician, the single read-only `diagnose` step.
Claude Code keeps the other steps and Codex stays the independent checker. If Grok's task
road is not ready in time, Claude Code takes that step and Grok joins in a later run, so the
Claude Code and Codex core is not delayed. Kimi and DeepSeek remain "not yet supported".

## What remains non-negotiable in V1

The product is a local-first control plane for heterogeneous coding harnesses.
Its unit of value is a project decision across independent participants, supported
by evidence and explicit human responsibility — not a chat or a model leaderboard.
The principles in [product direction](specs/2026-08-03-product-direction.md) and
[HCP direction](specs/2026-08-03-hcp-competitive-product-direction.md) remain; their
dated capability labels and schedules are not today's completion report.

- A usable Workflow Studio: editable steps/connections, keyboard and pointer parity,
  clear participant/model choices, real parameter consumption, and an uncluttered
  first path. Drafts survive refreshes and concurrent request completions honestly.
- Bounded execution from immutable revisions: reached gates, conditions and loop
  bounds govern eligibility; no hidden authority escalation and no unbounded
  autonomous executor. A step starts only through a permitted road: a per-step
  confirmation, or a bounded automatic (Policy) run the owner authorized after
  reviewing its explicit limits. Under such a run routine steps start without
  per-action confirmation, human gates still wait for a person, and pause,
  resume and revoke are explicit controls.
- A real independent checker: a different participant, possibly on the same harness,
  judges the exact doer result and consumed materials under visible budgets. A
  process exit, a human approval and verified work remain three different facts.
- Studio-owned briefs, instructions and artifact inputs; exact preview binding;
  a contained working copy and an explicitly accepted result, never an automatic
  overwrite of the user's original repository.
- Historical journals and frozen revision bytes remain readable. New requirements
  use additive fields and explicit live refusals, not silent reinterpretation.

Completion is measured by [owner acceptance](owner-acceptance.md), including the
developer's real-result rehearsal and the owner's separate hands-on pass, plus
[release gates](release-smoke.md). A small V2 utility used in this acceptance
exercise is a test of V1's usefulness, not permission to start the V2 implementation.

## Preserve for V2 — do not reopen before alpha

### One entry point for subscription harnesses («единая розетка»)

Owner direction, 2026-11-07. A user brings subscriptions to complete vendor
harnesses. Each keeps its own tools and execution loop. December Command connects
their roles, workspaces, handoffs, budgets and results in one workflow. The
catalogue shows what each installed harness has actually demonstrated, including
account access, supported roles and quota windows. A reading the vendor does not
provide is displayed as unknown.

The conversational launcher starts with the task in the user's own words. It asks
only for missing details and drafts an editable Dalio cycle or a user-defined
no-code cycle. It proposes participants, a separate checker, time and action
limits suited to the task, and shows where a person will make a decision. The
user can revise those choices in conversation or in Studio. Both views use the
same plan and the same preview. Execution begins with explicit bounded permission.

Acceptance example: on a clean installation, a colleague connects their own
subscriptions and asks to fix a counter that counts failed runs as successes.
They can see why Grok is assigned diagnosis, what Codex may edit, who checks the
change and the limits of the first action. After the run they can find the change,
test result, checker verdict and their decision together, then reuse the cycle on
a second task. Measure time to an accepted result, human interventions and vendor
quota readings where available. Reuse on a second task is a separate product signal.

The immediate rehearsal is the full Codex and Grok Dalio cycle. A three-harness
rehearsal with Kimi Code follows confirmed subscription access and a verified task
on that harness. Previous Claude Code rehearsal evidence remains attached to its
specific version and steps. **Arachnid** is the owner's proposed product name.

### Arachnid Studio: рабочее место оператора

Решение владельца от 9 ноября 2026. Первым экраном Studio должен быть разговор с Атласом.
«Атлас» — имя роли ведущего харнесса, которого выбирает пользователь. В шапке чата
видно назначение, например «Атлас · Codex». Оператор ставит цель, меняет команду или цикл, принимает решения
и получает результат в одной сессии. Харнессы поставщиков подключаются как инструменты
по личным подпискам и сохраняют свои собственные интерфейсы и возможности.

| Область | Что видит и делает оператор |
| --- | --- |
| Слева | Сессии и история задач. Выбор восстанавливает разговор, текущий шаг и связанные результаты. Одна сессия может включать несколько задач и запусков. |
| В центре | Основной чат с Атласом. Здесь появляются цель, предложенная команда, следующий шаг, запрос решения и принятый результат. Для обычного запуска хватает разговора. |
| Справа, по запросу | Рабочее представление выбранного агента или харнесса в конкретной сессии. Оператор открывает его, чтобы увидеть ход работы, ввод и вывод. Закрытие панели возвращает к тому же месту в основном чате. |

По умолчанию Атлас предлагает пять шагов Далио, роли подключённых харнессов
с учётом их подтверждённых возможностей и отдельного проверяющего. Оператор может
сказать «поменяй проверяющего» или выбрать свой опубликованный no-code цикл. Перед
исполнением чат показывает обновлённый план, границы и точки решения. Совет и
просмотр возможностей сами по себе не запускают задачу.

Команда «покажи лимиты» открывает панель подписок с доступными окнами, расходом
и временем сброса. Для отсутствующих показаний выводится «неизвестно». Эта панель,
редактор ролей, цикл, журналы и подробности участников открываются по запросу.
Для харнесса используется поддерживаемый способ доступа к его сессии. Если поставщик
не предоставляет встраиваемое представление, Studio показывает доступные действия
и предлагает открыть родное приложение. На узком экране список сессий и детали
участника открываются по очереди с возвратом в тот же разговор.

**Адаптивная инфографика.** Содержимое правой панели определяется ролью участника,
текущей задачей и вопросом оператора. На вопрос «почему?» диагност показывает вывод,
исследованные файлы и основания. На «что изменилось?» исполнитель показывает diff
и результаты тестов. На «можно принять?» проверяющий показывает свой вердикт и
проверенную ревизию. Один харнесс в разных ролях получает разные представления.
Сначала видны данные для текущего решения. Подробности можно раскрыть или запросить
в чате, сохраняя выбранный шаг. Форма следует за данными: орбита показывает ход
цикла, diff — изменения, шкала времени — окна квоты с известным временем сброса.

**Визуальный референс, 11 ноября 2026 — Minicharts.** Владелец предложил
[Minicharts](https://april-zhu.com/minicharts) как идею предметной интерактивной
инфографики для рабочего представления харнесса. Это развитие адаптивной панели,
а не решение перенести мультяшные шаблоны или установить сторонний skill.
Данные получают выразительную форму, связанную с работой участника: орбиты,
узлы, связи, слои и сегменты. Палитра, типографика, глубина и движение согласованы
с тёмной Studio Arachnid; числовые пропорции и подписи сохраняют точность.

При открытии участника оператор получает краткую сводку «делает / делал / сделал»
и доступных ресурсов. Представление выбирается по роли, задаче и вопросу,
а не закрепляется навсегда за брендом харнесса. Подробности раскрываются по запросу;
тот же чат с Атласом остаётся в центре. Декоративная форма помогает читать данные,
а фактические diff, тесты и вердикт выбранной попытки остаются доступны рядом.

| Вопрос оператора | Полезное представление и основание |
| --- | --- |
| Что сейчас происходит? | Орбита текущего цикла, наблюдаемый статус и лента реальных событий: кто работает, что завершено, где ожидание или отказ. Внутренний ход мыслей не имитируется. |
| Что исследовал диагност? | Исследованные материалы и связи «вывод — основание», только если они переданы харнессом и доступны в артефактах. |
| Что изменил исполнитель и можно ли принять? | Сводка изменений и проверок с переходом в фактический diff, тесты и независимый вердикт именно выбранной попытки и ревизии. |
| Что было сделано раньше? | История задач и результатов с отдельно видимыми завершением исполнения, проверкой и принятием человеком. |
| Сколько подписки осталось? | Отдельные окна квоты, сообщённые поставщиком: остаток или расход, единицы, время наблюдения, источник и известный момент сброса. |

Графики строятся из структурированных показаний и событий; художественная форма
не меняет значения. Неизвестное не равно нулю, устаревшие показания явно помечены.
Число локальных действий не становится расходом подписки или процентом готовности.
Аккаунтная квота не выдаётся за расход конкретной задачи. ETA, токены и экономия
появляются только при наличии подтверждённого источника или явно обозначенной оценки.
Размеры и сравнения остаются проверяемыми: выбор элемента открывает исходное событие,
артефакт или показание. Подписи и состояние читаются без опоры только на цвет;
движение учитывает reduced motion. Открытие графика не разрешает исполнение или приёмку.

Критерий будущего среза: на принятом Codex + Grok оператор открывает Do на орбите,
видит сводку работы, diff, тесты и вердикт этой попытки, раскрывает основания
и окна подписки без потери разговора с Атласом. Для отсутствующих показаний
видно «неизвестно», для демонстрационных данных — явная отметка.
Это зафиксированное направление V2; оно не объявляет новую реализацию готовой
и не заменяет ближайшую проверку полного Далио на `4deb571`.

**Адаптивная память пользователя.** Атлас пополняет память в фоне и подбирает для
текущей задачи сведения о пользователе, его харнессах и агентах. Новый пользователь
начинает со своей памяти. Предусмотрены три вида записей и процесс их консолидации.

- **Эпизодическая память** хранит события сессий: задачу, шаг, участника, результат
  и решение оператора. Запись отсылает к исходному событию.
- **Семантическая память** хранит подтверждённые факты о проектах и предпочтения
  пользователя, включая стиль общения. Например, краткий итог по умолчанию и
  подробные доказательства по запросу на ревью.
- **Процедурная память** хранит повторяемые способы работы: выбор цикла, назначения
  ролей, ожидаемые проверки и удобный порядок приёмки.
- **Консолидация** связывает повторяющиеся эпизоды с фактами и процедурами,
  сохраняет основания и учитывает явные поправки пользователя. По запросу Атлас
  объясняет, что вспомнил и почему это применимо. Оператор может исправить вывод
  и выбрать, какие сведения передать конкретному харнессу.

**Приёмка компоновки.** Коллега открывает новую сессию и просит исправить счётчик.
В чате он видит Далио и предложенные роли, меняет одну роль и подтверждает границы.
Затем открывает работу Grok справа, смотрит лимиты, возвращается в чат, видит
проверенные изменения и принимает результат. После переключения на прежнюю сессию
и обратно задача, разговор и решение сохраняются. Другому пользователю эта память
недоступна. Вариант с собственным циклом проходит тот же путь.

**Критерий макета — Do на орбите Далио.** Оператор выбирает
Do на орбите текущей задачи. Справа открываются diff фактических изменений Codex и
результаты тестов именно этой попытки; рядом доступно заключение отдельного
проверяющего. В центре остаётся тот же чат с Атласом. Оператор спрашивает «какой
тест подтверждает исправление?», видит соответствующий тест и может вернуться к
diff. Выбор шага, файла или теста сам по себе не означает принятия результата.

**Рабочая оболочка, 09.11.2026.** Корень установленной Arachnid открывает сессии
проекта, чат Атласа и орбиту выбранного запуска. На принятом цикле Codex + Grok
проверены обе стороны diff, результаты тестов и независимый вердикт именно выбранной
попытки Do. Разбор Атласа использует сохранённые данные. Участники, лимиты и история
открываются по запросу. [Проверка сборки](recovery/2026-10-20/tasks/ARACHNID-SHELL-REPORT.md).

Дальнейшая цель — диалоговый запуск и персональная память. Проверенный альфа-мастер уже даёт подготовку задачи,
предпросмотр, разрешение и приёмку. Приоритет следующего изменения Studio — связать
эти возможности основным чатом и проверить этот сценарий целиком.
В [кликабельном макете](prototypes/arachnid-studio.html) оператор выбирает шаг на орбите
или переходит [сразу к Do](prototypes/arachnid-studio.html#do). Справа видны изменения
двух файлов, семь проверенных тестов и вердикт по снимку принятого запуска `dalio-patch`.
Ответы Атласа демонстрационные. Сессии, участники, память и лимиты открываются локально.
Данные и границы проверки перечислены в [отчёте сцены](recovery/2026-10-20/tasks/UX-ATLAS-ORBIT-REPORT.md).
Референс владельца — [пост New World AI о Biotech Studio](https://t.me/newworld2080/8800).
В присланной записи около 0:49 видны узкая история слева, свободное место в
центре и ввод внизу. В 1:21 справа открывается широкая рабочая область, а разговор
остаётся на экране. В 2:01 там видны цели, в 2:39 — Roadmap. Для Arachnid это
означает, что справа можно работать и с планом или результатом выбранной сессии,
пока чат остаётся доступен. Компоновка сохраняется в светлой и тёмной теме.

### Other V2 commitments

- **Stage two: up to three concurrent runs per project** (owner decision, 2026-11-02).
  A run is one execution of a cycle for a task. The three tasks may use the same
  cycle template or different ones. Studio shows which runs are working, waiting
  for a person, or queued, and why. A run waiting at a human gate releases its
  execution slot; its decision, workspace, artifacts and authorization stay its own.
  Shared subscription limits or workspace conflicts may reduce actual concurrency.
  Acceptance: start four authorized, independent tasks. Observe three overlapping
  executions and the fourth queued. When one reaches a gate or finishes, the fourth
  can start. Resuming the waiting run respects the same ceiling; pausing one run
  leaves the others working.
- Additional harnesses, including the parked Qwen and GLM work; no new transport
  claim enters the alpha catalogue without its own reviewed real-install evidence.
- **Experience Ledger / evidence-weighted Harness Graph.** Preserve project-owned
  experience about immutable configurations, task classes, handoff edges, review
  complementarity and graph topology. Every inference must show sample size,
  supporting evidence, freshness and applicability. Unknown model versions remain
  unknown; changed configurations do not inherit unqualified trust. No private
  prompts, secrets, chain-of-thought, context-free ranking or silent model switch.
- Recommendations among configured participants, graph changes with preview and
  human authorization, marketplace/cloud work, and a general sandbox/worktree
  platform. None is smuggled into an alpha closeout fix.
- Export run brief is a useful next candidate, not a new condition of this release.

## Approved V2 directions: memory, measured improvement and human choice

These are planned directions, not shipped V1 features or promises of a particular savings percentage.

- **Qwen** is planned for V2; the V1 execution catalogue remains the five agreed harnesses.
- **Memory and portable handoffs:** keep the task goal, constraints, confirmed findings,
  open questions and references to original evidence available across participants and sessions.
  The [operator workspace](#arachnid-studio-рабочее-место-оператора) defines personal
  episodic, semantic and procedural memory, consolidation and view selection by role and task.
- **Dream-RSI-inspired experiments:** use prior work to propose changes to the strategy
  around an existing harness. This does not require rewriting a vendor's agent.
- **SoL-Pi-inspired context handoffs:** first compare a full research handoff with a compact
  evidence-linked handoff on separate tasks. Preserve source access and initially keep
  the independent checker's inputs unchanged. Measure missed facts, result quality,
  corrections, time, resource use and human intervention, including the cost of summarizing.
  Batching actions, choosing compaction points and processing observations are additional
  experiments only where the harness exposes the necessary interface; installing one
  upstream extension does not optimize all five native harnesses automatically.
- **Human approval:** every strategy change is a proposal for the person to confirm.
  An experiment passing its checks does not grant permission to apply a new strategy.

Use V1 to help build V2. Establish reliable memory and measurable run history before
claiming self-improvement or moving a proposed optimization into ordinary work.

## Why the two older HCP editions disagree

The bundled edition was last updated by commit `47f5f9ffc44a4aab7bf1ebc866b6d508d2fb83b9`;
it retains the historical four-day strike. A later owner working copy, headed
**Updated 2026-08-24**, adds §4.12 Experience Ledger and a fourteen-day strike.
At this closeout that later file was untracked, not a committed revision; its
SHA-256 was `78f500d223f3c713748493c667d28bdb7a65603389db1cc18f466261389f3f1b`.
The ideas above preserve that later direction without rewriting either document
or pretending its calendar is a new deadline. The dated 2026-09-05 closeout decision
governs current delivery; the next-version ideas remain in this explicit queue.
