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

from conductor import harnesses, merge
from tests.test_panel_cascade import free_names, function_body, panel_html, script

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
    # whole Orbit or to inherit a neighbour's.
    body = function_body("orbitStage")
    assert re.findall(r"harnessName\(([^)]*)\)", body) == ["r.harness"]


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
