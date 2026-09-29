"use strict";
// Step 2, "Материалы": what the agents receive as code and as documents, as pure functions.
//
// The model hands this module plain values -- what the git read said, the cards the owner
// made -- and it answers with values: how to say the git state, what the cards would compose,
// whether they fit. It imports nothing and keeps no state, so the model above it cannot be
// reached back and nothing here can answer from anything but its arguments.
export const MATERIAL_KINDS = Object.freeze(["plan", "ideas", "scheme", "note", "project_doc"]);
export const MATERIAL_LIMITS = Object.freeze({count: 12, bytes: 49152});
//: A state that ends the wizard in every mode: the project is not one repository, or it tracks
//: the product's own folders (spec 6.2.1, L39). Nothing can be seeded from it.
const ENDS_THE_WIZARD = Object.freeze(["not_repo_root", "unsupported"]);
//: The closed words this module can say, each with a message in the catalogue: what the git
//: step says, the exits it offers, and why a card was refused.
export const GIT_SENTENCES = Object.freeze(["repo", "unborn", "not_git", "not_repo_root",
  "unsupported", "unsafe_directory", "unavailable", "not_active", "reading", "failed"]);
export const GIT_EXITS = Object.freeze(["first_commit", "connect_git", "run_without_git",
  "reread"]);
export const REFUSALS = Object.freeze(["too_many_materials", "already_added", "doc_unknown",
  "document_not_text", "read_failed"]);
const encoder = new TextEncoder();
const GIT_OID = /^[0-9a-f]{40}(?:[0-9a-f]{24})?$/;
const DOC_ID = /^d-[0-9a-f]{32}$/;

//: How a card that came from the starter documents says so, in the document's language: the
//: owner's edit of a document the agents wrote, and not the agents' own words (spec 6.2.2).
const STARTER_MARK = Object.freeze({ru: "из стартовых документов · правка владельца",
  en: "from the starter documents · owner's edit"});
const HEADING = Object.freeze({ru: "Материалы", en: "Materials"});
const NONE = Object.freeze({ru: "Материалов нет", en: "No materials"});
const LINK_LINE = Object.freeze({
  ru: (path, oid) => `Файл проекта в рабочей папке: \`${path}\` (git blob \`${oid}\`), `
    + "текст не скопирован",
  en: (path, oid) => `Project file in the work folder: \`${path}\` (git blob \`${oid}\`), `
    + "text not copied",
});

function bytes(text) {
  return encoder.encode(text).length;
}

// -- cards -------------------------------------------------------------------------------

export function isMaterialKind(kind) {
  return MATERIAL_KINDS.includes(kind);
}

//: A document the read listed, kept as the card it becomes. The read is the only source of
//: its id, path and oid: an id the owner's page invented is not a document.
export function documentCard(key, row) {
  return {key, kind: "project_doc", title: "", content: "", source: null, mode: "link",
    docId: row.doc_id, gitOid: row.git_oid, path: row.path, length: row.length,
    fetched: false, blocked: null};
}

export function textCard(key, event) {
  return {key, kind: event.kind, title: typeof event.title === "string" ? event.title : "",
    content: typeof event.content === "string" ? event.content : "",
    source: event.source === "starter_docs" ? "starter_docs" : null, mode: null,
    docId: null, gitOid: null, path: null, length: null, fetched: false, blocked: null};
}

export function isOid(value) {
  return typeof value === "string" && GIT_OID.test(value);
}

//: Whether a listed row is one the wizard may take: a real id, an oid, a path, a length.
export function isDocumentRow(row) {
  return row !== null && typeof row === "object" && DOC_ID.test(row.doc_id ?? "")
    && isOid(row.git_oid) && typeof row.path === "string" && row.path !== ""
    && Number.isSafeInteger(row.length) && row.length >= 0;
}

export function isComplete(card) {
  if (card.kind === "project_doc") return card.mode === "link" || card.content.trim() !== "";
  return card.title.trim() !== "" && card.content.trim() !== "";
}

// -- what the cards say ------------------------------------------------------------------

function cardTitle(card, lang) {
  return card.source === "starter_docs" ? `${card.title} · ${STARTER_MARK[lang]}` : card.title;
}

//: The closed body of one card for `POST …/materials` (spec 6.2.3): keys per kind, never a
//: path, a root or a directory -- the server finds the path by the document id.
function bodyItem(card, lang) {
  if (card.kind !== "project_doc") {
    return {kind: card.kind, title: cardTitle(card, lang), content: card.content};
  }
  const link = {kind: card.kind, doc_id: card.docId, git_oid: card.gitOid, mode: card.mode};
  return card.mode === "copy" ? {...link, content: card.content} : link;
}

export function bodyOf(cards, lang) {
  if (!HEADING[lang]) throw new Error("unknown document language");
  return {lang, items: cards.map((card) => bodyItem(card, lang))};
}

function section(card, number, lang) {
  if (card.kind === "project_doc") {
    if (card.mode === "link") {
      const head = `## ${number}. ${card.path} · ${card.kind}`;
      return `${head}\n${LINK_LINE[lang](card.path, card.gitOid)}`;
    }
    // A copy is headed with the blob it was read at, as the server heads it.
    return `## ${number}. ${card.path}@${card.gitOid} · ${card.kind}\n${card.content}`;
  }
  const body = card.kind === "scheme" ? `\`\`\`mermaid\n${card.content}\n\`\`\`` : card.content;
  return `## ${number}. ${cardTitle(card, lang)} · ${card.kind}\n${body}`;
}

//: An approximation of the document the server will compose from these cards: the exact bytes
//: are the server's alone, this is the text the estimate and the argv arithmetic measure. It says
//: what `command/materials.py` says, and a test holds its size at or above the composed one, so
//: the desk never calls a list small that the server would refuse as too large.
export function composeText(cards, lang) {
  const sections = cards.map((card, at) => section(card, at + 1, lang));
  const parts = [`# ${HEADING[lang]}`, ...(sections.length > 0 ? sections : [NONE[lang]])];
  return `${parts.join("\n\n")}\n`;
}

//: The "≈" the owner sees while typing, in the longer of the two languages, and the gate
//: against sending what would be refused anyway.
export function estimateOf(cards) {
  const size = bytes(composeText(cards, "ru"));
  const overBytes = size > MATERIAL_LIMITS.bytes;
  const linkable = cards.filter((card) => card.kind === "project_doc" && card.mode === "copy")
    .map((card) => card.key);
  return {count: cards.length, bytes: size, overCount: cards.length > MATERIAL_LIMITS.count,
    overBytes, hint: overBytes && linkable.length > 0 ? "make_link" : null, linkable};
}

// -- git ---------------------------------------------------------------------------------

function branchOf(head) {
  return typeof head?.ref === "string" ? head.ref.replace(/^refs\/heads\//, "") : null;
}

function paramsOf(git) {
  if (git.state === "repo") {
    return {ref: branchOf(git.head), commit: String(git.head?.commit ?? "").slice(0, 7),
      dirty: git.dirty_paths ?? null};
  }
  return git.state === "unsupported" ? {names: [...(git.unsupported?.names ?? [])]} : {};
}

function exitsOf(state, starter) {
  if (state === "unborn") return ["first_commit"];
  if (state === "not_git") return starter ? ["connect_git"] : ["connect_git", "run_without_git"];
  return state === "not_active" ? ["connect_git"] : [];
}

const COMMANDS = Object.freeze({unsafe_directory: "safe_directory", unavailable: "pin_git"});
//: A read that has not landed, or has failed, is not a fact about the project, so the step holds
//: (a failed read offers to be read again). It is judged before the starter's own stop, which
//: would say "no repository" about a repository nobody has looked at yet.
const HOLDS = Object.freeze({reading: "git_reading", failed: "git_failed"});

//: What the step says about where the agents get their code, from the one git read and the
//: mode. `stop` is why the step cannot be left, `blocks` whether it cannot: a state that ends
//: the wizard, a read still out or lost, or a starter that has no repository yet (in view, git
//: waits for activation and the starter goes on to be queued). No state is guessed: an unread
//: or failed read is its own, in view as everywhere; `not_active` is what the server says when
//: it says it (spec 6.2.1), never what the desk supposes before the answer lands.
export function gitFacts(read, mode) {
  const starter = mode.starterId !== null;
  let state = "reading", git = null;
  if (read && read.status === "failed") state = "failed";
  else if (read && read.status === "ok") {
    git = read.payload?.git ?? {};
    state = typeof git.state === "string" ? git.state : "failed";
  }
  const ends = ENDS_THE_WIZARD.includes(state);
  const needsGit = starter && !mode.view && state !== "repo";
  const held = Object.hasOwn(HOLDS, state) ? HOLDS[state] : null;
  const stop = ends ? "git_stops" : held ?? (needsGit ? "starter_needs_git" : null);
  return {state, sentence: state, params: git === null ? {} : paramsOf(git),
    exits: state === "failed" ? ["reread"] : exitsOf(state, starter), blocks: stop !== null,
    stop, command: COMMANDS[state] ?? null};
}

//: The project-instructions row (spec 6.2.1, L31): only when files were found, defaulting to
//: what the last seed chose until the owner says otherwise.
export function instructionsRow(read, choice) {
  const rows = read && read.status === "ok" ? read.payload?.git?.agent_instructions : null;
  if (!rows || !Number.isSafeInteger(rows.found) || rows.found <= 0) return null;
  const standing = rows.default_include === true;
  return {found: rows.found, include: typeof choice === "boolean" ? choice : standing,
    default: standing};
}

// -- the document picker -----------------------------------------------------------------

export function pickerOf(open, read, cards) {
  const held = new Set(cards.filter((card) => card.docId !== null).map((card) => card.docId));
  let status = "idle";
  if (open) status = read === undefined ? "reading" : read.status === "ok" ? "ready" : "failed";
  const listed = read && read.status === "ok" ? read.payload : null;
  const rows = Array.isArray(listed?.documents) ? listed.documents.filter(isDocumentRow) : [];
  return {open, status, truncated: listed?.truncated === true,
    documents: rows.map((row) => ({doc_id: row.doc_id, path: row.path, length: row.length,
      git_oid: row.git_oid, added: held.has(row.doc_id)}))};
}
