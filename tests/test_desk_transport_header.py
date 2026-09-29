"""The wire doors' header says what really differs from the text it was moved from.

`desk-transport.js` was cut out of the Studio's boot module and then had its stateless
doors hoisted to module level. A header that says nothing changed in that move is a claim a
reader trusts and the diff of the move contradicts, so the header now lists what differs.
What a test can hold of a sentence is its facts: the false claim is refused, and every name
the header gives as a difference is a name the module declares.
"""
from __future__ import annotations

import re

from tests.test_panel_cascade import strip_comments
from tests.test_studio_source import PANEL

TRANSPORT = PANEL / "desk-transport.js"
#: Phrasings of the claim that the move left the text as it was.
UNCHANGED_CLAIM = re.compile(
    r"nothing\s+(?:here\s+)?(?:has\s+been\s+)?changed|text\s+is\s+unchanged|unchanged\s+in\s+the\s+move",
    re.IGNORECASE)


def header_of(source: str) -> str:
    """The opening block of `//` comment lines, joined into one string."""
    lines = []
    for line in source.splitlines()[1:]:
        if not line.startswith("//"):
            break
        lines.append(line[2:].strip())
    return " ".join(lines)


def _declared(code: str) -> set[str]:
    """Function names, the names of a function's parameters, and top-level constants."""
    names = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)", code))
    for parameters in re.findall(r"function\s+[A-Za-z_$][\w$]*\s*\(([^)]*)\)", code):
        names |= {part.split("=")[0].strip() for part in parameters.split(",") if part.strip()}
    return names | set(re.findall(r"(?:const|let)\s+([A-Za-z_$][\w$]*)", code))


def header_faults(header: str, code: str) -> list[str]:
    """Every way a header misdescribes the module it heads."""
    faults = ["claims nothing changed in the move"] if UNCHANGED_CLAIM.search(header) else []
    named = set(re.findall(r"`([A-Za-z_$][\w$]*)`", header))
    faults += [f"names `{name}`, which the module does not declare"
               for name in sorted(named - _declared(code))]
    return faults


def test_the_transport_header_makes_no_false_claim_and_names_only_real_names():
    source = TRANSPORT.read_text(encoding="utf-8")
    header = header_of(source)
    assert len(header) > 300, "the header is gone"
    assert header_faults(header, strip_comments(source)) == []


def test_the_header_check_refuses_the_claim_and_a_name_the_module_lacks():
    source = TRANSPORT.read_text(encoding="utf-8")
    code = strip_comments(source)
    claim = "Nothing here has been changed in the move. " + header_of(source)
    assert any("nothing changed" in fault for fault in header_faults(claim, code))
    planted = header_of(source) + " The `imaginaryDoor` is new."
    assert header_faults(planted, code) == [
        "names `imaginaryDoor`, which the module does not declare"]


def test_the_header_lists_the_names_that_crossed_the_seam():
    header = header_of(TRANSPORT.read_text(encoding="utf-8"))
    for name in ("locale", "dropSession", "foreignSession", "postJson", "openStream"):
        assert f"`{name}`" in header, name
