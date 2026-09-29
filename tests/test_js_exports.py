"""The export reader proven on its own text (`tests/js_exports.py`).

Every seam guard that reads a panel module's exports stands on this reader, so a text that
derails it turns those guards green for the wrong reason. The cases below are the shapes a real
module can hold: a second door in every spelling of `export`, names after the first in a comma
declaration and inside a destructuring, and prose or a regex literal sitting inside a declaration
with a quote or a bracket in it.
"""
from __future__ import annotations

from tests.js_exports import at_top, exported_names


def test_the_export_reader_sees_declarations_lists_default_and_star_exports():
    """The seam guard's eyes, proven on text with a second door in every form."""
    source = "\n".join([
        "export function drawEdges() {}", "export async function later() {}",
        "export const A = 1;", "export let b = 2;", "export var c = 3;",
        "export class D {}", "export {\n  e, f as g,\n};", 'export * from "./x.js";',
        "export default 1;", "const notExported = 1; // export let hidden",
    ])
    assert sorted(exported_names(source)) == sorted([
        "drawEdges", "later", "A", "b", "c", "D", "e", "g", "*", "default"])
    assert exported_names("function quiet() {}\n") == []


def test_the_export_reader_sees_every_name_of_a_comma_declaration_and_of_a_destructuring():
    """A second door hides in the names after the first: `export const a = 1, b = 2`, or in a
    pattern the reader took for no name at all: `export const {a, b} = source`.
    """
    source = "\n".join([
        "export const a = 1, b = 2;", "export let x = f(1, 2), y;",
        'export var s = "p,q;r", t = [1, 2];', "export const {c, d: e, ...f} = obj;",
        "export const [g, , h = 3, ...i] = arr;", "export const {j: {k, l = 1}, m: [n]} = deep;",
        'export const {o = "a,b", p: q = fn(1, 2)} = other;',
        "export const multi = {\n  u: 1,\n  v: 2,\n}, second = 3;", "export function fn() {}",
        "const inner = 1, notExported = 2; // export const hidden = 1, alsoHidden = 2",
    ])
    assert sorted(exported_names(source)) == sorted([
        "a", "b", "x", "y", "s", "t", "c", "e", "f", "g", "h", "i", "k", "l", "n", "o", "q",
        "multi", "second", "fn"])


def test_a_trailing_comment_with_an_apostrophe_inside_a_declaration_does_not_hide_its_names():
    source = "\n".join(["export const a = 1, // it's the first", "  b = 2; // don't stop here",
                        "export const c = 3;"])
    assert exported_names(source) == ["a", "b", "c"]


def test_a_regex_literal_holding_a_quote_or_a_bracket_does_not_hide_the_names_after_it():
    source = "\n".join([
        "export const pattern = /[\"'(]/, other = 4;", "export const z = 5;",
        r"export const slash = /a\/b[/]c/gi, more = 6;",
    ])
    assert exported_names(source) == ["pattern", "other", "z", "slash", "more"]


def test_a_block_comment_inside_a_declaration_is_prose_whatever_it_holds():
    source = "export const a = 1, /* it's; a `note` */ b = 2;\nexport const c = 3;"
    assert exported_names(source) == ["a", "b", "c"]


def test_a_slash_after_an_operand_is_a_division_and_a_slash_in_a_string_is_text():
    source = "\n".join([
        "export const half = 10 / 2, third = f(9) / 3, url = \"http://x/y\", tail = a[0] / 2;",
        "export const last = 1;",
    ])
    assert exported_names(source) == ["half", "third", "url", "tail", "last"]


def test_the_top_level_reader_yields_nothing_from_inside_a_comment_or_a_regex():
    text = "a, // b, c\n d /* e, */ , /f, g/ , h"
    seen = "".join(char for _, char in at_top(text) if not char.isspace())
    assert seen == "a,d,,h"
