"""The rules of a flow and the address of each fault (spec 7.4, 7.11 item 2).

One minimal flow per code shows the code raised at its own address. The property that carries the
design is checked on mutations of an extension-free corpus: whatever the mutation, the address
rules leave nothing for the real constructor to refuse, and no row points at a step or a road that
does not exist.
"""
import copy
import json
from pathlib import Path

import pytest

from conductor.command import flow_rules as rules
from conductor.command.flow_rules import FLOW_CODES, flow_rules
from conductor.command.graph_template_document import GraphTemplate
from conductor.command.plan_budget import plan_budget
from conductor.command.workflow_flow import (
    KIND_TITLES, LINK_WHEN, compile_flow, import_template, settled_flow)
from tests.test_command_plan_budget import LIMITS, dispatch, with_loops
from tests.test_command_workflow_flow import (
    CANONICAL, CYCLES, canonical_flow, chain, fixture_flow, review, step)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "flow"
TOP = {"step_id": "plan"}


def build(flow):
    """The template a compiled flow makes, or None when the core refuses it."""
    try:
        return GraphTemplate.from_dict(
            {**compile_flow(flow), "template_id": "cycle-test", "revision": 1})
    except Exception:  # noqa: BLE001 -- any refusal at all means "not buildable"
        return None


def budget_of(flow, limits=LIMITS):
    template = build(flow)
    assert template is not None, "the flow of a budget case must build"
    return plan_budget(*template.settled(), limits)


def rows_of(flow, **asked):
    return flow_rules(flow, **asked)


def codes(rows):
    return [row["code"] for row in rows]


def good():
    return chain(review("plan"), dispatch("do"), step("result", "human"))


def errors_of(rows):
    return [row for row in rows if row["severity"] == "error"]


def test_a_flow_that_breaks_no_rule_raises_no_row():
    assert rows_of(good()) == []
    assert rows_of(good(), budget=budget_of(good())) == []


def test_every_row_has_the_four_keys_and_the_severity_of_its_code():
    flow = good()
    flow["steps"][1]["verifier_role_id"] = None
    for row in rows_of(flow):
        assert list(row) == ["code", "severity", "at", "params"]
        assert row["severity"] == FLOW_CODES[row["code"]]
    assert set(FLOW_CODES.values()) == {"error", "warning"}


def test_the_role_kinds_of_the_capability_table_are_the_kinds_the_titles_name():
    assert set(rules.CAPABILITY_OF_KIND) == set(KIND_TITLES)


# --- one minimal flow per code, at its own address ---------------------------------------------


def mutated(flow, change):
    change(flow)
    return flow


def case_flow_invalid():
    flow = good()
    flow["steps"][0]["bogus"] = 1
    return rows_of(flow), TOP


def case_id_invalid():
    flow = mutated(good(), lambda f: (f["steps"][2].update(step_id="bad id!"),
                                      f["links"][1].update(to="bad id!")))
    return rows_of(flow), {"step_id": "bad id!"}


def case_id_repeated():
    flow = mutated(good(), lambda f: f["steps"].append(review("plan")))
    return rows_of(flow), TOP


def case_step_id_reserved():
    flow = chain(review("brief"), step("result", "human"))
    return rows_of(flow), {"step_id": "brief"}


def case_text_invalid():
    flow = mutated(good(), lambda f: f["steps"][1].update(title="two\nlines"))
    return rows_of(flow), {"step_id": "do"}


def case_ref_unknown():
    flow = mutated(good(), lambda f: f["links"].append(
        {"from": "do", "to": "ghost", "when": "success"}))
    return rows_of(flow), {"link": ["do", "ghost", "success"]}


def case_when_invalid():
    flow = mutated(good(), lambda f: f["links"][1].update(when="approved"))
    return rows_of(flow), {"link": ["do", "result", "approved"]}


def case_link_makes_cycle():
    flow = mutated(good(), lambda f: f["links"].append(
        {"from": "do", "to": "plan", "when": "success"}))
    return rows_of(flow), {"link": ["do", "plan", "success"]}


def case_ext_invalid():
    flow = mutated(good(), lambda f: f["steps"][1]["ext"].update(arguments=5))
    return rows_of(flow), {"step_id": "do"}


def case_dispatch_without_checker():
    flow = mutated(good(), lambda f: f["steps"][1].update(verifier_role_id=None))
    return rows_of(flow), {"step_id": "do"}


def case_checker_is_doer():
    flow = mutated(good(), lambda f: f["steps"][1].update(verifier_role_id="role-doer"))
    return rows_of(flow), {"step_id": "do"}


def case_dead_join():
    join = dispatch("join")
    flow = {"flow_version": 1, "title": "Branches", "ext": {}, "steps": [
        step("decide", "human"), review("a"), review("b", role_id="role-reviewer"), join,
        step("result", "human")], "links": [
        {"from": "decide", "to": "a", "when": "approved"},
        {"from": "decide", "to": "b", "when": "rejected"},
        {"from": "a", "to": "join", "when": "success"},
        {"from": "b", "to": "join", "when": "success"},
        {"from": "join", "to": "result", "when": "success"}]}
    return rows_of(flow), {"step_id": "join"}


def case_final_gate_missing():
    return rows_of(chain(review("plan"), dispatch("do"))), None


def case_dispatch_not_accepted():
    flow = mutated(good(), lambda f: f["links"][1].update(when="failed"))
    return rows_of(flow), {"step_id": "do"}


def case_loop_body_empty():
    flow = mutated(good(), lambda f: (
        f["steps"].append(step("fix", "loop", back_to="result", bound=2)),
        f["links"].append({"from": "do", "to": "fix", "when": "failed"})))
    return rows_of(flow), {"step_id": "fix"}


def case_gate_before_dispatch():
    flow = mutated(good(), lambda f: f["ext"].update(execution_contract=None))
    return rows_of(flow), {"step_id": "do"}


def case_instruction_from_invalid():
    flow = mutated(good(), lambda f: f["steps"][1].update(instruction_from="plan"))
    return rows_of(flow), {"step_id": "do"}


def case_reads_invalid():
    flow = mutated(good(), lambda f: f["steps"][1].update(reads=["result"]))
    return rows_of(flow), {"step_id": "do"}


def case_bound_range():
    flow = mutated(good(), lambda f: (
        f["steps"].append(step("fix", "loop", back_to="do", bound=0)),
        f["links"].append({"from": "do", "to": "fix", "when": "failed"})))
    return rows_of(flow), {"step_id": "fix"}


def case_timeout_range():
    flow = mutated(good(), lambda f: f["steps"][1].update(timeout_seconds=100000))
    return rows_of(flow), {"step_id": "do"}


def case_clean_over_actions():
    flow = chain(*[review(f"r{n}") for n in range(9)], step("result", "human"))
    return rows_of(flow, budget=budget_of(flow)), None


def case_clean_over_time():
    flow = fixture_flow("desk-standard")
    tight = {**LIMITS, "max_total_task_seconds": 1000}
    return rows_of(flow, budget=budget_of(flow, tight)), None


def case_template_refused():
    flow = chain(step("first", "human", ext={"gate_id": "gate-same"}),
                 step("second", "human", ext={"gate_id": "gate-same"}))
    flow["links"][0]["when"] = "approved"
    return rows_of(flow), None


def case_contract_refused():
    document = {**compile_flow(good()), "title": ""}  # a document the address rules never saw
    return rows_of(good(), doc=document), None


def case_worst_over_actions():
    flow = fixture_flow("dalio-v5")
    return rows_of(flow, budget=budget_of(flow)), None


def case_worst_over_time():
    flow = fixture_flow("desk-standard")
    tight = {**LIMITS, "max_total_task_seconds": 5500}
    return rows_of(flow, budget=budget_of(flow, tight)), None


def case_timeout_clamped():
    flow = mutated(good(), lambda f: f["steps"][1].update(timeout_seconds=3000))
    return rows_of(flow, budget=budget_of(flow)), {"step_id": "do"}


def case_review_after_dispatch():
    flow = chain(dispatch("do"), review("look"), step("result", "human"))
    return rows_of(flow), {"step_id": "look"}


def case_role_kind_mismatch():
    flow = mutated(good(), lambda f: f["steps"][0].update(role_id="role-doer"))
    return rows_of(flow), TOP


def case_link_outside_desk():
    flow = mutated(good(), lambda f: f["links"][0].update(when="always"))
    return rows_of(flow), {"link": ["plan", "do", "always"]}


def case_fork_failure_stops():
    flow = chain(review("plan"), review("left", role_id="role-reviewer"),
                 step("result", "human"))
    flow["steps"].append(review("right", role_id="role-designer"))
    flow["links"].append({"from": "plan", "to": "right", "when": "success"})
    return rows_of(flow), TOP


def case_loop_order():
    return rows_of(fixture_flow("dalio-v5")), {"step_id": "correct"}


def case_rework_after_correction():
    return rows_of(fixture_flow("dalio-v5")), {"step_id": "do"}


def case_return_after_correction():
    return rows_of(fixture_flow("desk-standard-tester")), {"step_id": "do"}


def binding_of(**changes):
    every = {"role-analyst": {"capabilities": ["review"], "verifies": False},
             "role-doer": {"capabilities": ["dispatch"], "verifies": False},
             "role-checker": {"capabilities": ["review"], "verifies": True}}
    return {**every, **changes}


def case_role_unassigned():
    return rows_of(good(), binding={"role-doer": binding_of()["role-doer"],
                                    "role-checker": binding_of()["role-checker"]}), TOP


def case_role_capability_unsupported():
    unsupported = {"capabilities": ["dispatch"], "verifies": False}
    return rows_of(good(), binding=binding_of(**{"role-analyst": unsupported})), TOP


def case_checker_cannot_verify():
    silent = {"capabilities": ["review"], "verifies": False}
    return rows_of(good(), binding=binding_of(**{"role-checker": silent})), {"step_id": "do"}


CASES = {name[len("case_"):]: value for name, value in dict(globals()).items()
         if name.startswith("case_")}


def test_there_is_one_case_for_every_flow_code_and_for_nothing_else():
    assert set(CASES) == set(FLOW_CODES)


@pytest.mark.parametrize("code", sorted(FLOW_CODES))
def test_every_flow_code_is_raised_by_its_own_form_at_its_own_address(code):
    rows, at = CASES[code]()
    raised = [row for row in rows if row["code"] == code]
    assert raised, f"{code} was not raised; rows: {codes(rows)}"
    assert any(row["at"] == at for row in raised), [row["at"] for row in raised]
    assert all(row["severity"] == FLOW_CODES[code] for row in raised)


def test_a_flow_the_form_refuses_answers_one_row_and_nothing_else():
    flow = good()
    flow["steps"][1]["ext"] = {"speed": 1}
    rows = rows_of(flow)
    assert codes(rows) == ["flow_invalid"] and rows[0]["at"] == {"step_id": "do"}
    assert rows[0]["params"] == {"path": "flow.steps[1].ext.speed"}
    assert codes(rows_of("not a flow")) == ["flow_invalid"]
    assert rows_of("not a flow")[0]["at"] is None


def test_a_step_refused_alone_is_addressed_to_that_step():
    flow = good()
    flow["steps"][1]["ext"] = {"arguments": 5}
    rows = rows_of(flow)
    assert [(row["code"], row["at"], row["params"]) for row in rows] == [
        ("ext_invalid", {"step_id": "do"}, {"field": "arguments"})]


def test_a_step_refused_for_more_than_one_key_names_no_single_field():
    flow = good()
    flow["steps"][1]["ext"] = {"arguments": 5, "resources": 6}
    rows = rows_of(flow)
    assert [(row["code"], row["params"]) for row in rows] == [("ext_invalid", {})]


@pytest.mark.parametrize("word", ["success", "failed"])
def test_a_road_repeated_between_the_same_two_steps_is_addressed_to_the_repeat(word):
    flow = good()
    flow["links"].append({"from": "plan", "to": "do", "when": word})
    raised = [(row["code"], row["at"]) for row in rows_of(flow)]
    assert ("id_repeated", {"link": ["plan", "do", word]}) in raised


def test_a_fault_already_named_is_not_named_again_as_a_refused_step():
    flow = good()
    flow["steps"][1].update(timeout_seconds=100000, verifier_role_id="role-doer")
    assert sorted(codes(rows_of(flow))) == ["checker_is_doer", "timeout_range"]


def test_binding_rows_are_asked_for_only_when_a_binding_is_given():
    assert codes(rows_of(good())) == []
    assert codes(rows_of(good(), binding={})) == ["role_unassigned"] * 3
    assert codes(rows_of(good(), binding=binding_of())) == []


def test_rules_leave_the_flow_and_the_document_they_were_given_alone():
    flow = fixture_flow("dalio-v5")
    document = compile_flow(flow)
    before = copy.deepcopy((flow, document))
    flow_rules(flow, document, {}, budget_of(flow))
    assert (flow, document) == before


def state_of(cycle):
    return json.loads((FIXTURES / f"{cycle}.flow-state.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("cycle", CYCLES)
def test_the_fixture_diagnostics_are_what_the_rules_say(cycle):
    state = state_of(cycle)
    rows = rows_of(state["flow"], budget=state["budget"])
    assert rows == state["diagnostics"]
    assert state["publishable"] is (not errors_of(rows))


def test_dalio_copy_is_publishable_with_exactly_its_five_warning_codes():
    flow = import_template(GraphTemplate.from_dict(json.loads(
        (Path(rules.__file__).parent / "templates" / "dalio-v5.json").read_text(
            encoding="utf-8"))).as_dict())
    rows = rows_of(flow, budget=budget_of(flow))
    assert errors_of(rows) == []
    assert set(codes(rows)) == {"link_outside_desk", "loop_order", "rework_after_correction",
                                "worst_over_actions", "worst_over_time"}


# --- what the rules leave for the constructor --------------------------------------------------

ANY_WORD = tuple(LINK_WHEN)


def flows_of_the_corpus():
    corpus = {**CANONICAL, "canonical": canonical_flow()}
    corpus.update({cycle: fixture_flow(cycle) for cycle in CYCLES if cycle != "dalio-v5"})
    return corpus


def each_mutation(flow):
    """Small breakages of one extension-free flow: every one is a flow a person could draw."""
    steps, links = flow["steps"], flow["links"]
    for number in range(len(links)):
        yield f"drop link {number}", lambda f, n=number: f["links"].pop(n)
        yield f"repeat link {number}", lambda f, n=number: f["links"].append(dict(f["links"][n]))
        yield f"reverse link {number}", lambda f, n=number: f["links"][n].update(
            {"from": f["links"][n]["to"], "to": f["links"][n]["from"]})
        for word in ANY_WORD:
            yield f"link {number} says {word}", lambda f, n=number, w=word: f["links"][n].update(
                when=w)
    for number, row in enumerate(steps):
        yield f"drop step {number}", lambda f, n=number: f["steps"].pop(n)
        yield f"rename step {number} as the first", lambda f, n=number: f["steps"][n].update(
            step_id=f["steps"][0]["step_id"])
        yield f"link {number} to itself", lambda f, n=number: f["links"].append(
            {"from": f["steps"][n]["step_id"], "to": f["steps"][n]["step_id"], "when": "success"})
        yield f"link the last step to {number}", lambda f, n=number: f["links"].append(
            {"from": f["steps"][-1]["step_id"], "to": f["steps"][n]["step_id"],
             "when": "success"})
        if row["type"] == "agent":
            yield f"no checker {number}", lambda f, n=number: f["steps"][n].update(
                verifier_role_id=None)
            yield f"own checker {number}", lambda f, n=number: f["steps"][n].update(
                verifier_role_id=f["steps"][n]["role_id"])
            yield f"other capability {number}", lambda f, n=number: f["steps"][n].update(
                capability="review" if f["steps"][n]["capability"] == "dispatch"
                else "dispatch")
            yield f"reads the last {number}", lambda f, n=number: f["steps"][n].update(
                reads=[f["steps"][-1]["step_id"]])
            yield f"instructed by the first {number}", lambda f, n=number: f["steps"][n].update(
                instruction_from=f["steps"][0]["step_id"])
        if row["type"] == "loop":
            yield f"loop {number} home to itself", lambda f, n=number: f["steps"][n].update(
                back_to=f["steps"][n]["step_id"])
            yield f"loop {number} home to the last", lambda f, n=number: f["steps"][n].update(
                back_to=f["steps"][-1]["step_id"])
            yield f"loop {number} bound 0", lambda f, n=number: f["steps"][n].update(bound=0)
            yield f"loop {number} bound 100", lambda f, n=number: f["steps"][n].update(bound=100)
    yield "no execution contract", lambda f: f["ext"].update(execution_contract=None)


def every_mutant():
    for name, base in flows_of_the_corpus().items():
        for change_name, change in each_mutation(base):
            flow = copy.deepcopy(base)
            change(flow)
            yield f"{name}: {change_name}", flow


MUTANTS = list(every_mutant())


def addresses_exist(flow, rows):
    ids = {row["step_id"] for row in flow["steps"]}
    roads = {(link["from"], link["to"], link["when"]) for link in flow["links"]}
    for row in rows:
        at = row["at"]
        assert at is None or ("step_id" in at and at["step_id"] in ids) or (
            "link" in at and tuple(at["link"]) in roads), (row, "points at nothing")


def test_the_corpus_is_large_enough_to_mean_something():
    assert len(MUTANTS) > 1000


def test_clean_rules_imply_a_clean_constructor_on_the_extension_free_corpus():
    unaddressed = []
    for name, flow in MUTANTS:
        rows = rows_of(flow)
        addresses_exist(flow, rows)
        if {"template_refused", "contract_refused"} & set(codes(rows)):
            unaddressed.append((name, codes(rows)))
        if not errors_of(rows):
            assert build(flow) is not None, name
    assert unaddressed == [], f"the constructor refused what no rule addressed: {unaddressed[:5]}"


def test_the_corpus_of_mutants_reaches_most_of_the_codes_it_is_meant_to_exercise():
    seen = set()
    for _, flow in MUTANTS:
        seen |= set(codes(rows_of(flow)))
    assert {"ref_unknown", "when_invalid", "link_makes_cycle", "dispatch_without_checker",
            "checker_is_doer", "instruction_from_invalid", "reads_invalid", "bound_range",
            "loop_body_empty", "gate_before_dispatch", "id_repeated", "dead_join",
            "dispatch_not_accepted", "final_gate_missing"} <= seen


def test_settled_flows_only_reach_the_rules():
    assert all(settled_flow(flow) == flow for _, flow in MUTANTS[:50])
