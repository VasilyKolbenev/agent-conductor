"""The materials document of a run, composed as a pure function (spec 6.2.3).

The desk sends the owner's materials as a list of items; the server publishes them as one human
document, `artifact-materials`, which the entry steps of a cycle read. What that document says is
decided here and nowhere else, so the same items and language always give the same bytes: the
artifact id is a digest of them, and a request repeated after a lost answer must find the document
already standing.

Pure: no store, clock, randomness or I/O. Judging an item against the seed record, and turning a
refusal into the wire's `materials_refused`, belong to the caller. The caller hands over `base`,
the files the seed really copied into the task folder. A path the seed skipped is left out of it,
and the caller refuses that link first as `doc_not_seeded`: only the seed's own record knows why a
file is missing. The desk never sends a path; the composer reads it from `base` by document id.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from .artifacts import ARTIFACT_CONTENT_LIMIT
from .contract_values import ContractError

#: At most this many materials in one document (spec 6.2.2).
MAX_MATERIALS = 12
TEXT_KINDS = ("plan", "ideas", "scheme", "note")
PROJECT_DOC = "project_doc"
LANGS = ("ru", "en")
#: The reasons this composer can give, the `detail.reason` of `materials_refused`. A seventh,
#: `doc_not_seeded`, needs the seed's skip list and is the caller's.
REFUSALS = ("too_many_materials", "materials_too_large", "document_not_text", "doc_unknown",
            "materials_base_moved", "seed_missing")

_DOC_ID = re.compile(r"d-[0-9a-f]{32}\Z")
_GIT_OID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
_LINK_KEYS = frozenset({"kind", "doc_id", "git_oid", "mode"})
#: The closed keys of each shape an item can take; a `path`, `root` or `dir` is in none of them.
_KEYS = {"text": frozenset({"kind", "title", "content"}), "link": _LINK_KEYS,
         "copy": _LINK_KEYS | {"content"}}

_HEADING = {"ru": "Материалы", "en": "Materials"}
_NONE = {"ru": "Материалов нет", "en": "No materials"}
_LINK_LINE = {
    "ru": "Файл проекта в рабочей папке: `{path}` (git blob `{oid}`), текст не скопирован",
    "en": "Project file in the work folder: `{path}` (git blob `{oid}`), text not copied",
}


class BaseFile(NamedTuple):
    """One file the seed copied: its path in the base tree and its git blob id."""

    path: str
    git_oid: str


class MaterialsRefused(ValueError):
    """A list the composer will not turn into a document.

    `reason` is one of `REFUSALS`; `index` is the place of the material it names, or None when
    it is about the list as a whole.
    """

    def __init__(self, reason: str, *, index: int | None = None) -> None:
        if reason not in REFUSALS:
            raise ValueError(f"{reason!r} is not a reason the composer names")
        super().__init__(reason if index is None else f"{reason} (material {index + 1})")
        self.reason = reason
        self.index = index


class _Section(NamedTuple):
    kind: str
    heading: str
    body: str


def compose_materials(items: Sequence[Mapping[str, Any]], lang: str,
                      base: Mapping[str, BaseFile] | None) -> str:
    """The text of `artifact-materials` for these items, in this language.

    The document is `# <Materials>` and then one section per item, `## <n>. <heading> · <kind>`,
    in order. A scheme is fenced as Mermaid; a link says where the file lies in the work folder
    and that its text was not copied; a copy is headed `path@oid` and carries the owner's text;
    no items at all give a short document that says so, because every entry step reads this
    artifact and a missing input would refuse the run.

    Args:
        items: The `items` of the request body: `plan`, `ideas`, `scheme` or `note` with `title`
            and `content`, or `project_doc` with `doc_id`, `git_oid`, `mode` (`link` or `copy`)
            and, for a copy, `content`.
        lang: `ru` or `en`; only the words the composer writes change, never the owner's text.
        base: The files the seed copied, by document id, or None when the task has no seed.

    Returns:
        The document, ending in one newline, at most `ARTIFACT_CONTENT_LIMIT` UTF-8 bytes.

    Raises:
        MaterialsRefused: More than `MAX_MATERIALS` items (judged before any item is read), a
            document over the byte limit, a copy that is not text, a project document the base
            lacks, a link whose blob is not the base's, or a project document with no seed.
        ContractError: The body is not in the closed shape, or `base` is not what it says.
    """
    if lang not in LANGS:
        raise ContractError(f"lang must be one of {', '.join(LANGS)}")
    if not isinstance(items, (list, tuple)):
        raise ContractError("items must be a list")
    if len(items) > MAX_MATERIALS:
        raise MaterialsRefused("too_many_materials")
    sections = [_section(at, item, lang, base) for at, item in enumerate(items)]
    parts = [f"# {_HEADING[lang]}"]
    parts += [f"## {number}. {one.heading} · {one.kind}\n{one.body}"
              for number, one in enumerate(sections, start=1)] or [_NONE[lang]]
    document = "\n\n".join(parts) + "\n"
    if len(document.encode("utf-8")) > ARTIFACT_CONTENT_LIMIT:
        raise MaterialsRefused("materials_too_large")
    return document


def _section(at: int, item: object, lang: str, base: Mapping[str, BaseFile] | None) -> _Section:
    if not isinstance(item, Mapping):
        raise ContractError(f"items[{at}] must be an object")
    kind = item.get("kind")
    if kind in TEXT_KINDS:
        return _text_section(at, item)
    if kind == PROJECT_DOC:
        return _document_section(at, item, lang, base)
    raise ContractError(
        f"items[{at}].kind must be one of {', '.join((*TEXT_KINDS, PROJECT_DOC))}")


def _text_section(at: int, item: Mapping[str, Any]) -> _Section:
    _closed(at, item, "text")
    title = _line(f"items[{at}].title", item["title"])
    content = _text(f"items[{at}].content", item["content"])
    return _Section(item["kind"], title, _fenced(content) if item["kind"] == "scheme" else content)


def _document_section(at: int, item: Mapping[str, Any], lang: str,
                      base: Mapping[str, BaseFile] | None) -> _Section:
    mode = item.get("mode")
    if mode not in ("link", "copy"):
        raise ContractError(f"items[{at}].mode must be link or copy")
    _closed(at, item, mode)
    doc_id = _grammar(f"items[{at}].doc_id", item["doc_id"], _DOC_ID)
    oid = _grammar(f"items[{at}].git_oid", item["git_oid"], _GIT_OID)
    held = _held(at, doc_id, base)
    if mode == "link":
        if held.git_oid != oid:
            raise MaterialsRefused("materials_base_moved", index=at)
        return _Section(PROJECT_DOC, held.path, _LINK_LINE[lang].format(path=held.path, oid=oid))
    content = item["content"]
    if not isinstance(content, str) or not content.strip():
        raise ContractError(f"items[{at}].content must be non-blank text")
    if not _is_text(content):
        raise MaterialsRefused("document_not_text", index=at)
    # A copy is the owner's text, not a claim about the base, so its blob is not compared: the
    # heading names the one it was read at.
    return _Section(PROJECT_DOC, f"{held.path}@{oid}", content)


def _held(at: int, doc_id: str, base: Mapping[str, BaseFile] | None) -> BaseFile:
    if base is None:
        raise MaterialsRefused("seed_missing", index=at)
    held = base.get(doc_id)
    if held is None:
        raise MaterialsRefused("doc_unknown", index=at)
    if not isinstance(held, BaseFile) or not _quotable(held.path):
        raise ContractError("base holds BaseFile rows whose path is one line without a backtick")
    return held


def _closed(at: int, item: Mapping[str, Any], shape: str) -> None:
    """Refuse a key the shape does not name and a key it needs that is missing."""
    if set(item) != _KEYS[shape]:
        raise ContractError(f"items[{at}] must carry exactly {sorted(_KEYS[shape])}, "
                            f"it has {sorted(map(str, item))}")


def _grammar(name: str, value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.match(value) is None:
        raise ContractError(f"{name} is not a well-formed identifier")
    return value


def _is_text(value: str) -> bool:
    """Whether the text can stand in a document: no NUL, and it encodes as UTF-8."""
    if "\x00" in value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be non-blank text")
    if not _is_text(value):
        raise ContractError(f"{name} must be UTF-8 text without NUL")
    return value


def _line(name: str, value: object) -> str:
    text = _text(name, value)
    if "\n" in text or "\r" in text:
        raise ContractError(f"{name} must be one line")
    return text


def _quotable(path: object) -> bool:
    """A path a heading and a code span can carry: one line, no backtick, and text."""
    return (isinstance(path, str) and path != "" and _is_text(path)
            and not set(path) & {"\n", "\r", "`"})


def _fenced(content: str) -> str:
    """The Mermaid block, its fence longer than any run of backticks inside the text."""
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}mermaid\n{content}\n{fence}"
