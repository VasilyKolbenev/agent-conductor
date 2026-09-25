"use strict";
// Interface copy only; identifiers and server-authored evidence are never translated here.
export const AGENTS_COPY = Object.freeze({
  "agents.handler_missing": [
    "This screen was mounted without a {name} handler.",
    "В этом экране не подключено действие {name}."
  ],
  "agents.not_recorded": [
    "not recorded by this build",
    "эта версия не сохраняет эти данные"
  ],
  "agents.not_stated": [
    "not stated",
    "не указано"
  ],
  "agents.workflow_says": [
    "The workflow says",
    "В процессе указано"
  ],
  "agents.authority": [
    "This run's authority",
    "Полномочия запуска"
  ],
  "agents.receipt": [
    "Receipt",
    "Квитанция"
  ],
  "agents.answer": [
    "Answer",
    "Ответ"
  ],
  "agents.causes": [
    "Causes the gate to become",
    "Состояние после ответа"
  ],
  "agents.actor": [
    "Decided by",
    "Кто решил"
  ],
  "agents.decided_at": [
    "Decided at",
    "Время решения"
  ],
  "agents.reason": [
    "Reason",
    "Причина"
  ],
  "agents.supersedes": [
    "Supersedes",
    "Заменяет"
  ],
  "agents.configuration": [
    "Against configuration",
    "Для конфигурации"
  ],
  "agents.step": [
    "The step",
    "Шаг"
  ],
  "agents.gate": [
    "The gate",
    "Контрольная точка"
  ],
  "agents.run": [
    "In run",
    "В запуске"
  ],
  "agents.run_command": [
    "Run this",
    "Выполните"
  ],
  "agents.writes": [
    "It writes",
    "Записывает"
  ],
  "agents.required_fields": [
    "Each row carries",
    "Обязательные поля"
  ],
  "agents.optional_fields": [
    "And may also carry",
    "Необязательные поля"
  ],
  "agents.restart": [
    "Then restart with",
    "Затем перезапустите"
  ],
  "agents.proven_controls": [
    "Capabilities it is proven to serve",
    "Подтверждённые возможности"
  ],
  "agents.provider": [
    "Carried by",
    "Провайдер"
  ],
  "agents.model": [
    "Model",
    "Модель"
  ],
  "agents.binding_controls": [
    "Capabilities this binding may be asked for",
    "Разрешённые возможности участника"
  ],
  "agents.bound_run": [
    "Frozen into run",
    "Закреплён в запуске"
  ],
  "agents.roles": [
    "Roles it carries",
    "Роли участника"
  ],
  "agents.receipt_title": [
    "The receipt this decision wrote",
    "Квитанция этого решения"
  ],
  "agents.choose_answer": [
    "Choose one of the four answers.",
    "Выберите один из четырёх ответов."
  ],
  "agents.answer_choices": [
    "Your answer, and what each one causes",
    "Ваш ответ и его последствия"
  ],
  "agents.record_decision": [
    "Record this decision",
    "Записать решение"
  ],
  "agents.unblocks": [
    "What becomes runnable once this is answered",
    "Какие шаги открывает ответ"
  ],
  "agents.decisions": [
    "Decisions",
    "Решения"
  ],
  "agents.no_provider": [
    "No provider is configured",
    "Провайдеры не настроены"
  ],
  "agents.harnesses": [
    "Harnesses this build and this machine can reach",
    "Доступные на этом компьютере инструменты"
  ],
  "agents.participants": [
    "Participants",
    "Участники"
  ],
  "agents.agents": [
    "Agents",
    "Участники"
  ],
  "agents.halted": [
    "Nothing further is offered in this run: it was halted.",
    "Запуск остановлен; дальнейшие действия недоступны."
  ],
  "agents.availability_available": [
    "This machine can start it.",
    "Этот компьютер может запустить инструмент."
  ],
  "agents.availability_executable_absent": [
    "The pinned executable is not where the config says.",
    "Исполняемый файл отсутствует по указанному пути."
  ],
  "agents.availability_version_mismatch": [
    "The executable is there and is not the pinned version.",
    "Исполняемый файл найден, но его версия отличается от закреплённой."
  ],
  "agents.availability_unconfigured": [
    "No provider configuration names it, so nothing was looked at.",
    "Настройка провайдера отсутствует; проверка не выполнялась."
  ],
  "agents.availability_unknown": [
    "This build does not describe that machine state.",
    "Эта версия не описывает такое состояние компьютера."
  ],
  "agents.implementation_real_experimental": [
    "This build talks to the real product, experimentally.",
    "Эта версия экспериментально работает с настоящим продуктом."
  ],
  "agents.implementation_fixture_only": [
    "This build answers from a fixture and starts nothing.",
    "Эта версия отвечает тестовыми данными и ничего не запускает."
  ],
  "agents.implementation_unproven": [
    "This build claims nothing about how it would talk to it.",
    "Способ работы с продуктом в этой версии не подтверждён."
  ],
  "agents.implementation_unknown": [
    "This build does not describe that transport state.",
    "Эта версия не описывает такой способ подключения."
  ],
  "agents.auth_api_key": [
    "Configured to read a credential from the environment.",
    "Настроено чтение ключа из окружения."
  ],
  "agents.auth_subscription": [
    "Configured to use the vendor's own login, kept in its own directory.",
    "Настроена собственная авторизация провайдера в отдельном каталоге."
  ],
  "agents.auth_unpinned": [
    "No provider configuration names it, so no login was pinned.",
    "Настройка провайдера отсутствует; способ входа не закреплён."
  ],
  "agents.auth_unknown": [
    "This build does not describe that login state.",
    "Эта версия не описывает такой способ входа."
  ],
  "agents.decision_approve": [
    "The work behind this gate is accepted and the plan may go on.",
    "Работа за этой точкой принята; план может продолжаться."
  ],
  "agents.decision_reject": [
    "The work behind this gate is refused. The plan does not go on.",
    "Работа за этой точкой отклонена; план не продолжается."
  ],
  "agents.decision_request_changes": [
    "The work is sent back for changes. Say what must change.",
    "Работа возвращается на доработку. Укажите, что изменить."
  ],
  "agents.decision_waive": [
    "The gate is set aside without judging the work. Say why.",
    "Точка пропускается без оценки работы. Укажите причину."
  ],
  "agents.gate_explainer": [
    "A gate is a step the plan itself marks as needing a person's answer. Nothing behind it is carried out until one is recorded, and no amount of waiting changes that.",
    "План требует ответа человека в этой точке. Следующие действия не выполняются, пока ответ не записан."
  ],
  "agents.unblocks_unknown": [
    "What becomes runnable is read off the plan's edges. This view was not given them for this gate, so nothing here claims to know.",
    "Дальнейшие шаги определяются связями плана. Для этой точки связи не получены; доступные шаги неизвестны."
  ],
  "agents.immutable": [
    "A decision is immutable. It is corrected only by a later receipt that supersedes it, and both stay in the journal.",
    "Решение неизменно. Исправление создаёт новую квитанцию, заменяющую прежнюю; обе остаются в журнале."
  ],
  "agents.actor_hint": [
    "Type who is deciding, as a plain id: letters, digits, dot, underscore or hyphen, up to 128 characters.",
    "Укажите идентификатор автора решения: латинские буквы, цифры, точка, подчёркивание или дефис; не более 128 символов."
  ],
  "agents.approval_required": [
    "This gate requires explicit human approval, so it cannot be waived. Approve it, reject it, or ask for changes.",
    "Эта точка требует явного одобрения человека и не может быть пропущена. Одобрите, отклоните или запросите изменения."
  ],
  "agents.submit_missing": [
    "This screen was mounted without a submitDecision handler, so nothing here can be recorded.",
    "Запись решений в этом экране не подключена."
  ],
  "agents.edit_missing": [
    "This screen was mounted without an editDecision handler, so these controls cannot take an answer.",
    "Ввод решения в этом экране не подключён."
  ],
  "agents.contradiction": [
    "This gate's recorded answers contradict each other; the journal supports no answer and the screen offers none.",
    "Записанные ответы противоречат друг другу. Действующий ответ не установлен; новое решение недоступно."
  ],
  "agents.schedule_missing": [
    "This build was not given this run's schedule, so this window cannot say whether the plan has reached this gate. It offers no answer rather than guessing at one.",
    "Расписание запуска не получено. Неизвестно, достигнута ли эта точка; запись ответа недоступна."
  ],
  "agents.unreachable": [
    "This gate will never be asked: what leads to it is unreachable too.",
    "Эта точка не будет достигнута: ведущие к ней шаги недоступны."
  ],
  "agents.receipt_missing": [
    "This view was not given the receipt behind that answer. It is in the run's journal, on the Runs screen.",
    "Квитанция этого ответа не получена. Она хранится в журнале на экране запусков."
  ],
  "agents.no_decisions": [
    "Nothing is waiting for you. When a run reaches a gate, the step and its choices appear here.",
    "Ожидающих решений нет. Когда запуск достигнет контрольной точки, здесь появятся шаг и варианты ответа."
  ],
  "agents.decisions_lede": [
    "Every answer here becomes an immutable receipt in the run's own journal. Nothing is executed by answering; a decision changes what the plan is allowed to do next, and nothing else.",
    "Ответ записывается как неизменная квитанция в журнал запуска. Сам ответ ничего не выполняет: он определяет разрешённые дальнейшие шаги плана."
  ],
  "agents.choose_gate": [
    "Choose a gate on the left to see why it is asking and what each answer causes.",
    "Выберите точку слева, чтобы узнать причину запроса и последствия каждого ответа."
  ],
  "agents.no_provider_explainer": [
    "This build resolved no provider, so nothing on this machine can carry out a step. That is a configuration this project does not have yet, not a failure.",
    "Провайдеры ещё не настроены. Чтобы выполнять шаги на этом компьютере, сначала добавьте настройку."
  ],
  "agents.setup_explainer": [
    "It asks which harness you have, where it is on this machine, and which environment variables it may read — NAMES only. It never asks for a credential: a value is read from your environment when a step runs and is written down nowhere.",
    "Команда запросит инструмент, путь к нему и имена разрешённых переменных окружения. Секретные значения вводить не нужно: они читаются из окружения при запуске шага."
  ],
  "agents.provider_explainer": [
    "Three facts per row, and they answer different questions. What the MACHINE resolved is whether the pinned executable is there; what the BUILD claims is whether this version talks to the real product or answers from a fixture; what the CONFIG pinned is which login it would use. None is read off another, and none of them is evidence that a real authenticated run ever happened.",
    "Для каждого инструмента отдельно показаны наличие исполняемого файла, реализация подключения и настроенный способ входа. Эти сведения сами по себе не подтверждают успешный запуск с авторизацией."
  ],
  "agents.model_unpinned": [
    "No model was pinned for this instance, so whatever the provider's own configuration decides is what runs. That is not a default this screen chose.",
    "Для участника модель не закреплена. Её выбирает собственная настройка провайдера."
  ],
  "agents.provider_unknown": [
    "This build's roster carries no provider by that name, so nothing here can say whether this machine could still start it.",
    "Такого провайдера нет в текущем списке. Возможность запуска на этом компьютере неизвестна."
  ],
  "agents.roles_unknown": [
    "A materialized plan names instances, not roles: the role is a workflow document's word and it is not carried into the run's plan.",
    "План запуска содержит участников. Названия ролей из документа процесса в нём не сохранены."
  ],
  "agents.no_participants": [
    "No run in view binds anybody yet. A participant exists only inside a run: opening one is what binds an instance to a provider and freezes it for that run's whole life.",
    "В показанных запусках участников пока нет. При создании запуска участник связывается с провайдером на всё время этого запуска."
  ],
  "agents.participant_explainer": [
    "A participant is one instance a run bound to one provider, frozen when the run was opened. It never changes afterwards, which is why it can disagree with the roster above.",
    "Участник связан с одним провайдером при создании запуска. Привязка неизменна и может отличаться от текущих настроек выше."
  ],
  "agents.agents_lede": [
    "A workflow names roles. A run binds each role to a participant, and a participant names one configured provider and at most one model. Nothing in a workflow document may name a provider, a model or a run.",
    "Процесс задаёт роли. В запуске роли связываются с участниками, а участники — с настроенными провайдерами и при необходимости с моделями."
  ],
  "agents.opens_on": [
    "opens on {condition}",
    "открывается при {condition}"
  ],
  "agents.gate_state": [
    "gate {decision}",
    "точка: {decision}"
  ],
  "agents.reason_required": [
    "A reason is required when the answer is {action}.",
    "Для ответа {action} обязательна причина."
  ],
  "agents.causes_state": [
    "causes: {decision}",
    "результат: {decision}"
  ],
  "agents.reopened": [
    "This gate was already answered. Answering it now writes a receipt that supersedes {receipt}; both stay in the journal, and a decision is never edited.",
    "Ответ уже записан. Новый ответ создаст квитанцию вместо {receipt}; обе сохранятся в журнале. Прежнее решение не редактируется."
  ],
  "agents.reason_limit": [
    "Reason (up to {limit} characters)",
    "Причина (до {limit} символов)"
  ],
  "agents.stream_down": [
    "The live connection is down, so nothing can be recorded until it is back. What you have typed here is kept.",
    "Связь прервана. Запись недоступна до восстановления связи; введённый текст сохранён."
  ],
  "agents.ended": [
    "This run has ended (Plan: {plan}); no decision can be recorded.",
    "Запуск окончен (план: {plan}); запись решений недоступна."
  ],
  "agents.waiting": [
    "This gate cannot be answered yet. ALL incoming roads must open before this step may run. Waiting on: {waiting}.",
    "Ответ пока недоступен: все входящие связи должны быть выполнены. Ожидаются: {waiting}."
  ],
  "agents.closed": [
    "This gate will never be asked: the road into it was closed by {closed}.",
    "Точка не будет достигнута: входящую ветку закрыли {closed}."
  ],
  "agents.machine_state": [
    "on this machine: {availability}",
    "на этом компьютере: {availability}"
  ],
  "agents.quota_no_data": [
    "No readings are available.",
    "Показания недоступны."
  ],
  "agents.quota_source_error": [
    "The source could not be read.",
    "Не удалось прочитать источник."
  ],
  "agents.quota_not_authenticated": [
    "The source did not confirm a signed-in account.",
    "Источник не подтвердил авторизацию."
  ],
  "agents.quota_not_supported": [
    "This source does not provide readings.",
    "Этот источник не предоставляет показаний."
  ],
  "agents.quota_malformed_payload": [
    "The source returned unreadable data.",
    "Источник вернул некорректные данные."
  ],
  "agents.quota_empty": [
    "Usage has not been read yet.",
    "Показания ещё не прочитаны."
  ],
  "agents.quota_loading": [
    "Reading usage…",
    "Чтение показаний…"
  ],
  "agents.quota_failed": [
    "Usage could not be read. Refresh usage to retry.",
    "Не удалось прочитать показания. Нажмите «Обновить», чтобы повторить."
  ],
  "agents.quota_disconnected": [
    "Connection lost. Usage will refresh after reconnecting.",
    "Связь потеряна. Показания обновятся после подключения."
  ],
  "agents.quota_unavailable": [
    "Unavailable",
    "Недоступно"
  ],
  "agents.quota_stale_window": [
    "Stale window — current allowance is unknown.",
    "Окно устарело — текущий остаток неизвестен."
  ],
  "agents.quota_reset_window": [
    "Window reset after this reading — its current allowance is unknown.",
    "Окно сброшено после этого показания — текущий остаток неизвестен."
  ],
  "agents.quota_deferred": [
    "Update deferred: a step is running (last try {at}). Shown is the last reading, with its own time.",
    "Обновление отложено: идёт шаг (последняя попытка {at}). Показано последнее показание с его собственным временем."
  ],
  "agents.quota_current": [
    "Current at last read",
    "Актуально при последнем чтении"
  ],
  "agents.quota_used": [
    "Used",
    "Использовано"
  ],
  "agents.quota_remaining": [
    "Remaining",
    "Осталось"
  ],
  "agents.quota_resets": [
    "Resets",
    "Сброс"
  ],
  "agents.quota_starts": [
    "Starts",
    "Начало"
  ],
  "agents.quota_window": [
    "Window",
    "Период"
  ],
  "agents.quota_total": [
    "Total balance",
    "Общий баланс"
  ],
  "agents.quota_granted": [
    "Granted balance",
    "Предоставленный баланс"
  ],
  "agents.quota_topped": [
    "Topped-up balance",
    "Пополненный баланс"
  ],
  "agents.quota_unknown_account": [
    "Billing account unknown. This reading is kept separate from other agents.",
    "Платёжный аккаунт неизвестен. Показание хранится отдельно от других участников."
  ],
  "agents.quota_verified": [
    "Verified billing account. Listed agents share this account and source.",
    "Платёжный аккаунт подтверждён. Перечисленные участники используют один аккаунт и источник."
  ],
  "agents.quota_source": [
    "Source",
    "Источник"
  ],
  "agents.quota_observed": [
    "Observed",
    "Время наблюдения"
  ],
  "agents.quota_freshness": [
    "Freshness",
    "Свежесть"
  ],
  "agents.quota_stale": [
    "Stale — current values are unknown",
    "Данные устарели; текущие значения неизвестны"
  ],
  "agents.quota_no_observation": [
    "No observation",
    "Наблюдения нет"
  ],
  "agents.quota_funds": [
    "Source reports funds available",
    "Источник сообщает о доступности средств"
  ],
  "agents.quota_yes": [
    "Yes",
    "Да"
  ],
  "agents.quota_no": [
    "No",
    "Нет"
  ],
  "agents.quota_reset": [
    "Reset",
    "Сброс"
  ],
  "agents.quota_reset_na": [
    "Not applicable (monetary balance)",
    "Не применяется к денежному балансу"
  ],
  "agents.quota_refresh": [
    "Refresh usage",
    "Обновить показания"
  ],
  "agents.quota_title": [
    "Usage and reset",
    "Лимиты, баланс и сброс"
  ],
  "agents.quota_intro": [
    "Latest available readings, refreshed every minute while this page is open.",
    "Последние доступные показания. Пока страница открыта, они обновляются каждую минуту."
  ],
  "agents.quota_previous": [
    "Previous read retained below; its current status is unconfirmed.",
    "Ниже сохранены прежние показания; их текущее состояние не подтверждено."
  ],
  "agents.quota_empty_catalog": [
    "The catalog contains no providers.",
    "В каталоге нет провайдеров."
  ],
  "agents.quota_minutes": [
    "{minutes} minutes",
    "{minutes} мин."
  ],
  "agents.quota_error": [
    "Source error. {reason}",
    "Ошибка источника. {reason}"
  ],
  "agents.quota_no_data_prefix": [
    "Data unavailable. {reason}",
    "Данные недоступны. {reason}"
  ],
  "agents.quota_cache": [
    "Cache checked: {at}. Freshness limit: {seconds} seconds.",
    "Кэш проверен: {at}. Срок актуальности: {seconds} с."
  ],
  "agents.isolation_before": [
    "Stopped before the step runs",
    "Отказ до запуска шага"
  ],
  "agents.isolation_after": [
    "Noticed only after it has run",
    "Обнаружение после запуска"
  ],
  "agents.isolation_absent": [
    "Not confined by this build",
    "Эта версия не ограничивает"
  ],
  "agents.isolation_unsettled": [
    "Not established for this configuration",
    "Для этой настройки не установлено"
  ],
  "agents.isolation_unknown": [
    "Not established for this configuration — nothing here says it does or does not stand.",
    "Для этой настройки не установлено, действует ли защита."
  ],
  "agents.isolation_not_applicable": [
    "Not a protection this configuration has: it needs something this run did not ask for.",
    "В этой настройке защита не применяется: для неё нужны условия, которые запуск не запрашивал."
  ],
  "agents.isolation_vendor_unknown": [
    "This integration carries no reviewed declaration for this provider, so nothing is stated here either way — neither that a vendor sandbox mode is requested nor that none is.",
    "Для этого провайдера нет проверенного описания интеграции. Не установлено, запрашивает ли она режим изоляции провайдера."
  ],
  "agents.isolation_vendor_none": [
    "This integration reviewed this provider and requests NO vendor sandbox mode on any road. That is a statement about what this build asks for, not a finding that the vendor ships none.",
    "Интеграция проверена: ни на одном пути она не запрашивает режим изоляции провайдера. Это описание запроса этой версии, а не возможностей самого провайдера."
  ],
  "agents.isolation_requested": [
    "Requested of the vendor — {requests}. Whether the platform enforces it is the vendor's business, not a boundary this build imposes.",
    "У провайдера запрошено: {requests}. Применение этих ограничений зависит от платформы провайдера; сама эта версия их не обеспечивает."
  ],
  "agents.isolation_summary": [
    "{count} checks stand for {instance} · {adapter} on the {capability} road. This build starts an ordinary process with your own rights.",
    "Действующих проверок: {count}; участник {instance} · {adapter}, путь {capability}. Эта версия запускает обычный процесс с вашими правами."
  ],
  "agents.isolation_summary_one": [
    "{count} check stand for {instance} · {adapter} on the {capability} road. This build starts an ordinary process with your own rights.",
    "Действующих проверок: {count}; участник {instance} · {adapter}, путь {capability}. Эта версия запускает обычный процесс с вашими правами."
  ],
  "agents.isolation_details": [
    "What that means",
    "Что это означает"
  ]
});
