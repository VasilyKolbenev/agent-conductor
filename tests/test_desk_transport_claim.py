"""Both network doors of the transport carry the project claim, and only they name it.

Spec 4.5.1: once a desk is bound to a project, the single GET and the single POST of
`desk-transport.js` send `X-Conduct-Project`. A door that forgot it would let a stale window
read or write another project's data, and no test of the desk's own behaviour would notice,
because the answer would simply come back. So this guard reads the transport's code and holds
three facts of it: the header's name is written once, in one helper; each door calls that
helper; and no other module of the panel writes the header. Each fact is shown failing on a
copy of the real module with exactly that fact broken.
"""
from __future__ import annotations

import re

import pytest

from tests.test_panel_cascade import strip_comments
from tests.test_studio_source import PANEL

TRANSPORT = PANEL / "desk-transport.js"
HEADER = "X-Conduct-Project"
HELPER = "claimHeader"
#: The two doors, by the function that opens each one on the wire.
DOORS = ("readJson", "postJson")


def _balanced(code: str, start: int, opening: str, closing: str) -> int:
    """The index just past the group that opens at `start`."""
    depth, at = 0, start
    while at < len(code):
        depth += code[at] == opening
        depth -= code[at] == closing
        at += 1
        if depth == 0:
            return at
    raise AssertionError("an unbalanced group")


def door_body(code: str, name: str) -> str:
    """The text of one function, its parameters' own parentheses and braces included."""
    found = re.search(rf"function\s+{name}\s*\(", code)
    if found is None:
        return ""
    after_params = _balanced(code, found.end() - 1, "(", ")")
    brace = code.index("{", after_params)
    return code[brace:_balanced(code, brace, "{", "}")]


def claim_faults(transport: str, others: dict[str, str]) -> list[str]:
    """Every way the claim header is missing from a door or written outside the transport.

    Args:
        transport: The text of `desk-transport.js`.
        others: The text of every other module of the panel, by file name.

    Returns:
        One sentence per fault; empty when both doors carry the claim and nobody else names it.
    """
    code = strip_comments(transport)
    faults = []
    if code.count(f'"{HEADER}"') != 1:
        faults.append(f"the transport does not write {HEADER} exactly once")
    for name in DOORS:
        body = door_body(code, name)
        if not body:
            faults.append(f"the {name} door is gone")
        elif f"{HELPER}(" not in body:
            faults.append(f"the {name} door does not carry {HEADER}")
        elif body.count(f"{HELPER}(") != 1:
            faults.append(f"the {name} door carries {HEADER} more than once")
    faults += [f"{file} names {HEADER}, which only the transport's two doors send"
               for file, text in sorted(others.items())
               if HEADER.lower() in strip_comments(text).lower()]
    return faults


def _others() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in PANEL.glob("*.js")
            if path.name != TRANSPORT.name}


def _edit(old: str, new: str):
    def apply(text: str) -> str:
        assert old in text, f"the sabotage target is gone from the module: {old!r}"
        return text.replace(old, new, 1)
    return apply


#: Each defect the guard claims to refuse: the edit that plants it in a copy of the real
#: transport, and a word its fault must contain.
BROKEN = {
    "a read door without the claim": (
        _edit(f"...{HELPER}(claimed)", ""), "readJson door does not carry"),
    "a write door without the claim": (
        _edit(f"...{HELPER}(claimed), ", ""), "postJson door does not carry"),
    "a second spelling of the header": (
        lambda text: text + f'\nconst LATE_HEADER = {{"{HEADER}": "x"}};\n', "exactly once"),
}


def test_both_doors_of_the_transport_carry_the_claim_and_nobody_else_names_it():
    source = TRANSPORT.read_text(encoding="utf-8")
    assert claim_faults(source, _others()) == []


@pytest.mark.parametrize("edit,needle", list(BROKEN.values()), ids=list(BROKEN))
def test_the_claim_check_refuses_each_defect_and_names_it(edit, needle):
    faults = claim_faults(edit(TRANSPORT.read_text(encoding="utf-8")), _others())
    assert faults, "a defective transport was accepted"
    assert any(needle in fault for fault in faults), faults


def test_the_claim_check_refuses_another_module_that_names_the_header():
    others = {**_others(), "desk.js": f'const HEADERS = {{"{HEADER}": "p"}};\n'}
    faults = claim_faults(TRANSPORT.read_text(encoding="utf-8"), others)
    assert any("desk.js names" in fault for fault in faults), faults


def test_the_claim_check_reads_code_and_not_the_prose_around_it():
    prose = f"// the {HEADER} header is sent by {HELPER}(claimed) in both doors\n"
    others = {**_others(), "desk.js": prose}
    source = TRANSPORT.read_text(encoding="utf-8")
    assert claim_faults(source, others) == []
