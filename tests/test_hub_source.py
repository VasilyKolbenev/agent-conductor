"""Source-level contract of the hub's page and of the registry that serves it (spec 4.1.10, 4.6.3).

The hub page is a window of its own: the hub answers `GET /` with `hub.html` and `/hub/<name>` with
the files of `HUB_ASSETS`, the import closure of `hub.js`, and nothing else. So this module holds
the page to the shape that serving depends on -- a document with a language and a title, every
reference an absolute `/hub/...` path, nothing inline and no English written as a literal -- and
holds each module to what it may reach: only its siblings and the four modules the desk shares,
never a Studio file, the wire only in `hub.js`, no clock anywhere else, no path of a child's, no
automation state compared. Like `test_studio_source.py` and `test_desk_source.py` this is the
change-detection half: it reads text and says nothing about what a browser renders. Every check is a
function over text, and the tables of planted defects feed each one what it claims to refuse, so a
check that silently stopped biting reds here and not in a review.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from conductor.hub import assets
from tests.studio_partition import SHARED_MODULES
from tests.test_desk_style import PAIRS, THEMES, palette_faults, tokens
from tests.test_panel_cascade import rules, strip_comments
from tests.test_panel_colour import contrast
from tests.test_panel_contrast import NONTEXT_MIN, TEXT_MIN

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
PAGE = PANEL / "hub.html"
STYLE = PANEL / "hub.css"
LINE_CAP = 800
#: The hub's own files by name, grown by the commit that adds one (the registry is held to exactly
#: these and the four shared modules). `hub-frame.js` and `hub-add.js` are not written yet.
OWN = ("hub.js", "hub-copy.js", "hub-rail.js", "hub-stub.js")
SHARED = tuple(sorted(SHARED_MODULES))
JS_TYPE = "text/javascript; charset=utf-8"
CSS_TYPE = "text/css; charset=utf-8"
#: The one script and the one stylesheet the page loads, each by its absolute `/hub/` path.
SCRIPT_TAG = '<script src="/hub/hub.js" type="module">'
LINK_TAG = '<link rel="stylesheet" href="/hub/hub.css">'
PRODUCT_NAME = "December Command"
LABEL_ATTRIBUTES = ("aria-label", "title", "alt", "placeholder")
ANY_REFERENCE = r"\b(?:href|src|action|formaction)\s*="
QUOTED_REFERENCE = r'\b(?:href|src|action|formaction)="([^"]*)"'
IMPORTS = r'from "(\./[a-z0-9-]+\.js)";'
#: Each hub module with the one set of siblings it may import. The shared modules import only each
#: other (the desk's guard holds them), so the hub's closure is these plus those.
PERMITTED = {
    "hub-copy.js": {"./desk-status-copy.js"},
    "hub-rail.js": {"./desk-hash.js", "./desk-status.js", "./desk-time.js", "./hub-copy.js"},
    "hub-stub.js": {"./desk-time.js", "./hub-copy.js", "./hub-rail.js"},
    "hub.js": {"./desk-hash.js", "./hub-copy.js", "./hub-rail.js", "./hub-stub.js"},
}
REGIONS = (("top", "hubTop"), ("banners", "hubBanners"), ("confirm", "hubConfirm"),
           ("rail", "hubRail"), ("center", "hubCenter"), ("side", "hubSide"))


def _source(name: str) -> str:
    return (PANEL / name).read_text(encoding="utf-8")


def _code(name: str) -> str:
    return strip_comments(_source(name))


# -- the packaged files and the registry -----------------------------------------------------------


def test_the_hub_files_are_packaged_and_each_is_under_the_line_cap():
    for name in ("hub.html", "hub.css", *OWN):
        path = PANEL / name
        assert path.is_file() and path.parent == PANEL, name
        assert len(path.read_text(encoding="utf-8").splitlines()) <= LINE_CAP, name


def _closure(start: str) -> set[str]:
    seen, pending = set(), [start]
    while pending:
        name = pending.pop()
        if name not in seen:
            seen.add(name)
            pending += [ref[2:] for ref in re.findall(IMPORTS, _source(name))]
    return seen


def test_the_registry_is_exactly_the_import_closure_of_hub_js_and_its_stylesheet():
    closure = _closure("hub.js")
    served = {name for _, name in assets.HUB_ASSETS.values()}
    assert served == closure | {"hub.css"}, sorted(served ^ (closure | {"hub.css"}))
    assert closure == {*OWN, *SHARED}, "every module of the hub is reached from hub.js"
    assert "hub.html" not in served, "the entry page is answered by `GET /`, never by a row"
    for route, (kind, name) in assets.HUB_ASSETS.items():
        assert route == f"/hub/{name}", route
        assert kind == (CSS_TYPE if name.endswith(".css") else JS_TYPE), route


def test_the_registry_serves_each_file_byte_for_byte_from_the_packaged_directory():
    for route, (_kind, name) in assets.HUB_ASSETS.items():
        assert (PANEL / name).is_file(), route
        assert re.fullmatch(r"[a-z][a-z-]*\.(?:js|css)", name), name


# -- the entry page --------------------------------------------------------------------------------


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
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.names: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.names += [name for name, _value in attrs]


def _inline_faults(html: str) -> list[str]:
    faults = []
    if re.findall(r"<script\b[^>]*>", html, re.IGNORECASE) != [SCRIPT_TAG]:
        faults.append("the script tags are not exactly the one the page may carry")
    if re.findall(r"<link\b[^>]*>", html, re.IGNORECASE) != [LINK_TAG]:
        faults.append("the link tags are not exactly the one stylesheet")
    if re.search(r"<style\b", html, re.IGNORECASE):
        faults.append("the page carries a <style> block")
    seen = _Attributes()
    seen.feed(html)
    seen.close()
    if "style" in seen.names or re.search(r"[\s/]style\s*=", html, re.IGNORECASE):
        faults.append("the page carries an inline style attribute")
    if (any(name.startswith("on") for name in seen.names)
            or re.search(r"[\s/]on[a-z]+\s*=", html, re.IGNORECASE)):
        faults.append("the page carries an inline handler")
    return faults


class _Words(HTMLParser):
    """The text and labelling attributes of a page; comments and scripts are not words."""

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
        if not ref.startswith("/hub/"):
            faults.append(f"reference is not an absolute /hub/ path: {ref}")
        elif "//" in ref or ".." in ref or ":" in ref:
            faults.append(f"reference leaves the hub's directory: {ref}")
    return faults


def hub_page_faults(html: str) -> list[str]:
    """Every way `html` fails the hub page's contract, as plain sentences (empty when sound)."""
    return (_document_faults(html) + _inline_faults(html) + _reference_faults(html)
            + _text_faults(html))


CLEAN = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    f"<title>{PRODUCT_NAME}</title>\n{LINK_TAG}\n{SCRIPT_TAG}</script>\n</head>\n<body>\n"
    '<p data-i18n="hub.path.none"></p>\n</body>\n</html>\n')
BROKEN = {
    "no doctype": (CLEAN.replace("<!doctype html>\n", ""), "no <!doctype html>"),
    "no language": (CLEAN.replace(' lang="en"', ""), "carries no lang"),
    "no title": (CLEAN.replace(f"<title>{PRODUCT_NAME}</title>\n", ""), "no title"),
    "a second script": (CLEAN.replace("</body>", '<script src="/hub/other.js"></script></body>'),
                        "script tags are not exactly"),
    "an inline script": (CLEAN.replace("</body>", "<script>run()</script></body>"),
                         "script tags are not exactly"),
    "a style block": (CLEAN.replace("</head>", "<style>p{}</style></head>"), "<style> block"),
    "a style attribute": (CLEAN.replace("<p ", '<p style="x:y" '), "inline style attribute"),
    "an inline handler": (CLEAN.replace("<p ", '<p onclick="go()" '), "inline handler"),
    "a second stylesheet": (CLEAN.replace("</head>", '<link rel="stylesheet" href="/hub/x.css">'
                                          "</head>"), "link tags are not exactly"),
    "a reference into the panel": (CLEAN.replace("/hub/hub.css", "/panel/desk.css"),
                                   "not an absolute /hub/ path"),
    "a reference to another origin": (CLEAN.replace("/hub/hub.css", "http://x.test/a.css"),
                                      "not an absolute /hub/ path"),
    "a traversing reference": (CLEAN.replace("/hub/hub.css", "/hub/../hub.css"),
                               "leaves the hub's directory"),
    "an unquoted reference": (CLEAN.replace('href="/hub/hub.css"', "href=/hub/hub.css"),
                              "not a double-quoted attribute"),
    "a sentence written in": (CLEAN.replace('data-i18n="hub.path.none"></p>',
                                            '>No project chosen</p>'), "written as a literal"),
    "an aria-label written in": (CLEAN.replace("<p ", '<p aria-label="Projects" '),
                                 "aria-label written as a literal"),
}


def test_the_hub_page_check_passes_a_sound_page_and_only_a_sound_page():
    assert hub_page_faults(CLEAN) == []


@pytest.mark.parametrize("html,needle", list(BROKEN.values()), ids=list(BROKEN))
def test_the_hub_page_check_refuses_each_defect_and_names_it(html, needle):
    faults = hub_page_faults(html)
    assert faults, "a defective page was accepted"
    assert any(needle in fault for fault in faults), faults


def test_the_hub_page_meets_its_own_contract_and_names_its_regions_once_each():
    html = PAGE.read_text(encoding="utf-8")
    assert hub_page_faults(html) == []
    assert re.findall(QUOTED_REFERENCE, html) == ["/hub/hub.css", "/hub/hub.js"]
    for region, ident in REGIONS:
        assert html.count(f'id="{ident}"') == 1, ident
        tag = re.search(rf'<[a-z]+ [^>]*id="{ident}"[^>]*>', html)
        assert tag and f'data-region="{region}"' in tag[0], ident
        assert f'data-i18n-label="hub.{region}.label"' in tag[0], ident
    assert html.count('id="hubShell"') == 1 and html.count('id="hubStatus"') == 1
    assert re.findall(r'data-region="([a-z]+)"', html) == [name for name, _ in REGIONS]


# -- what each module may reach --------------------------------------------------------------------

#: Words no hub file may carry: the Studio's sealed list (markup, storage, eval, a second
#: transport).
SEALED = ("innerhtml", "outerhtml", "insertadjacenthtml", "localstorage", "sessionstorage",
          "document.cookie", "console.", "eval(", "new function(", "import(", "importscripts",
          "xmlhttprequest", "websocket", "webtransport", "rtcpeerconnection", "sendbeacon")
#: What only the boot and transport module may use: a door, a clock, a timer, the platform.
ONLY_HUB_JS = ("fetch(", "eventsource", "settimeout(", "setinterval(", "date.now", "new date(",
               "navigator.", "performance.")
#: What only the frame module (not yet written) may use.
ONLY_FRAME = ("postmessage(", "location.replace", "window.open(", 'addeventlistener("message"')
DOM_WORDS = ("document.", "window.", "globalthis.")
#: What a hub file may never compare or name: the state of a run (the shared module says it), a
#: path of a child's (the page never asks a child), the automation's state.
BANNED_NAMES = (r"human_state", r"last_outcome", r"reason_code", r"/command\b",
                r"automation\??\.state", r"automation\[")


def hub_module_faults(name: str, code: str) -> list[str]:
    """Every rule `code` (comments stripped) breaks for the hub module called `name`."""
    lowered = code.lower()
    faults = [f"sealed word: {word}" for word in SEALED if word in lowered]
    if name != "hub.js":
        faults += [f"only hub.js may use {word}" for word in ONLY_HUB_JS if word in lowered]
    faults += [f"only the frame may use {word}" for word in ONLY_FRAME if word in lowered]
    if name == "hub-copy.js":
        faults += [f"the copy is data and reaches for {word}" for word in DOM_WORDS
                   if word in lowered]
    faults += [f"a banned name: {pattern}" for pattern in BANNED_NAMES if re.search(pattern, code)]
    wanted = PERMITTED.get(name)
    for ref in re.findall(IMPORTS, code):
        if wanted is not None and ref not in wanted:
            faults.append(f"{name} may not import {ref}")
        if re.match(r"\./(?:studio|command)-", ref):
            faults.append(f"the hub reaches for a Studio module: {ref}")
    return faults


PLANTED = {
    "innerHTML": ("hub-rail.js", "const a = node.innerHTML;", "sealed word: innerhtml"),
    "storage": ("hub.js", "const a = localStorage;", "sealed word: localstorage"),
    "a console call": ("hub-rail.js", "console.log(1);", "sealed word: console."),
    "a second door in the rail": ("hub-rail.js", "await fetch(url);", "only hub.js may use fetch("),
    "a stream in the copy": ("hub-copy.js", "new EventSource(u);",
                             "only hub.js may use eventsource"),
    "a clock in the rail": ("hub-rail.js", "const a = Date.now();", "only hub.js may use date.now"),
    "a timer in the rail": ("hub-rail.js", "setTimeout(f, 1);", "only hub.js may use settimeout("),
    "the platform in the rail": ("hub-rail.js", "navigator.language;", "only hub.js may use"),
    "a message from elsewhere": ("hub.js", "window.postMessage(1, u);",
                                 "only the frame may use postmessage("),
    "a navigation": ("hub-rail.js", "location.replace(u);", "only the frame may use location"),
    "the DOM in the copy": ("hub-copy.js", "document.title = 1;", "the copy is data"),
    "a human state": ("hub-rail.js", "if (run.human_state === 1) {}", "banned name: human_state"),
    "an outcome": ("hub-rail.js", "run.last_outcome;", "banned name: last_outcome"),
    "an automation state": ("hub-rail.js", "automation.state === 'x';",
                            "banned name: automation"),
    "a child's path": ("hub.js", "const a = '/command/runs';", "banned name: /command"),
    "a Studio import": ("hub-rail.js", 'import {a} from "./studio-i18n.js";',
                        "may not import ./studio-i18n.js"),
    "the view helper": ("hub.js", 'import {element} from "./command-view.js";',
                        "reaches for a Studio module"),
    "an import outside the row": ("hub-copy.js", 'import {a} from "./hub-rail.js";',
                                  "may not import ./hub-rail.js"),
}


@pytest.mark.parametrize("name,plant,needle", list(PLANTED.values()), ids=list(PLANTED))
def test_the_hub_module_check_refuses_each_planted_defect_and_names_it(name, plant, needle):
    faults = hub_module_faults(name, _code(name) + "\n" + plant)
    assert any(needle in fault for fault in faults), faults


def test_the_hub_module_check_reads_code_and_not_the_prose_around_it():
    prose = "// innerHTML, fetch(, /command/runs, human_state, localStorage, Date.now\n"
    assert hub_module_faults("hub-rail.js", strip_comments(prose + _source("hub-rail.js"))) == []


@pytest.mark.parametrize("name", OWN)
def test_each_hub_module_meets_its_own_contract(name):
    assert hub_module_faults(name, _code(name)) == []
    assert set(re.findall(IMPORTS, _source(name))) == PERMITTED[name], name


FUNCTION_CAP = 50
FUNCTION = re.compile(r"^(?:export )?function \w+\([^)]*\) \{\n(.*?)^\}$",
                      re.MULTILINE | re.DOTALL)


def long_functions(source: str) -> list[str]:
    """The named functions of a module that are longer than the cap, with their length."""
    found = [(match.group(0).splitlines()[0], match.group(0).count("\n") + 1)
             for match in FUNCTION.finditer(source)]
    return [f"{head} is {length} lines" for head, length in found if length > FUNCTION_CAP]


def test_the_function_check_finds_a_function_over_the_cap_and_only_that_one():
    body = "".join(f"  step({n});\n" for n in range(FUNCTION_CAP))
    long = f"export function tooLong(a) {{\n{body}}}\n"
    short = "function fine(a) {\n  return a;\n}\n"
    assert long_functions(short) == [] and len(long_functions(short + long)) == 1
    assert "tooLong" in long_functions(short + long)[0]


@pytest.mark.parametrize("name", OWN)
def test_every_hub_function_is_at_most_fifty_lines(name):
    assert long_functions(_source(name)) == []


# -- the stylesheet --------------------------------------------------------------------------------


def _wrap(css: str) -> str:
    return "<style>" + css + "</style><script></script>"


CSS = STYLE.read_text(encoding="utf-8")
#: Text on the page's own ground (`--space` is the body): held to the text floor in both themes.
ON_SPACE = (("--ink", "--space", TEXT_MIN), ("--muted", "--space", TEXT_MIN))
#: The pairs a rule may set text on: the measured ones, never the quiet colour (non-text floor
#: only).
MEASURED = {(paint, ground) for paint, ground, _ in (*PAIRS, *ON_SPACE) if paint != "--faint"}
#: A text colour with no ground of its own stands on the page's ground or a panel: only the four
#: colours measured on both.
ON_EITHER = {"--ink", "--muted", "--ion", "--amber"}


def sheet_faults(css: str) -> list[str]:
    """Every way the hub's sheet leaves the approved system: tokens, floors, targets, motion."""
    faults = palette_faults(_wrap(css))
    declared = rules(_wrap(css))
    controls = {"button", "select", "input", "a"}
    floor = [rule for rule in declared if rule.decls.get("min-height") == "44px"]
    reached = {part for rule in floor for part in re.findall(r"[a-z]+$", rule.selector)
               if part in controls}
    faults += [f"{kind} is not held to the 44px target floor"
               for kind in sorted(controls - reached)]
    if re.search(r"@import|url\(|@font-face", css):
        faults.append("the sheet loads something from outside itself")
    if "@keyframes" in css or "animation" in css:
        faults.append("the sheet animates")
    faults += [f"a colour outside the system: {match}" for match in re.findall(
        r"(?<![\w-])#[0-9a-fA-F]{3,8}\b", re.sub(r":root\[?[^{]*\{[^}]*\}", "", css))]
    faults += [f"text in --faint: {rule.selector}" for rule in declared
               if rule.decls.get("color", "").strip() == "var(--faint)"]
    for rule in declared:
        paint = re.findall(r"var\((--[a-z-]+)\)", rule.decls.get("color", ""))
        ground = re.findall(r"var\((--[a-z-]+)\)", rule.decls.get("background", ""))
        if paint and ground and (paint[0], ground[0]) not in MEASURED:
            faults.append(f"text stands on an unmeasured ground: {rule.selector}")
        elif paint and not ground and paint[0] not in ON_EITHER:
            faults.append(f"text in a token with no ground of its own: {rule.selector}")
    return faults


def _swap(old: str, new: str):
    return lambda css: css.replace(old, new, 1)


SHEET_BROKEN = {
    "a token moved": (_swap("--ion:#d4f99b", "--ion:#d4f99c"), "is not the concept's"),
    "a third :root block": (lambda css: css + ":root{--ink:#000}\n", "expected exactly 2"),
    "a target under the floor": (_swap("min-height:44px", "min-height:40px"), "44px target floor"),
    "an import": (lambda css: '@import "x.css";\n' + css, "loads something from outside"),
    "a remote image": (lambda css: css + "\na{background:url(http://x)}", "loads something"),
    "an animation": (lambda css: css + "\na{animation:x 1s}", "animates"),
    "a colour written by hand": (lambda css: css + "\np{border-color:#abcdef}",
                                 "a colour outside the system"),
    "faint used for text": (lambda css: css + "\np{color:var(--faint)}", "text in --faint"),
    "a ground nobody measured": (lambda css: css + "\np{color:var(--ink);background:var(--line)}",
                                 "unmeasured ground"),
}


def test_the_hub_sheet_meets_its_whole_contract():
    assert sheet_faults(CSS) == []


@pytest.mark.parametrize("edit,needle", list(SHEET_BROKEN.values()), ids=list(SHEET_BROKEN))
def test_the_hub_sheet_check_refuses_each_defect_and_names_it(edit, needle):
    faults = sheet_faults(edit(CSS))
    assert faults, "a defective sheet was accepted"
    assert any(needle in fault for fault in faults), faults


@pytest.mark.parametrize("theme", THEMES)
def test_every_pair_the_hub_paints_clears_its_floor_in_both_themes(theme):
    palette = tokens(theme, _wrap(CSS))
    for foreground, ground, floor in (*PAIRS, *ON_SPACE):
        ratio = contrast(palette[foreground], palette[ground])
        assert ratio >= floor, f"{theme}: {foreground} on {ground} is {ratio:.2f}:1, floor {floor}"
    assert NONTEXT_MIN < TEXT_MIN
