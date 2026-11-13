"use strict";

const grok = /grok|грок/i, codex = /codex|кодекс/i;
const transfer = /переда[лнчй]|переда[её]т|получил|handoff|hand|pass|sen[dt]|give|receiv/i;
const testing = /тест|tests?|unittest/i;
const reviewer = /проверяющ|ревьюер|\b(?:checker|reviewer|verifier)\b/i;
const verdict = /вердикт|\bverdict\b/i;
const decision = /приня|подтверд|одобр|отклони|решил|accept|approv|confirm|reject|decid|conclud/i;
const reference = /из (этого|них)|из переданного|по этому|эти |этот |это |those|that|of it/i;
const changed = /исправил|поменял|изменил|поправил|\b(?:fix(?:ed)?|chang(?:e|ed)|patch(?:ed)?)\b/i;

function implicitAuthor(question) {
  const verb = question.replace(/^(?:а )?что (?:именно )?(?:он |они |там )?/i, "");
  if (/^(?:исправ|измен|поправ)ил[аи]?$|^поменял[аи]?$|^(?:изменилось|поменялось)$/i.test(verb)) {
    return true;
  }
  return /^(?:changed|fix|change|patch)$/i.test(question.replace(
    /^(?:and )?what (?:exactly )?(?:did (?:it|they|he) )?/i, ""));
}

export function handoffIntent(text, context) {
  const g = text.search(grok), c = text.search(codex);
  if (g >= 0 && c >= 0 && transfer.test(text)) {
    const source = text.match(/(?:от|from)\s+(grok|грок|codex|кодекс)/i);
    const recipient = text.match(/(гроку|кодексу)(?![а-яё])|(?:\bto\s+)(grok|codex)/i);
    const reverse = source ? codex.test(source[1])
      : recipient ? grok.test(recipient[1] || recipient[2])
      : /получил|receiv/i.test(text) ? c > g : g > c;
    return reverse ? {kind: "transfer", from: "codex", to: "grok-build"}
      : {kind: "transfer", from: "grok-build", to: "codex"};
  }
  if (context && (verdict.test(text) || reviewer.test(text) && decision.test(text))) {
    return {kind: "verdict"};
  }
  if (context && changed.test(text) && !testing.test(text)) {
    const question = text.trim().replace(/[?!.]+$/, "").trim().replace(/\s+/g, " ");
    const named = c >= 0 || g >= 0;
    const matches = c >= 0 ? g < 0 && context.to === "codex" : context.to === "grok-build";
    const knownOther = /claude|клод|kimi|кими|deepseek|дипсик/i.test(question);
    if (named || knownOther) return {kind: matches && named && !knownOther
      ? "changes" : "other-author"};
    if (implicitAuthor(question)) return {kind: "changes"};
  }
  if (testing.test(text) && (reference.test(text) || context && g < 0 && c < 0)) {
    return {kind: context ? "tests" : "clarify"};
  }
  return null;
}

export function sameHandoff(link, pinned) {
  return pinned && link.source.artifactId === pinned.sourceId
    && link.target.artifactId === pinned.targetId
    && link.source.attemptId === pinned.sourceAttempt
    && link.target.attemptId === pinned.targetAttempt;
}

export function handoffPin(link) {
  return {sourceId: link.source.artifactId, targetId: link.target.artifactId,
    sourceAttempt: link.source.attemptId, targetAttempt: link.target.attemptId};
}

export function sameContinuation(row, pin) {
  return pin && row.inputArtifactId === pin.inputId && row.target.actionId === pin.actionId
    && row.target.nodeId === pin.nodeId && row.target.attemptId === pin.attemptId;
}

export function continuationPin(row) {
  return {inputId: row.inputArtifactId, actionId: row.target.actionId,
    nodeId: row.target.nodeId, attemptId: row.target.attemptId};
}
