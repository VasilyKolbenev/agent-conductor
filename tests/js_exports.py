"""The export reader the source guards use: every name a JavaScript module exports.

Not a test module (pytest does not collect it): `test_studio_canvas.py` holds the seam guards that
call it, `test_desk_wizard_source.py` holds the renderer's, and `test_js_exports.py` proves it. It
left `test_studio_canvas.py` when that file neared the 800-line cap.
"""
from __future__ import annotations

import re

_EXPORT_DECLARATION = re.compile(
    r"^export\s+(?:async\s+)?(?:function\s*\*?|class)\s+(\w+)", re.MULTILINE)
_EXPORT_BINDINGS = re.compile(r"^export\s+(?:const|let|var)\s+", re.MULTILINE)
_EXPORT_LIST = re.compile(r"^export\s*\{([^}]*)\}", re.MULTILINE)
_EXPORT_OTHER = re.compile(r"^export\s+(default\b|\*)", re.MULTILINE)


#: A slash after one of these opens a regex literal; after an operand it is a division.
_REGEX_OPENERS = frozenset("(,=:[!&|?{};+-*%<>~^")
_REGEX_KEYWORDS = frozenset({"return", "typeof", "case", "do", "else", "in", "instanceof", "new",
                             "of", "throw", "void", "yield", "await", "delete"})
_WORD_END = re.compile(r"([A-Za-z_$][\w$]*)\Z")


def _string_end(text: str, at: int) -> int:
    """The index after the quoted string that opens at `at` (the end of `text` when unclosed)."""
    quote, cursor = text[at], at + 1
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 1
        elif text[cursor] == quote:
            return cursor + 1
        cursor += 1
    return len(text)


def _starts_regex(before: str) -> bool:
    """Whether a slash after this text opens a regex literal and not a division."""
    if before == "" or before[-1] in _REGEX_OPENERS:
        return True
    word = _WORD_END.search(before)
    return word is not None and word.group(1) in _REGEX_KEYWORDS


def _regex_end(text: str, at: int) -> int | None:
    """The index after the regex literal that opens at `at`, or None when its line ends first."""
    inside_class, cursor = False, at + 1
    while cursor < len(text) and text[cursor] != "\n":
        char = text[cursor]
        if char == "\\":
            cursor += 1
        elif char == "[" or char == "]":
            inside_class = char == "["
        elif char == "/" and not inside_class:
            cursor += 1
            while cursor < len(text) and text[cursor].isalpha():
                cursor += 1
            return cursor
        cursor += 1
    return None


def _literal_end(text: str, at: int, before: str) -> int | None:
    """Where the string, comment or regex literal that starts at `at` ends, else None."""
    if text[at] in "\"'`":
        return _string_end(text, at)
    if text.startswith("//", at):
        line = text.find("\n", at)
        return len(text) if line < 0 else line
    if text.startswith("/*", at):
        block = text.find("*/", at + 2)
        return len(text) if block < 0 else block + 2
    return _regex_end(text, at) if text[at] == "/" and _starts_regex(before) else None


def _scan(text: str):
    """Cut `text` into (start, end, kind) pieces: a `comment`, a `literal` (a string or a regex)
    or one `char`. What stands inside a comment or a literal is prose or data, never structure."""
    at, last = 0, 0
    while at < len(text):
        end = _literal_end(text, at, text[max(0, last - 32):last])
        if end is None:
            yield at, at + 1, "char"
            last = last if text[at].isspace() else at + 1
            at += 1
            continue
        comment = text.startswith(("//", "/*"), at)
        yield at, end, "comment" if comment else "literal"
        last = last if comment else end
        at = end


def strip_comments(text: str) -> str:
    """`text` with each comment blanked to spaces, newlines kept, so no offset moves."""
    return "".join(re.sub(r"[^\n]", " ", text[start:end]) if kind == "comment"
                   else text[start:end] for start, end, kind in _scan(text))


def at_top(text: str):
    """Every (index, character) of `text` that stands outside brackets, strings, comments and
    regex literals."""
    depth = 0
    for start, _end, kind in _scan(text):
        char = text[start]
        if kind != "char":
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif depth == 0:
            yield start, char


def split(text: str, mark: str) -> list[str]:
    """`text` cut at each `mark` that stands at the top, outside brackets and strings."""
    edges = [-1, *(at for at, char in at_top(text) if char == mark), len(text)]
    return [text[left + 1:right] for left, right in zip(edges, edges[1:])]


def declaration(code: str, start: int) -> str:
    """The text from `start` to the `;` that ends the declaration, or to the end of `code`."""
    ends = [at for at, char in at_top(code[start:]) if char == ";"]
    return code[start:start + ends[0]] if ends else code[start:]


def bound_names(target: str) -> list[str]:
    """The names one declarator's left side binds: a name, or an object or array pattern
    with its renames, defaults, rest elements and nested patterns."""
    target = target.strip()
    if target[:1] not in ("{", "["):
        return [target] if target.isidentifier() else []
    names = []
    for element in split(target[1:-1], ","):
        head = split(element, "=")[0]
        bound = split(head, ":")[-1] if target[0] == "{" else head
        names += bound_names(bound.strip().removeprefix("..."))
    return names


def exported_names(code: str) -> list[str]:
    """Every name a module exports, whichever form of `export` says it.

    A guard that counted only `export function` and `export const` would stay
    green for a second door spelled `export let`, `export class`, `export {..}`,
    `export default` or `export * from`, or for the names after the first in
    `export const a = 1, b = 2` and those inside `export const {a, b} = source`.
    The listed names are the ones a reader imports, so `a as b` counts as `b`; a
    default and a star are named as such. Comments are prose and are read as blanks.
    """
    code = strip_comments(code)
    names = _EXPORT_DECLARATION.findall(code)
    for match in _EXPORT_BINDINGS.finditer(code):
        for declarator in split(declaration(code, match.end()), ","):
            names += bound_names(split(declarator, "=")[0])
    for body in _EXPORT_LIST.findall(code):
        names += [part.split(" as ")[-1].strip() for part in body.split(",") if part.strip()]
    names += ["default" if word.startswith("default") else "*"
              for word in _EXPORT_OTHER.findall(code)]
    return names
