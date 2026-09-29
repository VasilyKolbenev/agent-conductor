"""Source-level guards of the desk's address: its hash module, its one listener, its one message.

The desk's address is a hash the hub, a bookmark or a person can set, so it is untrusted input,
and the modules that read it are held to what they may reach. Each check below is a function
over TEXT, and the table of broken modules feeds it every defect it claims to refuse, so a check
that silently stopped biting reds here rather than in a review.

Like `test_desk_source.py` this is the change-detection half: it reads source text and says
nothing about what a browser does with it. The browser's half is `browser_tests/test_desk_hash.py`
and `browser_tests/test_desk_embed.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_panel_cascade import strip_comments
from tests.test_studio_source import DOM_FORMS

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
HASH_MODULE = PANEL / "desk-hash.js"
#: Everything a module that is values in and values out may not reach: the page, the wire, the
#: platform, the address bar, storage and timers. The hub's page loads the hash module without
#: the rest of the desk, so a reach here would be a reach into a page that has no desk.
REACHES = DOM_FORMS + ("fetch(", "eventsource", "navigator.", "location", "history",
                       "postmessage", "localstorage", "sessionstorage", "settimeout(",
                       "setinterval(")
FROM = re.compile(r"""\bfrom\s*["']([^"']+)["']""")


def pure_module_faults(source: str) -> list[str]:
    """Every way a shared desk module stops being values in and values out.

    Args:
        source: The text of the module.

    Returns:
        One sentence per fault; empty when the module reaches nothing and imports nothing.
    """
    code = strip_comments(source)
    lowered = code.lower()
    faults = [f"reaches {word!r}" for word in REACHES if word in lowered]
    return faults + [f"imports {name}: a shared module imports nothing"
                     for name in FROM.findall(code)]


def _append(text: str):
    return lambda source: source + text


#: Each defect the check claims to refuse: the edit that plants it in a copy of the real module,
#: and a word its fault must contain.
IMPURE = {
    "the page": (_append("\nconst title = document.title;\n"), "document."),
    "the global object": (_append("\nwindow.name = 'x';\n"), "window."),
    "the wire": (_append("\nfetch('/command/tasks');\n"), "fetch("),
    "the platform": (_append("\nconst language = navigator.language;\n"), "navigator."),
    "the address bar": (_append("\nconst here = location.hash;\n"), "location"),
    "the history": (_append("\nhistory.replaceState(null, '', '#a');\n"), "history"),
    "a message": (_append("\nparent.postMessage({}, 'x');\n"), "postmessage"),
    "storage": (_append("\nlocalStorage.getItem('a');\n"), "localstorage"),
    "a timer": (_append("\nsetTimeout(() => 1, 5);\n"), "settimeout("),
    "another module": (_append('\nimport {taskStatus} from "./desk-status.js";\n'), "imports"),
}


def test_the_desk_hash_module_is_values_in_and_values_out_and_imports_nothing():
    source = HASH_MODULE.read_text(encoding="utf-8")
    assert len(source.splitlines()) > 40, "the module is gone"
    assert pure_module_faults(source) == []


@pytest.mark.parametrize("edit,needle", list(IMPURE.values()), ids=list(IMPURE))
def test_the_purity_check_refuses_each_planted_reach_and_names_it(edit, needle):
    faults = pure_module_faults(edit(HASH_MODULE.read_text(encoding="utf-8")))
    assert faults, "a defective module was accepted"
    assert any(needle in fault for fault in faults), faults
