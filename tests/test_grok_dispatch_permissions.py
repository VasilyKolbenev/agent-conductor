"""Grok's dispatch road may change files, and no other road or permission grows (spec 10.2).

Measured live on 28.09.2026 (live-grok-2): a headless Grok run without auto-approval denies the
Edit and Write tools, so a dispatch ended "no changed file". The ruling is narrow: the dispatch
argv, and only it, gains ``--allow Edit --allow Write``. Shell stays gated, there is no yolo or
bypass flag, the prompt stays the last token, and the version preflight and the account
exchange keep the argv they had.

Two kinds of witness, neither of them alone enough:

- the argv, read off the spec the adapter built (the only place the whole command exists);
- the behaviour, through a fake that denies a write unless the argv allows it, as the pinned
  guide says the real binary does (``tests/_fakegrok.py``). The control runs the same task with
  the flags removed and shows the fake really denies, so the behavioural witness cannot pass
  just because the fake never gated anything.

No live run is made here: the one live dispatch that edits a file waits for the owner's window.
"""
from __future__ import annotations

from conductor.command.adapters.artifact_transport import ArtifactAwareTransport
from conductor.command.adapters.grok_build import (
    GROK_AUTH_RPC,
    GROK_QUOTA_RPC,
    GrokBuildAdapter,
)

from tests import _fakegrok
from tests.test_command_grok_transport import _recorded, a_harness, a_request, run_once

#: The only tool names a Grok dispatch may be told to allow (case-sensitive in the vendor).
ALLOWED = ("Edit", "Write")
#: Spellings of a wider grant. None may stand in a dispatch argv.
WIDER = ("bash", "yolo", "bypass", "dangerous", "auto-approve", "permission", "sandbox")


def _dispatch_argv(tmp_path) -> tuple[str, ...]:
    adapter, runner, _exe = _recorded(tmp_path)
    assert run_once(adapter, a_request()).outcome == "succeeded"
    return tuple(runner.specs[1].argv)  # type: ignore[attr-defined]


def test_the_grok_dispatch_argv_allows_edit_and_write_and_keeps_the_prompt_last(tmp_path):
    argv = _dispatch_argv(tmp_path)

    flags = argv[1:-2]  # between the pinned binary and ``--single <prompt>``
    assert flags == ("--no-auto-update", "--output-format", "plain",
                     "--allow", "Edit", "--allow", "Write")
    assert argv[-2] == "--single"
    assert sorted(_fakegrok.allowed_tools(list(argv))) == sorted(ALLOWED)


def test_the_grok_dispatch_argv_grants_nothing_wider_than_edit_and_write(tmp_path):
    argv = _dispatch_argv(tmp_path)

    for token in argv[1:-1]:  # the prompt text is the operator's own words, not a grant
        assert not any(word in token.lower() for word in WIDER), f"WIDER_GRANT={token}"
    assert argv.count("--allow") == len(ALLOWED)


def test_the_version_preflight_and_the_account_exchange_carry_no_permission_flag(tmp_path):
    adapter, runner, exe = _recorded(tmp_path)
    run_once(adapter, a_request())

    assert tuple(runner.specs[0].argv) == (str(exe), "--version")  # type: ignore[attr-defined]
    for exchange in (GROK_AUTH_RPC, GROK_QUOTA_RPC):
        assert exchange.argv == ("--no-auto-update", "agent", "stdio")
        assert "--allow" not in exchange.argv


def test_grok_still_declares_no_review_road_so_no_review_argv_could_grow_an_allow():
    assert GrokBuildAdapter.review_enabled is False
    assert GrokBuildAdapter._review_argv is ArtifactAwareTransport._review_argv


def test_a_dispatch_through_the_denying_fake_changes_the_file_it_was_told_to(tmp_path):
    adapter, root, log = a_harness(tmp_path, FAKEGROK_WRITE_FILE="guard.py:# a real change\n")
    request = a_request()

    receipt = run_once(adapter, request)
    verification = adapter.verify(request, receipt)

    written = root / "work" / "work-001" / "guard.py"
    assert written.read_text(encoding="utf-8") == "# a real change\n"
    assert "file(s) changed" in verification.detail
    assert len(_fakegrok.prompt_spawns(log)) == 1


def test_the_same_dispatch_without_the_allow_flags_changes_nothing_in_the_fake(tmp_path):
    """The control: the fake denies, so the test above is not vacuous."""

    class NoPermissions(GrokBuildAdapter):
        def _task_argv(self, task_text):  # the pre-ruling argv, flags removed
            return ("--no-auto-update", "--output-format", "plain", "--single", task_text)

    adapter, root, log = a_harness(tmp_path, FAKEGROK_WRITE_FILE="guard.py:# a real change\n")
    denied = NoPermissions(adapter._pin, adapter._runner, root=root,
                           clock=adapter._clock, ids=adapter._ids)
    request = a_request()

    receipt = run_once(denied, request)
    verification = denied.verify(request, receipt)

    assert not (root / "work" / "work-001" / "guard.py").exists()
    assert "changed nothing" in verification.detail
    assert "--allow" not in _fakegrok.prompt_spawns(log)[0]["argv"]
