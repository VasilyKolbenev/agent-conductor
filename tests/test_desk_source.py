"""Source-level contract for the desk's page and for the registries that serve it.

The desk is the window that replaces the Studio's five tabs, and it is reachable
before any of its code exists: the hub mounts `/panel/desk.html` from the first
day. So this module holds the page to the shape the mounting depends on -- a
document with a language and a title, every reference an absolute `/panel/...`
path this server really serves, and nothing inline -- and holds the guards
themselves to account: each check below is a function over TEXT, and the table
of broken pages further down feeds it every defect it claims to refuse, so a
check that silently stopped biting reds here rather than in a review.

Like `test_studio_source.py` this is the change-detection half. It reads source
text and says nothing about what a browser renders.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import server, server_assets
from tests import studio_partition
from tests.studio_partition import hub_registry_names, packaged_names, partition_faults
from tests.test_panel_cascade import strip_comments
from tests.test_studio_source import SCREEN_STATES

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
DESK_PAGE = PANEL / "desk.html"
DESK_SCRIPT = PANEL / "desk.js"
#: The opening tags of the scripts the page may load, in order, exactly. A slice
#: that adds a script adds its tag here in the same commit, so a script cannot
#: arrive on the page unargued.
DESK_TAG = '<script src="/panel/desk.js" type="module">'
EXPECTED_SCRIPTS: tuple[str, ...] = (DESK_TAG,)
#: Every attribute that names another resource, quoted or not, and the quoted
#: form alone. A page whose two counts differ carries a reference the second
#: pattern cannot judge, and that is a fault in itself.
ANY_REFERENCE = r"\b(?:href|src|action|formaction)\s*="
QUOTED_REFERENCE = r'\b(?:href|src|action|formaction)="([^"]*)"'


def _document_faults(html: str) -> list[str]:
    faults = []
    if not html.lstrip().lower().startswith("<!doctype html>"):
        faults.append("the document has no <!doctype html>")
    if not re.search(r'<html\s[^>]*\blang="[a-z]{2}(?:-[A-Za-z]+)?"', html):
        faults.append("the <html> element carries no lang")
    if not re.search(r"<title[^>]*>\s*\S[^<]*</title>", html):
        faults.append("the document has no title")
    return faults


class _Attributes(HTMLParser):
    """Every attribute name of every start tag, as the tokenizer reads them, lower-cased."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.names: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.names += [name for name, _value in attrs]


def _attribute_names(html: str) -> list[str]:
    seen = _Attributes()
    seen.feed(html)
    seen.close()
    return seen.names


def _inline_faults(html: str, expected_scripts: tuple[str, ...]) -> list[str]:
    faults = []
    if re.findall(r"<script\b[^>]*>", html, re.IGNORECASE) != list(expected_scripts):
        faults.append("the script tags are not exactly the expected ones")
    if re.search(r"<style\b", html, re.IGNORECASE):
        faults.append("the page carries a <style> block")
    # The verdict is the tokenizer's: an attribute is whatever it reads as one, however it is
    # separated from what precedes it (a space, a `/`, or nothing after a quoted value). The
    # patterns stay as a second net over the raw text, and each is written to take a space or a
    # `/` as the separator, as the tokenizer does.
    names = _attribute_names(html)
    if "style" in names or re.search(r"[\s/]style\s*=", html, re.IGNORECASE):
        faults.append("the page carries an inline style attribute")
    if (any(name.startswith("on") for name in names)
            or re.search(r"[\s/]on[a-z]+\s*=", html, re.IGNORECASE)):
        faults.append("the page carries an inline handler")
    return faults


#: The one literal a person may read on the page: the product's own name, which is the
#: same word in both languages. Every other word comes from the catalogue.
PRODUCT_NAME = "December Command"
#: The attributes that hold words a person hears or sees: a screen reader's name for a
#: control, a tooltip, an image's text and a field's hint.
LABEL_ATTRIBUTES = ("aria-label", "title", "alt", "placeholder")


class _Words(HTMLParser):
    """The text nodes and the labelling attributes of a page, as the tokenizer reads them.

    A comment and the body of a script or a style are not words a person reads, so they
    are left out; everything else, the `<title>` included, is.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.texts: list[str] = []
        self.labels: list[tuple[str, str, str]] = []
        self._raw = 0

    def handle_starttag(self, tag, attrs):
        self.labels += [(tag, name, value or "") for name, value in attrs
                        if name in LABEL_ATTRIBUTES]
        self._raw += tag in ("script", "style")

    def handle_endtag(self, tag):
        self._raw -= bool(self._raw) and tag in ("script", "style")

    def handle_data(self, data):
        if not self._raw and data.strip():
            self.texts.append(data.strip())


def _text_faults(html: str) -> list[str]:
    words = _Words()
    words.feed(html)
    words.close()
    faults = [f"person-facing text written as a literal: {text!r}"
              for text in words.texts if text != PRODUCT_NAME]
    return faults + [f"person-facing {name} written as a literal on <{tag}>: {value!r}"
                     for tag, name, value in words.labels]


def _reference_faults(html: str) -> list[str]:
    refs = re.findall(QUOTED_REFERENCE, html)
    faults = []
    if len(re.findall(ANY_REFERENCE, html)) != len(refs):
        faults.append("a reference is not a double-quoted attribute")
    for ref in refs:
        if not ref.startswith("/panel/"):
            faults.append(f"reference is not an absolute /panel/ path: {ref}")
        elif "//" in ref or ".." in ref or ":" in ref:
            faults.append(f"reference leaves the packaged directory: {ref}")
    return faults


def desk_page_faults(
        html: str, expected_scripts: tuple[str, ...] = EXPECTED_SCRIPTS) -> list[str]:
    """Every way `html` fails the desk page's contract, as plain sentences.

    Args:
        html: The text of the page.
        expected_scripts: The opening `<script>` tags the page may carry.

    Returns:
        One sentence per fault; empty when the page is sound.
    """
    return (_document_faults(html) + _inline_faults(html, expected_scripts)
            + _reference_faults(html) + _text_faults(html))


CLEAN = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    f"<title>{PRODUCT_NAME}</title>\n{DESK_TAG}</script>\n</head>\n<body>\n"
    '<a href="/panel/index.html" data-i18n="desk.classic"></a>\n</body>\n</html>\n')
OTHER_TAG = '<script src="/panel/other.js" type="module">'
LINK = 'href="/panel/index.html"'
#: Each defect the checker claims to refuse, the page that carries it, and a
#: word the fault must contain -- so a check that refuses a page for the WRONG
#: reason does not pass for the right one.
BROKEN = {
    "a relative link": (CLEAN.replace(LINK, 'href="desk.css"'), "absolute"),
    "a link with a scheme": (
        CLEAN.replace(LINK, 'href="https://example.test/x"'), "absolute"),
    "a protocol-relative link": (
        CLEAN.replace(LINK, 'href="//example.test/x"'), "absolute"),
    "a traversal": (CLEAN.replace(LINK, 'href="/panel/../server.py"'), "leaves"),
    "a scheme behind the panel prefix": (
        CLEAN.replace(LINK, 'href="/panel/x:y"'), "leaves"),
    "a single-quoted reference": (
        CLEAN.replace(LINK, "href='/panel/index.html'"), "double-quoted"),
    "an unquoted reference": (
        CLEAN.replace(LINK, "href=/panel/index.html"), "double-quoted"),
    "a form action": (
        CLEAN.replace("</body>", '<form action="desk.css"></form>\n</body>'), "absolute"),
    "an inline script": (CLEAN.replace("</body>", "<script>run()</script>\n</body>"),
                         "script"),
    "an upper-case script tag": (CLEAN.replace("</body>", "<SCRIPT>run()</SCRIPT>\n</body>"),
                                 "script"),
    "a script nobody expected": (CLEAN.replace(
        "</body>", f"{OTHER_TAG}</script>\n</body>"), "script"),
    "the expected script missing": (CLEAN.replace(f"{DESK_TAG}</script>\n", ""), "script"),
    "a style block": (CLEAN.replace("</head>", "<style>a{}</style>\n</head>"), "style"),
    "an inline style attribute": (
        CLEAN.replace("<a ", '<a style="color:red" '), "style attribute"),
    "a single-quoted style attribute": (
        CLEAN.replace("<a ", "<a style='color:red' "), "style attribute"),
    "an upper-case style attribute": (
        CLEAN.replace("<a ", '<a STYLE="color:red" '), "style attribute"),
    # The tokenizer reads a `/` before an attribute name as a separator, as it reads a space:
    # `<a/style="x">` carries a style attribute, and so does `<a/onclick="x">` a handler.
    "a style attribute after a slash": (
        CLEAN.replace("<a ", '<a/style="color:red" '), "style attribute"),
    "a style attribute after a tab": (
        CLEAN.replace("<a ", '<a\tstyle="color:red" '), "style attribute"),
    "a style attribute after a newline": (
        CLEAN.replace("<a ", '<a\nstyle="color:red" '), "style attribute"),
    "an inline handler": (CLEAN.replace("<a ", '<a onclick="run()" '), "handler"),
    "a handler after a slash": (CLEAN.replace("<a ", '<a/onclick="run()" '), "handler"),
    "a handler after a tab": (CLEAN.replace("<a ", '<a\tonclick="run()" '), "handler"),
    "a handler after a newline": (CLEAN.replace("<a ", '<a\nonclick="run()" '), "handler"),
    # After a quoted value the tokenizer needs no separator either: it reads the next attribute
    # name where the closing quote ends (a parse error, and an attribute all the same).
    "a style attribute straight after a quoted value": (
        CLEAN.replace(LINK, LINK + 'style="color:red"'), "style attribute"),
    "a handler straight after a quoted value": (
        CLEAN.replace(LINK, LINK + 'onclick="run()"'), "handler"),
    "a handler on the root element straight after a quoted value": (
        CLEAN.replace('<html lang="en">', '<html lang="en"onload="run()">'), "handler"),
    "no language": (CLEAN.replace(' lang="en"', ""), "lang"),
    "an empty title": (CLEAN.replace(f"<title>{PRODUCT_NAME}</title>", "<title> </title>"),
                       "title"),
    "no title": (CLEAN.replace(f"<title>{PRODUCT_NAME}</title>\n", ""), "title"),
    "no doctype": (CLEAN.replace("<!doctype html>\n", ""), "doctype"),
    "a sentence written as a literal": (
        CLEAN.replace("</body>", "<p>The desk is being built.</p>\n</body>"), "literal"),
    "a link text written as a literal": (
        CLEAN.replace(' data-i18n="desk.classic"></a>', ">Classic panel</a>"), "literal"),
    "a title written as a literal": (
        CLEAN.replace(f"<title>{PRODUCT_NAME}</title>", "<title>Desk</title>"), "literal"),
    "an aria-label written as a literal": (
        CLEAN.replace("<a ", '<a aria-label="Tasks" '), "aria-label"),
    "a tooltip written as a literal": (
        CLEAN.replace("<a ", '<a title="Open the classic panel" '), "title"),
    "a placeholder written as a literal": (
        CLEAN.replace("</body>", '<input placeholder="Name">\n</body>'), "placeholder"),
}


def test_the_desk_page_check_passes_a_sound_page_and_only_a_sound_page():
    assert desk_page_faults(CLEAN) == []


@pytest.mark.parametrize("html,needle", list(BROKEN.values()), ids=list(BROKEN))
def test_the_desk_page_check_refuses_each_defect_and_names_it(html, needle):
    faults = desk_page_faults(html)
    assert faults, "a defective page was accepted"
    assert any(needle in fault for fault in faults), faults


def test_the_desk_page_check_allows_exactly_the_scripts_it_is_told_to_expect():
    page = CLEAN.replace("</body>", f"{OTHER_TAG}</script>\n</body>")
    assert desk_page_faults(page, (DESK_TAG, OTHER_TAG)) == []
    assert desk_page_faults(page, (DESK_TAG,)) != []
    assert desk_page_faults(CLEAN, (DESK_TAG, OTHER_TAG)) != []
    assert desk_page_faults(CLEAN, ()) != []


def test_the_desk_page_meets_its_own_contract():
    html = DESK_PAGE.read_text(encoding="utf-8")
    assert desk_page_faults(html) == []
    assert "/panel/desk.html" in server_assets.DESK_ASSETS


def test_every_reference_the_desk_page_makes_is_a_route_this_server_serves():
    """The page names its stylesheet, its script and one neighbour, all real routes.

    The list is exactly spec 5.6.8's, so a further reference has to be argued for
    here, and it is not empty so the served-route check below cannot pass by
    having nothing to judge.
    """
    html = DESK_PAGE.read_text(encoding="utf-8")
    refs = re.findall(QUOTED_REFERENCE, html)
    assert refs == ["/panel/desk.css", "/panel/desk.js", "/panel/index.html"]
    assert set(refs) <= set(server.PANEL_ASSETS), sorted(set(refs) - set(server.PANEL_ASSETS))
    assert html.count('<link rel="stylesheet" href="/panel/desk.css">') == 1
    assert html.count(f"{DESK_TAG}</script>") == 1


#: The regions spec 5.1 gives the desk besides its top bar, in reading order, with
#: the id the page gives each mount. Each starts `empty`: a mount is a container a
#: later module fills, and which word it stands in is a fact only a read can supply.
REGIONS = (("rail", "deskRail"), ("scene", "deskScene"), ("feed", "deskFeed"),
           ("summary", "deskSummary"), ("pult", "deskPult"))


def test_the_desk_page_carries_its_five_region_mounts_once_each_and_empty():
    html = DESK_PAGE.read_text(encoding="utf-8")
    for region, ident in REGIONS:
        assert html.count(f'id="{ident}"') == 1, ident
        tag = re.search(rf'<[a-z]+ [^>]*id="{ident}"[^>]*>', html)
        assert tag and f'data-region="{region}"' in tag[0], ident
        # Each mount is named to a screen reader from the catalogue, never by a literal.
        assert f'data-i18n-label="desk.{region}.label"' in tag[0], ident
        assert 'data-state="empty"' in tag[0] and "empty" in SCREEN_STATES, ident
        assert re.search(rf'id="{ident}"[^>]*></[a-z]+>', html), f"{ident} is not empty"
    assert re.findall(r'data-region="([a-z]+)"', html) == [name for name, _ in REGIONS]
    assert html.count('id="deskShell"') == 1 and html.count('id="deskStatus"') == 1


# -- the boot module -------------------------------------------------------------
#
# `desk.js` reads the routes of `DESK_READS` and paints what each read says on the mount it
# feeds. It may read no other route until one is argued for here, it writes no
# route out by hand (a route is `path.<name>` of the transport module), and it
# names only ids the page carries. The `X-Conduct-Project` header belongs to the transport's
# two doors (`tests/test_desk_transport_claim.py` holds them) and is never named here. The
# project claim itself is READ (`path.project`), first, by every window (spec 4.5.1).

#: The `path.<name>` reads the boot module makes, exactly: the two lists, the automation of
#: the newest run of each task (spec 5.2.1 reads it for every task, as the hub does), the
#: read of the chosen task's newest run and of its controls, and the project claim -- the first
#: read of every window (spec 4.5.1), which embed mode (spec 4.5.5) then reuses.
DESK_READS = frozenset({"tasks", "runs", "automation", "run", "controls", "project"})
MOUNT_IDS = frozenset(ident for _, ident in REGIONS)


def _binding_faults(code: str) -> list[str]:
    """The three facts of the binding the boot module holds (spec 4.5.1): the terminal state
    seals the door, the one read of the module ends the desk on a mismatch, and the first thing
    the boot of the data does is read the claim, before any list."""
    faults = []
    if "door.seal()" not in _function_body(code, "enterForeign"):
        faults.append("the terminal state does not seal the door")
    if "enterForeign()" not in _function_body(code, "readJson"):
        faults.append("a mismatch on a read does not end the desk")
    settle = _function_body(code, "settle")
    claim, lists = settle.find("readClaim()"), settle.find("load()")
    if claim < 0 or lists < 0 or claim > lists:
        faults.append("the claim is not read before the lists")
    return faults


def desk_boot_faults(source: str, page: str) -> list[str]:
    """Every way the desk's boot module steps outside what the shell has argued for.

    Args:
        source: The text of `desk.js`.
        page: The text of `desk.html`.

    Returns:
        One sentence per fault; empty when the module is within its contract.
    """
    code = strip_comments(source)
    faults = [f"a route written out as a literal: {literal}"
              for literal in re.findall(r"""["'`](/command[^"'`]*)""", code)]
    used = set(re.findall(r"\bpath\.([A-Za-z]+)\(", code))
    faults += [f"reads a route the shell has not argued for: path.{name}"
               for name in sorted(used - DESK_READS)]
    faults += [f"no longer reads path.{name}" for name in sorted(DESK_READS - used)]
    named = set(re.findall(r'"(desk[A-Z][A-Za-z]*)"', code))
    faults += [f"names id {ident}, which the page does not carry once"
               for ident in sorted(named) if page.count(f'id="{ident}"') != 1]
    faults += [f"does not mount {ident}" for ident in sorted(MOUNT_IDS - named)]
    if re.search(r"x-conduct-project", code, re.IGNORECASE):
        faults.append("names X-Conduct-Project, which only the transport's two doors send")
    return faults + _binding_faults(code)


def _edit(old: str, new: str):
    def apply(text: str) -> str:
        assert old in text, f"the sabotage target is gone from the module: {old!r}"
        return text.replace(old, new, 1)
    return apply


#: Each defect the guard claims to refuse: the edit that plants it in a copy of
#: the real module, and a word its fault must contain.
BOOT_BROKEN = {
    "a route written out as a literal": (_edit("path.runs()", '"/command/runs"'), "literal"),
    "a read nobody argued for": (_edit("path.runs()", "path.workflows()"), "not argued for"),
    "a read that was dropped": (_edit("path.tasks()", "path.runs()"), "no longer reads"),
    "an id the page does not carry": (_edit('"deskFeed"', '"deskFeeds"'), "does not carry"),
    "a mount the module forgot": (
        lambda text: text.replace('"deskFeed"', '"deskShell"'), "does not mount"),
    "a read the scene never argued for": (
        _edit("path.controls(runId)", "path.decisions(runId)"), "not argued for"),
    "a scene read that was dropped": (
        _edit("path.controls(runId)", "path.run(runId)"), "no longer reads"),
    "the project claim that embed mode needs, dropped": (
        _edit("path.project()", "path.runs()"), "no longer reads"),
    "a terminal state that leaves the door open": (
        _edit("  door.seal();\n", ""), "does not seal the door"),
    "a read that ignores a mismatch": (
        _edit("if (error instanceof Error && error.message === MISMATCH) enterForeign();\n",
              ""), "does not end the desk"),
    "lists read before the claim": (
        _edit("const claim = await readClaim();",
              "await load();\n  const claim = await readClaim();"), "before the lists"),
    "the project header named in the boot module, which has no door of its own": (
        lambda text: text + '\nconst HEADERS = {"X-Conduct-Project": "p"};\n',
        "X-Conduct-Project"),
}


def test_the_desk_boot_module_meets_its_contract():
    source = DESK_SCRIPT.read_text(encoding="utf-8")
    page = DESK_PAGE.read_text(encoding="utf-8")
    assert desk_boot_faults(source, page) == []
    assert "/panel/desk.js" in server_assets.DESK_ASSETS


@pytest.mark.parametrize("edit,needle", list(BOOT_BROKEN.values()), ids=list(BOOT_BROKEN))
def test_the_desk_boot_check_refuses_each_defect_and_names_it(edit, needle):
    faults = desk_boot_faults(edit(DESK_SCRIPT.read_text(encoding="utf-8")),
                              DESK_PAGE.read_text(encoding="utf-8"))
    assert faults, "a defective module was accepted"
    assert any(needle in fault for fault in faults), faults


# -- the boot module writes nothing ----------------------------------------------
#
# Facts enter the desk through a READ and through nothing else, and this module is the
# one that turns a read into a word on a region. It may not reach the mutation door
# (the transport's `submit` and the session it mints a write's token from), open a door
# of its own, or say a state word the seven do not hold. The event stream is not among
# them: it is a read, and the spec puts the desk's subscription in this module. The doors
# are named, not counted: the function reads the module's code, comments stripped, so
# prose that says "submit" does not red and a real call does.

#: What reaches a write, or a door of the module's own. Each is a word of the code.
WRITE_DOORS = (r"\bsubmit\b", r"\bdropSession\b", r"\bfetch\s*\(", r"\bmethod\s*:",
               r'"POST"', r"\bXMLHttpRequest\b", r"\bsendBeacon\b")
#: The functions whose returns ARE phases: every word they return is a state word.
PHASE_FUNCTIONS = ("phaseOf", "worst")


def _function_body(code: str, name: str) -> str:
    start = re.search(rf"function\s+{name}\s*\([^)]*\)\s*\{{", code)
    if start is None:
        return ""
    depth, at = 1, start.end()
    while at < len(code) and depth:
        depth += (code[at] == "{") - (code[at] == "}")
        at += 1
    return code[start.end():at]


def _state_words(code: str) -> set[str]:
    """Every literal the module puts in a state position: a mark, an attribute, a phase."""
    words = set(re.findall(r'\bmark\([^,()]+,\s*"([^"]*)"\s*\)', code))
    words |= set(re.findall(r'data-state"\s*,\s*"([^"]*)"', code))
    words |= set(re.findall(r'\bdataset\.state\s*=\s*"([^"]*)"', code))
    words |= set(re.findall(r'\bphase\s*:\s*"([^"]*)"', code))
    for name in PHASE_FUNCTIONS:
        words |= set(re.findall(r'"([a-z]+)"', _function_body(code, name)))
    return words


def desk_write_faults(source: str) -> list[str]:
    """Every way a desk module reaches a write door or says a stray state word.

    Args:
        source: The text of one desk module.

    Returns:
        One sentence per fault; empty when the module only reads and says the seven.
    """
    code = strip_comments(source)
    faults = [f"reaches a write door: {found.group(0)}"
              for pattern in WRITE_DOORS for found in re.finditer(pattern, code)]
    faults += [f"writes the state word {word!r}, which is not one of the seven"
               for word in sorted(_state_words(code) - set(SCREEN_STATES))]
    return faults


#: Each defect the guard claims to refuse: the edit that plants it in a copy of the real
#: module, and a word its fault must contain.
BOOT_WRITES = {
    "a submit taken from the transport": (
        lambda text: text + "\nconst {submit} = createTransport(locale);\n", "write door"),
    "a session drop": (lambda text: text + "\ndropSession();\n", "write door"),
    "a POST method": (lambda text: text + '\nconst OPTIONS = {method: "POST"};\n',
                      "write door"),
    "a door of its own": (lambda text: text + '\nfetch("/command/tasks");\n', "write door"),
    "a state word the seven do not hold, through mark": (
        lambda text: text + '\nmark(shell, "done");\n', "'done'"),
    "a phase word the seven do not hold, returned": (
        _edit('  return "ready";\n}', '  return "finished";\n}'), "'finished'"),
    "a phase word the seven do not hold, in a phase property": (
        _edit('Object.freeze({phase: "loading", list: NONE})',
              'Object.freeze({phase: "pending", list: NONE})'), "'pending'"),
    "a state word through setAttribute": (
        lambda text: text + '\nnode.setAttribute("data-state", "ok");\n', "'ok'"),
    "a state word through dataset": (
        lambda text: text + '\nnode.dataset.state = "idle";\n', "'idle'"),
}


def test_the_desk_boot_module_writes_nothing_and_says_only_the_seven_state_words():
    assert len(SCREEN_STATES) == 7
    assert desk_write_faults(DESK_SCRIPT.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("edit,needle", list(BOOT_WRITES.values()), ids=list(BOOT_WRITES))
def test_the_desk_write_check_refuses_each_planted_write_and_names_it(edit, needle):
    faults = desk_write_faults(edit(DESK_SCRIPT.read_text(encoding="utf-8")))
    assert faults, "a defective module was accepted"
    assert any(needle in fault for fault in faults), faults


def test_the_desk_write_check_does_not_take_the_stream_for_a_write_door():
    """The event stream is a read: a frame buys a re-read and is never a fact or a write.

    The boot module is where the spec puts its subscription (5.6.1), so a check that refused
    `openStream` would refuse the desk its own live updates the day they are written.
    """
    source = DESK_SCRIPT.read_text(encoding="utf-8")
    assert desk_write_faults(source + "\nconst stream = openStream();\n") == []


def test_the_desk_write_check_reads_code_and_not_the_prose_around_it():
    prose = '// it never calls submit() and never says "done" in mark(shell, "done")\n'
    assert desk_write_faults(prose + DESK_SCRIPT.read_text(encoding="utf-8")) == []


#: The modules of the desk that only read, draw or say a word: none reaches a write door, and
#: none says a state word outside the seven. A module joins this list the day it is written.
READ_SIDE = ("desk.js", "desk-rail.js", "desk-scene.js", "desk-status.js", "desk-hash.js",
             "desk-embed.js", "desk-time.js", "desk-queue-model.js", "desk-flag-model.js",
             "desk-feed-model.js", "desk-feed.js")
#: The render modules, and the one function each exports (`mountX(mount, state, handlers)`).
RENDER_MODULES = {"desk-rail.js": "mountRail", "desk-scene.js": "mountScene",
                  "desk-feed.js": "mountFeed", "desk-pult.js": "mountPult"}
#: The modules that draw a form and so name its event, `"submit"`: they are held to the same
#: guard with that one quoted word taken out, so a call to the transport's `submit` still
#: reds. A form of the console is not a door: its handler asks the boot module, which writes
#: nothing either.
FORM_SIDE = ("desk-pult.js",)


@pytest.mark.parametrize("name", READ_SIDE)
def test_no_read_side_desk_module_reaches_a_write_door_or_says_a_stray_state_word(name):
    source = (PANEL / name).read_text(encoding="utf-8")
    assert desk_write_faults(source) == []
    # Calibration: the same check bites a write planted in THIS module, so a clean answer
    # is not an empty one.
    assert desk_write_faults(source + "\nsubmit();\n")
    assert desk_write_faults(source + '\nmark(node, "done");\n')


@pytest.mark.parametrize("name", FORM_SIDE)
def test_a_desk_module_that_draws_a_form_reaches_no_write_door_though_it_names_the_event(name):
    source = (PANEL / name).read_text(encoding="utf-8")
    assert '"submit"' in source and desk_write_faults(source) != []
    plain = source.replace('"submit"', '""')
    assert desk_write_faults(plain) == []
    assert desk_write_faults(plain + "\nsubmit();\n")
    assert desk_write_faults(plain + "\nconst {submit} = createTransport(locale);\n")
    assert desk_write_faults(plain + '\nfetch("/command/tasks");\n')
    assert desk_write_faults(plain + '\nmark(node, "done");\n')


@pytest.mark.parametrize("name,mount", list(RENDER_MODULES.items()))
def test_a_desk_render_module_exports_only_its_mount(name, mount):
    code = strip_comments((PANEL / name).read_text(encoding="utf-8"))
    exported = re.findall(r"^export\s+(?:async\s+)?(?:function|const|class)\s+(\w+)", code,
                          re.MULTILINE)
    assert exported == [mount]


# -- the partition over studio*, desk* and hub* ---------------------------------
#
# `test_studio_source.py` holds the real directory to `partition_faults`; what is
# held HERE is the function itself, on synthetic input, so each way it claims to
# refuse a tree is shown refusing one and a check that stopped biting reds in
# this file rather than passing quietly over a real tree that happens to be clean.

#: `hub.html` is packaged and is NOT a registry row: spec 4.6.3 has `GET /` answer
#: it and `/hub/<name>` answer only `HUB_ASSETS`, the import closure of `hub.js`.
BASE = {
    "packaged": frozenset({"studio.js", "studio.css", "studio.html", "desk.html",
                           "desk-hash.js", "hub.js", "hub.html"}),
    "modules": frozenset({"studio.js", "desk-hash.js"}),
    "desk": frozenset({"desk.html", "desk-hash.js"}),
    "hub": frozenset({"hub.js", "desk-hash.js"}),
}


def _with(**changes):
    """The clean tree with some of its four sets replaced."""
    return {**BASE, **changes}


def _grown(key: str, *names: str) -> frozenset[str]:
    return BASE[key] | frozenset(names)


TORN = {
    "a desk file no registry names": (
        _with(packaged=_grown("packaged", "desk-extra.js"),
              modules=_grown("modules", "desk-extra.js")), "DESK_ASSETS"),
    "a js module no guard names": (
        _with(packaged=_grown("packaged", "desk-extra.js"),
              desk=_grown("desk", "desk-extra.js")), "MODULES"),
    "a studio module no guard names": (
        _with(packaged=_grown("packaged", "studio-extra.js")), "MODULES"),
    "a guard row naming no file": (
        _with(modules=_grown("modules", "desk-gone.js")), "MODULES names no packaged"),
    "a desk registry row naming no file": (
        _with(desk=_grown("desk", "desk-gone.html")), "DESK_ASSETS row names no"),
    "a hub file inside the desk registry": (
        _with(desk=_grown("desk", "hub.js")), "hub file in DESK_ASSETS"),
    "a hub file no hub registry names": (
        _with(hub=frozenset({"desk-hash.js"})), "hub file in no HUB_ASSETS"),
    "a hub registry row naming no file": (
        _with(hub=_grown("hub", "hub-gone.js")), "HUB_ASSETS row names no"),
    "a hub registry row that is neither a hub file nor shared": (
        _with(hub=_grown("hub", "desk.html")), "neither a hub file nor a shared"),
    "a shared module missing from the hub registry": (
        _with(hub=frozenset({"hub.js"})), "shared module missing"),
    "a hub file while no hub registry exists": (
        _with(hub=None), "no hub registry exists"),
    "the hub entry page listed as a registry row": (
        _with(hub=_grown("hub", "hub.html")), "entry page listed in HUB_ASSETS"),
    "a hub registry with no packaged entry page": (
        _with(packaged=BASE["packaged"] - {"hub.html"}), "entry page not packaged"),
}


def test_the_partition_check_passes_a_tree_every_file_of_which_is_accounted_for():
    assert partition_faults(**BASE) == []


@pytest.mark.parametrize("tree,needle", list(TORN.values()), ids=list(TORN))
def test_the_partition_check_refuses_each_way_a_tree_can_come_apart(tree, needle):
    faults = partition_faults(**tree)
    assert faults, "a broken tree was accepted"
    assert any(needle in fault for fault in faults), faults


def test_a_missing_hub_registry_is_tolerated_only_while_no_hub_file_is_packaged():
    quiet = _with(packaged=frozenset({"studio.js", "desk.html", "desk-hash.js"}),
                  hub=None)
    assert partition_faults(**quiet) == []
    assert partition_faults(**_with(hub=None)) != []


#: The name spec 4.6.3 gives the document `GET /` answers on the hub, written here
#: on purpose rather than read from the helper, so the helper's own constant is
#: held to the spec and not to itself.
HUB_ENTRY = "hub.html"
#: The hub's own rows of the `/hub/<name>` allowlist (spec 4.6.3), then the four
#: modules it shares with the desk (spec 4.1.10). `hub.html` is in neither list.
SPEC_HUB_OWN = ("hub.css", "hub.js", "hub-frame.js", "hub-rail.js", "hub-stub.js",
                "hub-add.js", "hub-copy.js")
SPEC_SHARED = ("desk-hash.js", "desk-status.js", "desk-status-copy.js", "desk-time.js")


def test_the_partition_names_the_hub_entry_page_the_spec_gives_the_root():
    assert studio_partition.HUB_ENTRY_PAGE == HUB_ENTRY


def test_the_hub_entry_page_is_held_packaged_and_outside_the_hub_registry():
    """Each entry-page rule alone: one defect in, exactly one sentence out.

    A row that named its defect by `any(needle in fault)` would still pass if a
    second mechanism reported the same tree, so these two are compared whole.
    """
    listed = partition_faults(**_with(hub=_grown("hub", HUB_ENTRY)))
    assert listed == [f"hub entry page listed in HUB_ASSETS: {HUB_ENTRY}"]
    missing = partition_faults(**_with(packaged=BASE["packaged"] - {HUB_ENTRY}))
    assert missing == [f"hub entry page not packaged: {HUB_ENTRY}"]


def test_the_tree_spec_4_6_3_describes_is_accounted_for_with_the_entry_page_outside_the_registry():
    """The day the hub page is packaged and its registry is written to spec.

    Eleven `HUB_ASSETS` rows go through the loader exactly as lane H's module
    would hand them over; `hub.html` is the twelfth packaged file and is served
    at `/`, so it is not one of them. Listing it as a row is what this partition
    once demanded, so that tree is shown refused as well.
    """
    def row(name: str) -> tuple[str, str]:
        kind = "text/css" if name.endswith(".css") else "text/javascript"
        return f"{kind}; charset=utf-8", name

    module = SimpleNamespace(HUB_ASSETS={
        f"/hub/{name}": row(name) for name in SPEC_HUB_OWN + SPEC_SHARED})
    hub = hub_registry_names(lambda _name: module)
    assert len(hub) == 11 and HUB_ENTRY not in hub
    shared = frozenset(SPEC_SHARED)
    tree = {
        "packaged": frozenset(SPEC_HUB_OWN) | shared | {HUB_ENTRY, "desk.html", "studio.js"},
        "modules": shared | {"studio.js"},
        "desk": shared | {"desk.html"},
        "hub": hub,
    }
    assert partition_faults(**tree) == []
    assert partition_faults(**{**tree, "hub": hub | {HUB_ENTRY}}) != []


def test_the_partition_reads_only_studio_desk_and_hub_files_with_a_page_suffix(tmp_path):
    for name in ("studio.js", "studio.css", "desk.html", "hub.js", "graph.js",
                 "index.html", "desk.json", "notes.txt", "command.js"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert packaged_names(tmp_path) == frozenset(
        {"studio.js", "studio.css", "desk.html", "hub.js"})


def _absent(name: str):
    raise ModuleNotFoundError(f"No module named {name!r}", name=name)


def test_a_hub_registry_that_is_not_written_yet_reads_as_absent_not_as_empty():
    assert hub_registry_names(_absent) is None

    def package_absent(_name: str):
        raise ModuleNotFoundError("No module named 'conductor.hub'", name="conductor.hub")

    assert hub_registry_names(package_absent) is None


def test_a_hub_registry_written_later_is_read_by_the_name_lane_h_gives_it():
    seen = []
    module = SimpleNamespace(HUB_ASSETS={
        "/hub/hub.js": ("text/javascript; charset=utf-8", "hub.js"),
        "/hub/desk-hash.js": ("text/javascript; charset=utf-8", "desk-hash.js")})

    def importer(name: str):
        seen.append(name)
        return module

    assert hub_registry_names(importer) == frozenset({"hub.js", "desk-hash.js"})
    assert seen == ["conductor.hub.assets"]


def test_a_registry_that_exists_but_is_broken_is_never_read_as_absent():
    def other_module_missing(_name: str):
        raise ModuleNotFoundError("No module named 'tomli_w'", name="tomli_w")

    with pytest.raises(ModuleNotFoundError):
        hub_registry_names(other_module_missing)
    with pytest.raises(AttributeError):
        hub_registry_names(lambda _name: SimpleNamespace())
    with pytest.raises(AssertionError):
        hub_registry_names(lambda _name: SimpleNamespace(HUB_ASSETS=("hub.js",)))
    with pytest.raises(AssertionError):
        hub_registry_names(lambda _name: SimpleNamespace(HUB_ASSETS={"/hub/hub.js": "hub.js"}))
