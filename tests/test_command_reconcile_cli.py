"""Reconcile as an operation an operator can actually reach.

`ControlRuntime.reconcile` has existed since the durable-core slice, and ADR
0002 sent the operator straight to it. Two things made that unusable, and both
are what this module holds.

**It could not be found.** `reconcile` takes a run id and an action id, and
nothing in the product would ever say what they were. A durable request with no
effect lease writes no message, changes no exit code and appears in no listing;
finding one meant reading `records.jsonl` and replaying the causality rules by
eye. `survey` answers it, and the test below proves the answer is the runtime's
own by driving a real stuck action into a real store and then closing exactly
what the listing named.

**It could not be run.** The ADR printed a three-line snippet that raises
`TypeError`: `ControlRuntime(RunStore(project_root))` supplies one argument
where the constructor requires `registry` positionally and `clock` and `ids` as
keyword-only. The documented recovery had never been executed. `close` is that
call spelled correctly, and `test_the_documented_recovery_runs_as_written`
executes the ADR's snippet itself rather than trusting its prose.

What is deliberately NOT re-tested here: every refusal `reconcile` holds. Those
belong to `tests/test_command_runtime_reconcile.py` and are asked of the runtime
directly. This module's whole claim is about REACH -- that the operation can be
found and invoked without a Python prompt -- so it drives the CLI's own entry
point and asserts on exit codes and streams.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from conductor import __main__ as cli
from conductor.command import reconcile
from conductor.command.runtime import ControlRuntime, ExecutionError

from tests.test_command_runtime_authorize import a_store
from tests.test_command_runtime_execute import ScriptedAdapter, authorized

ADR = Path(__file__).resolve().parents[1] / "docs" / "adr" / \
    "0002-command-run-identity-and-store.md"


def a_project(tmp_path):
    """A real project root whose run store holds one request-only action."""
    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)
    store = a_store(root)
    _, authorization = authorized(store, ScriptedAdapter())
    return root, store, authorization


def test_the_survey_names_the_action_a_crash_stranded_and_nothing_else(tmp_path):
    """The listing is the runtime's three questions, not a fourth opinion.

    A request-only action is the whole target: a durable request, no attempt
    event, no terminal. An action that reached any of those belongs to
    `execute`'s recovery roads, and naming it here would send an operator to an
    operation that will refuse it.
    """
    root, store, authorization = a_project(tmp_path)
    action_id = authorization.request.action_id

    rows = dict(reconcile.survey(root))

    assert rows == {"run-001": (action_id,)}


def test_an_action_that_already_ended_is_not_offered_for_reconcile(tmp_path):
    """The other side of the same question, so the survey is not just permissive.

    Without this, a survey that named every action it found would pass the test
    above and send an operator to a refusal for every finished action in the
    project.
    """
    root, store, authorization = a_project(tmp_path)
    action_id = authorization.request.action_id
    assert dict(reconcile.survey(root))["run-001"] == (action_id,)

    reconcile.close(root, "run-001", action_id)

    assert dict(reconcile.survey(root))["run-001"] == ()


def test_the_cli_closes_exactly_the_action_its_own_listing_named(tmp_path, capsys):
    """The two halves are one road: what is listed is what can be closed.

    A listing that named an id the closing road would refuse, or a closing road
    that took an id no listing could produce, would each leave the operator
    exactly where the Python API left them.
    """
    root, store, authorization = a_project(tmp_path)

    assert cli.main(["reconcile", "--dir", str(root)]) == 0
    listed = capsys.readouterr().out.split()
    assert len(listed) == 2, listed
    run_id, action_id = listed

    assert cli.main(["reconcile", "--dir", str(root),
                     "--run", run_id, "--action", action_id]) == 0
    receipt = json.loads(capsys.readouterr().out)

    assert receipt["outcome"] == "unknown"
    assert receipt["action_id"] == action_id
    assert receipt["run_id"] == run_id
    assert receipt["exit_code"] is None


def test_a_clean_project_says_so_on_stderr_and_leaves_stdout_empty(tmp_path, capsys):
    """Nothing to reconcile is a legitimate answer, and it is not a failure.

    stdout carries only the primary result, which is a list of ids; an operator
    piping it must receive an empty document rather than a sentence.
    """
    root = tmp_path / "project"
    (root / "conductor").mkdir(parents=True)

    assert cli.main(["reconcile", "--dir", str(root)]) == 0

    streams = capsys.readouterr()
    assert streams.out == ""
    assert "no action in this project is waiting for reconcile" in streams.err


def test_half_a_reference_is_refused_rather_than_guessed(tmp_path, capsys):
    """A run with no action and an action of no run are both unanswerable.

    Filling in the other half is the one thing a recovery command must not do:
    the whole operation is closing a specific durable action, and closing a
    guessed one is exactly the harm reconcile's refusals exist to prevent.
    """
    root, _, authorization = a_project(tmp_path)

    assert cli.main(["reconcile", "--dir", str(root), "--run", "run-001"]) == 1
    assert "--action is missing" in capsys.readouterr().err

    assert cli.main(["reconcile", "--dir", str(root),
                     "--action", authorization.request.action_id]) == 1
    assert "--run is missing" in capsys.readouterr().err


def test_a_refusal_the_runtime_holds_reaches_stderr_with_exit_one(tmp_path, capsys):
    """The CLI adds no permission: a refusal below it is a refusal at the top.

    Closing the same action twice is the cheapest of reconcile's own refusals to
    reach, and it proves the command reports rather than swallows one.
    """
    root, _, authorization = a_project(tmp_path)
    action_id = authorization.request.action_id
    assert cli.main(["reconcile", "--dir", str(root),
                     "--run", "run-001", "--action", action_id]) == 0
    capsys.readouterr()

    assert cli.main(["reconcile", "--dir", str(root),
                     "--run", "run-001", "--action", action_id]) == 1

    streams = capsys.readouterr()
    assert streams.out == ""
    assert "already has a terminal result" in streams.err


def test_a_directory_that_is_not_a_project_is_refused_before_anything_writes(
        tmp_path, capsys):
    """`reconcile` joins the commands that may not conjure a project.

    Without this the command would reach `RunStore`, whose `runs_root.mkdir(
    parents=True)` creates `conductor/` as a side effect -- the exact first-hour
    defect `preview` and `integration-smoke` were fixed for.
    """
    bare = tmp_path / "not-a-project"
    bare.mkdir()

    assert cli.main(["reconcile", "--dir", str(bare)]) == 1

    assert "run `conduct init`" in capsys.readouterr().err
    assert list(bare.iterdir()) == []


def test_the_documented_recovery_runs_as_written(tmp_path):
    """The ADR's snippet is executed, not read.

    It used to raise `TypeError` before reconcile was reached:
    `ControlRuntime(RunStore(project_root))` names one argument where the
    constructor requires three. A procedure that has never been run is a
    procedure nobody has checked, and this is the only recovery the product
    documents for this state.
    """
    root, _, authorization = a_project(tmp_path)
    snippet = re.search(r"\n(    from conductor.*?)\n\n", ADR.read_text(
        encoding="utf-8"), re.DOTALL)
    assert snippet is not None, "ADR 0002 no longer carries a recovery snippet"
    source = "\n".join(line[4:] for line in snippet.group(1).splitlines())

    namespace = {"project_root": root, "run_id": "run-001",
                 "action_id": authorization.request.action_id}
    exec(compile(source, str(ADR), "exec"), namespace)  # noqa: S102 - the point

    assert namespace["receipt"].outcome == "unknown"
    assert dict(reconcile.survey(root))["run-001"] == ()


def test_the_adr_no_longer_says_the_operation_has_no_subcommand(tmp_path):
    """The prose and the parser must agree about what this build ships.

    Derived from the parser rather than matched against a sentence, so adding
    the verb and forgetting the document reds, and so does the reverse.
    """
    verbs = set(cli._build_parser()._subparsers._group_actions[0].choices)
    text = ADR.read_text(encoding="utf-8")

    assert "reconcile" in verbs
    assert "There is no `conduct reconcile` subcommand" not in text
    assert "conduct reconcile" in text
