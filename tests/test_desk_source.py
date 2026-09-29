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
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import server, server_assets
from tests import studio_partition
from tests.studio_partition import hub_registry_names, packaged_names, partition_faults

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
DESK_PAGE = PANEL / "desk.html"
#: The opening tags of the scripts the page may load, in order, exactly. None
#: yet: the page is a stub. The slice that adds `desk.js` adds its tag here in
#: the same commit, so a script cannot arrive on the page unargued.
EXPECTED_SCRIPTS: tuple[str, ...] = ()
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


def _inline_faults(html: str, expected_scripts: tuple[str, ...]) -> list[str]:
    faults = []
    if re.findall(r"<script\b[^>]*>", html, re.IGNORECASE) != list(expected_scripts):
        faults.append("the script tags are not exactly the expected ones")
    if re.search(r"<style\b", html, re.IGNORECASE):
        faults.append("the page carries a <style> block")
    if re.search(r"\sstyle\s*=", html, re.IGNORECASE):
        faults.append("the page carries an inline style attribute")
    if re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE):
        faults.append("the page carries an inline handler")
    return faults


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
            + _reference_faults(html))


CLEAN = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    "<title>Desk</title>\n</head>\n<body>\n"
    '<a href="/panel/index.html">Classic panel</a>\n</body>\n</html>\n')
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
        "</body>", '<script src="/panel/desk.js" type="module"></script>\n</body>'),
        "script"),
    "a style block": (CLEAN.replace("</head>", "<style>a{}</style>\n</head>"), "style"),
    "an inline style attribute": (
        CLEAN.replace("<a ", '<a style="color:red" '), "style attribute"),
    "a single-quoted style attribute": (
        CLEAN.replace("<a ", "<a style='color:red' "), "style attribute"),
    "an upper-case style attribute": (
        CLEAN.replace("<a ", '<a STYLE="color:red" '), "style attribute"),
    "an inline handler": (CLEAN.replace("<a ", '<a onclick="run()" '), "handler"),
    "no language": (CLEAN.replace(' lang="en"', ""), "lang"),
    "an empty title": (CLEAN.replace("<title>Desk</title>", "<title> </title>"), "title"),
    "no title": (CLEAN.replace("<title>Desk</title>\n", ""), "title"),
    "no doctype": (CLEAN.replace("<!doctype html>\n", ""), "doctype"),
}


def test_the_desk_page_check_passes_a_sound_page_and_only_a_sound_page():
    assert desk_page_faults(CLEAN) == []


@pytest.mark.parametrize("html,needle", list(BROKEN.values()), ids=list(BROKEN))
def test_the_desk_page_check_refuses_each_defect_and_names_it(html, needle):
    faults = desk_page_faults(html)
    assert faults, "a defective page was accepted"
    assert any(needle in fault for fault in faults), faults


def test_the_desk_page_check_allows_exactly_the_scripts_it_is_told_to_expect():
    tag = '<script src="/panel/desk.js" type="module">'
    page = CLEAN.replace("</body>", f"{tag}</script>\n</body>")
    assert desk_page_faults(page, (tag,)) == []
    assert desk_page_faults(page, ()) != []
    assert desk_page_faults(CLEAN, (tag,)) != []


def test_the_desk_page_meets_its_own_contract():
    html = DESK_PAGE.read_text(encoding="utf-8")
    assert desk_page_faults(html) == []
    assert "/panel/desk.html" in server_assets.DESK_ASSETS


def test_every_reference_the_desk_page_makes_is_a_route_this_server_serves():
    """The page names exactly one neighbour, and that neighbour is a real route.

    The list is exact so a second reference has to be argued for here, and it
    is not empty so the served-route check below cannot pass by having nothing
    to judge. The slice that adds `desk.css` and `desk.js` extends it to
    `["/panel/desk.css", "/panel/desk.js", "/panel/index.html"]` (spec 5.6.8).
    """
    html = DESK_PAGE.read_text(encoding="utf-8")
    refs = re.findall(QUOTED_REFERENCE, html)
    assert refs == ["/panel/index.html"]
    assert set(refs) <= set(server.PANEL_ASSETS), sorted(set(refs) - set(server.PANEL_ASSETS))


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
