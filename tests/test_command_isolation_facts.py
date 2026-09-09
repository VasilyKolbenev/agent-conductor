"""The three answers are told apart, and the table cannot drift from the code.

`isolation_facts` is the product's own statement of what it refuses before a
child starts, what it only notices afterwards, and what it does not isolate at
all. A statement like that is worth exactly as much as the checks under it, so
this module holds two kinds of guard.

The structural ones keep the table honest as a table: three categories and no
fourth, no duplicate name or sentence, and -- the load-bearing one -- every fact
naming code that actually exists, resolved by import. Prose about a guard drifts
from the guard; a claim that cannot survive its implementation being renamed is
a claim nobody can check.

The driven ones keep the two active categories from swapping places, which is
the error that would matter: a person told a condition is refused before the
spawn, when really the model ran first and the result was withheld afterwards,
has been told something false about what their machine did. One representative
of each is driven end to end here and the difference asserted where it shows --
in whether a child ran at all. Every individual protection keeps its own witness
in its own module; this asks only which side of the spawn it falls on.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest  # noqa: F401 -- parametrized cases below

from conductor.command.isolation_facts import (
    BY_CATEGORY,
    CATEGORIES,
    DETECTED_AFTER_SPAWN,
    ISOLATION_FACTS,
    NOT_ISOLATED,
    REFUSED_BEFORE_SPAWN,
    facts_as_dicts,
)

from tests import _fakeclaude
from tests.test_command_claude_transport import a_harness, a_request, run_once
from tests.test_command_instruction_binding import PREVIEWED, _arguments


def _fact(name: str):
    found = [row for row in ISOLATION_FACTS if row.name == name]
    assert len(found) == 1, f"expected exactly one fact named {name!r}"
    return found[0]


def test_the_table_has_three_answers_and_every_one_of_them_is_used():
    """A fourth category would be an answer nobody defined; an EMPTY third would
    be the lie this module exists to prevent.

    A build that listed only refusals and detections would be true line by line
    and false in shape: it would read as confinement to a person who was never
    told there is none.
    """
    assert set(CATEGORIES) == {
        REFUSED_BEFORE_SPAWN, DETECTED_AFTER_SPAWN, NOT_ISOLATED}
    assert {fact.category for fact in ISOLATION_FACTS} == set(CATEGORIES)
    for category in CATEGORIES:
        assert BY_CATEGORY[category], f"{category} claims nothing"
    assert len(BY_CATEGORY[NOT_ISOLATED]) >= 2


def test_no_two_facts_share_a_name_or_a_sentence():
    """Two rows saying the same thing are one row to a reader, and a duplicate
    name would make `_fact` above answer for the wrong claim."""
    names = [fact.name for fact in ISOLATION_FACTS]
    sentences = [fact.sentence for fact in ISOLATION_FACTS]

    assert len(set(names)) == len(names)
    assert len(set(sentences)) == len(sentences)
    assert sum(len(rows) for rows in BY_CATEGORY.values()) == len(ISOLATION_FACTS)


def test_every_claim_names_code_that_exists():
    """The anti-prose guard.

    A protection that is renamed or deleted takes its claim down with it, rather
    than leaving the product asserting a guard it no longer has. Resolved by
    import, so a path that merely looks plausible does not pass.
    """
    for fact in ISOLATION_FACTS:
        module_path, _, attribute = fact.implemented_by.rpartition(".")
        module = importlib.import_module(module_path)
        assert hasattr(module, attribute), (
            f"{fact.name} claims {fact.implemented_by}, which does not exist")


def test_the_readable_shape_carries_the_same_rows():
    """A screen may not show a grouping or a row the table does not hold."""
    rows = facts_as_dicts()

    assert len(rows) == len(ISOLATION_FACTS)
    assert {row["name"] for row in rows} == {f.name for f in ISOLATION_FACTS}
    assert {row["category"] for row in rows} <= set(CATEGORIES)
    assert all(set(row) == {"name", "category", "sentence", "implemented_by"}
               for row in rows)


def test_a_refused_before_spawn_fact_really_costs_no_child(tmp_path):
    """The claim is about TIMING, so it is asked where timing shows.

    `instruction_bytes_moved` says the run stops before the spawn. The proof is
    that no child ran at all -- not that the outcome was a failure, which a
    detection after the fact also produces.
    """
    from conductor.command.adapters.task_binding import content_digest
    from conductor.command.adapters.harness_workspace import INSTRUCTION_DIR

    assert _fact("instruction_bytes_moved").category == REFUSED_BEFORE_SPAWN
    adapter, root, log = a_harness(tmp_path, instruction=PREVIEWED)
    promised = content_digest(PREVIEWED)
    (root / INSTRUCTION_DIR / "instr-001.md").write_text(
        "Something else entirely.\n", encoding="utf-8", newline="\n")

    receipt = run_once(adapter, a_request(
        arguments=_arguments(instruction_digest=promised)))

    assert receipt.outcome == "failed", receipt.detail
    assert _fakeclaude.prompt_spawns(log) == [], (
        "a fact filed as refused-before-spawn let a child run")


def test_a_detected_after_spawn_fact_really_needed_the_child_to_run(
        tmp_path, monkeypatch):
    """And the other side of the same question.

    `profile_home_retained` is filed as a detection, and it has to be: the home
    cannot fail to go until after the attempt that minted it is over. So the
    child DID run, and what this build withheld is the verdict on top of the
    work -- which is a materially different sentence to tell an operator.
    """
    from conductor.command.adapters import harness_workspace
    from conductor.command.adapters.harness_profile import retained_detail

    assert _fact("profile_home_retained").category == DETECTED_AFTER_SPAWN
    adapter, _root, log = a_harness(tmp_path)
    real = harness_workspace.HarnessWorkspace.discard_home
    seen: list[int] = []

    def refuse(self, home):
        real(self, home)
        seen.append(1)
        # The TASK's own home, never the version probe's: a probe that could not
        # be discarded stops the dispatch before any task, which is the other
        # category and would prove the opposite of what this asks.
        if len(seen) == 2:
            raise OSError("this machine would not take the home back")

    monkeypatch.setattr(
        harness_workspace.HarnessWorkspace, "discard_home", refuse)

    receipt = run_once(adapter, a_request())

    assert len(_fakeclaude.prompt_spawns(log)) == 1, (
        "a fact filed as detected-after-spawn refused before the child ran")
    # Derived from the code that writes it rather than pinned as a phrase: a
    # substring would red on an honest rewording and pass on a wrong sentence
    # that happened to contain it.
    assert retained_detail(adapter.profile.tool_noun) in receipt.detail, (
        receipt.detail)


def _snapshot_after_writing(tmp_path, relative: str):
    """Run one dispatch whose child writes to `relative`, and hand back the pair.

    The child's working directory is its own work item, so the path is written
    from there -- which is how a test says "beside me, inside the tree" and
    "above the tree" with the same knob.
    """
    from conductor.command.adapters.headless_values import attempt_relation

    adapter, root, log = a_harness(
        tmp_path, **{_fakeclaude.WRITE_FILE: f"{relative}:written-by-child"})
    request = a_request()

    run_once(adapter, request)

    assert len(_fakeclaude.prompt_spawns(log)) == 1, "the child never ran"
    snapshot = adapter._attempts[attempt_relation(request)]
    return snapshot, root


def test_a_change_beside_the_work_item_inside_the_tree_is_observed(tmp_path):
    """The protection the table claims, driven where it holds.

    A neighbouring work item is inside `work/`, so the before/after comparison
    sees it. This is the positive control for the limit below: without it, the
    limit would read as "this build notices nothing".
    """
    snapshot, root = _snapshot_after_writing(tmp_path, "../work-002/beside.txt")

    assert (root / "work" / "work-002" / "beside.txt").is_file()
    assert snapshot.before != snapshot.after, (
        "a write inside the observed tree went unseen")


def test_a_change_above_the_work_tree_is_NOT_observed_and_the_table_says_so(
        tmp_path):
    """The limit, held as a fact rather than left to a reader's optimism.

    The child writes into the project root, above `work/`. The file really
    appears and the comparison does not move, because the walk starts at the
    work tree. A review found the table promising more than this, which is the
    kind of sentence that gets read as confinement -- so the claim now names the
    boundary and this holds it to that.
    """
    snapshot, root = _snapshot_after_writing(tmp_path, "../../above.txt")

    assert (root / "above.txt").is_file(), "the fixture proved nothing"
    assert snapshot.before == snapshot.after, (
        "the observation boundary moved; the table's sentence is now wrong")
    sentence = _fact("work_outside_the_item").sentence
    assert "`work/` and nothing above it" in sentence
    assert "may not be detected" in sentence


@pytest.mark.parametrize("name", [
    "scope_is_declarative", "no_operating_system_boundary",
    "vendor_sandbox_is_the_vendors"])
def test_the_absences_are_stated_as_absences(name):
    """The third category says what this build does NOT do, so its rows may not
    read as protections.

    Held over the words because that is where this particular failure happens:
    an absence rewritten in the grammar of a guarantee is how "declarative" ends
    up being read as "confined".
    """
    fact = _fact(name)

    assert fact.category == NOT_ISOLATED
    assert any(word in fact.sentence for word in
               ("does not", "no ", "not ", "cannot")), fact.sentence


def test_the_vendors_own_sandbox_is_a_per_provider_fact_this_module_will_not_name():
    """Whose mechanism it is, and whose question WHICH provider is.

    Saying "sandboxed" for a roster would be false for whichever member ships
    nothing, and saying nothing would hide a real protection another member runs
    under. So the row states the kind of promise and defers the roster -- which
    it must: this module is on the request path, where nothing may know a
    provider's name, and a table that hard-coded two vendors would also be a
    table to edit whenever the roster moved.
    """
    from conductor.command import isolation_facts
    from tests.test_alpha1_gate_g_provider_breadth import _identity_tokens

    sentence = _fact("vendor_sandbox_is_the_vendors").sentence

    assert "vendor's" in sentence and "not this build's" in sentence
    assert "none, nothing is claimed" in sentence
    # And the rule itself, held over the whole module rather than this one row:
    # a provider identity anywhere here is the request path learning a name.
    source = Path(isolation_facts.__file__).read_text(encoding="utf-8").lower()
    for token in _identity_tokens():
        assert token not in source, f"the request path learned {token!r}"


# -- the declared set, held equal to the implemented one, in both directions --


def _declaring_classes():
    """Every class in the adapters package that claims to run a named guard."""
    from conductor.command import adapters as package

    found = []
    for path in sorted(Path(package.__file__).resolve().parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                names = [target.id for target in statement.targets
                         if isinstance(target, ast.Name)]
                if "isolation_guards" not in names:
                    continue
                found.append((path.name, node.name, statement.value))
    return found


def _claimed_names(value):
    return [key.value for key in value.keys if isinstance(key, ast.Constant)]


def test_no_transport_claims_a_guard_this_table_does_not_hold():
    """A misspelling must not become "not a protection this configuration has".

    The standings turn an undeclared name into `not_applicable`, which is a
    MEASURED absence -- so a guard claimed under a name this table never held
    would quietly move every other row's meaning: the reader is told the
    integration looked and found nothing, when the integration named something
    that does not exist.
    """
    known = {fact.name for fact in ISOLATION_FACTS}

    for module, owner, value in _declaring_classes():
        for name in _claimed_names(value):
            assert name in known, f"{module}:{owner} claims unknown guard {name!r}"


def test_every_guard_this_table_states_is_claimed_by_some_transport():
    """The other direction, and it is the one that keeps `not_applicable` honest.

    `not_applicable` means "this build implements it, and not on this road". A
    row nothing in the tree claims cannot mean that: it is either a guard whose
    code was deleted, leaving the sentence behind, or a claim no transport was
    ever wired to make -- and both reach a person as a protection some OTHER
    configuration supposedly has.

    The two absences and the vendor's own row are excluded by name, not by
    filtering on a category: they are statements about what this build does NOT
    do, and no transport implements an absence.
    """
    claimed = {name for _module, _owner, value in _declaring_classes()
               for name in _claimed_names(value)}
    stated = {fact.name for fact in ISOLATION_FACTS
              if fact.category != NOT_ISOLATED}

    assert stated == claimed, (
        "declared and implemented have drifted: "
        f"unclaimed={sorted(stated - claimed)} unstated={sorted(claimed - stated)}")


def test_a_dispatch_only_transport_does_not_inherit_the_checkers_measurement(
        tmp_path):
    """Inheriting a method's NAME is not carrying its road.

    `ArtifactAwareTransport.__init_subclass__` sets `verify_for` to None for a
    transport that serves no review road. The class still has the attribute, and
    a declaration read off the class body alone would hand that transport the
    checker's own login measurement -- a claim it cannot keep. The registration
    is what answers, because the registration is what knows which seams this
    adapter really registered.
    """
    from conductor.command.adapters import AdapterRegistry
    from tests.test_command_dsh_harness import a_harness

    adapter, _root, _log = a_harness(tmp_path)
    registry = AdapterRegistry([adapter])
    adapter_id = adapter.manifest.adapter_id

    guards = registry.isolation_guards(adapter_id)

    assert adapter.verify_for is None, "this fixture is no longer dispatch-only"
    assert "login_directory_gained_state" not in guards
    # And it keeps every guard it CAN make, so this is a strike and not a mute.
    assert "uncontained_route" in guards
    # A road it does not serve is struck too: `review` is not in its manifest.
    assert all("review" not in roads for roads in guards.values()), guards
