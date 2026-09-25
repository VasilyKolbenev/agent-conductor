"use strict";
// Interface messages only; user text and protocol values stay unchanged.
export const RUN_STEP_COPY = Object.freeze({
  "runstep.not_stated": [
    "not stated",
    "не указано"
  ],
  "runstep.missing_handler": [
    "This screen was mounted without a {name} handler.",
    "Этот экран открыт без обработчика {name}."
  ],
  "runstep.controls_missing": [
    "This run's controls read has not landed here, so this window cannot say whether any adapter serves {pair}.",
    "Сведения о доступных действиях этого запуска ещё не получены. Пока неизвестно, обслуживает ли какой-либо адаптер пару {pair}."
  ],
  "runstep.adapter_missing": [
    "This build serves no adapter for {pair}, so nothing here can carry this step out. The step is offered and the control is shut.",
    "В этой сборке нет адаптера для пары {pair}, поэтому выполнить шаг здесь нельзя. Шаг показан, но кнопка недоступна."
  ],
  "runstep.confirm_road": [
    "To carry a step out, open a new run of this workflow's published revision with authority confirm: the Open a run form on the Workflow screen grants it explicitly.",
    "Чтобы выполнить шаг, откройте новый запуск опубликованной версии этого процесса в режиме подтверждения (confirm). Этот режим явно задаётся в форме «Открыть запуск» на экране процесса."
  ],
  "runstep.no_workflow_road": [
    "This run follows no workflow. To carry a step out, publish a workflow and open a run of it with authority confirm: the Open a run form on the Workflow screen grants it explicitly.",
    "Этот запуск не связан с процессом. Чтобы выполнить шаг, опубликуйте процесс и откройте его запуск в режиме подтверждения (confirm). Этот режим явно задаётся в форме «Открыть запуск» на экране процесса."
  ],
  "runstep.nothing_permitted": [
    "This run's authority is {mode}: nothing may be proposed on it and nothing runs. {road}",
    "Режим этого запуска — {mode}: предложения и исполнение недоступны. {road}"
  ],
  "runstep.proposals_only": [
    "A proposal stands on this step and this run's authority is {mode}: nothing can confirm it here. {road}",
    "Для этого шага уже есть предложение. Режим запуска — {mode}: подтвердить предложение здесь нельзя. {road}"
  ],
  "runstep.proposed_under": [
    "In a {mode} run a proposal is a durable record and nothing carries it out here.",
    "В режиме {mode} предложение сохраняется в журнале; эта форма не запускает его исполнение."
  ],
  "runstep.mode_observe": [
    "observe",
    "наблюдение (observe)"
  ],
  "runstep.mode_propose": [
    "propose",
    "предложения (propose)"
  ],
  "runstep.mode_confirm": [
    "confirm",
    "подтверждение (confirm)"
  ],
  "runstep.mode_policy": [
    "policy",
    "ограниченное автоматическое выполнение (policy)"
  ],
  "runstep.instruction": [
    "Instruction {ref}",
    "Инструкция {ref}"
  ],
  "runstep.input": [
    "Input {ref}",
    "Входной документ {ref}"
  ],
  "runstep.no_document": [
    "no durable document",
    "нет сохранённого документа"
  ],
  "runstep.instruction_missing_bound": [
    "No document stood under {ref} when this proposal was written, so the machine's instructions/{ref}.md is read if it exists and the attempt is refused before anything is spawned if not.",
    "На момент записи предложения документа с именем {ref} не было. Будет прочитан файл instructions/{ref}.md на этой машине; если его нет, попытка будет отклонена до запуска процесса."
  ],
  "runstep.instruction_missing_now": [
    "No document stands under {ref} in this run, so a proposal made now binds the machine's instructions/{ref}.md if it exists -- or is refused before anything is spawned. Publish a document under {ref} below, and a proposal made after that binds it.",
    "В этом запуске нет документа с именем {ref}. Новое предложение привяжет файл instructions/{ref}.md на этой машине, если он есть; иначе получит отказ до запуска процесса. Опубликуйте ниже документ с именем {ref}, чтобы следующее предложение привязало его."
  ],
  "runstep.document": [
    "durable document {artifact} · {bytes} bytes · written {at}",
    "сохранённый документ {artifact} · {bytes} байт · записан {at}"
  ],
  "runstep.instruction_bound": [
    "The one standing when this proposal was written: confirming this proposal runs it. A document published since is durable and is not what runs; the newest one standing is bound by the next proposal made on this step, once this attempt has answered.",
    "Это документ на момент записи предложения: подтверждение запустит именно его. Документ, опубликованный позже, сохранён, но здесь не исполняется. После завершения этой попытки следующее предложение шага привяжет новейший документ."
  ],
  "runstep.instruction_now": [
    "The one standing now: a proposal made now binds it, and a document published after that proposal is not what runs.",
    "Это текущий документ: новое предложение привяжет его. Документ, опубликованный после предложения, не заменит исполняемый материал."
  ],
  "runstep.input_missing": [
    "no durable document -- the attempt is refused before anything is spawned",
    "нет сохранённого документа — попытка будет отклонена до запуска процесса"
  ],
  "runstep.inputs_bound": [
    "Each input is the document standing when this proposal was written; the child reads exactly these, whatever is published since.",
    "Каждый входной документ выбран на момент записи предложения. Процесс прочитает именно эти документы, независимо от более поздних публикаций."
  ],
  "runstep.inputs_now": [
    "Each input is the newest document standing under its reference now: a proposal made now binds these, and one published after it is not what the child reads.",
    "Показаны новейшие входные документы с указанными именами. Новое предложение привяжет их; документы, опубликованные позже, не заменят материалы процесса."
  ],
  "runstep.step": [
    "Step",
    "Шаг"
  ],
  "runstep.instance": [
    "Instance",
    "Участник"
  ],
  "runstep.capability": [
    "Capability",
    "Действие"
  ],
  "runstep.arguments": [
    "Arguments",
    "Аргументы"
  ],
  "runstep.longest": [
    "Longest this may run",
    "Максимальное время исполнения"
  ],
  "runstep.attempt_id": [
    "Attempt id",
    "Идентификатор попытки"
  ],
  "runstep.scope": [
    "Scope",
    "Область работы"
  ],
  "runstep.verifier": [
    "Independent verifier",
    "Независимый проверяющий"
  ],
  "runstep.materials": [
    "Verification materials",
    "Материалы проверки"
  ],
  "runstep.ceilings": [
    "Task time ceilings",
    "Предельное время задач"
  ],
  "runstep.proposal": [
    "Proposal",
    "Предложение"
  ],
  "runstep.proposed_at": [
    "Proposed at",
    "Предложено"
  ],
  "runstep.proposed_by": [
    "Proposed by",
    "Автор предложения"
  ],
  "runstep.why": [
    "Why",
    "Причина"
  ],
  "runstep.preview_digest": [
    "Preview digest",
    "Хеш предпросмотра"
  ],
  "runstep.config_digest": [
    "Against configuration",
    "Хеш конфигурации"
  ],
  "runstep.arguments_note": [
    "The arguments are the plan's own bytes. The server refuses a proposal that does not repeat them, so they are shown rather than offered.",
    "Аргументы точно соответствуют плану. Сервер отклонит предложение с другими значениями, поэтому здесь их можно только просмотреть."
  ],
  "runstep.seconds": [
    "{seconds}s",
    "{seconds} с"
  ],
  "runstep.timeout_note": [
    "The window asks for this step's own ceiling or {seconds}s, whichever is smaller. A plan may name a ceiling above what a run's budget allows, and an attempt past that budget is refused at the Confirm rather than here.",
    "Запрашивается предел этого шага или {seconds} с — меньшее из двух. План может задавать время выше бюджета запуска; превышение бюджета будет отклонено при подтверждении, а не в этой форме."
  ],
  "runstep.scope_note": [
    "Scope is a declaration this run's records carry, not a boundary this build enforces: nothing narrows what a step may touch by it, and the sandbox the adapter runs under is what does. It is stated here rather than typed, because a control over a value nothing reads would be a promise this build does not keep.",
    "Область работы записывается в журнал, но сама по себе в этой сборке не ограничивает доступ шага. Доступ ограничивает среда изоляции адаптера. Значение показано без редактирования, чтобы поле не обещало защиту, которую оно не обеспечивает."
  ],
  "runstep.same_adapter": [
    "Verified by the same participant's adapter over its own post-observation evidence; no independent checker is named by this step.",
    "Проверяет адаптер того же участника по собственным данным после исполнения. Независимый проверяющий для этого шага не назначен."
  ],
  "runstep.provider_default": [
    "provider default",
    "по умолчанию у провайдера"
  ],
  "runstep.binding_missing": [
    "{instance} · binding not available in this read",
    "{instance} · привязка отсутствует в полученных данных"
  ],
  "runstep.materials_dispatch": [
    "The instruction, input documents, the work item's file listing with digests, and the whole contents of changed files up to 32 KiB each. Under confirmation a larger file is listed by digest and available to the checker in its read-only work area; a bounded run refuses it before any check.",
    "Инструкция, входные документы, список файлов задачи с хешами и полное содержимое изменённых файлов до 32 КиБ каждый. При подтверждении более крупный файл указан по хешу и доступен проверяющему в его рабочей области только для чтения; ограниченный запуск отклоняет его до проверки."
  ],
  "runstep.materials_review": [
    "The result document this attempt produced and the input documents it was given.",
    "Документ результата этой попытки и переданные ей входные документы."
  ],
  "runstep.verification_frame": [
    "The complete encoded verification frame must fit 256 KiB. JSON expansion counts; an oversized frame refuses the check before it starts.",
    "Весь закодированный пакет проверки должен помещаться в 256 КиБ с учётом расширения при кодировании JSON. Превышение размера отклоняет проверку до её запуска."
  ],
  "runstep.verification_output": [
    "The checker's capture is bounded by its provider. Only the first non-empty verdict line is judged. Only an explicitly authorized bounded run may record typed correction findings: 1–16 findings within 8192 canonical UTF-8 bytes. Unstructured checker prose is not a durable result.",
    "Объём ответа проверяющего ограничен провайдером. Учитывается только первая непустая строка вердикта. Только явно разрешённый ограниченный запуск может записывать типизированные замечания для исправления: от 1 до 16 замечаний, не более 8192 байт канонического UTF-8. Свободный текст проверяющего не становится сохранённым результатом."
  ],
  "runstep.verification_ceiling": [
    "{ceiling}s for the attempt + {ceiling}s for one check (2 × {ceiling}s = {total}s combined task time). Bounded version preflights and setup add wall-clock time. This run's budget must cover both task ceilings.",
    "{ceiling} с на попытку + {ceiling} с на одну проверку (2 × {ceiling} с = {total} с общего времени задач). Проверка версии и подготовка добавляют время ожидания. Бюджет запуска должен покрывать оба предела."
  ],
  "runstep.writing": [
    "Writing… this control is shut until the server answers and this run has been read again. What you have typed here is kept.",
    "Запись… Кнопка недоступна до ответа сервера и повторного чтения запуска. Введённые данные сохранены."
  ],
  "runstep.stream_down": [
    "The live connection is down, so nothing can be recorded until it is back. What you have typed here is kept.",
    "Соединение прервано. Запись станет доступна после восстановления связи. Введённые данные сохранены."
  ],
  "runstep.propose_hint": [
    "Type who is proposing this step and why, and it can be written.",
    "Укажите автора предложения и причину, чтобы записать его."
  ],
  "runstep.proposer_invalid": [
    "Type who is proposing, as a plain id: letters, digits, dot, underscore or hyphen, up to 128 characters.",
    "Укажите автора предложения простым идентификатором: латинские буквы, цифры, точка, подчёркивание или дефис; не более 128 символов."
  ],
  "runstep.rationale_missing": [
    "Say why this step is being proposed. The reason becomes part of the durable record.",
    "Укажите, зачем предлагается этот шаг. Причина будет сохранена в журнале."
  ],
  "runstep.propose": [
    "Propose this step",
    "Предложить этот шаг"
  ],
  "runstep.proposed_note": [
    "A proposal is a durable record and runs nothing: it is a request for an attempt, and confirming it is what authorizes one.",
    "Предложение сохраняется в журнале и ничего не запускает. Оно запрашивает попытку; разрешение на неё даётся подтверждением."
  ],
  "runstep.rationale": [
    "Why (up to {limit} characters)",
    "Причина (до {limit} символов)"
  ],
  "runstep.unversioned": [
    "This proposal has no material-binding revision. Its history is readable, but this window cannot claim that the proposal bound the documents shown now.",
    "У этого предложения нет версии привязки материалов. Историю можно читать, но нельзя утверждать, что предложение привязало показанные сейчас документы."
  ],
  "runstep.confirmer_invalid": [
    "Type who is confirming, as a plain id: letters, digits, dot, underscore or hyphen, up to 128 characters.",
    "Укажите подтверждающего простым идентификатором: латинские буквы, цифры, точка, подчёркивание или дефис; не более 128 символов."
  ],
  "runstep.proposal_missing": [
    "This step reads as proposed and this window cannot find the proposal standing on it. Read the run again: nothing is offered against a record that is not there.",
    "Шаг отмечен как предложенный, но действующее предложение не найдено. Прочитайте запуск снова: без этой записи подтверждение недоступно."
  ],
  "runstep.confirm": [
    "Confirm this proposal",
    "Подтвердить это предложение"
  ],
  "runstep.requested_note": [
    "The request is a durable record. Whatever runs, runs on the server's worker; this window only reads.",
    "Запрос сохраняется в журнале. Исполнение происходит в рабочем процессе сервера; это окно только читает состояние."
  ],
  "runstep.read_again": [
    "Read again: this step is offered only while the run's plan calls it runnable and the request fits what the run allows; the run was read again.",
    "Запуск прочитан снова. Шаг доступен, только пока план допускает его исполнение, а запрос соответствует разрешениям запуска."
  ],
  "runstep.confirmed_by": [
    "Confirmed by",
    "Кто подтверждает"
  ],
  "runstep.authorize": [
    "Confirm and authorize",
    "Подтвердить и разрешить"
  ],
  "runstep.rebind": [
    "This proposal predates material binding. Create a new proposal below, review its materials, and confirm that one. The earlier proposal stays in the history.",
    "Это предложение создано до появления привязки материалов. Создайте ниже новое предложение, проверьте его материалы и подтвердите его. Прежнее предложение останется в истории."
  ]
});
