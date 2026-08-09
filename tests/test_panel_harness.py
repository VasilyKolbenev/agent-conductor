"""Harness identity in the panel: what the badge may say, and what it may never move.

Three kinds of guard live here, and they are not equally strong.

The first executes real code: `conductor.harnesses`, `conductor.merge` and the
real HTTP server. What it establishes — that the registry route answers with
`as_payload()` and nothing else, that `state.json` is byte-for-byte what the
merger produced, that an unregistered string resolves to itself with the
neutral accent — holds whatever the panel does with any of it.

The second computes colours from the panel's declarations through the cascade
model in tests/test_panel_cascade.py, exactly as tests/test_panel_contrast.py
does, and reports arithmetic. A ratio here is a ratio between the colours those
declarations ask for; nothing is rendered and nothing is sampled off a screen.

The third reads the panel's source text. It establishes what the panel
*declares* — which functions may reach the registry at all, which rules may
spend a harness accent — and not what a reader finally sees. The same behaviour
written another way goes through, which is the limit every panel module in this
repository states and §10 of the plan carries as post-alpha work. No name,
docstring or comment below may promise a rendered result.

One duplication is deliberate and is guarded rather than removed. The fallback
monogram is a rule stated twice — once in `harnesses._monogram`, once in the
panel, because a static file cannot import Python — and
:func:`test_the_panels_fallback_monogram_rule_and_the_registrys_agree_on_one_table`
holds both to one table of strings. What that test compares is Python's own
behaviour against a Python model built from the panel's *declared* pieces: the
separator class is parsed out of the panel, and the branch structure is pinned
separately by a source read. No JavaScript is executed anywhere in this suite,
so a rewrite of the panel's function that keeps those pieces and computes
something else would pass here.
"""
import json
import re
import urllib.request
from datetime import datetime, timezone

import pytest

from conductor import harnesses, merge, server, store
from tests.test_panel_cascade import (
    E, ENVIRONMENTS, INTERACTIONS, computed, environments, free_names,
    function_body, panel_html, paint_profile, rules, script, touched)
from tests.test_panel_colour import contrast
from tests.test_panel_contrast import (
    NONTEXT_MIN, TEXT_MIN, THEMES, _hex_to_rgb, _mix_srgb, surface, tokens)
from tests.test_panel_style import root_declarations
from tests.test_server import start
from tests.test_store import write_project, good_lane

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

# ── the panel's declared halves of the registry ────────────────────────────
BADGE = "hb"                     # the badge's own class, and the stem of its parts


def panel_neutral_accent() -> dict[str, str]:
    """Parse the neutral pair the panel falls back to."""
    found = re.search(r"const NEUTRAL_ACCENT = \{(.*?)\};", panel_html(), re.S)
    assert found, "the panel no longer carries a NEUTRAL_ACCENT pair"
    return dict(re.findall(r'(\w+):\s*"([^"]+)"', found.group(1)))


def panel_mono_split() -> str:
    """Parse the separator the panel's fallback monogram splits an id on."""
    found = re.search(r"const MONO_SPLIT = (/.*?/u);\n", panel_html())
    assert found, "the panel no longer carries a MONO_SPLIT pattern"
    return found.group(1)


def panel_payload_fields() -> set[str]:
    """Every field of a payload row the panel's reader reaches for."""
    return set(re.findall(r"row\.([a-z_]+)", function_body("loadRegistry")))


def test_the_panel_falls_back_to_the_neutral_pair_the_registry_declares():
    # The second copy of a value again, and again allowed only with the guard
    # that reddens when it drifts. Both directions: renaming the pair in Python
    # fails here, and so does editing either hex in the panel. NEUTRAL_DARK and
    # NEUTRAL_LIGHT are public for exactly this reason.
    assert panel_neutral_accent() == {"dark": harnesses.NEUTRAL_DARK,
                                      "light": harnesses.NEUTRAL_LIGHT}


def test_the_panel_reads_every_field_the_payload_carries_and_no_other():
    # The panel's other copy of the registry's shape. `as_payload` decides what
    # a badge is drawn from; the panel's reader has to want exactly that, so a
    # field added there and ignored here fails, and a field the panel invented
    # fails too. Two-directional, like the product-name table DEC-UI-2 keeps.
    assert panel_payload_fields() == set(harnesses.as_payload()[0])


# ── the route: presentation data, served beside the state and never in it ──
def test_the_registry_route_answers_with_the_payload_and_nothing_else(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    srv, base = start(root)
    try:
        with urllib.request.urlopen(base + "/harnesses.json", timeout=5) as r:
            body, headers = r.read(), dict(r.headers)
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert headers["Cache-Control"] == "no-store"
        assert json.loads(body) == harnesses.as_payload()
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_registry_route_is_the_same_bytes_for_every_project(tmp_path):
    # A presentation route and not part of Protocol v1: it carries the bundled
    # registry, so nothing a project writes can change a byte of it. Two
    # projects with different maps, lanes and harnesses, one answer.
    plain = write_project(tmp_path / "a", lanes={"claude": good_lane()})
    other = write_project(tmp_path / "b")
    bodies = []
    for root in (plain, other):
        srv, base = start(root)
        try:
            with urllib.request.urlopen(base + "/harnesses.json", timeout=5) as r:
                bodies.append(r.read())
        finally:
            srv.shutdown()
            srv.server_close()
    assert bodies[0] == bodies[1] == server.HARNESSES_JSON


def _served_state(root) -> bytes:
    srv, base = start(root)
    try:
        with urllib.request.urlopen(base + "/state.json", timeout=5) as r:
            return r.read()
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_state_document_is_byte_for_byte_what_the_merger_produced(tmp_path):
    # The acceptance line DO-4 was held to and DEC-UI-3 inherits: serving the
    # registry adds nothing to state.json. Held by rebuilding the document from
    # the same files with the same merger and comparing bytes — not fields — so
    # a key order, an encoding or a smuggled badge field all show up.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    raw = _served_state(root)
    served = json.loads(raw)
    loaded = store.load(root)
    # Merged again at the instant the served document records, because staleness
    # is computed against that instant: two different clocks would be two
    # different documents for a reason that has nothing to do with this slice.
    expected = merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                           loaded.events, loaded.skipped_events,
                           datetime.fromisoformat(served["generated_at"]))
    assert raw == json.dumps(expected, ensure_ascii=False).encode("utf-8")


def test_no_value_the_registry_supplies_appears_in_the_state_document(tmp_path):
    # The demo fixture declares `claude-code` and `codex`, both registered. The
    # state document may carry those strings — they are what the map wrote — and
    # may not carry one thing the registry knows about them: not a display name,
    # not a monogram, not an accent, not a documentation link.
    from conductor import demo
    root = demo.materialize(tmp_path / "demo")
    raw = _served_state(root).decode()
    for entry in harnesses.known():
        assert entry.display_name not in raw, entry.display_name
        assert entry.accent_dark not in raw and entry.accent_light not in raw
        if entry.docs:
            assert entry.docs not in raw, entry.docs
    for field in ("monogram", "display_name", "accent_dark", "accent_light"):
        assert field not in raw, field


# ── an unregistered harness: neutral, minimal, and never a borrowed brand ──
# Strings a project might plausibly write, every one of them absent from the
# registry, and the first four chosen to resemble a product that is in it.
LOOKALIKES = ["Claude Code", "claude-code-local", "cursor-agent", "codex-cli",
              "Some Local Agent", "my_own_agent", "Кодекс", "中文", "x", "!!"]


@pytest.mark.parametrize("name", LOOKALIKES)
def test_a_harness_the_registry_never_registered_stays_itself_and_stays_neutral(name):
    # The acceptance line, from the side that can be executed. `resolve` is the
    # rule the panel mirrors: the string is its own display name, the accent is
    # the fixed neutral pair, and there is no documentation link — so a string
    # that reads like Claude Code is never shown as Claude Code, and never
    # borrows Claude Code's colour. The monogram is derived from the string, so
    # it is never a blank either.
    assert harnesses.get(name) is None
    resolved = harnesses.resolve(name)
    assert resolved.display_name == name
    assert (resolved.accent_dark, resolved.accent_light) == \
        (harnesses.NEUTRAL_DARK, harnesses.NEUTRAL_LIGHT)
    assert resolved.docs == ""
    assert resolved.monogram, name
    assert name not in {entry.id for entry in harnesses.known()}


def test_a_lookalike_string_takes_no_registered_products_accent_or_link():
    # The same claim as a relation over the whole registry rather than one row
    # at a time: no unregistered string may resolve to any vendor's accent or to
    # any vendor's documentation page, whatever it is spelt like.
    vendor_accents = {(e.accent_dark, e.accent_light) for e in harnesses.vendors()}
    vendor_docs = {e.docs for e in harnesses.vendors()}
    for name in LOOKALIKES:
        resolved = harnesses.resolve(name)
        assert (resolved.accent_dark, resolved.accent_light) not in vendor_accents, name
        assert resolved.docs not in vendor_docs, name


def test_the_panel_resolves_an_unregistered_string_through_its_own_fallback():
    # The panel's half, source-read. `harnessOf` reaches the loaded registry by
    # id and, failing that, builds the fallback out of three things: the name
    # lookup, the monogram rule and the neutral pair. It reaches for nothing
    # else, so there is no room for a nearest match, a hashed hue or a second
    # table of near-names — without this test having to know what one would be
    # called.
    body = function_body("harnessOf")
    assert free_names(body, {"id"}) == {"REGISTRY", "String", "harnessName",
                                        "monogramOf", "NEUTRAL_ACCENT"}
    assert 'docs: ""' in body, body


def test_the_minimal_card_differs_from_a_registered_one_by_the_vendor_link_alone():
    # What "minimal" means here, held at both ends. In the data: every vendor
    # entry carries a documentation page and the two entries that name no vendor
    # — `custom` and any unregistered string — carry none. In the panel: the
    # link is the one part of a badge that is conditional, and its condition is
    # that the resolved page is an https URL. The monogram and the name are
    # emitted unconditionally, which is what makes a blank impossible.
    for entry in harnesses.vendors():
        assert entry.docs.startswith("https://"), entry.id
    assert harnesses.get(harnesses.CUSTOM).docs == ""
    assert harnesses.resolve("Some Local Agent").docs == ""
    body = function_body("harnessBadge")
    assert 'if (h.docs.startsWith("https://"))' in body, body
    assert body.count("if (") == 1, body        # the link is the only condition
    assert 'class: "hb__m" }, h.monogram' in body, body
    assert 'class: "hb__n" }, h.name' in body, body


# ── the fallback monogram: one rule, stated twice, held to one table ───────
# Python splits an id on `[\W_]+` — anything that is not a Unicode word
# character, plus the underscore, which `\w` would otherwise keep. The panel
# splits on the class parsed out of it below. The two are the same set written
# in the two dialects: JavaScript has no `\w` shorthand for Unicode, so the
# panel spells the complement of "letter or digit" directly, and needs no
# separate underscore case because `_` is neither.
PANEL_SPLIT = r"/[^\p{L}\p{N}]+/u"
PYTHON_SPLIT = r"[\W_]+"

# Strings the registry does not register, because for one that it does `resolve`
# answers with the registered monogram and the fallback rule is not what runs:
# `codex` is badged CX and its initials are CO, and comparing those two would be
# comparing the registry against itself.
MONOGRAM_TABLE = ["claude-code-local", "codex-cli", "my_own_agent",
                  "Some Local Agent", "Кодекс", "中文", "x", "c++", "a-", "ßa",
                  "!!", "", "42-alpha", "one two three", "MiXeD"]


def _panel_rule(harness_id: str) -> str:
    """Apply the panel's declared monogram rule, in Python.

    The separator comes from the panel's own source through
    :func:`panel_mono_split`; the branch structure is the rule stated in the
    panel's comment and pinned, separately, by
    :func:`test_the_panels_fallback_monogram_is_built_from_the_string_alone`.
    This is a model of the panel's source and not an execution of it — no
    JavaScript runs in this suite.
    """
    assert panel_mono_split() == PANEL_SPLIT, panel_mono_split()
    words = [word for word in re.split(PYTHON_SPLIT, harness_id) if word]
    if not words:
        return "?"
    initials = words[0][0] + words[1][0] if len(words) > 1 else words[0][:2]
    return initials.upper()[:2]


@pytest.mark.parametrize("harness_id", MONOGRAM_TABLE)
def test_the_panels_fallback_monogram_rule_and_the_registrys_agree_on_one_table(
        harness_id):
    # The guard the duplication is allowed to exist with. Every row covers a
    # branch: two words, one word, an id with no letter or digit at all, a
    # single character, a Unicode word, and `ß`, which upper-cases into two
    # characters and would badge three wide if the cut came first.
    assert harnesses.get(harness_id) is None, harness_id
    assert _panel_rule(harness_id) == harnesses.resolve(harness_id).monogram


def test_the_panels_fallback_monogram_is_built_from_the_string_alone():
    # The half the table cannot see: what the panel's function is allowed to
    # depend on. It reaches for the split pattern and for `String`, so there is
    # nowhere for a registry lookup, a stored table or a hue to enter — and a
    # colour derived from a name is the thing this fallback exists instead of.
    body = function_body("monogramOf")
    assert free_names(body, {"id", "words", "w", "initials"}) == {"MONO_SPLIT", "String"}
    assert 'return "?"' in body, body                     # no letter or digit at all
    # Upper-case, and only then cut: ß upper-cases into SS, so a cut taken first
    # would badge three characters wide. And the cut counts code points, which is
    # what keeps an astral character from being halved.
    assert 'return [...initials.toUpperCase()].slice(0, 2).join("");' in body, body
    for hue in ("hsl", "hsv", "#", "hash", "charCodeAt"):
        assert hue not in body, hue


# ── several harnesses at once, each drawn as its own ──────────────────────
def test_several_different_harnesses_on_several_stages_stay_several(tmp_path):
    # The merger's half: three roles on three stages, two registered products
    # and one string the registry has never seen, all reaching the state
    # document as the map wrote them.
    roles = [{"id": "impl", "harness": "claude-code", "stage": "design", "reviews": []},
             {"id": "rev", "harness": "codex", "stage": "deliver", "reviews": ["impl"]},
             {"id": "ops", "harness": "Some Local Agent", "stage": "detect",
              "reviews": []}]
    map_data = {"schema_version": 1, "project": "p",
                "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
                "cycle": {"phases": ["detect", "design", "deliver"], "roles": roles}}
    state = merge.merge(map_data, None, [], [], 0, NOW)
    assert [(r["harness"], r["stage"]) for r in state["cycle"]["roles"]] == \
        [("claude-code", "design"), ("codex", "deliver"),
         ("Some Local Agent", "detect")]
    # And the registry keeps them three: three distinct badges, because the
    # display name, the monogram and the accent are resolved per string.
    badges = {(h.display_name, h.monogram, h.accent_dark, h.accent_light)
              for h in (harnesses.resolve(r["harness"]) for r in roles)}
    assert len(badges) == 3, badges


def test_a_badge_is_built_from_one_harness_string_and_from_nothing_else():
    # Why two stages cannot end up sharing one product's badge: the builder is
    # handed a harness string and reaches for the resolver, the element helper
    # and nothing more. It cannot see a neighbouring role, a lane, an order or a
    # status, because none of them is in scope.
    assert free_names(function_body("harnessBadge"), {"id", "h", "badge"}) == \
        {"harnessOf", "el"}


def test_a_lanes_product_is_the_one_its_own_role_declares():
    # The join the agents block draws, and its whole extent: a lane names a
    # role, the cycle names that role's harness. Both hops are state.json's, so
    # nothing is invented — and a lane whose role the cycle never declared is
    # absent from the map rather than given a neighbour's product.
    body = function_body("harnessByAuthor")
    assert free_names(body, {"s", "byRole", "out", "r", "l"}) == {"Map", "String"}
    assert "r.harness" in body and "l.role" in body and "l.author" in body


# ── branding decides nothing: order, status, queue position ───────────────
def _definitions() -> dict[str, str]:
    """Every top-level declaration of the script, whole, keyed by its name.

    The script is cut at each column-zero ``function``/``const``/``let``, so
    every byte belongs to exactly one chunk and nothing a declaration contains
    can fall outside the one it belongs to. A body read to its closing brace
    would be tidier and would also miss whatever sits between two declarations.
    """
    src = script()
    starts = [(m.start(), m.group(1)) for m in
              re.finditer(r"^(?:async\s+function|function|const|let)\s+([A-Za-z_$][\w$]*)",
                          src, re.M)]
    assert starts, "the script no longer declares anything at the top level"
    bounds = [start for start, _ in starts] + [len(src)]
    return {name: src[bounds[i]:bounds[i + 1]] for i, (_, name) in enumerate(starts)}


# Every name that is the registry, resolves through it, or holds a value taken
# out of it. A definition mentioning one of these is a definition that knows
# what product something is running.
REGISTRY_NAMES = {"REGISTRY", "HARNESS_NAMES", "NEUTRAL_ACCENT", "MONO_SPLIT",
                  "loadRegistry", "monogramOf", "harnessName", "harnessOf",
                  "harnessBadge", "harnessByAuthor"}

# Where harness identity is allowed to be known, and what each place does with
# it. Everything else in the script is on the other side of the line: it cannot
# name a product, so it cannot order, rank or classify by one.
HARNESS_READERS = {
    "HARNESS_NAMES": "the product-name table DEC-UI-2 keeps against the registry",
    "harnessName": "the lookup over that table, falling back to the string",
    "REGISTRY": "the badge half of the registry, as loaded from /harnesses.json",
    "NEUTRAL_ACCENT": "the neutral pair an unregistered harness gets",
    "loadRegistry": "the boundary that validates a payload row before it is kept",
    "MONO_SPLIT": "the separator the fallback monogram splits an id on",
    "monogramOf": "the fallback monogram, from the string alone",
    "harnessOf": "resolution: the registry entry, or the neutral fallback",
    "harnessBadge": "the badge itself — monogram, name, and the vendor link",
    "harnessByAuthor": "the lane-to-role-to-harness join, read off state.json",
    "orbitStage": "draws a badge per role standing on the stage",
    "renderUnstaged": "draws a badge per role the Orbit could not place",
    "renderAgents": "draws a badge per lane, beside the lane's own status chip",
    "renderDetail": "draws a badge per lane that contested the selected node",
    "loadHarnesses": "the one request for the registry, made once",
}


def test_the_only_places_that_know_what_product_is_running_are_named_here():
    # Held the way the accent's six roles are held: every place is named with
    # what it does there, so a new one cannot appear without someone deciding
    # what it is for. The load-bearing half is the other direction — nothing
    # that decides an order, a status or a queue position is in this set, and a
    # branch added to one of them that consulted a harness would fail here.
    reading = {name: source for name, source in _definitions().items()
               if free_names(source, set()) & REGISTRY_NAMES}
    assert set(reading) == set(HARNESS_READERS), \
        set(reading) ^ set(HARNESS_READERS)


# What decides an order, a status or a queue position. Every one of them is
# outside the set above; naming them says which promises DEC-UI-3 is making, so
# a regression reads as a broken promise rather than as a set that grew.
DECIDERS = ("statusOf", "attentionOf", "laneChip", "renderQueue", "attentionAlerts",
            "renderFindings", "layoutMap", "drawNodes", "orbitProject", "renderMap")


@pytest.mark.parametrize("name", DECIDERS)
def test_nothing_that_decides_an_order_a_status_or_a_queue_position_knows_a_product(
        name):
    assert name not in HARNESS_READERS
    assert not free_names(_definitions()[name], set()) & REGISTRY_NAMES


def test_the_agents_block_keeps_the_order_it_was_handed_and_every_lanes_own_chip():
    # The order is the state document's: the block walks `lanes` and does not
    # reorder, regroup or drop any of them, and the badge is appended to a row
    # that is already built. The status is the row's own chip, emitted from the
    # lane before any harness is looked at, so the badge is never what says how
    # a lane is doing.
    body = function_body("renderAgents")
    assert "for (const l of lanes)" in body, body
    for undo in (".sort(", ".reverse(", ".filter(", ".slice("):
        assert undo not in body, undo
    assert body.index("laneChip(l)") < body.index("harnessBadge("), body
    assert free_names(function_body("laneChip"), {"l"}) == {"chip"}


def test_a_badge_carries_no_status_word_glyph_or_colour_of_its_own():
    # The badge may not become a second, quieter status carrier. Two halves: the
    # builder spells none of the status vocabulary, and no rule that styles a
    # badge paints with a semantic token or with December Red — so nothing about
    # it can be read as pass, fail, blocked, running or waiting.
    spoken = set(re.findall(r'"([^"]*)"', function_body("harnessBadge")))
    for word in ("pass", "fail", "blocked", "running", "idle", "contested",
                 "stale", "broken", "active"):
        assert word not in spoken, word
    for rule in rules():
        if BADGE not in rule.selector:
            continue
        for prop, value in rule.decls.items():
            for token in ("--accent", "--pass", "--wait", "--fail"):
                assert token not in value, (rule.selector, prop, value)


# ── the channel rule: where a harness accent may never go ─────────────────
# The six places §6 of conductor/harnesses.py forbids, built as the chains the
# panel draws them in. What is asked of each is a relation and not a name: no
# declaration that wins for this element may reference a harness accent.
HTML = E("html", **{"data-attention": "high"})
BODY = E("body")
CARD = E("div", "card")
STAGE = [E("div", "orbit"), E("div", "orb", "orb--current")]
STATUSES = ("pass", "fail", "blocked", "running", "idle", "contested")


def _forbidden_chains() -> dict[str, list]:
    chains = {}
    for cls in STATUSES:
        chains[f"the {cls} node's outline"] = [
            HTML, BODY, CARD, E("svg"), E("g", "node", "node--" + cls), E("rect", "box")]
    for cls in ("edge", "edge--dead", "edge--idle"):
        classes = ["edge"] if cls == "edge" else ["edge", cls]
        chains[f"the map's .{cls}"] = [HTML, BODY, CARD, E("svg"), E("path", *classes)]
    chains["a step of the trajectory"] = [HTML, BODY, CARD, *STAGE[:1], E("svg"),
                                          E("path", "trk")]
    chains["the return to the first stage"] = [HTML, BODY, CARD, *STAGE[:1], E("svg"),
                                               E("path", "trk", "trk--next")]
    chains["the trajectory's arrow head"] = [HTML, BODY, CARD, *STAGE[:1], E("svg"),
                                             E("path", "arw", "arw--orb")]
    chains["the vertical link"] = [HTML, BODY, CARD, *STAGE[:1], E("div", "lnk"), E("i")]
    chains["the primary action"] = [HTML, BODY, CARD, E("button", "copy")]
    for cls in ("pass", "fail", "blocked", "running", "idle", "contested"):
        chains[f"the {cls} pill's glyph"] = [HTML, BODY, CARD, E("div", "det"),
                                             E("span", "pill", "p--" + cls),
                                             E("i", "gl")]
    for cls in ("ok", "bad", "wait", "run", "idle"):
        chains[f"the {cls} chip's glyph"] = [HTML, BODY, CARD,
                                             E("span", "vd", "vd--" + cls), E("i", "gl")]
    return chains


HARNESS_ACCENT_VARS = ("--hb", "--hb-dark", "--hb-light")


def _mentions_harness_accent(values) -> list[str]:
    return [value for value in values
            if any(var in value for var in HARNESS_ACCENT_VARS)]


@pytest.mark.parametrize("where", sorted(_forbidden_chains()))
@pytest.mark.parametrize("interaction", [None, *sorted(INTERACTIONS)])
def test_no_carrier_of_a_status_or_an_action_resolves_a_harness_accent(where,
                                                                       interaction):
    # The channel rule, held where it is actually spent rather than as a list of
    # rules that are allowed to spell it. A harness accent reaching any of these
    # would make a product's colour say something about a state, an edge, a
    # trajectory or the one button the panel calls primary — and it is checked
    # under the pointer as well, because a rule scoped to :hover is still a rule.
    chain = _forbidden_chains()[where]
    for label, env in ENVIRONMENTS:
        win = computed(touched(chain, interaction), env=env)
        assert not _mentions_harness_accent(win.values()), (label, where, win)


def test_the_focus_ring_is_the_palettes_and_never_a_products():
    # The fifth forbidden place. Focus is drawn by one global rule, and what it
    # spends is December Red — the accent's role 5. A harness accent reaching it
    # would mean the ring around a focused control changed colour with whatever
    # product happened to be beside it.
    for label, env in ENVIRONMENTS:
        for chain in ([E("button", "copy")], [E("a", "hb__d")],
                      [E("g", "node", "node--running")]):
            win = computed(touched(chain, "focus"), env=env)
            assert not _mentions_harness_accent(win.values()), (label, win)
        assert "var(--accent)" in computed(touched([E("button", "copy")], "focus"),
                                           env=env)["outline"], label


def test_a_harness_accent_is_declared_on_the_badge_and_reaches_nothing_else():
    # The positive half, which is what keeps the six above from passing by
    # resolving nothing at all: the badge's own swatch does resolve a harness
    # accent, in every environment. And the two custom properties the accents
    # arrive in are set on the badge element by the script — never in `:root`,
    # where they would be inheritable by every element on the page.
    badge = [HTML, BODY, CARD, E("span", "hb"), E("span", "hb__m")]
    for label, env in ENVIRONMENTS:
        win = computed(badge, env=env)
        assert _mentions_harness_accent(win.values()), (label, win)
    dark, light = root_declarations()
    for name in ("--hb", "--hb-dark", "--hb-light"):
        assert name not in dark and name not in light, name
    written = {literal for literal in re.findall(r'"([^"]*)"', script())
               if "--hb" in literal}
    assert written == {"--hb-dark:", ";--hb-light:"}, written
    assert function_body("harnessBadge").count("--hb-dark:") == 1


@pytest.mark.parametrize("interaction", sorted(INTERACTIONS))
def test_no_interaction_repaints_the_badge_or_anything_it_is_made_of(interaction):
    # Owner invariant 1 reaches the badge too: the parts of it are elements the
    # panel gives paint to, so a pointer may add to them and may not repaint
    # them. The link is the one part that answers to hover at all, and what it
    # moves is the thickness of its underline, which is not a paint.
    for parts in (["hb"], ["hb", "hb__m"], ["hb", "hb__n"], ["hb", "hb__d"]):
        chain = [HTML, BODY, CARD] + [E("span", cls) for cls in parts]
        for label, env in ENVIRONMENTS:
            assert paint_profile(chain, interaction, env) == \
                paint_profile(chain, None, env), (parts, label, interaction)


def test_a_badge_is_never_declared_hidden_until_a_pointer_arrives():
    # §4's no-hidden-mandatory-hover, for the surface this slice adds. Identity
    # that only appears under a pointer is identity a touch device never sees.
    for parts in (["hb"], ["hb", "hb__m"], ["hb", "hb__n"], ["hb", "hb__d"]):
        chain = [HTML, BODY, CARD] + [E("span", cls) for cls in parts]
        for interaction in [None, *sorted(INTERACTIONS)]:
            for label, env in ENVIRONMENTS:
                shown = computed(touched(chain, interaction), env=env).get("display", "")
                assert shown != "none", (parts, label, interaction)


# ── the accents, measured against the surfaces they are drawn on ──────────
# Every surface a badge sits on, as the chain the panel builds it in. The badge
# is the same element everywhere; what changes beneath it is the card.
SURFACES = {
    "an agents row on a card": [HTML, BODY, CARD],
    "an agents row on a lit card": [HTML, BODY, E("div", "card", "lit")],
    "an Orbit stage": [HTML, BODY, CARD, E("div", "orbit"),
                       E("div", "orb", "orb--neutral")],
    "the detail card": [HTML, BODY, CARD, E("div", "det")],
}


def badge_tint_pct() -> float:
    """Read the strength of the swatch's tint out of the stylesheet."""
    value = computed([E("span", "hb"), E("span", "hb__m")])["background"]
    found = re.fullmatch(r"color-mix\(in srgb,var\(--hb\) ([\d.]+)%,transparent\)",
                         value)
    assert found, value
    return float(found.group(1))


def badge_accents() -> list[tuple[str, str, str]]:
    """Every accent the panel can put on a swatch: the registry's, and neutral."""
    rows = [(row["id"], row["accent_dark"], row["accent_light"])
            for row in harnesses.as_payload()]
    return rows + [("<unregistered>", harnesses.NEUTRAL_DARK, harnesses.NEUTRAL_LIGHT)]


def measure_badge(theme: str, accent: str, where: str,
                  env: frozenset = frozenset()) -> tuple[float, float]:
    """Return (swatch contour vs the card, monogram vs the swatch's own tint)."""
    under = surface(theme, SURFACES[where], env)
    tint = _mix_srgb(_hex_to_rgb(accent), badge_tint_pct(), under)
    ink = tokens(theme)["--ink"]
    return contrast(_hex_to_rgb(accent), under), contrast(ink, tint)


@pytest.mark.parametrize("where", sorted(SURFACES))
@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("row", badge_accents(), ids=lambda r: r[0])
def test_every_accent_the_registry_ships_is_legible_on_every_surface_it_lands_on(
        row, theme, where):
    # The measurement the slice asks for, and it is a measurement: the accents
    # come from the registry itself, the tint strength is read out of the
    # stylesheet, and the surface is composited through the cascade. Two numbers
    # per row, because the swatch says two things — a contour, which 1.4.11
    # governs at 3:1, and a monogram, which is text and answers to 4.5:1.
    harness_id, dark, light = row
    accent = dark if theme == "dark" else light
    for label, env in environments(theme):
        contour, monogram = measure_badge(theme, accent, where, env)
        assert contour >= NONTEXT_MIN, \
            f"{label}: {harness_id} contour on {where} is {contour:.2f}:1"
        assert monogram >= TEXT_MIN, \
            f"{label}: {harness_id} monogram on {where} is {monogram:.2f}:1"


def test_the_product_name_beside_a_swatch_runs_on_a_measured_palette_colour():
    # The third mark of the badge is the name, and it is deliberately not the
    # vendor's colour: it runs on --muted, whose pairs against every card
    # surface are already measured in tests/test_panel_contrast.py. So no part
    # of a product's identity is spelt in a colour nobody measured.
    for label, env in ENVIRONMENTS:
        assert computed([E("span", "hb"), E("span", "hb__n")],
                        env=env)["color"] == "var(--muted)", label


# ── loading the registry: once, and never at the cost of the panel ────────
def test_the_panel_asks_for_the_registry_once_and_asks_nothing_else_of_the_network():
    # Two claims about the one request. It is made once — there is no retry and
    # no poll, because the bundled registry cannot change under a running panel
    # and a copy of this file opened without a server would retry forever. And
    # the panel reaches for three same-origin paths in total: no machine is
    # probed, no vendor asset is fetched, and nothing is loaded from anywhere
    # but the server that served the panel.
    src = script()
    assert set(re.findall(r'fetch\("([^"]*)"', src)) == {"/state.json", "/harnesses.json"}
    assert set(re.findall(r'new EventSource\("([^"]*)"', src)) == {"/events"}
    assert src.count('fetch("/harnesses.json"') == 1
    assert src.count("loadHarnesses(") == 2          # the declaration and the one call


def test_a_registry_that_never_arrives_leaves_every_other_surface_alone():
    # The static-checkpoint case, which is an ordinary mode and not an edge: a
    # copy of this file is opened with no server behind it. The failure path
    # returns, so nothing after it runs; the panel's own state document is
    # fetched separately and drawn regardless; and resolution then takes the
    # neutral branch for every harness, because the registry is simply empty.
    body = function_body("loadHarnesses")
    catch = body[body.index("catch"):]
    assert re.match(r"catch \(err\) \{\s*return;", catch.strip()), catch
    assert "$(" not in body, body                    # touches no surface of its own
    # `try`, `catch`, `throw` and `await` are keywords this repository's
    # identifier scanner does not know; they are bound here so that what is left
    # is the four names the loader actually reaches for.
    assert free_names(body, {"r", "err", "try", "catch", "throw", "await"}) == \
        {"fetch", "loadRegistry", "Error", "LAST", "render"}
    # And nothing in the render pipeline asks whether the registry arrived.
    for name in ("render", "renderOrbit", "renderAgents", "renderMap", "renderDetail"):
        assert "REGISTRY" not in function_body(name), name


def test_a_payload_row_the_panel_cannot_trust_is_dropped_rather_than_repaired():
    # The boundary. An accent reaches the DOM as the value of a custom property,
    # so a row is kept only when both accents are six-digit hex and every field
    # drawn from it is a non-empty string. A dropped row is not a failure state:
    # its harness resolves to the neutral badge like any unregistered one.
    body = function_body("loadRegistry")
    assert body.count("continue;") == 4, body
    assert "HEX_RE.test(row.accent_dark)" in body and "HEX_RE.test(row.accent_light)" in body
    assert re.search(r"const HEX_RE = /\^#\[0-9a-f\]\{6\}\$/i;", panel_html())
    assert "Array.isArray(rows)" in body, body
    assert free_names(body, {"rows", "row"}) == {"REGISTRY", "Array", "HEX_RE"}
