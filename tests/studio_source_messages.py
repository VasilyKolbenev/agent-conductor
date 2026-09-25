"""Resolve only literal catalog keys reached by source message calls.

This does not append a catalog: removing the call removes its prose witness.
Dynamic keys remain dynamic and require dedicated semantic rendering tests.

What one reached call becomes, so a guard keeps judging BEHAVIOUR:

- ``localize(state, "k")`` -> the English row, as a JS string literal;
- ``L(state, "k", {a: exprA, b})`` -> a JS template literal, each ``{a}``
  placeholder replaced by ``${exprA}``, a literal string parameter spliced in
  as its text. ``String(expr)`` renders as ``${expr}``: a template literal
  applies ToString itself, so the two spellings name one value;
- ``L(state, cond ? "k1" : "k2", ...)`` -> ``(cond ? <k1> : <k2>)``, each
  branch rendered as above;
- any other key -- a template literal, a concatenation, a table lookup -- is
  left exactly as written, because it cannot be resolved from source;
- the first argument is whatever the module really passes; it is never read.

A reached key the catalogues do not carry, or a parameter object that does not
name exactly the placeholders its message declares, is an AssertionError: both
are what ``studio-i18n.message`` throws on at render time.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from tests.test_graph_source import _code as raw_code

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
_ROW = re.compile(
    r'"([a-z_]+\.[a-zA-Z0-9_]+)"\s*:\s*(\[(?:[^\]"\\]|\\.|"(?:[^"\\]|\\.)*")*\])')
_HEAD = re.compile(r"\b(?:localize|L)\(")
_KEY = re.compile(r'^"([a-z_]+\.[a-zA-Z0-9_]+)"$')
_TERNARY = re.compile(
    r'^(.+?)\s*\?\s*"([a-z_]+\.[a-zA-Z0-9_]+)"\s*:\s*"([a-z_]+\.[a-zA-Z0-9_]+)"$',
    re.DOTALL)
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_NAME = re.compile(r"^[a-z_]+$")
_QUOTED = re.compile(r'^"(?:[^"\\\n]|\\.)*"$')
_CLOSER = {"(": ")", "[": "]", "{": "}"}


class Unscannable(ValueError):
    """The text after a call head is not a call this reader can walk."""


@lru_cache(maxsize=None)
def _messages():
    rows = {}
    # The shared table in studio-i18n.js is a catalogue too; a screen reaches
    # its keys the same way.
    for path in (*sorted(PANEL.glob("studio-*-copy.js")), PANEL / "studio-i18n.js"):
        text = path.read_text(encoding="utf-8")
        for hit in _ROW.finditer(text):
            rows[hit[1]] = json.loads(hit[2])
    return rows


def message_english(key):
    """The English row one reached key names; a key nothing declares fails."""
    rows = _messages()
    if key not in rows:
        raise AssertionError("Unknown reached UI message: " + key)
    return rows[key][0]


def message_russian(key):
    """The Russian row of the same key, for a witness of what a Russian reader is told."""
    message_english(key)
    return _messages()[key][1]


def _past_string(text, at):
    """The index just past the string or template literal opening at ``at``."""
    quote = text[at]
    index = at + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
        elif char == quote:
            return index + 1
        elif quote == "`" and text.startswith("${", index):
            index = _past_bracket(text, index + 1)
        elif char == "\n" and quote != "`":
            break
        else:
            index += 1
    raise Unscannable(f"unterminated string literal at {at}")


def _past_bracket(text, at):
    """The index just past the bracket closing the one opening at ``at``."""
    stack = [_CLOSER[text[at]]]
    index = at + 1
    while index < len(text) and stack:
        char = text[index]
        if char in "\"'`":
            index = _past_string(text, index)
            continue
        if char in _CLOSER:
            stack.append(_CLOSER[char])
        elif char == stack[-1]:
            stack.pop()
        index += 1
    if stack:
        raise Unscannable(f"unbalanced {text[at]!r} at {at}")
    return index


def _arguments(text):
    """The top-level comma-separated pieces of an argument list, stripped."""
    pieces, start, index = [], 0, 0
    while index < len(text):
        char = text[index]
        if char in "\"'`":
            index = _past_string(text, index)
        elif char in _CLOSER:
            index = _past_bracket(text, index)
        elif char == ",":
            pieces.append(text[start:index].strip())
            start = index = index + 1
        else:
            index += 1
    pieces.append(text[start:].strip())
    return [piece for piece in pieces if piece]


def _parameters(literal):
    """``{a: exprA, b}`` as a name -> expression map; None when it is not that."""
    if not (literal.startswith("{") and literal.endswith("}")):
        return None
    named = {}
    for entry in _arguments(literal[1:-1]):
        name, colon, expression = entry.partition(":")
        name = name.strip()
        if _NAME.match(name) is None:
            return None
        named[name] = expression.strip() if colon else name
    return named


def _literal_text(expression):
    """The text of a double-quoted literal parameter, or None for an expression."""
    if _QUOTED.match(expression) is None:
        return None
    try:
        return json.loads(expression)
    except ValueError:
        return None


def _unwrapped(expression):
    """``String(expr)`` is ``expr``: a template literal applies ToString itself."""
    if expression.startswith("String(") and _past_bracket(expression, 6) == len(expression):
        return expression[7:-1].strip()
    return expression


def _escaped(text):
    """``text`` as it must be spelled inside a template literal."""
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def _render(key, named):
    """One message as the literal the call evaluates to, parameters spliced in."""
    text = message_english(key)
    declared = set(_PLACEHOLDER.findall(text))
    if set(named) != declared:
        raise AssertionError(
            f"{key} declares {sorted(declared)} and the call passes {sorted(named)}")
    literal = {name: _literal_text(expression) for name, expression in named.items()}
    if all(value is not None for value in literal.values()):
        return json.dumps(_PLACEHOLDER.sub(lambda hit: literal[hit[1]], text),
                          ensure_ascii=False)

    def splice(hit):
        if literal[hit[1]] is not None:
            return _escaped(literal[hit[1]])
        return "${" + _unwrapped(named[hit[1]]) + "}"
    return "`" + _PLACEHOLDER.sub(splice, _escaped(text)) + "`"


def _rendered_call(key, params):
    """What one call with this key argument and this parameter argument says."""
    named = _parameters(params)
    if named is None:
        return None
    literal = _KEY.match(key)
    if literal is not None:
        return _render(literal[1], named)
    ternary = _TERNARY.match(key)
    if ternary is None:
        return None
    return (f"({ternary[1]} ? {_render(ternary[2], named)}"
            f" : {_render(ternary[3], named)})")


def _resolved_at(text, start):
    """``text`` with the call whose head is at ``start`` rendered, if it can be."""
    opening = text.index("(", start)
    try:
        end = _past_bracket(text, opening)
        args = _arguments(text[opening + 1:end - 1])
    except Unscannable:
        return text
    if len(args) not in (2, 3):
        return text
    rendered = _rendered_call(args[1], args[2] if len(args) == 3 else "{}")
    return text if rendered is None else text[:start] + rendered + text[end:]


def rendered_source(text):
    """``text`` with every resolvable reached call replaced by what it says.

    Innermost first: the last call head in the text encloses no other, and
    rendering it moves nothing that stands before it.
    """
    for start in reversed([hit.start() for hit in _HEAD.finditer(text)]):
        text = _resolved_at(text, start)
    return text


def _code(*paths):
    return rendered_source(raw_code(*paths))
