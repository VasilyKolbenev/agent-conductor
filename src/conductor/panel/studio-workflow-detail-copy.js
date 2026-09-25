"use strict";
// Interface copy only; user text and protocol identifiers stay unchanged.
export const WORKFLOW_DETAIL_COPY = Object.freeze({
  "workflow_detail.input_none": [
    "This step requires no input artifact.",
    "Этот шаг не требует входных материалов."
  ],
  "workflow_detail.drop_ref": [
    "Stop requiring {ref}",
    "Больше не требовать {ref}"
  ],
  "workflow_detail.remove": [
    "Remove",
    "Убрать"
  ],
  "workflow_detail.require": [
    "Require it",
    "Добавить требование"
  ],
  "workflow_detail.ref_grammar": [
    "An artifact reference must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}.",
    "Имя материала должно соответствовать [A-Za-z0-9][A-Za-z0-9._-]{0,127}."
  ],
  "workflow_detail.ref_duplicate": [
    "This step already requires {ref}. A run resolves each reference once, so asking for one twice is refused where the resolution happens.",
    "Шаг уже требует {ref}. Каждое имя разрешается один раз; повтор одного имени приведёт к отказу."
  ],
  "workflow_detail.require_label": [
    "Require an artifact",
    "Требовать материал"
  ],
  "workflow_detail.input_schema_none": [
    "none — the reviewed schema for this step's capability declares no artifact input, so there is none to name",
    "нет — проверенная схема возможности этого шага не предусматривает входных материалов"
  ],
  "workflow_detail.arguments_source": [
    "the step's capability arguments",
    "аргументы возможности шага"
  ],
  "workflow_detail.input_unnamed": [
    "none — this step names no input artifact",
    "нет — шаг не указывает входных материалов"
  ],
  "workflow_detail.input_source": [
    "the step's capability arguments, resolved before the spawn",
    "аргументы возможности шага, разрешаемые до запуска процесса"
  ],
  "workflow_detail.ref_note": [
    "A reference is a HANDOFF NAME and not a document: a run resolves it to the latest artifact standing under that name at the moment this step runs. Every other argument of this step is carried across untouched when this list changes.",
    "Ссылка задаёт имя передаваемого материала. Запуск связывает его с актуальным документом под этим именем. Изменение списка не затрагивает остальные аргументы шага."
  ],
  "workflow_detail.input_required": [
    "This schema REQUIRES at least one, and leaving the list empty has a plain cost: no run of this workflow can be opened at all while it is, because the open-run route judges every step's payload against the same reviewed schema — by the contract rather than by this window.",
    "Схема требует хотя бы один материал. С пустым списком создать запуск нельзя: сервер проверяет аргументы каждого шага по этой же схеме."
  ],
  "workflow_detail.input_optional": [
    "This schema admits an EMPTY list, so requiring nothing is a real answer: the step is then spawned with its instruction and no durable material beside it.",
    "Схема допускает пустой список. Тогда шаг получит свою инструкцию без дополнительных сохранённых материалов."
  ],
  "workflow_detail.publishes_nothing": [
    "publishes nothing",
    "ничего не публикует"
  ],
  "workflow_detail.ref_optional_grammar": [
    "An artifact reference must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}, or be empty.",
    "Имя материала должно соответствовать [A-Za-z0-9][A-Za-z0-9._-]{0,127} либо быть пустым."
  ],
  "workflow_detail.produced_label": [
    "Produced artifact",
    "Выходной материал"
  ],
  "workflow_detail.output_schema_none": [
    "none — the reviewed schema for this step's capability declares no result artifact reference, so a step of this kind publishes no document of its own",
    "нет — схема возможности этого шага не предусматривает публикацию отдельного выходного документа"
  ],
  "workflow_detail.output_changes": [
    "What it leaves instead is a CHANGE. The bound adapter digests what this step altered under its own work directory, folds in the identifiers of the artifacts it was given, and records that digest as the run's verification evidence. There is nothing to name here because no document is written.",
    "Результат такого шага — изменения в его рабочем каталоге. Адаптер связывает их контрольную сумму с входными материалами; после проверки она становится доказательством запуска. Отдельный документ не создаётся."
  ],
  "workflow_detail.output_unnamed": [
    "none — this step names no result artifact",
    "нет — шаг не задаёт имя выходного материала"
  ],
  "workflow_detail.output_source": [
    "the step's capability arguments, published after the spawn",
    "аргументы возможности шага; публикация после исполнения"
  ],
  "workflow_detail.output_empty_note": [
    "Clearing it is allowed and it has a plain cost, met at the run rather than here: a step of this kind that names no result artifact is REFUSED when it is reached — nothing it produced could be published, so no task is spawned at all and the model call is never spent.",
    "Поле можно очистить, но такой шаг будет отклонён при достижении в запуске: его результат некуда публиковать. Процесс не запустится и обращение к модели не будет потрачено."
  ],
  "workflow_detail.handoff_none": [
    "none — this step requires no artifact, so there is nothing for another step to hand it",
    "нет — шаг не требует материалов от других шагов"
  ],
  "workflow_detail.workflow_source": [
    "this workflow document",
    "этот документ процесса"
  ],
  "workflow_detail.produced_by": [
    " — produced by {steps}",
    " — создают: {steps}"
  ],
  "workflow_detail.external_input": [
    " — no step in this workflow produces it. A run is handed it on the Runs screen, under Publish a document, before this step can run.",
    " — ни один шаг этого процесса его не создаёт. До выполнения шага передайте документ запуску через «Опубликовать документ» на экране запусков."
  ],
  "workflow_detail.handoff_count": [
    "{met} of {total} met by a step in this workflow",
    "Шаги этого процесса создают {met} из {total}"
  ],
  "workflow_detail.run_source": [
    "the durable records of run {run}",
    "сохранённые записи запуска {run}"
  ],
  "workflow_detail.run_products_none": [
    "none — no artifact in this run's journal was published by an action of this step",
    "нет — действия этого шага ещё не публиковали материалов в журнале запуска"
  ],
  "workflow_detail.run_products_note": [
    "The handoff name, the identity and the media type. The CONTENT is deliberately not here: an artifact is durable material a run hands between roles, and this window says what exists rather than reproducing it — the Runs screen shows the same three facts and no more.",
    "Показаны имя передачи, идентификатор и тип содержимого. Этот список сообщает о наличии материалов, передаваемых между ролями; сами документы здесь не воспроизводятся."
  ],
  "workflow_detail.missing_inapplicable": [
    "none — this step is given no input artifacts, so there is none to be missing",
    "не применяется — у шага нет входных материалов"
  ],
  "workflow_detail.contract_source": [
    "the workflow contract",
    "контракт процесса"
  ],
  "workflow_detail.missing_default": [
    "fail — reach the step, then refuse it (the default)",
    "fail — отклонить шаг при достижении (по умолчанию)"
  ],
  "workflow_detail.missing_fail": [
    "fail — reach the step, then refuse it",
    "fail — отклонить шаг при достижении"
  ],
  "workflow_detail.missing_block": [
    "block — do not offer the step until the artifact exists",
    "block — ждать появления материала, не предлагая шаг"
  ],
  "workflow_detail.missing_note": [
    "Both answers are fail-closed and nothing here skips the step or substitutes another document. With FAIL — which is also what saying nothing means — the step is offered, reached, and refused when the input cannot be resolved: no task is spawned and no model call is spent, and the run carries a durable failure. With BLOCK the step is never offered at all while the artifact is absent, so nothing is attempted and nothing fails — the plan waits, and this screen says which document it is waiting for.",
    "Оба варианта запрещают выполнение без нужного материала. FAIL (также значение по умолчанию) предлагает шаг, но при достижении записывает отказ без процесса и обращения к модели. BLOCK не предлагает шаг до появления материала: попытки нет, план ждёт, а экран показывает недостающий документ. Шаг не пропускается, материал не подменяется."
  ],
  "workflow_detail.frozen_source": [
    "the plan run {run} froze",
    "план, замороженный запуском {run}"
  ],
  "workflow_detail.waiting_note": [
    "This step is not offered until every artifact named above exists in this run. Publish them, or answer the step that produces them, and it becomes available.",
    "Шаг станет доступен, когда в запуске появятся все перечисленные материалы. Опубликуйте их или выполните шаг, который их создаёт."
  ],
  "workflow_detail.handoff_heading": [
    "Handoff mapping",
    "Передача материалов"
  ],
  "workflow_detail.products_heading": [
    "What this run produced",
    "Что создал этот запуск"
  ],
  "workflow_detail.none": [
    "none",
    "нет"
  ],
  "workflow_detail.evidence_ids_note": [
    "Identifiers only. Nothing here states that any of them verified anything.",
    "Это только идентификаторы. Само их наличие не подтверждает результат проверки."
  ],
  "workflow_detail.no_outgoing": [
    "No outgoing connection: this step ends the plan as drawn.",
    "Исходящих связей нет: этот шаг завершает нарисованный план."
  ],
  "workflow_detail.disconnect_pair": [
    "Disconnect {from} from {to}",
    "Разъединить {from} и {to}"
  ],
  "workflow_detail.disconnect": [
    "Disconnect",
    "Разъединить"
  ],
  "workflow_detail.condition_none": [
    "carries out no work — no condition",
    "не выполняет работу — условия нет"
  ],
  "workflow_detail.always": [
    "always — unconditional",
    "всегда — без условия"
  ],
  "workflow_detail.condition_on_approved": [
    "approved",
    "одобрено"
  ],
  "workflow_detail.condition_on_rejected": [
    "rejected",
    "отклонено"
  ],
  "workflow_detail.condition_on_changes_requested": [
    "changes requested",
    "нужны изменения"
  ],
  "workflow_detail.condition_on_waived": [
    "waived",
    "пропущено"
  ],
  "workflow_detail.condition_on_succeeded": [
    "succeeded",
    "успех"
  ],
  "workflow_detail.condition_on_failed": [
    "failed",
    "неудача"
  ],
  "workflow_detail.condition_on_bound_reached": [
    "bound reached",
    "достигнут предел"
  ],
  "workflow_detail.condition_on_bound_remaining": [
    "bound remaining",
    "остались проходы"
  ],
  "workflow_detail.routing_only_gate": [
    "none — only a gate's answer routes",
    "не применяется — направление выбирает только ответ на проверку"
  ],
  "workflow_detail.routing_no_step": [
    "none — this gate opens no step",
    "нет — эта проверка не открывает шагов"
  ],
  "workflow_detail.document_source": [
    "the workflow document",
    "документ процесса"
  ],
  "workflow_detail.routing_every": [
    "every answer opens {steps}",
    "любой ответ открывает: {steps}"
  ],
  "workflow_detail.routing_heading": [
    "Decision routing",
    "Направление после решения"
  ],
  "workflow_detail.no_other_step": [
    "There is no other step to connect this one to.",
    "Других шагов для соединения пока нет."
  ],
  "workflow_detail.connect": [
    "Connect",
    "Соединить"
  ],
  "workflow_detail.connect_to": [
    "Connect to",
    "Соединить с"
  ],
  "workflow_detail.demand_yes": [
    "yes — this gate may not be waived",
    "да — эту проверку нельзя пропустить"
  ],
  "workflow_detail.demand_no": [
    "no — this gate may be approved, rejected, sent back for changes, or waived",
    "нет — можно одобрить, отклонить, запросить изменения или пропустить проверку"
  ],
  "workflow_detail.demand_note": [
    "Waiving is the one answer that closes a gate without judging the work. Requiring explicit human approval removes it: the Decisions screen stops offering it, the server refuses it before anything is recorded, and a journal carrying one is refused when it is read. Rejecting and requesting changes stay available — this makes the gate harder to pass, never harder to fail. A connection out of this gate on `on_waived` becomes a road no run could travel, so publishing one is refused.",
    "Пропуск закрывает проверку без оценки работы. Требование явного одобрения человека запрещает пропуск на экране решений, при записи сервером и при чтении журнала. Отклонение и запрос изменений остаются доступны. Связь on_waived при этом недостижима, поэтому опубликовать её нельзя."
  ],
  "workflow_detail.gate_id_note": [
    "The id a Human's decision receipt names. A run's gate state is read through it, and through nothing else.",
    "Идентификатор проверки, который указывается в записи решения человека. По нему определяется состояние проверки в запуске."
  ],
  "workflow_detail.human_only_gate": [
    "none — only a gate step carries one",
    "не применяется — решение человека относится только к шагу проверки"
  ],
  "workflow_detail.loop_only": [
    "none — only a loop step reopens work",
    "не применяется — работу повторно открывает только шаг цикла"
  ],
  "workflow_detail.loop_bound_error": [
    "A loop bound is a whole number from {min} to {max}.",
    "Предел цикла — целое число от {min} до {max}."
  ],
  "workflow_detail.loop_bound_label": [
    "Loop bound (greatest pass)",
    "Предел цикла (последний проход)"
  ],
  "workflow_detail.loop_note": [
    "A bound is a ceiling on the POSITION — the greatest pass this work may reach — never a count of reopenings beside it. Which pass a run is on is the run's own fact and is shown under Assignment's run context, never here.",
    "Предел задаёт наибольший номер прохода, а не дополнительное число повторов. Текущий проход — факт запуска; он показан в его контексте в разделе назначения."
  ],
  "workflow_detail.condition_missing_edge": [
    "none — this drawing does not carry that road",
    "нет — такой связи нет на схеме"
  ],
  "workflow_detail.condition_missing_work": [
    "none — {step} carries out no work, so it produces no word",
    "нет — {step} не выполняет работу и не даёт исхода"
  ],
  "workflow_detail.condition_label": [
    "Condition",
    "Условие"
  ],
  "workflow_detail.outgoing_heading": [
    "Outgoing connections",
    "Исходящие связи"
  ],
  "workflow_detail.human_routing": [
    "Human decision routing",
    "Направление после решения человека"
  ],
  "workflow_detail.loop_heading": [
    "Loop",
    "Цикл"
  ],
  "workflow_detail.read_phase": [
    "read: {phase}",
    "чтение: {phase}"
  ],
  "workflow_detail.publishing_blocked": [
    "{count} problems block publishing this draft.",
    "Публикацию черновика блокируют проблемы: {count}."
  ],
  "workflow_detail.publishing_one": [
    "{count} problem blocks publishing this draft.",
    "Публикацию черновика блокирует одна проблема ({count})."
  ],
  "workflow_detail.publishing_ready": [
    "Nothing blocks publishing this draft.",
    "Публикация этого черновика не заблокирована."
  ],
  "workflow_detail.run_join_note": [
    "Run {run} is a DIFFERENT document. This build cannot prove it followed this workflow revision — a materialized plan records no workflow identity — so a step id is the only join, and run words appear only inside the boxes marked run.",
    "Запуск {run} — отдельный документ. В плане нет идентификатора ревизии процесса, поэтому совпадение с этой ревизией не подтверждено. Связь установлена только по идентификаторам шагов; факты запуска показаны в блоках «запуск»."
  ],
  "workflow_detail.draft_sentence": [
    "Editing the DRAFT — an unpublished workflow document. Nothing here has run.",
    "Редактируется черновик — неопубликованный документ процесса. Ничего на этой схеме ещё не исполнялось."
  ],
  "workflow_detail.revision_sentence": [
    "Showing published revision{revision} — immutable and read-only. Edit as new draft copies it into a draft you can change; this revision stays exactly as it is.",
    "Опубликованная ревизия{revision} доступна только для чтения. «Изменить как новый черновик» создаёт редактируемую копию; эта ревизия останется неизменной."
  ],
  "workflow_detail.no_workflow": [
    "No workflow document is open. Choose a workflow, or start one from a bundled starter.",
    "Документ процесса не открыт. Выберите процесс или создайте его из готового шаблона."
  ],
  "workflow_detail.add_after": [
    "Add {kind} after the selected step",
    "Добавить {kind} после выбранного шага"
  ],
  "workflow_detail.add_kind": [
    "{glyph} Add {kind}",
    "{glyph} Добавить: {kind}"
  ],
  "workflow_detail.add_step": [
    "Add a step",
    "Добавить шаг"
  ],
  "workflow_detail.new_step_note": [
    "A new step is added after the selected one, unbound and unconnected until you give it a role in the inspector.",
    "Новый шаг добавляется после выбранного. Задайте ему роль и связи в панели свойств."
  ],
  "workflow_detail.published_note": [
    "A published revision is immutable, so no step can be added to it.",
    "В опубликованную ревизию нельзя добавлять шаги."
  ],
  "workflow_detail.pan_zoom": [
    "Pan and zoom",
    "Сдвиг и масштаб"
  ],
  "workflow_detail.pan_left": [
    "Pan left",
    "Сдвинуть влево"
  ],
  "workflow_detail.pan_right": [
    "Pan right",
    "Сдвинуть вправо"
  ],
  "workflow_detail.pan_up": [
    "Pan up",
    "Сдвинуть вверх"
  ],
  "workflow_detail.pan_down": [
    "Pan down",
    "Сдвинуть вниз"
  ],
  "workflow_detail.zoom_out": [
    "Zoom out",
    "Уменьшить"
  ],
  "workflow_detail.zoom_in": [
    "Zoom in",
    "Увеличить"
  ],
  "workflow_detail.reset_view": [
    "Reset view",
    "Сбросить вид"
  ],
  "workflow_detail.reset_pan_zoom": [
    "Reset pan and zoom",
    "Сбросить сдвиг и масштаб"
  ],
  "workflow_detail.view_reading": [
    "zoom {zoom}% · pan {x},{y}",
    "масштаб {zoom}% · сдвиг {x},{y}"
  ],
  "workflow_detail.canvas_keys": [
    "Keyboard: arrows move the selection · Alt+arrows move the selected step on the canvas · Shift+arrows pan · + and − zoom, 0 resets · t, g, l add a task, a human gate or a loop after the selection · d duplicates · Delete removes · Esc clears. Connecting two steps is a drag from a step's port, or the Transitions section of the inspector.",
    "Клавиши: стрелки — выбор · Alt+стрелки — перемещение шага · Shift+стрелки — сдвиг схемы · + и − — масштаб, 0 — сброс · t, g, l — добавить задачу, проверку человека или цикл после выбранного шага · d — копия · Delete — удалить · Esc — снять выбор. Чтобы соединить шаги, перетащите порт или откройте раздел переходов в панели свойств."
  ],
  "workflow_detail.kind_task": [
    "Task",
    "Задача"
  ],
  "workflow_detail.kind_gate": [
    "Human gate",
    "Проверка человека"
  ],
  "workflow_detail.kind_loop": [
    "Loop",
    "Цикл"
  ],
  "workflow_detail.kind_review": [
    "Review",
    "Рецензия"
  ],
  "workflow_detail.kind_unknown": [
    "unknown: {kind}",
    "неизвестный тип: {kind}"
  ],
  "workflow_detail.run_label": [
    "run",
    "запуск"
  ],
  "workflow_detail.phase_idle": [
    "idle",
    "ожидает"
  ],
  "workflow_detail.phase_proposed": [
    "proposed",
    "предложен"
  ],
  "workflow_detail.phase_requested": [
    "requested",
    "запрошен"
  ],
  "workflow_detail.phase_running": [
    "running",
    "выполняется"
  ],
  "workflow_detail.phase_observed": [
    "observed",
    "результат получен"
  ],
  "workflow_detail.phase_unreadable": [
    "unreadable phase",
    "состояние не читается"
  ],
  "workflow_detail.no_result": [
    "no result recorded",
    "результат не записан"
  ],
  "workflow_detail.gate_reading": [
    "gate: {decision}",
    "проверка: {decision}"
  ],
  "workflow_detail.decision_idle": [
    "idle",
    "ожидает"
  ],
  "workflow_detail.decision_satisfied": [
    "satisfied",
    "одобрено"
  ],
  "workflow_detail.decision_failed": [
    "failed",
    "отклонено"
  ],
  "workflow_detail.decision_changes_requested": [
    "changes_requested",
    "нужны изменения"
  ],
  "workflow_detail.decision_waived": [
    "waived",
    "пропущено"
  ],
  "workflow_detail.decision_unknown": [
    "unknown",
    "неизвестно"
  ],
  "workflow_detail.pass_reading": [
    "pass {pass}{bound}",
    "проход {pass}{bound}"
  ],
  "workflow_detail.bound_reached": [
    " · bound reached",
    " · достигнут предел"
  ],
  "workflow_detail.role_reading": [
    "role: {role}",
    "роль: {role}"
  ],
  "workflow_detail.no_role": [
    "no role — nothing will run this step",
    "роль не задана — выполнять шаг некому"
  ],
  "workflow_detail.gate_id_reading": [
    "gate id: {id}",
    "проверка: {id}"
  ],
  "workflow_detail.loop_reading": [
    "↻ at most ×{bound} · reopens {step}",
    "↻ не более ×{bound} · возврат к {step}"
  ],
  "workflow_detail.after": [
    "after {steps}",
    "после {steps}"
  ],
  "workflow_detail.start": [
    "start",
    "начало"
  ],
  "workflow_detail.port_aria": [
    "Connect from {title}. Drag to another step, or use the Transitions section of the inspector.",
    "Соединить из {title}. Перетащите на другой шаг или используйте раздел переходов в панели свойств."
  ],
  "workflow_detail.port_help": [
    "Drag from this port onto another step to connect them, or use the Transitions section of the inspector.",
    "Перетащите этот порт на другой шаг или используйте раздел переходов в панели свойств."
  ],
  "workflow_detail.port_no_target": [
    "A connection needs a different step under the pointer when you let go.",
    "Отпустите указатель над другим шагом, чтобы создать связь."
  ],
  "workflow_detail.edge_aria": [
    "Connection from {from} to {to}{back}",
    "Связь из {from} в {to}{back}"
  ],
  "workflow_detail.edge_back": [
    ", a step backwards",
    ", шаг назад"
  ],
  "workflow_detail.empty_canvas": [
    "Nothing is drawn because no workflow document is open.",
    "Схема пуста: документ процесса не открыт."
  ],
  "workflow_detail.empty_steps": [
    "This workflow document has no steps yet. Add one from the palette, or press t, g or l.",
    "В процессе пока нет шагов. Добавьте шаг с панели или клавишами t, g, l."
  ],
  "workflow_detail.canvas_help": [
    "Canvas controls and keyboard",
    "Управление схемой и клавиши"
  ],
  "workflow_detail.canvas_positions": [
    "Drag a step to place it, or hold Alt and press an arrow. Where you put it is stored in the workflow document and comes back on reload. A step nobody has placed is laid out by its connections; order is edited in the inspector, and it is a different fact from position.",
    "Перетащите шаг или используйте Alt со стрелкой. Положение сохраняется в документе и восстанавливается при загрузке. Неразмещённые шаги располагаются по связям. Порядок задаётся отдельно в панели свойств."
  ],
  "workflow_detail.read_empty": [
    "empty",
    "пусто"
  ],
  "workflow_detail.read_loading": [
    "loading",
    "загрузка"
  ],
  "workflow_detail.read_ready": [
    "ready",
    "готово"
  ],
  "workflow_detail.read_failed": [
    "failed",
    "ошибка"
  ],
  "workflow_detail.stage_goal": [
    "goal",
    "цель"
  ],
  "workflow_detail.stage_identify": [
    "identify",
    "проблемы"
  ],
  "workflow_detail.stage_diagnose": [
    "diagnose",
    "причины"
  ],
  "workflow_detail.stage_design": [
    "design",
    "план"
  ],
  "workflow_detail.stage_do": [
    "do",
    "исполнение"
  ],
  "workflow_detail.orbit_region": ["Workflow team orbit", "Орбита команды процесса"],
  "workflow_detail.orbit_lenses": ["Workflow view", "Вид процесса"],
  "workflow_detail.lens_team": ["Team orbit", "Орбита команды"],
  "workflow_detail.lens_connections": ["Connections", "Связи"],
  "workflow_detail.orbit_team": ["Workflow team", "Команда процесса"],
  "workflow_detail.orbit_roles_note": ["Roles · not live agents", "Роли · не живые агенты"],
  "workflow_detail.orbit_unassigned": ["Human & unassigned", "Человек и без роли"],
  "workflow_detail.orbit_selected": ["Selected", "Выбрано"],
  "workflow_detail.orbit_steps_one": ["{count} step", "Шагов: {count}"],
  "workflow_detail.orbit_steps": ["{count} steps", "Шагов: {count}"],
  "workflow_detail.orbit_no_roles": ["No roles yet", "Ролей пока нет"],
  "workflow_detail.orbit_choose_step": ["Choose a step to edit its assignment, execution limits, artifacts and verification in the inspector.", "Выберите шаг, чтобы изменить в инспекторе его назначение, пределы исполнения, документы и проверку."],
  "workflow_detail.orbit_empty": ["Add a step to build your team.", "Добавьте шаг, чтобы собрать команду."],
  "workflow_detail.orbit_positions_note": ["Orbit positions are navigation, not execution order. Connections holds the actual routes. Harnesses and models are assigned when opening a run.", "Положение на орбите — навигация, а не порядок исполнения. Настоящие маршруты — во вкладке «Связи». Harness'ы и модели назначаются при открытии запуска."],
  "workflow_detail.orbit_duty_both": ["perform + verify", "выполняет + проверяет"],
  "workflow_detail.orbit_duty_perform": ["perform", "выполняет"],
  "workflow_detail.orbit_duty_verify": ["verify", "проверяет"],
  "workflow_detail.orbit_duty_gate": ["human decision", "решение человека"],
  "workflow_detail.orbit_duty_loop": ["loop control", "управление петлёй"],
  "workflow_detail.orbit_duty_none": ["not assigned", "не назначен"]
});
