"""What the Orbit is drawn from, and what the Orbit may never claim.

Two kinds of guard live here and they are not equally strong, so the module
says which is which before either of them runs.

The first kind executes the real merger. It builds map and lane inputs, calls
`conductor.merge.merge`, and asserts relations over the `state.json` it gets
back — that design-time `stage` metadata changes nothing else, that the current
phase is computed from lane reports alone, that a project declaring no cycle
still reports its lanes and its roles. Those are behaviour claims about running
code and they hold whatever the panel does with the result.

The second kind reads the panel's *source text*: the `<style>` block parsed
into rules by tests/test_panel_cascade.py, the `<script>` block read as
characters. No browser runs, no DOM is built, nothing is rasterised. A guard of
that kind establishes what the panel *declares* and not what a reader finally
sees — the same limit tests/test_panel_style.py states at length, inherited
here for the same reason and with the same consequence: every name and
docstring below stays inside the source-level claim, and none of them may
promise a rendered result. Assertions on a rendered result are §10 post-alpha
work.
"""
import re
from datetime import datetime, timedelta, timezone

import pytest

from conductor import harnesses, merge, prompts, templates
from tests.test_panel_cascade import (
    E, computed, environments, free_names, function_body, panel_html,
    reachable_from, script)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
RECENT = "2026-07-30T11:00:00+00:00"
LONG_AGO = "2026-07-01T11:00:00+00:00"


def cycle_map(phases, roles):
    """A minimal valid map carrying one cycle, as `merge.merge` takes it."""
    return {"schema_version": 1, "project": "p",
            "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
            "cycle": {"phases": list(phases), "roles": list(roles)}}


def role(rid, harness="cc", stage=None, reviews=()):
    out = {"id": rid, "harness": harness, "reviews": list(reviews)}
    if stage is not None:
        out["stage"] = stage
    return out


def lane(author, role_id=None, phase=None, updated=RECENT, waits=(), staleness=None):
    data = {"schema_version": 1, "author": author, "updated": updated}
    if role_id is not None:
        data["role"] = role_id
    if phase is not None:
        data["now"] = {"task": "t", "phase": phase}
    if waits:
        data["waits_on_human"] = list(waits)
    if staleness is not None:
        data["staleness_after_minutes"] = staleness
    return {"author": author, "data": data, "error": None}


def wait(wid="w-1", kind="decision", title="Ship it?"):
    return {"id": wid, "kind": kind, "title": title, "why": "because", "blocks": []}


# ── what the Orbit is drawn from: the merger's own output ──────────────────
def test_declaring_a_stage_on_a_role_changes_nothing_in_the_state_but_that_role_row():
    # §2.3: `stage` is design-time metadata. It may not reach readiness, review
    # state, the queue or any merge rule — so the whole state document is
    # compared, not a chosen field, and the only difference allowed is the key
    # itself. Executed against the real merger, so a merge rule that started
    # consulting `stage` fails here whatever it consulted it for.
    roles = [role("impl"), role("rev", reviews=["impl"])]
    staged = [role("impl", stage="design"), role("rev", stage="deliver", reviews=["impl"])]
    lanes = [lane("claude", "impl", phase="design"), lane("codex", "rev")]
    plain = merge.merge(cycle_map(["design", "deliver"], roles), None, lanes, [], 0, NOW)
    with_stage = merge.merge(cycle_map(["design", "deliver"], staged), None,
                             lanes, [], 0, NOW)

    assert [{k: v for k, v in r.items() if k != "stage"}
            for r in with_stage["cycle"]["roles"]] == plain["cycle"]["roles"]
    assert [r.get("stage") for r in with_stage["cycle"]["roles"]] == ["design", "deliver"]
    stripped = dict(with_stage, cycle=dict(with_stage["cycle"],
                                           roles=plain["cycle"]["roles"]))
    assert stripped == plain


def test_the_current_phase_is_the_one_a_lane_reported_not_the_one_a_role_was_assigned():
    # §2.3 again, from the runtime side. The role is assigned to `design` and
    # its lane says it is in `detect`; the merger reports `detect`, and nothing
    # anywhere reports `design` as current.
    state = merge.merge(cycle_map(["detect", "design"], [role("impl", stage="design")]),
                        None, [lane("claude", "impl", phase="detect")], [], 0, NOW)
    assert state["cycle"]["current_phase"] == "detect"
    assert state["cycle"]["roles"][0]["stage"] == "design"


def test_an_assigned_stage_alone_never_makes_a_phase_current():
    # The honest empty case §2.2 requires: no lane reports a phase, so the
    # state document carries no current phase at all — not the assigned one,
    # not the first one, not any one.
    state = merge.merge(cycle_map(["detect", "design"], [role("impl", stage="design")]),
                        None, [lane("claude", "impl")], [], 0, NOW)
    assert "current_phase" not in state["cycle"]


def test_a_role_that_declares_no_stage_keeps_its_legacy_row_and_gains_no_null():
    # §2.4: a role without a stage is not a role with a missing stage. The key
    # is absent, so a panel grouping by `stage` cannot mistake a null for a
    # declared phase named nothing.
    state = merge.merge(cycle_map(["detect"], [role("impl")]), None, [], [], 0, NOW)
    assert state["cycle"]["roles"] == [{"id": "impl", "harness": "cc", "reviews": []}]


def test_a_project_that_declares_no_cycle_still_reports_its_lanes_and_its_nodes():
    # §2.4: the legacy project. No cycle table at all, and everything else the
    # panel draws is still in the state document.
    legacy = {"schema_version": 1, "project": "p",
              "nodes": [{"id": "n", "label": "n", "kind": "artifact"}]}
    state = merge.merge(legacy, None, [lane("claude")], [], 0, NOW)
    assert state["cycle"] == {"phases": [], "roles": []}
    assert [ln["author"] for ln in state["lanes"]] == ["claude"]
    assert [n["id"] for n in state["map"]["nodes"]] == ["n"]


def test_a_cycle_that_declares_roles_and_no_phases_keeps_every_role():
    # The N = 0 input the owner's table names: no phases, participants intact.
    state = merge.merge(cycle_map([], [role("impl", stage="design"), role("rev")]),
                        None, [lane("claude", "impl")], [], 0, NOW)
    assert state["cycle"]["phases"] == []
    assert [r["id"] for r in state["cycle"]["roles"]] == ["impl", "rev"]
    assert [ln["author"] for ln in state["lanes"]] == ["claude"]


def test_an_empty_project_merges_without_raising_and_still_carries_the_cycle_key():
    # §5: absent phases, roles and lanes must not raise. The merger is the
    # first place that could, so it is the first place asked.
    state = merge.merge(cycle_map([], []), None, [], [], 0, NOW)
    assert state["cycle"] == {"phases": [], "roles": []}
    assert state["lanes"] == [] and state["human_queue"] == []


def test_a_lane_reporting_a_phase_the_map_never_declared_is_warned_and_left_undeclared():
    # The panel places a phase marker by matching `now.phase` against the
    # declared list, so it matters that the merger never smuggles an
    # undeclared phase into `current_phase`.
    state = merge.merge(cycle_map(["detect"], [role("impl")]), None,
                        [lane("claude", "impl", phase="somewhere-else")], [], 0, NOW)
    assert "current_phase" not in state["cycle"]
    assert any("somewhere-else" in w for w in state["warnings"])


def test_a_human_wait_carries_the_lane_authors_that_raised_it():
    # How a wait reaches a phase at all: the queue item names its source
    # lanes, a lane names its role, and a role names its stage. Each hop is
    # data the merger already emits, and this pins the first one.
    state = merge.merge(cycle_map(["detect"], [role("impl", stage="detect")]), None,
                        [lane("claude", "impl", waits=[wait()])], [], 0, NOW)
    assert state["human_queue"][0]["sources"] == ["claude"]
    assert state["lanes"][0]["role"] == "impl"


def test_a_stale_lane_keeps_the_role_that_lets_a_phase_show_it_has_gone_quiet():
    # A broken lane loses its role — `_lane_view` cannot read one out of a file
    # it could not parse — so a broken lane can never be attributed to a phase.
    # A stale lane keeps it, which is why "gone quiet" is the lane-health fact
    # the Orbit is able to place and "unreadable" is not.
    stale = lane("claude", "impl", updated=LONG_AGO, staleness=60)
    broken = {"author": "codex", "data": None, "error": "unreadable"}
    state = merge.merge(cycle_map(["detect"], [role("impl", stage="detect")]), None,
                        [stale, broken], [], 0, NOW)
    by_author = {ln["author"]: ln for ln in state["lanes"]}
    assert by_author["claude"]["stale"] is True and by_author["claude"]["role"] == "impl"
    assert by_author["codex"]["broken"] is True and by_author["codex"]["role"] is None


def test_a_phase_with_no_participant_is_an_ordinary_state_of_the_merged_document():
    # §2.4: `default-orbit` deliberately staffs nobody on `goal`. The state
    # document says so by simply carrying no role with that stage, which is a
    # shape the panel has to draw rather than an error it has to report.
    state = merge.merge(cycle_map(["goal", "detect"], [role("impl", stage="detect")]),
                        None, [], [], 0, NOW)
    assert state["cycle"]["phases"] == ["goal", "detect"]
    assert [r.get("stage") for r in state["cycle"]["roles"]] == ["detect"]
    assert state["warnings"] == []


@pytest.mark.parametrize("count", [0, 1, 2, 3, 5, 8, 10])
def test_any_number_of_declared_phases_survives_the_merge_unchanged_and_in_order(count):
    # Cyclicity is a property of the shape, not of the number five (§2bis). The
    # merger is the source the shape is built from, so it is pinned first: the
    # list comes back the length it went in and in the order it went in.
    phases = [f"phase-{i}" for i in range(count)]
    state = merge.merge(cycle_map(phases, []), None, [], [], 0, NOW)
    assert state["cycle"]["phases"] == phases


def test_a_unicode_or_mixed_case_phase_name_reaches_the_state_document_byte_for_byte():
    # §2.1a: the value in the data is never mutated. Pinned at the merger,
    # which is where a normalisation or a case fold would have to happen for
    # the panel to receive anything but the author's own bytes.
    names = ["Кодекс", "中文", "Design-Review", "délivrer"]
    state = merge.merge(cycle_map(names, [role("impl", stage="中文")]), None, [], [], 0, NOW)
    assert state["cycle"]["phases"] == names
    assert state["cycle"]["roles"][0]["stage"] == "中文"


def test_two_roles_on_two_phases_each_keep_the_harness_string_the_map_declared():
    # §2.6: the protocol carries the harness *string* and nothing else. Two
    # different harnesses on two different stages stay two different strings,
    # and neither is normalised toward a registry id.
    roles = [role("impl", harness="claude-code", stage="design"),
             role("rev", harness="Some Local Agent", stage="deliver")]
    state = merge.merge(cycle_map(["design", "deliver"], roles), None, [], [], 0, NOW)
    assert [(r["harness"], r["stage"]) for r in state["cycle"]["roles"]] == \
        [("claude-code", "design"), ("Some Local Agent", "deliver")]


# ── stage names: one presentational liberty, and nothing else ──────────────
def panel_shipped_stages() -> set[str]:
    """Parse the set of stage ids the panel is allowed to capitalise."""
    found = re.search(r"const SHIPPED_STAGES = new Set\(\[(.*?)\]\)", panel_html(), re.S)
    assert found, "the panel no longer carries a SHIPPED_STAGES set"
    return set(re.findall(r'"([^"]+)"', found.group(1)))


def test_the_stages_the_panel_will_capitalise_are_the_ones_python_ships():
    # §2.1a, consequence 3. The set lives in Python twice — the phases the
    # `default-orbit` template writes, and the stages `prompts` knows a contract
    # for — and a third copy in a static HTML file is a second source of one
    # truth. It is allowed only with this: both Python sources are read here and
    # the three sets must be one set. Renaming a shipped stage in Python and not
    # in the panel fails, and so does the panel quietly adopting a sixth.
    template = templates.get("default-orbit")
    declared = re.search(r"phases = \[(.*?)\]", template).group(1)
    from_template = set(re.findall(r'"([^"]+)"', declared))
    from_prompts = set(prompts._STAGE_CONTRACTS)
    assert from_template == from_prompts, from_template ^ from_prompts
    assert panel_shipped_stages() == from_template, \
        panel_shipped_stages() ^ from_template


def test_a_shipped_stage_id_is_capitalised_by_a_class_and_not_by_a_rewrite():
    # The liberty, and its exact extent. The stage builder decides one thing
    # from the shipped set — whether the label element also carries `cap` — and
    # the class is the whole of the difference. The name itself is appended as
    # `String(name)` either way, so what reaches the text node is the author's
    # bytes and the capital is a property of the rendering.
    body = function_body("orbitStage")
    assert re.search(r'SHIPPED_STAGES\.has\(name\) \? " cap" : ""', body), body
    assert re.search(r'class:\s*"orb__name"\s*\+\s*\(SHIPPED_STAGES', body), body
    assert "String(name)" in body, body


def test_the_shipped_set_is_asked_for_membership_and_never_for_a_replacement():
    # §2.1a: a user's `research` is never shown as `Detect`. The strongest form
    # of that available to a source read is what the set can *do*: it is a Set
    # and it is touched exactly once, by `.has`. A lookup table mapping a name
    # to a canonical term cannot be spelt that way, and neither can a
    # normalisation pass — both would have to reach for the set a second time or
    # index it, and either shows up here.
    src = script()
    assert src.count("SHIPPED_STAGES") == 2          # the declaration and the test
    assert len(re.findall(r"SHIPPED_STAGES\.has\(", src)) == 1
    assert not re.search(r"SHIPPED_STAGES\s*\[", src)


def test_no_rule_capitalises_a_stage_name_that_is_not_a_shipped_id():
    # The blanket `text-transform` this arrangement exists instead of. The only
    # rule in the stylesheet that transforms text on a stage label is the one
    # keyed on `.cap`, and `.orb__name` on its own resolves no transform at all
    # — which is what keeps a custom name, a Unicode name and an already mixed
    # case name looking exactly as their author wrote them.
    label = [E("div", "orbit"), E("div", "orb", "orb--neutral"), E("span", "orb__name")]
    capped = label[:-1] + [E("span", "orb__name", "cap")]
    for theme in ("dark", "light"):
        for _, env in environments(theme):
            assert "text-transform" not in computed(label, env=env)
            assert computed(capped, env=env)["text-transform"] == "capitalize"


@pytest.mark.parametrize("name", ["research", "delivery-check", "Design-Review",
                                  "Кодекс-ревью", "実装", "中文", "délivrer",
                                  "reproduce the report"])
def test_a_name_the_panel_did_not_ship_is_outside_the_one_set_that_changes_anything(name):
    # The fourth naming test, from the data side. Every one of these is a name a
    # project might write; none is in the set; so none can be given the capital,
    # and — because membership is the only thing the set decides — none can be
    # given a different word either. The merger tests above hold the other half:
    # the bytes reach the state document unchanged.
    assert name not in panel_shipped_stages()


# ── what the drawing code is allowed to depend on ──────────────────────────
# Source reads, and the module docstring's second kind. What each of these
# establishes is a *dependence*: the set of names a function reaches for
# outside itself. That is weaker than running the function and stronger than
# looking for a word, and it is the strongest form available here — no browser
# runs in this suite, so nothing below may be read as a claim about a drawing.
def test_the_trajectory_of_a_cycle_is_a_function_of_the_phase_count_and_of_nothing_else():
    # §2.2. The list of connections is what the picture is made of, and if it
    # could consult anything besides the count — a lane's report, a status
    # table, a stored history — the panel would be able to draw a travelled
    # path. It reaches for no name at all.
    assert free_names(function_body("orbitEdges"), {"n", "out", "i"}) == set()


def _braced(source: str, marker: str) -> str:
    """Return the body of the first block opening after ``marker``."""
    start = source.index(marker)
    i = j = source.index("{", start)
    depth = 0
    while True:
        depth += (source[j] == "{") - (source[j] == "}")
        j += 1
        if depth == 0:
            return source[i + 1:j - 1]


def test_a_cycle_with_no_phases_still_renders_every_role_it_could_not_place():
    # The owner's N = 0 row, held where it can be: the drawing is inside a
    # branch on the phase count and the roles are outside it, so an Orbit with
    # nothing to draw cannot take the participants down with it. The empty
    # message is the complement of the same count.
    body = function_body("renderOrbit")
    drawn = _braced(body, "if (proj.phases.length)")
    assert "drawOrbitRing" in drawn and "drawOrbitColumn" in drawn
    assert "renderUnstaged(proj.unstaged)" in body
    assert "renderUnstaged" not in drawn
    assert '$("cycleEmpty").hidden = proj.phases.length > 0;' in body


def test_the_orbit_writes_to_its_own_surfaces_and_to_no_others():
    # §2.4, the part a legacy project depends on: an Orbit that cannot draw
    # itself must not be able to hide anything else. The surfaces it may reach
    # are the field, its two layers, the empty message, the hint, and the group
    # the roles it could not place go into — the lanes, the map, the agents block
    # and the findings table are not among them.
    #
    # Reading the body of renderOrbit alone was not that claim. renderOrbit calls
    # renderUnstaged, which the reading never entered, so `$("agents").hidden =
    # true` inserted into renderUnstaged left this green while the same line
    # inside renderOrbit reddened it — the guard held the outermost function and
    # read as if it held the Orbit. So the surfaces are counted over renderOrbit
    # together with everything it can reach, and the walk is required to reach
    # renderUnstaged, which is where the hole was.
    reached = reachable_from("renderOrbit")
    assert {"renderUnstaged", "drawOrbitRing", "drawOrbitColumn"} <= reached, reached
    assert {surface for name in reached
            for surface in re.findall(r'\$\("(\w+)"\)', function_body(name))} == \
        {"orbitField", "orbitSvg", "orbitBody", "cycleEmpty", "cycleHint", "roles"}


def test_both_layouts_are_built_from_the_one_edge_list_and_the_one_stage_builder():
    # §2bis: the cycle closes at every count in both layouts, and the reason is
    # that there is one list of connections and one builder for a stage. Two
    # consumers and one producer — a third way to draw a connection would have
    # to appear here first.
    for name in ("drawOrbitRing", "drawOrbitColumn"):
        body = function_body(name)
        assert "orbitEdges(" in body, name
        assert "orbitStage(" in body, name
    assert script().count("orbitEdges(") == 3       # the producer and its two consumers
    assert script().count("orbitStage(") == 3


def test_the_vertical_layout_walks_the_declared_phases_in_the_order_they_arrive():
    # §4 and the owner's narrow row. What can be established by reading the
    # source is the walk: the stages are appended by iterating `proj.phases`
    # itself, the step link between two of them is emitted from the edge list,
    # and the return is appended after the loop as an element of its own. That
    # the browser then paints them in that order is not established here.
    body = function_body("drawOrbitColumn")
    assert re.search(r"proj\.phases\.forEach\(\(p, i\) =>", body), body
    assert 'e.kind === "step" && e.from === i' in body
    assert 'e.kind === "next"' in body
    assert body.index("forEach") < body.index('e.kind === "next"')
    for undo in (".sort(", ".reverse(", ".slice(").__iter__():
        assert undo not in body, undo


def test_a_human_wait_marks_a_stage_that_already_exists_and_can_never_add_one():
    # §2.5: the queue is a state on a stage, not an entity of its own. The seat
    # table is built once, from the declared phases, and never grown — there is
    # no `set` on it anywhere — so nothing a lane raises can put a node on the
    # Orbit that the map did not declare.
    body = function_body("orbitProject")
    assert "new Map(phases.map(" in body
    assert "seats.set(" not in body
    assert 'seat.marks.add("waiting")' in body


def test_a_stage_assignment_places_a_role_and_a_lane_report_never_moves_it():
    # §2.3, held as a relation instead of a reading. The seat table is reached
    # into three times in the whole projection, and the three arguments are the
    # whole design: the stage a role declares, which is what decides where that
    # role is drawn; the phase the merger computed, which is what decides which
    # stage is current; and the phase the layout is drawing, which is how it
    # fetches what it has to show. A lane's own `now.phase` is compared and
    # never looked up, so a runtime report cannot move a role to another stage —
    # it can only raise the mismatch mark.
    body = function_body("orbitProject")
    assert re.findall(r"seats\.get\(([^)]*)\)", body) == \
        ["r.stage", "cycle.current_phase", "p"]
    assert 'seat.marks.add("mismatch")' in body


def test_the_projection_reads_the_cycle_and_the_state_document_and_nothing_else():
    # What decides a stage's marks. The projection reaches for two collection
    # constructors and for no other name, so there is nowhere for a clock, a
    # stored history or a second table of stages to enter — which is what makes
    # "every mark is a fact already in state.json" checkable rather than stated.
    bound = {"cycle", "s", "phases", "roles", "held", "l", "asking", "w", "a",
             "seats", "p", "unstaged", "r", "seat", "lanes", "elsewhere", "now"}
    assert free_names(function_body("orbitProject"), bound) == {"Map", "Set"}


def test_the_geometry_counts_off_the_phase_list_and_not_off_a_number_of_its_own():
    # §2.1's central prohibition, and the one a dependence guard cannot reach:
    # `for (let i = 0; i + 1 < 5; i++)` introduces no new name and hard-wires
    # the Default Orbit into the panel. So the count is held positively — the
    # connection list carries no number except the 0 and the 1 it needs to walk
    # a list, both loops are bounded by the phase count, and the angle of a
    # stage divides the turn by that count.
    edges = function_body("orbitEdges")
    assert set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?", edges)) <= {"0", "1"}, edges
    assert re.search(r"for \(let i = 0; i \+ 1 < n; i\+\+\)", edges), edges
    ring = function_body("orbitRing")
    assert re.search(r"for \(let i = 0; i < n; i\+\+\)", ring), ring
    assert "orbitAngle(i, n)" in ring
    angle = re.search(r"const orbitAngle = (.*?);\n", panel_html()).group(1)
    assert "/ n" in angle, angle


def test_the_ellipse_is_derived_from_the_count_the_field_and_the_stage_box_alone():
    # §2.1. Geometry from the declared cycle means the radii answer to how many
    # phases there are and how much room the field has, and to nothing else. A
    # pentagon hard-coded into the panel, a lookup keyed on a phase name, or a
    # reading of the viewport taken behind the layout's back would all show up
    # here as a name this function has no business knowing.
    bound = {"n", "w", "bw", "bh", "rx", "ry", "i", "a", "b", "apart", "point"}
    assert free_names(function_body("orbitRing"), bound) == \
        {"Math", "orbitAngle", "ORBIT_GUTTER"}
    assert free_names(function_body("orbitBox"), {"n", "w", "apex", "fits"}) == \
        {"Math", "orbitAngle", "ORBIT_GUTTER"}


# ── the harness table the panel keeps, against the registry Python ships ───
def panel_harness_names() -> dict[str, str]:
    """Parse the panel's id-to-product-name table."""
    block = re.search(r"const HARNESS_NAMES = \{(.*?)\n\};", panel_html(), re.S)
    assert block, "the panel no longer carries a HARNESS_NAMES table"
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block.group(1)))


def test_the_panel_names_every_registered_harness_exactly_as_the_registry_does():
    # §2.6, and the second-source-of-truth problem it creates. The panel is a
    # single static file with no way to import Python, so the registry's display
    # names have to be copied into it — and a copy is only allowed to exist with
    # a guard that goes red when it drifts. Entry by entry, both directions: a
    # row added to conductor/harnesses.py and not to the panel fails here, and
    # so does a product renamed in the panel alone.
    assert panel_harness_names() == \
        {entry.id: entry.display_name for entry in harnesses.known()}


def test_the_panel_registers_no_harness_the_registry_has_not():
    # The other half of "the UI commit does not change the registry": Gemini CLI
    # and OpenCode are named in the product brief and are not in the registry
    # today, and adding either one to the panel would ship a registry change
    # through the back door. Held as a set relation rather than by naming the
    # two, so the next brief entry is covered by the same line.
    assert set(panel_harness_names()) == {entry.id for entry in harnesses.known()}


@pytest.mark.parametrize("name", ["Some Local Agent", "gemini-cli", "opencode",
                                  "Кодекс", "中文", "my_own_agent", "x"])
def test_an_unregistered_harness_resolves_to_the_string_the_map_wrote(name):
    # The neutral fallback, from the side that can be executed: `resolve` hands
    # back the string as its own display name for anything it does not know, and
    # the panel's table does not know these either. Nothing normalises them
    # toward a registry id, which is what a slugify or a nearest-match would do.
    assert harnesses.resolve(name).display_name == name
    assert name not in panel_harness_names()


def test_the_panel_has_one_source_for_a_harness_name_and_falls_back_to_the_string():
    # A dependence claim, source-read: the lookup reaches for the table and for
    # `String`, and for nothing else. That is what rules out the second fallback
    # §2.6 forbids — a hue hashed out of the name, a guessed monogram, a second
    # table of near-matches — without this test having to know what one would be
    # called. `String(id)` is the whole of the fallback, so an unregistered
    # harness is shown as itself.
    expression = re.search(r"const harnessName = (.*?);\n", panel_html(), re.S).group(1)
    assert free_names(expression, {"id"}) == {"HARNESS_NAMES", "String"}
    assert script().count("HARNESS_NAMES") == 2      # the table, and this lookup


def test_each_role_on_a_stage_resolves_its_own_harness():
    # §2.6 asks for several different harnesses on different stages, each shown
    # as its own. The stage builder resolves exactly one thing — the harness of
    # the role it is drawing — so it has no way to resolve one product for a
    # whole Orbit or to inherit a neighbour's. DEC-UI-3 moved the resolution
    # from the name lookup to the badge builder, which resolves the name, the
    # monogram and the accent together; the relation held here is the same one.
    body = function_body("orbitStage")
    assert re.findall(r"harnessBadge\(([^)]*)\)", body) == ["r.harness"]
    assert "harnessName(" not in body


def test_the_merger_never_reports_that_a_phase_was_completed():
    # §2.2: v1 has no run history, so there is nothing in the state document
    # that could make a "travelled path" true. Held as a property of the cycle
    # projection: it carries the declared phases, the roles, and at most the
    # one phase a lane is reporting right now.
    lanes = [lane("claude", "impl", phase="deliver",
                  updated=(NOW - timedelta(minutes=5)).isoformat()),
             lane("codex", "rev", phase="design", updated=RECENT)]
    state = merge.merge(cycle_map(["design", "deliver"],
                                  [role("impl"), role("rev")]), None, lanes, [], 0, NOW)
    assert set(state["cycle"]) == {"phases", "roles", "current_phase"}
    assert state["cycle"]["current_phase"] == "deliver"
