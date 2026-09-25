"use strict";
export const RUNFORM_COPY = Object.freeze({
  "runform.m1": [
    "This screen was mounted without an editOpening handler.",
    "В этом экране не подключено редактирование запуска."
  ],
  "runform.m2": [
    "This build does not describe that mode.",
    "Описание этого режима отсутствует."
  ],
  "runform.m3": [
    "Open a run",
    "Открыть запуск"
  ],
  "runform.m4": [
    "A run follows a PUBLISHED revision, and this workflow has none yet. Publishing the draft is what makes one.",
    "Для запуска нужна опубликованная версия процесса. Сначала опубликуйте черновик."
  ],
  "runform.m5": [
    "Run id",
    "ID запуска"
  ],
  "runform.m6": [
    "Cycle id",
    "ID цикла"
  ],
  "runform.m7": [
    "Authority (mode)",
    "Режим управления"
  ],
  "runform.m8": [
    "no participant",
    "участник не выбран"
  ],
  "runform.m9": [
    "Harness default (unpinned)",
    "По умолчанию в harness"
  ],
  "runform.m10": [
    "Optional full model ID. This form checks identifier syntax, not model availability or whether the harness supports model routing.",
    "Необязательный полный ID модели. Проверяется формат ID, но не доступность модели и не поддержка её выбора в harness."
  ],
  "runform.m11": [
    "No provider on this machine is available, so no role can be bound. The Agents screen names the file to write.",
    "На этом компьютере нет доступных провайдеров. Настройте их на экране участников, чтобы назначить роли."
  ],
  "runform.m12": [
    "Each role binds a configured harness and an optional full model ID. Blank means the harness default (unpinned); changing harness clears its model. Model availability is not checked here. The server freezes these choices; no paths, argv or credentials are sent.",
    "Для каждой роли выберите настроенный harness и, при необходимости, полный ID модели. Пустое поле оставляет модель по умолчанию. Смена harness очищает модель. Выбор фиксируется на всё время запуска; доступность модели здесь не проверяется."
  ],
  "runform.m13": [
    "Open the run",
    "Создать запуск"
  ],
  "runform.m14": [
    "This screen was mounted without an onOpenRun handler.",
    "В этом экране не подключено создание запуска."
  ],
  "runform.m15": [
    "Choose or create a readable task above before opening a new run.",
    "Перед созданием запуска выберите или создайте доступную задачу выше."
  ],
  "runform.m16": [
    "Role {role}",
    "Роль {role}"
  ],
  "runform.m17": [
    "Model: {role}",
    "Модель: {role}"
  ],
  "runform.m18": [
    "Revision {revision} names no role, so a run of it binds nobody.",
    "В версии {revision} роли не заданы; в запуске не будет участников."
  ],
  "runform.not_stated": [
    "not stated",
    "не указано"
  ],
  "runform.mode_observe": [
    "Nothing is proposed and nothing runs. The run watches.",
    "Только наблюдение. Работа не предлагается и не исполняется."
  ],
  "runform.mode_propose": [
    "Steps may be proposed, and nothing can confirm one here. Nothing is carried out.",
    "Можно предлагать шаги, но нельзя разрешить их исполнение. Ничего не исполняется."
  ],
  "runform.mode_confirm": [
    "Every effecting step waits for a person before it is carried out.",
    "Каждый шаг с последствиями ждёт подтверждения человека."
  ],
  "runform.mode_policy": [
    "Bounded automatic work requires a separate human preview and permission. Opening the run grants no execution permission.",
    "Автоматическая работа в заданных пределах требует отдельного предпросмотра и разрешения человека. Создание запуска ничего не разрешает."
  ],
  "runform.label_observe": [
    "Observe",
    "Наблюдение"
  ],
  "runform.label_propose": [
    "Propose",
    "Предложения"
  ],
  "runform.label_confirm": [
    "Confirm each step",
    "Подтверждение шагов"
  ],
  "runform.label_policy": [
    "Bounded automation",
    "Автоматически в заданных пределах"
  ]
});
