"""The wizard model's step 4 ("Роли и указания"): roles, harness offers, instruction fields.

The roster, the quotas and the previous run are stand-in reads under `tests/fixtures/wizard/`
(the provider rows carry the three facts the wizard needs: `capabilities`, `task_channel`,
`offered`); the flows are lane L's fixtures. Every test is a value, run through the real module.
"""
from __future__ import annotations

from tests.desk_wizard_node import PRELUDE, fixture, run_js

FLOWS = {"standard": fixture("flow", "desk-standard.flow-state.json"),
         "short": fixture("flow", "desk-short.flow-state.json"),
         "starter": fixture("flow", "desk-starter-docs.flow-state.json"),
         "tester": fixture("flow", "desk-standard-tester.flow-state.json"),
         "dalio": fixture("flow", "dalio-v5.flow-state.json")}
DATA = {"flows": FLOWS, "workflows": fixture("wizard", "workflows.json"),
        "runs": fixture("wizard", "runs.json"), "tasks": fixture("wizard", "tasks.json"),
        "unpinned": fixture("wizard", "project_cycle_none.json"),
        "pinned": fixture("wizard", "project_cycle.json"),
        "quotas": fixture("wizard", "quotas.json"),
        "previous_run": fixture("wizard", "previous_run.json"),
        "previous_revision": fixture("wizard", "previous_revision.json")}
#: A wizard on the roles step. `reads` answers what the step draws on, `land` answers whichever
#: flow ask is outstanding, `atRoles` chooses a cycle by pinning it, lands its flow and moves on.
ROLES = PRELUDE + """
const digest = "sha256:" + "b".repeat(64);
const ok = (payload) => ({status: "accepted", payload});
const answer = (state, ask, result) => wiz.reduceWizard(state, {type: "answered", ask, result});
const flowOf = (base, over = {}) => ({...structuredClone(base), draft_digest: digest,
  source: "draft", published: null, ...over});
const flowAsk = (state) => wiz.wantedAsks(state).find(
  (ask) => ask.name === "flow" || ask.name === "flow_read");
const land = (state, flow) => answer(state, flowAsk(state), ok(flow));
const pin = (id) => ({pinned: {workflow_id: id, latest_revision: 1, set_by: "Вы: Василий",
  set_at: "2026-09-28T13:50:00Z"}});
const reads = (state, over = {}) => Object.entries({workflows: d.workflows, runs: d.runs,
  cycle_read: d.unpinned, tasks: d.tasks, quotas: d.quotas, ...over})
  .reduce((now, [name, payload]) => reply(now, name, payload), state);
const atCycle = (over = {}) => reads(opened(run(started(), {type: "next"})), over);
const atRoles = (over = {}, flow = d.flows.standard) =>
  wiz.reduceWizard(land(atCycle(over), flowOf(flow)), {type: "next"});
const standardAt = (id, base = d.flows.standard) => atRoles({cycle_read: pin(id)}, base);
const assigned = (state) => Object.fromEntries(wiz.assignmentView(state)
  .map((row) => [row.role_id, [row.provider, row.by]]));
const gate = (state) => wiz.canAdvance(state).reason;
const binding = (state, over = {}, base = d.flows.standard) => land(state, flowOf(base, over));
"""


def _union(flow: dict) -> list[str]:
    """Those who carry steps out, in step order, then the roles that only verify."""
    steps = [step for step in flow["steps"] if step["type"] == "agent"]
    roles = list(dict.fromkeys(step["role_id"] for step in steps))
    verifiers = [step.get("verifier_role_id") for step in steps]
    return roles + [role for role in dict.fromkeys(verifiers) if role and role not in roles]


def test_roles_are_the_union_of_role_and_verifier_role_over_the_flow_steps():
    out = run_js(ROLES + """
      show(Object.fromEntries(Object.entries(d.flows).map(([name, state]) => [name,
        wiz.rolesOf(state.flow).map((role) => [role.role_id, role.kind, role.needs,
          role.steps, role.verifies])])));
    """, DATA)
    for name, flow in FLOWS.items():
        assert [row[0] for row in out[name]] == _union(flow["flow"]), name
    assert out["standard"] == [
        ["role-analyst", "analyst", ["review"], ["analyst"], []],
        ["role-doer", "doer", ["dispatch"], ["do"], []],
        ["role-checker", "checker", ["review"], [], ["role-doer"]]]
    assert out["tester"][2] == ["role-tester", "tester", ["dispatch"], ["tester"], []]
    assert out["tester"][3] == ["role-checker", "checker", ["review"], [],
                                ["role-doer", "role-tester"]]
    assert "custom" in {row[1] for row in out["dalio"]}


def test_role_kinds_read_the_name_and_a_numbered_role_is_the_same_kind_again():
    out = run_js(ROLES + """
      show(["role-doer", "role-doer-2", "role-checker", "role-thinker", "doer", "role-", ""]
        .map(wiz.roleKind));
    """, DATA)
    assert out == ["doer", "doer", "checker", "custom", "custom", "custom", "custom"]


def test_review_roles_and_the_verifier_are_offered_only_harnesses_with_a_review_road():
    out = run_js(ROLES + """
      const roster = wiz.rosterOf(d.workflows.providers);
      const offers = (role) => wiz.offersFor(role, roster).map((row) => row.id);
      show({roster: roster.map((row) => [row.id, row.available, row.channel]),
        roles: wiz.rolesOf(d.flows.standard.flow).map((role) => [role.role_id, offers(role)])});
    """, DATA)
    assert out["roster"] == [["claude-code", True, "stdin"], ["codex", True, "stdin"],
                             ["grok-build", True, "argv"], ["kimi-code", False, "argv"],
                             ["deepseek-harness", True, "argv"]]
    assert out["roles"] == [["role-analyst", ["claude-code", "codex"]],
                            ["role-doer", ["claude-code", "codex", "grok-build",
                                           "deepseek-harness"]],
                            ["role-checker", ["claude-code", "codex"]]]


def test_a_harness_the_owner_hid_for_version_two_is_never_offered():
    out = run_js(ROLES + """
      const state = standardAt("desk-standard");
      const rows = wiz.assignmentView(state);
      const tried = wiz.reduceWizard(state, {type: "role-assign", role_id: "role-doer",
        provider_id: "qwen-code"});
      const bare = wiz.rosterOf([{provider_id: "x", display_name: "X",
        availability: "available", capabilities: ["dispatch"]}]);
      show({roster: wiz.rosterOf(d.workflows.providers).map((row) => row.id),
        offered_anywhere: rows.some((row) => row.offers.some((one) => one.id === "qwen-code")),
        assigned_anywhere: rows.some((row) => row.provider === "qwen-code"),
        assign_ignored: tried === state, unmarked_row: bare});
    """, DATA)
    assert "qwen-code" not in out["roster"]
    assert out["offered_anywhere"] is False and out["assigned_anywhere"] is False
    assert out["assign_ignored"] is True
    assert out["unmarked_row"] == [], "a row that does not say it is offered is not offered"


def test_an_unknown_or_stale_quota_is_shown_as_unknown_and_never_as_a_remainder():
    out = run_js(ROLES + """
      const of = (id, payload = d.quotas) => wiz.quotaOf(payload, id);
      const broken = structuredClone(d.quotas);
      broken.snapshots[0].state = "error";
      const windowStale = structuredClone(d.quotas);
      windowStale.snapshots[1].windows[0].freshness = "reset_passed";
      show({claude: of("claude-code"), codex: of("codex"), grok: of("grok-build"),
        kimi: of("kimi-code"), deepseek: of("deepseek-harness"), nobody: of("nobody"),
        no_read: of("codex", null), error: of("claude-code", broken),
        stale_window: of("codex", windowStale)});
    """, DATA)
    assert out["claude"] == {"known": True, "remaining": 12, "kind": "percent", "reason": None}
    assert out["codex"] == {"known": True, "remaining": 64, "kind": "percent", "reason": None}
    assert out["deepseek"] == {"known": True, "remaining": None, "kind": "balance",
                               "reason": None}
    unknown = {"known": False, "remaining": None, "kind": None}
    assert out["grok"] == {**unknown, "reason": "no_data"}
    assert out["kimi"] == {**unknown, "reason": "stale"}
    assert out["nobody"] == {**unknown, "reason": "no_data"}
    assert out["no_read"] == {**unknown, "reason": "no_data"}
    assert out["error"] == {**unknown, "reason": "source_error"}
    assert out["stale_window"] == {**unknown, "reason": "stale"}


def test_a_suggestion_prefers_a_known_remainder_to_an_unknown_one_and_the_verifier_a_new_face():
    out = run_js(ROLES + """
      const roles = wiz.rolesOf(d.flows.standard.flow);
      const grokFirst = [d.workflows.providers[2], ...d.workflows.providers.filter(
        (row) => row.provider_id !== "grok-build")];
      const picked = wiz.suggestAssignment(roles, grokFirst, d.quotas, {}, {});
      const nobody = wiz.suggestAssignment(roles, d.workflows.providers, null, {}, {});
      show({picked, nobody: nobody.assignment});
    """, DATA)
    assert out["picked"]["assignment"] == {"role-analyst": "codex", "role-doer": "codex",
                                           "role-checker": "claude-code"}
    assert out["picked"]["by"] == {"role-analyst": "suggestion", "role-doer": "suggestion",
                                   "role-checker": "suggestion"}
    assert "independent_pick" in out["picked"]["notes"]["role-checker"]
    assert out["nobody"] == {"role-analyst": "claude-code", "role-doer": "claude-code",
                             "role-checker": "codex"}


def test_an_argv_harness_is_not_suggested_for_the_doer_when_inputs_do_not_fit_and_says_why():
    out = run_js(ROLES + """
      const quotas = structuredClone(d.quotas);
      Object.assign(quotas.snapshots[2], {state: "observed", freshness: "current",
        windows: [{limit_id: "5h", window_id: "5h", used_percent: 10, remaining_percent: 90,
          freshness: "current"}]});
      const roles = wiz.rolesOf(d.flows.standard.flow);
      const at = (chars) => wiz.suggestAssignment(roles, d.workflows.providers, quotas, {},
        {chars: {"role-doer": chars}});
      const small = at(100), large = at(40000);
      show({small: [small.assignment["role-doer"], small.notes["role-doer"]],
        large: [large.assignment["role-doer"], large.notes["role-doer"]],
        fit: [wiz.argvFit("x".repeat(100), 200), wiz.argvFit("x", 32766),
          wiz.argvFit("x".repeat(2), 32766), wiz.argvFit("я".repeat(10), 40000)]});
    """, DATA)
    assert out["small"][0] == "grok-build" and "argv_not_fit" not in out["small"][1]
    assert out["large"][0] == "codex" and "argv_not_fit" in out["large"][1]
    assert out["fit"] == [{"chars": 300, "limit": 32767, "fits": True},
                          {"chars": 32767, "limit": 32767, "fits": True},
                          {"chars": 32768, "limit": 32767, "fits": False},
                          {"chars": 40010, "limit": 32767, "fits": False}]


def test_instruction_fields_follow_the_chosen_cycle_one_per_dispatch_step():
    out = run_js(ROLES + """
      const kinds = (state) => wiz.instructionFields(state, "en")
        .map((row) => [row.step_id, row.kind]);
      show({standard: kinds(standardAt("desk-standard")),
        short: kinds(standardAt("desk-short", d.flows.short)),
        tester: kinds(standardAt("cycle-7c1e5a90", d.flows.tester))});
    """, DATA)
    assert out["standard"] == [["do", "doer"]] and out["short"] == [["do", "doer"]]
    assert out["tester"] == [["do", "doer"], ["tester", "tester"]]


def test_a_cycle_without_dispatch_steps_has_no_instruction_fields():
    out = run_js(ROLES + """
      let state = run(open({starterId: "desk-starter-docs"}),
        {type: "edit-title", value: "Notes"}, {type: "edit-idea", value: "An app."},
        {type: "next"});
      state = reply(opened(state), "git", {git: {state: "repo", head: {ref: "refs/heads/main",
        commit: "abc1234"}, agent_instructions: {found: 0, default_include: false}}});
      state = reads(run(state, {type: "next"}));
      state = wiz.reduceWizard(land(state, flowOf(d.flows.starter)), {type: "next"});
      show({step: state.step, fields: wiz.instructionFields(state, "en"),
        roles: wiz.assignmentView(state).map((row) => row.role_id)});
    """, DATA)
    assert out["step"] == "roles" and out["fields"] == []
    assert out["roles"] == ["role-analyst", "role-reviewer", "role-designer"]


def test_the_doer_instruction_defaults_to_the_task_text_and_can_be_written_apart():
    out = run_js(ROLES + """
      const base = run(standardAt("desk-standard"), {type: "edit-hint", value: "Tests pass"});
      const field = (state) => wiz.instructionFields(state, "en")[0];
      const apart = run(base, {type: "instruction-own", step_id: "do", lang: "en"});
      const written = run(apart, {type: "instruction-edit", step_id: "do", text: "My own words."});
      const ignored = wiz.reduceWizard(base, {type: "instruction-edit", step_id: "do",
        text: "typed over the task text"});
      show({default: field(base), apart: field(apart), written: field(written),
        edit_on_task_text_ignored: ignored === base});
    """, DATA)
    default = out["default"]
    assert default["source"] == "task" and default["required"] is True and default["like"] is None
    assert default["text"] == "Make it work.\n\n## How to tell it is done (hint)\nTests pass"
    assert out["apart"]["source"] == "own" and out["apart"]["text"] == default["text"]
    assert out["written"]["text"] == "My own words." and out["written"]["source"] == "own"
    assert out["edit_on_task_text_ignored"] is True


def test_the_tester_instruction_is_required_and_starts_empty():
    out = run_js(ROLES + """
      const state = standardAt("cycle-7c1e5a90", d.flows.tester);
      const filled = run(state, {type: "instruction-edit", step_id: "tester",
        text: "Test the login form."});
      const rows = (one) => wiz.instructionFields(one, "en").map((row) =>
        [row.step_id, row.kind, row.source, row.required, row.text === "" ? "" : "text"]);
      show({fields: rows(state), gate: gate(state), gate_filled: gate(filled)});
    """, DATA)
    assert out["fields"] == [["do", "doer", "task", True, "text"],
                             ["tester", "tester", "own", True, ""]]
    assert out["gate"] == "instruction_empty"
    assert out["gate_filled"] != "instruction_empty"


def test_like_step_x_names_a_dispatch_step_with_no_like_of_its_own_and_carries_the_cost_note():
    out = run_js(ROLES + """
      const base = structuredClone(d.flows.tester);
      base.flow.steps.splice(3, 0, {...structuredClone(base.flow.steps[2]), step_id: "extra",
        role_id: "role-extra"});
      const state = standardAt("cycle-7c1e5a90", base);
      const rows = (one) => Object.fromEntries(wiz.instructionFields(one, "en").map((row) =>
        [row.step_id, [row.source, row.like, row.sharedWith, row.costNote]]));
      const like = (one, step_id, at) => wiz.reduceWizard(one, {type: "instruction-like",
        step_id, like: at});
      const shared = like(state, "tester", "do");
      show({start: rows(state), shared: rows(shared),
        do_on_a_shared_one: like(shared, "do", "tester") === shared,
        itself: like(state, "do", "do") === state,
        not_dispatch: like(state, "tester", "analyst") === state,
        unknown: like(state, "tester", "nope") === state,
        chain: like(shared, "extra", "tester") === shared,
        both: rows(like(shared, "extra", "do")).do[2],
        cleared: rows(like(shared, "tester", null)).tester});
    """, DATA)
    assert out["start"]["tester"] == ["own", None, [], False]
    assert out["shared"]["tester"] == ["like", "do", [], True]
    assert out["shared"]["do"] == ["task", None, ["tester"], False]
    assert out["do_on_a_shared_one"] and out["itself"] and out["not_dispatch"] and out["unknown"]
    assert out["chain"] is True and out["both"] == ["tester", "extra"]
    assert out["cleared"] == ["own", None, [], False]


def test_like_step_x_is_never_offered_on_a_cycle_the_product_owns():
    out = run_js(ROLES + """
      const base = structuredClone(d.flows.tester);
      base.workflow_id = "desk-standard";
      const state = standardAt("desk-standard", base);
      const tried = wiz.reduceWizard(state, {type: "instruction-like", step_id: "tester",
        like: "do"});
      show({ignored: tried === state,
        offers: wiz.instructionFields(state, "en").map((row) => row.likeChoices)});
    """, DATA)
    assert out == {"ignored": True, "offers": [[], []]}


def test_an_instruction_over_the_byte_limit_is_refused_and_an_argv_harness_shows_the_count():
    out = run_js(ROLES + """
      const base = standardAt("desk-standard");
      const own = (text) => run(base, {type: "instruction-own", step_id: "do", lang: "en"},
        {type: "instruction-edit", step_id: "do", text});
      const big = own("я".repeat(30000)), fine = own("я".repeat(24000));
      const toGrok = (state) => run(state, {type: "role-assign", role_id: "role-doer",
        provider_id: "grok-build"});
      const field = (state) => wiz.instructionFields(state, "en")[0];
      const withNote = run(toGrok(base), {type: "material-add", kind: "note", title: "T",
        content: "x".repeat(40000)});
      show({big: gate(big), fine: gate(fine), stdin: field(base).argv,
        argv: field(toGrok(base)).argv, inputs: wiz.inputChars(base),
        text: field(base).text.length, over: field(withNote).argv, over_gate: gate(withNote)});
    """, DATA)
    assert out["big"] == "instruction_too_large" and out["fine"] != "instruction_too_large"
    assert out["stdin"] is None
    assert out["argv"] == {"chars": out["text"] + out["inputs"], "limit": 32767, "fits": True}
    assert out["over"]["fits"] is False and out["over"]["chars"] > 32767
    assert out["over_gate"] == "instruction_argv_over"


def test_the_last_run_of_the_same_cycle_preselects_the_assignment_and_marks_new_roles_assign():
    out = run_js(ROLES + """
      let state = atCycle();
      const asks = wiz.wantedAsks(state).filter((ask) => ask.name.startsWith("previous_"))
        .map((ask) => [ask.id, ask.name, ask.target, ask.subject, ask.body]);
      const previous = (one) => reply(reply(one, "previous_run", d.previous_run,
        {subject: "task-b-r1"}), "previous_revision", d.previous_revision,
        {subject: "desk-standard"});
      const withTester = {...d.flows.tester, workflow_id: "desk-standard"};
      const at = (one, flow) => wiz.reduceWizard(land(one, flowOf(flow)), {type: "next"});
      const known = at(previous(state), withTester);
      const failed = at(reply(state, "previous_run", null, {status: "refused",
        code: "store_error", subject: "task-b-r1"}), d.flows.standard);
      show({asks, known: assigned(known), notes: wiz.assignmentView(known).map(
          (row) => [row.role_id, row.notes]), gate: gate(known),
        previous: wiz.previousAssignment(known), failed: assigned(failed),
        failed_previous: wiz.previousAssignment(failed)});
    """, DATA)
    assert out["asks"] == [
        ["read:run:task-b-r1", "previous_run", "run", "task-b-r1", None],
        ["read:revision:desk-standard:1", "previous_revision", "revision", "desk-standard",
         {"revision": 1}]]
    assert out["known"] == {"role-analyst": ["claude-code", "previous"],
                            "role-doer": ["codex", "previous"],
                            "role-tester": [None, None],
                            "role-checker": ["claude-code", "previous"]}
    assert ["role-tester", ["new_role"]] in out["notes"]
    assert out["gate"] == "roles_unassigned"
    assert out["previous"] == {"role-analyst": "claude-code", "role-doer": "codex",
                               "role-checker": "claude-code"}
    assert out["failed_previous"] is None
    assert {row[1] for row in out["failed"].values()} == {"suggestion"}


def test_a_role_the_owner_assigns_is_kept_and_only_an_offered_harness_is_accepted():
    out = run_js(ROLES + """
      const state = standardAt("desk-standard");
      const assign = (role_id, provider_id) => wiz.reduceWizard(state,
        {type: "role-assign", role_id, provider_id});
      const doer = assign("role-doer", "claude-code");
      show({owner: assigned(doer)["role-doer"], others_stay: assigned(doer)["role-analyst"],
        not_a_review_harness: assign("role-analyst", "grok-build") === state,
        unavailable: assign("role-doer", "kimi-code") === state,
        unknown_role: assign("role-nobody", "codex") === state,
        unknown_harness: assign("role-doer", "nobody") === state,
        cleared: assigned(run(doer, {type: "role-assign", role_id: "role-doer",
          provider_id: null}))["role-doer"],
        checker_avoids: assigned(doer)["role-checker"][0]});
    """, DATA)
    assert out["owner"] == ["claude-code", "owner"] and out["others_stay"][1] == "suggestion"
    assert all(out[key] for key in ("not_a_review_harness", "unavailable", "unknown_role",
                                    "unknown_harness"))
    assert out["cleared"][1] == "suggestion"
    assert out["checker_avoids"] == "codex"


def test_a_role_change_sends_the_binding_for_diagnostics_and_waits_for_the_write_in_flight():
    out = run_js(ROLES + """
      const state = standardAt("desk-standard");
      const first = flowAsk(state);
      const landed = land(state, flowOf(d.flows.standard));
      const changed = wiz.stepWizard(landed, {type: "role-assign", role_id: "role-doer",
        provider_id: "claude-code"});
      const again = wiz.stepWizard(changed.state, {type: "role-assign", role_id: "role-analyst",
        provider_id: "claude-code"});
      show({first: [first.body.binding, first.body.publish_revision, first.body.expected_digest],
        changed: changed.asks.map((ask) => [ask.name, ask.body.binding,
          ask.body.expected_digest, ask.body.publish_revision]),
        held: again.asks.length});
    """, DATA)
    assert out["first"] == [{"role-analyst": "codex", "role-doer": "codex",
                             "role-checker": "claude-code"}, None, "sha256:" + "b" * 64]
    assert out["changed"] == [["flow", {"role-analyst": "codex", "role-doer": "claude-code",
                                        "role-checker": "codex"}, "sha256:" + "b" * 64, None]]
    assert out["held"] == 0


def test_the_next_step_is_ready_only_with_every_role_assigned_and_every_instruction_filled():
    out = run_js(ROLES + """
      const noProviders = {...structuredClone(d.workflows), providers: []};
      const rows = [{code: "role_capability_unsupported", severity: "warning",
        at: {step_id: "do"}, params: {}}];
      const state = standardAt("desk-standard");
      show({no_providers: gate(atRoles({workflows: noProviders})),
        pending: gate(state), ready: gate(binding(state)),
        binding_rows: gate(binding(state, {diagnostics: rows})),
        refused: gate(answer(state, flowAsk(state), {status: "refused",
          code: "contract_invalid", payload: null})),
        last_step_next: wiz.nextStep(binding(state))});
    """, DATA)
    assert out["no_providers"] == "no_providers" and out["pending"] == "binding_pending"
    assert out["ready"] is None and out["binding_rows"] == "binding_rows"
    assert out["refused"] == "flow_refused"
    assert out["last_step_next"] is None


def test_the_roles_step_publishes_instructions_assignments_and_a_shared_instruction_choice():
    out = run_js(ROLES + """
      const base = structuredClone(d.flows.tester);
      const state = binding(run(standardAt("cycle-7c1e5a90", base),
        {type: "instruction-edit", step_id: "tester", text: "Test the login form."}), {}, base);
      const shared = binding(run(state, {type: "instruction-like", step_id: "tester",
        like: "do"}), {}, base);
      const roles = (one) => wiz.publications(one, "en").at(-1);
      show({own: roles(state), shared: roles(shared).writes.map((row) => row.target
        + ":" + (row.ref ?? "") + ":" + JSON.stringify(row.instruction_from ?? null))});
    """, DATA)
    own = out["own"]
    assert own["step"] == "roles"
    assert [(row["link"], row["target"], row.get("ref")) for row in own["writes"]] == [
        (5, "artifacts", "instruction-do"), (5, "artifacts", "instruction-tester"),
        (4, "runs", None)]
    assert own["writes"][1]["content"] == "Test the login form."
    assert own["writes"][0]["media_type"] == "text/markdown"
    assert set(own["writes"][2]["assignments"]) == {
        "role-analyst", "role-doer", "role-tester", "role-checker"}
    assert out["shared"] == ["artifacts:instruction-do:null", 'flow::{"tester":"do"}',
                             "runs::null"]
