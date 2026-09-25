"use strict";
// Interface copy only; document bytes and protocol IDs remain data.
export const RUN_DOCS_COPY = Object.freeze({
  "run_docs.not_stated": [
    "not stated",
    "не указано"
  ],
  "run_docs.missing_handler": [
    "This screen was mounted without a {name} handler.",
    "Для этого экрана не подключён обработчик {name}."
  ],
  "run_docs.choose_reference": [
    "Choose the reference this document answers.",
    "Выберите имя материала, которому соответствует документ."
  ],
  "run_docs.empty_body": [
    "Write the document: an empty body is refused at the boundary.",
    "Введите содержимое документа: пустой текст не принимается."
  ],
  "run_docs.over_limit": [
    "This document is {over} bytes over the {limit}-byte bound, so it cannot be published.",
    "Документ превышает предел {limit} байт на {over} байт; опубликовать его нельзя."
  ],
  "run_docs.size": [
    "{bytes} of {limit} bytes",
    "{bytes} из {limit} байт"
  ],
  "run_docs.body_label": [
    "The document (up to {limit} bytes of UTF-8)",
    "Документ (до {limit} байт UTF-8)"
  ],
  "run_docs.channel_argv": [
    "{adapter} receives its task on the command line: the whole command — this document, the instruction and every other input included — must fit in {limit} UTF-16 code units, its terminating NUL included. A larger task is refused before it starts.",
    "{adapter} получает задачу в командной строке: вся команда — вместе с этим документом, инструкцией и остальными входами — должна уместиться в {limit} единиц UTF-16 с завершающим NUL. Более крупная задача отклоняется до запуска."
  ],
  "run_docs.channel_stdin": [
    "{adapter} receives its task on standard input: the whole task — this document, the instruction and every other input included — must fit in {limit} bytes of UTF-8. A larger task is refused before it starts.",
    "{adapter} получает задачу через стандартный ввод: вся задача — вместе с этим документом, инструкцией и остальными входами — должна уместиться в {limit} байт UTF-8. Более крупная задача отклоняется до запуска."
  ],
  "run_docs.no_source": [
    "This run holds no document yet to start from.",
    "В запуске ещё нет документа, который можно взять за основу."
  ],
  "run_docs.copy": [
    "Copy into the editor",
    "Скопировать в редактор"
  ],
  "run_docs.start_from": [
    "Start from an existing document",
    "Взять за основу существующий документ"
  ],
  "run_docs.publish_this": [
    "Publish this document",
    "Опубликовать документ"
  ],
  "run_docs.writing": [
    "Writing… this control is shut until the server answers and this run has been read again. What you have typed here is kept.",
    "Запись… управление закрыто до ответа сервера и повторного чтения запуска. Введённый текст сохранён."
  ],
  "run_docs.stream_down": [
    "The live connection is down, so nothing can be recorded until it is back. What you have typed here is kept.",
    "Связь прервана. Запись станет доступна после восстановления соединения. Введённый текст сохранён."
  ],
  "run_docs.heading": [
    "Publish a document",
    "Опубликовать документ"
  ],
  "run_docs.publish_note": [
    "A document published here is immutable and is never edited or removed: a second document under the same reference stands beside the first, and whatever is proposed afterwards binds the newest one standing when the proposal is written.",
    "Опубликованный документ нельзя изменить или удалить. Новый документ с тем же именем сохранится рядом с прежним. Последующие предложения связываются с самым новым документом на момент записи предложения."
  ],
  "run_docs.reference_placeholder": [
    "choose a reference",
    "выберите имя материала"
  ],
  "run_docs.reference_label": [
    "Reference this document answers",
    "Имя материала для этого документа"
  ],
  "run_docs.document_id": [
    "Document id",
    "Идентификатор документа"
  ],
  "run_docs.minted_id": [
    "minted from the reference once one is chosen",
    "будет создан после выбора имени материала"
  ],
  "run_docs.media_type": [
    "Kind of text",
    "Тип текста"
  ],
  "run_docs.size_label": [
    "Size",
    "Размер"
  ],
  "run_docs.ended": [
    "This run is over: {ending}. No step of it will read a document published now, so none is offered.",
    "Запуск завершён: {ending}. Ни один его шаг уже не прочитает новый документ, поэтому публикация недоступна."
  ],
  "run_docs.ending_recorded": [
    "its ending is recorded",
    "завершение записано"
  ],
  "run_docs.ending_plan": [
    "the plan is {status}",
    "состояние плана: {status}"
  ],
  "run_docs.ending_complete": [
    "complete",
    "завершён"
  ],
  "run_docs.ending_cancelled": [
    "cancelled",
    "отменён"
  ],
  "run_docs.ending_failed": [
    "failed",
    "ошибка"
  ],
  "run_docs.no_references": [
    "This run's plan names no document reference: no step reads one, so there is nothing a document published here could be for.",
    "В плане нет ссылок на документы: ни один шаг не читает их, поэтому публиковать документ здесь не требуется."
  ],
  "run_docs.unversioned": [
    "This proposal has no material-binding revision. Its history is readable, but this window cannot claim that the proposal bound the documents shown now.",
    "У предложения нет версии привязки материалов. История доступна, но нельзя утверждать, что предложение связано с документами, показанными сейчас."
  ],
  "run_docs.bound_instruction": [
    "Instruction {ref} bound by {proposal}",
    "Инструкция {ref}, привязанная предложением {proposal}"
  ],
  "run_docs.local_instruction": [
    "the machine's instructions/{ref}.md, if it exists",
    "локальный файл instructions/{ref}.md, если он существует"
  ],
  "run_docs.bound_document": [
    "durable document {id}",
    "сохранённый документ {id}"
  ],
  "run_docs.bound_input": [
    "Input {ref} bound by {proposal}",
    "Входной материал {ref}, привязанный предложением {proposal}"
  ],
  "run_docs.missing_document": [
    "no durable document",
    "сохранённого документа нет"
  ],
  "run_docs.published": [
    "The document is a durable record in this run's journal. A step waiting for its reference is offered on the read that follows, and a proposal made from now on binds it.",
    "Документ сохранён в журнале запуска. После обновления станет доступен ожидающий его шаг; новые предложения будут связаны с этим документом."
  ]
});
