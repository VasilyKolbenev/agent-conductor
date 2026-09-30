"use strict";
// The words of the feed "Ход работы", English first and Russian second, like every other copy
// module of the panel: `studio-i18n.js` spreads this catalogue into the one table. A row of the
// feed is one sentence about one step of the plan, so each sentence carries the step's own title
// as a named parameter, never a joined string, and no message depends on a plural form. The words
// of an outcome (`scene.outcome_*`), of a duty (`scene.duty_*`) and of a finding's kind
// (`feedback.*`) are the Studio's own and are not said again here.
export const FEED_COPY = Object.freeze({
  // -- the head of the region ------------------------------------------------------------------
  "feed.title": ["Progress · run {run}", "Ход работы · запуск {run}"],
  "feed.order": ["newest at the bottom", "новые внизу"],
  "feed.none": ["The journal of this run holds no record the feed draws yet.",
    "В журнале этого запуска пока нет записей для ленты."],
  // -- who a row belongs to --------------------------------------------------------------------
  "feed.person": ["Person", "Человек"],
  "feed.participant_unknown": ["Unknown participant", "Неизвестный участник"],
  "feed.step_none": ["a step the plan does not name", "шаг, которого нет в плане"],
  "feed.gate_none": ["a gate the plan does not name", "точка, которой нет в плане"],
  // -- what a row says --------------------------------------------------------------------------
  "feed.proposed": ["Step “{step}” proposed", "Предложен шаг «{step}»"],
  "feed.started": ["Started step “{step}”", "Начат шаг «{step}»"],
  "feed.live": ["in progress", "идёт"],
  "feed.result": ["Result of step “{step}”: {word}", "Результат шага «{step}»: {word}"],
  "feed.verdict": ["Check of step “{step}”: {word}", "Проверка шага «{step}»: {word}"],
  "feed.verdict_verified": ["passed", "пройдена"],
  "feed.verdict_mismatch": ["not passed", "не пройдена"],
  "feed.verdict_error": ["ended in an error", "завершилась ошибкой"],
  "feed.verdict_unavailable": ["unavailable", "недоступна"],
  "feed.decision": ["Decision on “{step}”: {word}", "Решение на точке «{step}»: {word}"],
  "feed.decision_approve": ["approved", "одобрено"],
  "feed.decision_reject": ["rejected", "отклонено"],
  "feed.decision_request_changes": ["sent back for changes", "возвращено на доработку"],
  "feed.decision_waive": ["set aside without judging the work", "пропущено без оценки работы"],
  "feed.reason": ["Reason: {reason}", "Причина: {reason}"],
  "feed.document": ["Document “{ref}” published", "Опубликован документ «{ref}»"],
  "feed.findings": ["Findings of the check of step “{step}”",
    "Замечания проверки шага «{step}»"],
  // -- a document opened in its row -------------------------------------------------------------
  "feed.doc_open": ["Show the text", "Показать текст"],
  "feed.doc_large": ["This document is too large to show here.",
    "Документ слишком велик, чтобы показать его здесь."],
});
