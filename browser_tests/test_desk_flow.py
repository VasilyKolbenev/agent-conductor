"""The «Схема» panel in a real browser, on the real flow routes, in both languages (7.11 item 8).

The bench (`desk_flow_bench.py`) mounts the REAL model and renderer on the desk's page over a real
server and performs every ask on the real `…/flow` routes, so what a test reads back from the
server is what a cycle really holds, and the rows and the counter the panel draws are compared with
the answer the server really gave. Every test runs once in English and once in Russian: what is
asserted about a word is asserted against the catalogue's own message for that language, never a
literal, so a missing or swapped message fails in the language it is missing in.

Each scenario is one sentence of 7.11 item 8: a cycle with a tester and a fork built on the canvas
with the counter and the diagnostics following the server; an error row lighting its step, its road
and its loop; «Сначала эта ветка» reordering the branches with their numbers; «Начать с: Цикл Далио»
with its five warnings and the fix of `loop_order`; an extension field edited, published and
reopened; the quick mode building the canvas's flow. The rest are the claims the panel makes about
itself: a lost answer is read, never repeated; another window's change is said; typed text and the
caret survive a redraw.
"""
from __future__ import annotations

import json
import uuid

from playwright.sync_api import expect

from browser_tests.desk_flow_bench import Flow, desk_url, flow, lang  # noqa: F401

FIVE_WARNINGS = {"link_outside_desk", "loop_order", "rework_after_correction",
                 "worst_over_actions", "worst_over_time"}


def drawn_rows(bench: Flow) -> list[tuple[str, str]]:
    """The diagnostics the panel draws: (code, severity), in the order drawn."""
    return [tuple(pair) for pair in bench.page.eval_on_selector_all(
        "[data-flow-diag] li[data-diag]", "(nodes) => nodes.map((n) => [n.dataset.diag, "
        "n.dataset.severity])")]


def server_rows(rows: list[dict]) -> list[tuple[str, str]]:
    return [(row["code"], row["severity"]) for row in rows]


def counter(bench: Flow) -> dict[str, list[int]]:
    """The counter as drawn: actions and seconds of each line, read off its own attributes."""
    return bench.page.evaluate("""() => Object.fromEntries(["clean", "worst"].map((name) => {
      const line = document.querySelector(`[data-flow-counter] [data-counter-${name}]`);
      return [name, line ? [Number(line.dataset.actions), Number(line.dataset.seconds)] : null];
    }))""")


def from_starter(bench: Flow, starter: str) -> None:
    """Begin from a starter: a new cycle with its flow, written at once."""
    bench.open()
    bench.control(f"schema:new:starter:{starter}").click()
    bench.settle()


def step_ids(state: dict) -> list[str]:
    """The step ids of the flow a `FlowState` holds."""
    return [row["step_id"] for row in state["flow"]["steps"]]


def writes_of(bench: Flow) -> list[str]:
    """The cycle each write the panel asked was for, in order."""
    return [ask["subject"] for ask in bench.log() if ask["name"] == "schema_write"]


def server_counter(answer: dict) -> dict[str, list[int]]:
    budget = answer["budget"]
    return {name: [budget[name]["actions"], budget[name]["seconds"]] for name in ("clean", "worst")}


def test_a_cycle_with_a_tester_and_a_fork_built_on_the_canvas_follows_the_servers_answers(
        flow, lang):
    name = flow.open()
    expect(flow.control("schema:pick")).to_be_visible()
    seen = []
    for kind in ("analyst", "doer", "tester", "decision"):
        flow.add(kind)
        answer = flow.last("schema_write")
        assert drawn_rows(flow) == server_rows(answer["diagnostics"]), (
            "the rows are the server's, in its order, and the panel adds none of its own")
        assert counter(flow) == server_counter(answer), (
            "the counter is the server's after each edit")
        seen.append(json.dumps(counter(flow)))
    assert len(set(seen)) >= 2, "the counter moved with the cycle: it is not a fixed text"
    flow.select_step("analyst")
    flow.add("reviewer")
    assert drawn_rows(flow) == server_rows(flow.last("schema_write")["diagnostics"])
    steps = flow.page.eval_on_selector_all("[data-node-id]",
                                           "(nodes) => nodes.map((n) => n.dataset.nodeId)")
    assert steps == ["analyst", "doer", "tester", "decision", "reviewer", "doer-fix", "tester-fix"]
    held = flow.server(flow.view()["workflowId"])
    assert held["source"] == "draft" and [s["step_id"] for s in held["flow"]["steps"]] == steps
    assert flow.page.locator("[data-flow-branches]").count() == 1, "the fork says its rule"
    assert name.startswith("cycle-") and flow.view()["workflowId"].startswith("cycle-")
    heading = flow.page.locator("[data-flow-counter] h3").text_content()
    assert heading == flow.say("wizard.budget.heading")
    assert flow.page.locator("[data-flow] h2").first.text_content() == flow.say("schema.heading")
    assert flow.control("schema:save").text_content() == flow.say("schema.save")
    assert flow.page.locator('[data-add-kind="tester"]').text_content() == flow.say(
        "schema.add.tester")
    assert flow.page.locator("[data-lens]").count() == 2, "the canvas's two lenses are offered"


def test_check_asks_the_server_again_and_never_replaces_the_text_being_typed(flow):
    from_starter(flow, "desk-standard")
    before = len([ask for ask in flow.log() if ask["name"] == "schema_read"])
    flow.control("schema:check").click()
    expect(flow.root).to_have_attribute("data-flow-save", "saved")
    flow.page.wait_for_function("(n) => window.host.log.filter((a) => a.name === 'schema_read')"
                                ".length > n", arg=before)
    flow.select_step("do")
    flow.control("schema:field:purpose").fill("Typed and not committed")
    flow.dispatch(type="check")
    flow.page.wait_for_function("(n) => window.host.log.filter((a) => a.name === 'schema_read')"
                                ".length > n + 1", arg=before)
    assert flow.control("schema:field:purpose").input_value() == "Typed and not committed"


def test_a_revision_review_can_be_cancelled_and_nothing_is_written_by_it(flow):
    from_starter(flow, "desk-standard")
    writes = len([ask for ask in flow.log() if ask["name"] == "schema_write"])
    flow.control("schema:publish").click()
    expect(flow.page.locator("[data-flow-review]")).to_be_visible()
    expect(flow.control("schema:publish")).to_have_count(0)
    flow.control("schema:publish:cancel").click()
    expect(flow.page.locator("[data-flow-review]")).to_have_count(0)
    assert len([ask for ask in flow.log() if ask["name"] == "schema_write"]) == writes


def test_a_fork_is_said_to_run_one_branch_at_a_time_and_the_later_branch_waits_its_turn(flow):
    from_starter(flow, "desk-standard")
    assert flow.page.locator("[data-flow-branches]").count() == 0, "a line has no branches"
    flow.select_step("analyst")
    flow.add("reviewer")
    badges = flow.page.eval_on_selector_all(
        "[data-node-id][data-branch]", "(nodes) => nodes.map((n) => [n.dataset.nodeId, "
        "n.dataset.branch])")
    assert badges == [["do", "1"], ["result", "1"], ["reviewer", "2"]], (
        "a branch is what one road reaches and no other road of the fork reaches")
    note = flow.page.locator("[data-flow-branches]").text_content()
    assert note == flow.say("schema.branch.note")
    waiting = flow.page.locator('[data-node-id="reviewer"] .studio-node__waits').text_content()
    assert waiting == flow.say("schema.branch.waits")


def test_first_branch_reorders_the_branches_and_the_numbers_follow_the_order(flow):
    from_starter(flow, "desk-standard")
    flow.select_step("analyst")
    flow.add("reviewer")
    before = [s["step_id"] for s in flow.held()["steps"]]
    flow.select_step("reviewer")
    flow.control("schema:step:branch-first").click()
    flow.settle()
    after = [s["step_id"] for s in flow.held()["steps"]]
    assert after.index("reviewer") < after.index("do") and before.index("reviewer") > before.index(
        "do")
    numbers = flow.page.eval_on_selector_all(
        "[data-node-id][data-branch]", "(nodes) => Object.fromEntries(nodes.map((n) => "
        "[n.dataset.nodeId, n.dataset.branch]))")
    assert numbers == {"reviewer": "1", "do": "2", "result": "2"}
    assert [s["step_id"] for s in flow.server(flow.view()["workflowId"])["flow"]["steps"]] == after
    expect(flow.control("schema:step:branch-first")).to_have_count(0)


def test_an_error_row_lights_its_step_its_road_and_its_loop(flow, lang):
    from_starter(flow, "desk-standard")
    flow.select_step("do")
    flow.set_field("schema:field:verifier_role_id", "")
    flow.settle()
    row = flow.page.locator('[data-flow-diag] li[data-diag="dispatch_without_checker"]')
    expect(row).to_have_attribute("data-severity", "error")
    expect(flow.page.locator('[data-node-id="do"]')).to_have_attribute("data-diag", "error")
    assert flow.page.locator('[data-node-id="do"] .studio-node__diag').text_content() == flow.say(
        "wizard.diag.error"), "a mark is a word on the step, never a colour alone"
    flow.page.locator('[data-edge="do result"]').focus()
    flow.page.keyboard.press("Enter")
    expect(flow.page.locator("[data-flow-inspector]")).to_have_attribute("data-selected",
                                                                           "do result")
    flow.control("schema:field:when").select_option("rejected")
    flow.settle()
    expect(flow.page.locator('[data-flow-diag] li[data-diag="when_invalid"]')).to_have_count(1)
    expect(flow.page.locator('[data-edge="do result"]')).to_have_attribute("data-diag", "error")
    flow.select_step("do-fix")
    flow.control("schema:field:back_to").select_option("result")
    flow.settle()
    expect(flow.page.locator('[data-flow-diag] li[data-diag="loop_body_empty"]')).to_have_count(1)
    expect(flow.page.locator('[data-node-id="do-fix"]')).to_have_attribute("data-diag", "error")
    flow.page.locator('[data-flow-diag] li[data-diag="dispatch_without_checker"] '
                      '[data-focus^="schema:diag:show"]').click()
    expect(flow.page.locator("[data-flow-inspector]")).to_have_attribute("data-selected", "do")
    assert flow.page.locator("[data-flow-publish-why]").text_content() == flow.say(
        "schema.publish.blocked")
    expect(flow.control("schema:publish")).to_be_disabled()


def test_start_from_the_dalio_cycle_shows_its_five_warnings_and_the_fix_clears_loop_order(flow):
    from_starter(flow, "dalio-v5")
    assert set(flow.diag_codes()) == FIVE_WARNINGS
    assert {sev for _, sev in drawn_rows(flow)} == {"warning"}
    assert flow.page.locator("[data-flow-publish-why]").count() == 0, "warnings do not stop it"
    flow.control("schema:fix:rework-first").click()
    flow.settle()
    assert set(flow.diag_codes()) == FIVE_WARNINGS - {"loop_order"}
    expect(flow.control("schema:fix:rework-first")).to_have_count(0)
    title = flow.view()["flow"]["title"]
    assert flow.page.locator('[data-focus="schema:new:starter:dalio-v5"]').text_content() == (
        flow.say("schema.new.from", title=flow.say("schema.starter.dalio_v5")))
    assert title and flow.server(flow.view()["workflowId"])["flow"]["title"] == title


def test_an_always_road_out_of_an_agent_has_a_button_that_makes_it_on_success(flow):
    from_starter(flow, "dalio-v5")
    before = [(link["from"], link["to"], link["when"]) for link in flow.held()["links"]]
    assert ("goal", "identify", "always") in before
    button = flow.control("schema:fix:when-success:goal:identify")
    assert button.text_content() == flow.say("schema.fix.when_success")
    button.click()
    flow.settle()
    after = [(link["from"], link["to"], link["when"]) for link in flow.held()["links"]]
    assert ("goal", "identify", "success") in after
    assert [row for row in after if row[:2] != ("goal", "identify")] == [
        row for row in before if row[:2] != ("goal", "identify")], "nothing else moved"


def test_an_extension_field_edited_then_published_and_reopened_gives_an_equal_flow(flow):
    from_starter(flow, "dalio-v5")
    name = flow.view()["workflowId"]
    flow.select_step("goal")
    summary = flow.control("schema:fold:ext")
    expect(summary).to_contain_text("2"), "the heading carries the number of keys the step holds"
    summary.click()
    row = flow.page.locator('[data-ext-row="attempt_bound"]')
    expect(row).to_have_attribute("data-set", "false")
    flow.set_field("schema:field:attempt_bound", "2")
    flow.settle()
    assert flow.held()["steps"][0]["ext"]["attempt_bound"] == 2
    expect(summary).to_contain_text("3")
    flow.control("schema:publish").click()
    review = flow.page.locator("[data-flow-review] li[data-change]")
    expect(review.first).to_be_visible()
    assert flow.page.locator('[data-flow-review] li[data-change="step_added"]').count() >= 9
    flow.control("schema:publish:confirm").click()
    flow.settle()
    expect(flow.page.locator("[data-flow-published]")).to_be_visible()
    held = flow.held()
    flow.dispatch(type="open", workflowId=name, title="")
    expect(flow.root).to_have_attribute("data-flow-phase", "ready")
    again = flow.held()
    assert json.dumps(again, sort_keys=True) == json.dumps(held, sort_keys=True)
    assert flow.view()["source"] == "published" and flow.view()["latest"] == 1
    assert flow.server(name)["flow"]["steps"][0]["ext"]["attempt_bound"] == 2


def test_an_extension_key_is_given_back_to_the_compiler_by_one_press(flow):
    from_starter(flow, "dalio-v5")
    flow.select_step("goal")
    flow.control("schema:fold:ext").click()
    flow.control("schema:ext:reset:stage").click()
    flow.settle()
    assert "stage" not in flow.held()["steps"][0]["ext"]
    expect(flow.control("schema:ext:reset:stage")).to_have_count(0)
    computed = flow.page.locator('[data-ext-row="stage"] [data-ext-computed]')
    assert computed.text_content() == flow.say("schema.ext.computed")
    flow.set_field("schema:field:stage", "{")
    assert flow.view()["notice"] == {"key": "schema.model.field_json"}
    assert flow.page.locator("[data-flow-notice]").text_content() == flow.say(
        "schema.model.field_json")
    assert "stage" not in flow.held()["steps"][0]["ext"], "nothing half-written reaches the flow"


def test_the_quick_mode_builds_the_flow_the_canvas_builds(flow):
    quick_id = flow.open()
    flow.control("schema:new:quick").click()
    flow.type_into("schema:quick:title", "Same")
    for kind in ("analyst", "doer", "tester"):
        flow.control(f"schema:quick:add:{kind}").click()
    expect(flow.page.locator("[data-flow-quick] li[data-quick-row]")).to_have_count(3)
    flow.control("schema:quick:remove:0").click()
    flow.control("schema:quick:add:analyst").click()
    flow.control("schema:quick:build").click()
    flow.settle()
    by_quick = flow.server(flow.view()["workflowId"])["flow"]
    assert flow.view()["workflowId"] != quick_id, "a built flow is a new cycle under its own id"
    by_canvas_id = flow.open()
    for kind in ("doer", "tester", "analyst", "decision"):
        flow.add(kind)
    by_canvas = flow.server(flow.view()["workflowId"])["flow"]
    assert {**by_quick, "title": ""} == {**by_canvas, "title": ""}
    assert by_quick["title"] == "Same" and by_canvas_id != quick_id


def test_a_lost_answer_is_settled_by_reading_and_the_write_is_never_repeated_blindly(flow):
    name = flow.open()
    flow.page.evaluate("() => { window.host.lose = 1; }")
    flow.page.locator('[data-add-kind="analyst"]').click()
    flow.settle("saved")
    writes = [ask for ask in flow.log() if ask["name"] == "schema_write"]
    reads = [ask for ask in flow.log() if ask["name"] == "schema_read"]
    assert len(writes) == 1, "the lost write landed, so it is not written a second time"
    assert len(reads) == 2 and reads[-1]["subject"] == flow.view()["workflowId"]
    assert name and [s["step_id"] for s in flow.server(flow.view()["workflowId"])["flow"]["steps"]
                     ] == ["analyst"]
    assert flow.view()["save"] == "saved"


def test_the_late_answer_of_a_cycle_opened_first_does_not_fill_the_cycle_opened_second(flow):
    first = flow.open()
    flow.add("analyst")
    flow.add("doer")
    kept = step_ids(flow.server(first))
    flow.open()
    second = f"cycle-{uuid.uuid4().hex[:8]}"
    flow.hold(first)
    flow.hold(second)
    flow.control("schema:pick").select_option(first)
    flow.dispatch(type="open", workflowId=second, title="Fresh")
    flow.release(first)
    flow.page.wait_for_function("() => window.host.pending === 1")
    waiting = flow.page.evaluate("""() => {
      const view = window.host.view(), nodes = document.querySelectorAll("[data-node-id]");
      return [view.workflowId, view.phase, view.flow, nodes.length];
    }""")
    assert waiting == [second, "reading", None, 0], (
        "the answer of the first cycle lands nowhere while the second still waits for its own")
    flow.release(second)
    expect(flow.root).to_have_attribute("data-flow-phase", "ready")
    flow.idle()
    assert flow.view()["workflowId"] == second and flow.held()["steps"] == []
    before = len(writes_of(flow))
    flow.add("analyst")
    assert writes_of(flow)[before:] == [second], "the edit is written to the cycle that stands"
    assert step_ids(flow.server(second)) == ["analyst"]
    assert step_ids(flow.server(first)) == kept and len(kept) > 1, "the first cycle is as it was"


def test_a_change_made_in_another_window_is_said_and_shown_and_ours_is_not_written_over_it(flow):
    flow.open()
    flow.add("analyst")
    name = flow.view()["workflowId"]
    theirs = flow.held()
    theirs["title"] = "Theirs"
    assert flow.call("other", name, theirs)["status"] == "accepted"
    flow.page.locator('[data-add-kind="doer"]').click()
    flow.settle("conflict")
    assert flow.page.locator("[data-flow-notice]").text_content() == flow.say(
        "schema.write.conflict")
    assert flow.held()["title"] == "Theirs" and [s["step_id"] for s in flow.held()["steps"]] == [
        "analyst"], "what the other window wrote is what stands; ours was not written over it"
    assert flow.server(name)["flow"]["title"] == "Theirs"


def test_text_typed_into_a_field_and_its_caret_survive_a_redraw_and_leaving_commits_it(flow):
    from_starter(flow, "desk-standard")
    flow.select_step("do")
    field = flow.control("schema:field:title")
    field.click()
    field.press_sequentially("Build")
    flow.page.evaluate("""() => {
      const field = document.querySelector('[data-focus="schema:field:title"]');
      field.focus();
      field.setSelectionRange(2, 2);
    }""")
    flow.dispatch(type="view", pan={"x": 3, "y": 4}, zoom=1)
    flow.page.keyboard.type("X")
    caret = flow.page.evaluate("""() => {
      const field = document.querySelector('[data-focus="schema:field:title"]');
      return [field.value, field.selectionStart, document.activeElement === field];
    }""")
    assert caret == ["BuXild", 3, True], "the text and the caret are carried across the redraw"
    assert flow.held()["steps"][1]["title"] is None, "nothing is written while the text is typed"
    field.blur()
    flow.settle()
    assert flow.held()["steps"][1]["title"] == "BuXild"
    assert flow.server(flow.view()["workflowId"])["flow"]["steps"][1]["title"] == "BuXild"


def test_a_step_released_after_a_drag_is_written_with_its_position(flow):
    from_starter(flow, "desk-standard")
    assert flow.held()["steps"][1]["position"] is None, "a starter's steps carry no place yet"
    node = flow.page.locator('[data-node-id="do"]')
    node.scroll_into_view_if_needed()
    box = node.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    flow.page.mouse.move(x, y)
    flow.page.mouse.down()
    flow.page.mouse.move(x + 140, y + 70, steps=8)
    flow.page.mouse.up()
    flow.settle()
    placed = flow.server(flow.view()["workflowId"])["flow"]["steps"][1]
    assert placed["step_id"] == "do" and set(placed["position"]) == {"x", "y"}
    assert all(isinstance(value, int) for value in placed["position"].values())
    assert flow.held()["steps"][1]["position"] == placed["position"]


def test_pressing_publish_with_a_text_still_typed_writes_the_text_and_publishes_it_next(flow):
    from_starter(flow, "desk-standard")
    name = flow.view()["workflowId"]
    flow.select_step("do")
    flow.type_into("schema:field:title", "Build")
    flow.control("schema:publish").click()
    flow.settle()
    shown = flow.page.evaluate("""() => [document.querySelectorAll("[data-flow-review]").length,
      document.querySelector('[data-focus="schema:field:title"]').value,
      document.querySelector("[data-flow-notice]").textContent]""")
    assert shown == [0, "Build", flow.say("schema.write.publish_wait")], (
        "the text was written, not lost, and no review opened over a flow without it")
    assert flow.held()["steps"][1]["title"] == "Build"
    assert flow.server(name)["flow"]["steps"][1]["title"] == "Build"
    flow.control("schema:publish").click()
    expect(flow.page.locator("[data-flow-review]")).to_be_visible()
    flow.control("schema:publish:confirm").click()
    flow.settle()
    published = flow.server(name)
    assert published["source"] == "published" and published["flow"]["steps"][1]["title"] == "Build"


def test_a_text_typed_under_an_open_review_stays_typed_and_is_written_once_it_is_closed(flow):
    from_starter(flow, "desk-standard")
    name = flow.view()["workflowId"]
    flow.select_step("do")
    flow.control("schema:publish").click()
    expect(flow.page.locator("[data-flow-review]")).to_be_visible()
    flow.set_field("schema:field:title", "Kept")
    shown = flow.page.evaluate("""() => [document.querySelector(
      '[data-focus="schema:field:title"]').value, document.querySelector(
      "[data-flow-notice]").textContent]""")
    assert shown == ["Kept", flow.say("schema.write.publish_open")], (
        "leaving the field while a review is open loses nothing and says why it was not written")
    flow.control("schema:publish:cancel").click()
    flow.control("schema:save").click()
    flow.settle()
    assert flow.server(name)["flow"]["steps"][1]["title"] == "Kept"


def test_a_press_that_takes_focus_from_a_field_still_does_its_work_and_commits_the_field(flow):
    from_starter(flow, "desk-standard")
    flow.select_step("do")
    flow.control("schema:field:title").fill("Renamed")
    flow.page.locator('[data-add-kind="reviewer"]').click()
    flow.settle()
    held = flow.held()
    assert [row["step_id"] for row in held["steps"]].count("reviewer") == 1, (
        "the press was not swallowed by the redraw that committing the field made")
    assert held["steps"][1]["title"] == "Renamed"
    assert flow.server(flow.view()["workflowId"])["flow"]["steps"][1]["title"] == "Renamed"


def test_saving_writes_the_text_still_typed_and_a_ready_cycle_is_only_ever_copied(flow):
    flow.open("desk-standard")
    expect(flow.page.locator("[data-flow-ready]")).to_have_text(flow.say("schema.ready.none"))
    flow.control("schema:new:starter:desk-standard").click()
    flow.settle()
    name = flow.view()["workflowId"]
    assert name.startswith("cycle-") and name != "desk-standard"
    flow.select_step("do")
    flow.control("schema:field:purpose").fill("Only this")
    assert flow.held()["steps"][1]["purpose"] != "Only this", "typed, not yet written"
    flow.control("schema:save").click()
    flow.settle()
    assert flow.server(name)["flow"]["steps"][1]["purpose"] == "Only this"
    assert flow.server("desk-standard")["source"] == "none", "the ready cycle was never written"
    assert flow.last("schema_write")["workflow_id"] == name
