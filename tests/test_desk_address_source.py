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

from tests.test_desk_source import _function_body
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


# -- one listener, no inbound message, and an address moved only by replaceState -------
#
# The router is the one place a hash the desk did not write is read (spec 4.5.3), and the
# desk listens to nothing else that could move it: no `message` (the hub speaks to the desk
# through the hash alone) and no second `hashchange`. The router selects, reads and sets the
# appearance; it reaches no write door. The desk's own address is moved by one function, by
# `replaceState`, which fires no `hashchange`, so no write of its own can start a loop.
BOOT_MODULE = "desk.js"
ROUTER = "onHashChange"
LISTENER = re.compile(r"""addEventListener\(\s*["']([a-z]+)["']""")
LISTENING = re.compile(rf"""addEventListener\(\s*["']hashchange["']\s*,\s*{ROUTER}\s*\)""")
#: The one function that calls `replaceState`, and the ways a module could move the address
#: any other way: a new history entry, an assignment that fires `hashchange`, a navigation.
REMEMBER = "remember"
MOVES = (r"\bpushState\s*\(", r"\blocation\.hash\s*=(?!=)",
         r"\blocation\.(?:assign|replace)\s*\(", r"\blocation\.href\s*=(?!=)",
         r"\bhistory\.(?:back|forward|go)\s*\(")


def _sources() -> dict[str, str]:
    """Every desk module, by name, as written."""
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(PANEL.glob("desk*.js"))}


def listener_faults(sources: dict[str, str]) -> list[str]:
    """Every way the desk listens for more, or less, than its one `hashchange`.

    Args:
        sources: Each desk module's name and text.

    Returns:
        One sentence per fault; empty when exactly the boot module listens for `hashchange`
        (with the router) and nobody listens for `message`.
    """
    heard = [(name, event) for name, text in sources.items()
             for event in LISTENER.findall(strip_comments(text))]
    homes = [name for name, event in heard if event == "hashchange"]
    faults = [] if homes == [BOOT_MODULE] else [
        f"hashchange is heard by {homes or 'nobody'}, not by {BOOT_MODULE} alone"]
    faults += [f"{name} listens for message: the desk has no inbound channel"
               for name, event in heard if event == "message"]
    if not LISTENING.search(strip_comments(sources.get(BOOT_MODULE, ""))):
        faults.append(f"the listener is not {ROUTER}")
    return faults


def router_faults(source: str) -> list[str]:
    """Every way the router, or the module around it, reaches a write or moves the address.

    Args:
        source: The text of the boot module.

    Returns:
        One sentence per fault; empty when the router exists, writes nothing, and the address
        is moved only by `replaceState` in one function.
    """
    code = strip_comments(source)
    body = _function_body(code, ROUTER)
    faults = [] if body.strip() else [f"the router {ROUTER} is missing or empty"]
    faults += [f"the router calls {name}(" for name in ("write", "submit")
               if re.search(rf"\b{name}\s*\(", body)]
    faults += ["the module calls write(" for _ in re.findall(r"\bwrite\s*\(", code)[:1]]
    faults += [f"moves the address by {found.group(0)}" for pattern in MOVES
               for found in re.finditer(pattern, code)]
    calls = len(re.findall(r"\breplaceState\s*\(", code))
    if calls != 1 or "replaceState(" not in _function_body(code, REMEMBER):
        faults.append(f"replaceState is called {calls} times, and not once inside {REMEMBER}")
    return faults


def _in_router(call: str):
    anchor = f"async function {ROUTER}() {{"

    def apply(text: str) -> str:
        assert anchor in text, f"the sabotage target is gone from the module: {anchor!r}"
        return text.replace(anchor, f"{anchor}\n  {call}", 1)
    return apply


def _at_end(text: str):
    return lambda source: source + text


def _swap(old: str, new: str):
    def apply(source: str) -> str:
        assert old in source, f"the sabotage target is gone from the module: {old!r}"
        return source.replace(old, new, 1)
    return apply


def _grown(name: str, extra: str):
    """The desk's sources with `extra` written at the end of module `name`."""
    return lambda sources: {**sources, name: sources[name] + extra}


#: Each defect `router_faults` claims to refuse: the edit to a copy of the boot module, and a
#: word its fault must contain.
ROUTER_BROKEN = {
    "a write in the router": (_in_router('write("tasks", null, {});'), "calls write("),
    "a submit in the router": (_in_router('submit("tasks", null, {});'), "calls submit("),
    "a write anywhere in the module": (_at_end('\nwrite("tasks", null, {});\n'),
                                       "module calls write("),
    "a history entry": (_at_end('\nhistory.pushState(null, "", "#a");\n'), "pushState"),
    "an assignment that would fire hashchange": (_at_end('\nlocation.hash = "#a";\n'),
                                                 "location.hash ="),
    "a navigation": (_at_end('\nlocation.replace("#a");\n'), "location.replace("),
    "a second caller of replaceState": (
        _at_end('\nfunction rogue() { history.replaceState(null, "", "#a"); }\n'),
        "replaceState is called 2 times"),
    "no caller of replaceState": (_swap("history.replaceState(", "history.replace_state("),
                                  "replaceState is called 0 times"),
    "the router renamed away": (_swap(f"function {ROUTER}(", "function onChange("),
                                "missing or empty"),
}
#: The same, for the whole set of modules and the two events.
LISTENER_BROKEN = {
    "a second hashchange listener in the boot module": (
        _grown(BOOT_MODULE, '\nwindow.addEventListener("hashchange", () => 1);\n'),
        "hashchange"),
    "a hashchange listener in a region module": (
        _grown("desk-rail.js", '\nwindow.addEventListener("hashchange", () => 1);\n'),
        "hashchange"),
    "a message listener": (
        _grown(BOOT_MODULE, '\nwindow.addEventListener("message", () => 1);\n'), "message"),
    "a message listener in single quotes": (
        _grown("desk-scene.js", "\nwindow.addEventListener('message', () => 1);\n"), "message"),
    "the listener that is not the router": (
        lambda sources: {**sources, BOOT_MODULE: sources[BOOT_MODULE].replace(
            f'addEventListener("hashchange", {ROUTER})',
            'addEventListener("hashchange", () => 1)')}, "not onHashChange"),
}


def test_the_desk_listens_for_one_hashchange_in_its_boot_module_and_for_no_message():
    sources = _sources()
    assert BOOT_MODULE in sources and len(sources) > 10, "the desk's modules are not all read"
    assert listener_faults(sources) == []


@pytest.mark.parametrize("edit,needle", list(LISTENER_BROKEN.values()), ids=list(LISTENER_BROKEN))
def test_the_listener_check_refuses_each_planted_listener_and_names_it(edit, needle):
    faults = listener_faults(edit(_sources()))
    assert faults, "a defective desk was accepted"
    assert any(needle in fault for fault in faults), faults


def test_the_router_writes_nothing_and_the_address_moves_only_by_replace_state_in_one_function():
    assert router_faults((PANEL / BOOT_MODULE).read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("edit,needle", list(ROUTER_BROKEN.values()), ids=list(ROUTER_BROKEN))
def test_the_router_check_refuses_each_planted_defect_and_names_it(edit, needle):
    faults = router_faults(edit((PANEL / BOOT_MODULE).read_text(encoding="utf-8")))
    assert faults, "a defective module was accepted"
    assert any(needle in fault for fault in faults), faults
