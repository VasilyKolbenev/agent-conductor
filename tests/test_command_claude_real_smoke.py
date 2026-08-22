"""OPT-IN smoke against a REAL Claude Code install. Skips honestly; never fakes a pass.

Nothing here runs unless an operator points it at a real install, and nothing
installs, downloads or searches for anything. A missing install is an honest
skip, never a success:

    CONDUCT_CLAUDE_EXECUTABLE   absolute path to the claude binary

The prompt smoke needs one more opt-in and a real key, because it spends a real
model call. The key NAME is the vendor's own documented shell channel, and in
bare mode -- which this transport always uses -- it is the ONLY channel: Claude
Code reads no OAuth credential and no keychain under ``--bare``.

    CONDUCT_CLAUDE_REAL_PROMPT=1
    CONDUCT_CLAUDE_KEY_NAME     the env NAME holding the key, itself set
                                (``ANTHROPIC_API_KEY`` unless a deployment
                                renames it)

**Two things this file settles that nothing else can.**

The VERSION FORM. This adapter parses a form no source states and no binary
here printed: two Anthropic issue templates describe ``2.1.239 (Claude Code)``
under "Run ``claude --version`` and paste the output", and that is the whole of
the evidence -- vendor-described, locally unobserved. Every other provider in
this roster had either readable source or an observed print. So the version
smoke is not a formality here: it is the first contact between this parser and
the thing it was written for. It does NOT assert the installed build is the
reviewed one -- an operator may legitimately have another, and the adapter's
correct answer then is to refuse -- it asserts the RELATION between what the
real binary prints and what the adapter decides, and it says which of the two
possible refusals happened.

The FAR SIDE OF THE PIPE. The runner can report that a payload was written,
flushed and ended on the parent's side; no parent can see whether the child read
it. Below the operating system's pipe buffer the two are indistinguishable. So
the prompt smoke asks a real Claude Code for something it could only know from
what was piped: a marker that appears in the instruction and NOWHERE in argv,
the environment or the working directory. An answer carrying it is the only
evidence this build can obtain that the far side of the channel works.

Everything the module reaches the child through goes via the production
retention path; ``tests/test_real_smoke_retention.py`` guards that with tests
that cannot skip.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from conductor.command.adapters.claude_code import (
    CLAUDE_PROTOCOL,
    CLAUDE_PROVIDER_ID,
    HOME_DIR,
    MARKER_DIR,
    REVIEWED_CLAUDE_VERSION,
)
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers

from tests.test_command_claude_transport import NOW, _Ids, a_request

EXECUTABLE_ENV = "CONDUCT_CLAUDE_EXECUTABLE"
PROMPT_ENV = "CONDUCT_CLAUDE_REAL_PROMPT"
KEY_NAME_ENV = "CONDUCT_CLAUDE_KEY_NAME"


def _pin() -> str:
    """The one pin, or an honest skip naming exactly what is missing."""
    value = os.environ.get(EXECUTABLE_ENV, "")
    if not value:
        pytest.skip(f"no real Claude Code install: {EXECUTABLE_ENV} is not set")
    if not Path(value).is_absolute():
        pytest.skip(
            f"no real Claude Code install: {EXECUTABLE_ENV} is not an absolute path")
    if not Path(value).is_file():
        pytest.skip(
            f"no real Claude Code install: {EXECUTABLE_ENV} names no file on disk")
    return value


def _real_harness(tmp_path: Path, names: tuple[str, ...] = ()):
    executable = _pin()
    root = tmp_path / "root"
    root.mkdir()
    resolution = resolve_providers(
        [ProviderConfig(
            provider_id=CLAUDE_PROVIDER_ID, executable=executable,
            protocol=CLAUDE_PROTOCOL, env_allow=names)],
        root=root, clock=lambda: NOW, ids=_Ids())
    contract = next(
        row for row in resolution.contracts if row.provider_id == CLAUDE_PROVIDER_ID)
    assert contract.available is True, "the pin is on disk, so this must be available"
    return resolution.registry.resolve(CLAUDE_PROVIDER_ID), root


def _seed_instruction(root: Path, text: str) -> None:
    instructions = root / "instructions"
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        text, encoding="utf-8", newline="\n")


def test_a_real_install_prints_a_form_this_adapter_can_parse(tmp_path):
    """The parser meets a real binary, which is the only place it can be settled.

    It carries more weight here than for any other provider: nothing this parser
    was built from is a statement that WRITES the string. If a real install
    prints a shape it refuses, this fails with both strings in the message and
    what changes is the parser -- in review, not here.
    """
    adapter, root = _real_harness(tmp_path)
    _seed_instruction(root, "Report the current directory and change nothing.")
    adapter._workspace.work_root()
    outcome = adapter._attempt(("--version",), "work", timeout=60)

    assert outcome.status == "completed", (
        "the pinned Claude Code did not exit within the preflight budget")
    assert outcome.exit_code == 0, "the pinned build failed to report a version"
    from conductor.command.adapters.headless_cli import _version_token

    observed = _version_token(outcome.output)
    assert observed, "the pinned Claude Code printed no version token at all"
    parsed = adapter._version_matches(outcome.output)

    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))
    if parsed:
        # The reviewed build: the prompt was allowed to run, and whatever it did
        # the receipt is an OBSERVATION -- this smoke claims nothing about it.
        assert receipt.outcome in {"succeeded", "failed", "unknown", "cancelled"}
    else:
        assert receipt.outcome == "failed", (
            f"an unreviewed build must be refused, not run (installed "
            f"{observed!r}, reviewed {REVIEWED_CLAUDE_VERSION!r})")
        assert REVIEWED_CLAUDE_VERSION in receipt.detail
        assert observed not in receipt.detail, (
            "the observed version is raw child output and must never be echoed")
        # A refusal is correct for a DIFFERENT version and wrong for a shape the
        # parser cannot read. CONTAINMENT rather than a prefix: this vendor puts
        # the semver FIRST, so `startswith` would answer True for a print this
        # parser refuses for its suffix, and the one tripwire for a too-narrow
        # parser would stay silent on the exact defect it exists to catch.
        assert REVIEWED_CLAUDE_VERSION not in observed, (
            f"the install prints the reviewed semver in a shape this parser "
            f"refuses: {observed!r} -- widen the parser in review")


def test_no_claude_state_is_left_anywhere_a_real_install_would_have_put_it(tmp_path):
    """``CLAUDE_CONFIG_DIR`` relocates the config directory, so a real preflight
    writes something -- and after the spawn returns none of it may still stand
    under this build's home root. The operator's own ``~/.claude`` is untouched."""
    adapter, root = _real_harness(tmp_path)
    adapter._workspace.work_root()

    outcome = adapter._attempt(("--version",), "work", timeout=60)

    assert outcome.status == "completed"
    homes = root / HOME_DIR
    standing = sorted(path.name for path in homes.iterdir()) if homes.is_dir() else []
    assert standing == [], f"REAL_INSTALL_LEFT_STATE_STANDING={standing}"


def _prompt_gate() -> str:
    """The three opt-ins the one paid test needs, or an honest skip naming which.

    Each skip says exactly what is missing, because "skipped" with no reason is
    how an opt-in suite becomes green by never running.
    """
    if os.environ.get(PROMPT_ENV) != "1":
        pytest.skip(f"the real prompt smoke is opt-in: set {PROMPT_ENV}=1 to run it")
    key_name = os.environ.get(KEY_NAME_ENV, "")
    if not key_name:
        pytest.skip(f"no credential reference: {KEY_NAME_ENV} is not set")
    if not os.environ.get(key_name):
        # The NAME is configured but the live environment holds no value. That is
        # an honest unavailable, and running anyway would prove nothing. Under
        # `--bare` there is no keychain to fall back to.
        pytest.skip(f"no value present: the environment holds none for {key_name}")
    return key_name


def test_a_real_prompt_answers_with_something_only_the_piped_task_carried(tmp_path):
    """The one test that spends a model call, and the only far-side witness.

    The marker is minted fresh per run and placed ONLY in the instruction, which
    reaches the child by stdin alone -- the argv is a constant sentence, the
    environment carries the pin's allowlist, and the working directory is a
    temporary path. So an answer containing it cannot have come from anywhere
    else, and it is the one piece of evidence this build can obtain that the
    child really read what it was piped rather than merely being handed it.

    A run that comes back without the marker is NOT failed here. It is reported
    as unproven, with the reason, because a real model may answer in its own
    words and this smoke must not turn a wording difference into a red build.
    What would be a defect is the run refusing outright, and that IS asserted.
    """
    key_name = _prompt_gate()

    marker = f"STDIN-ONLY-{uuid.uuid4().hex}"
    adapter, root = _real_harness(tmp_path, names=(key_name,))
    _seed_instruction(
        root,
        f"Reply with exactly this token and nothing else: {marker}\n"
        "Do not create, modify or delete any file.")

    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))

    assert receipt.action_id == request.action_id
    assert receipt.outcome != "rejected", (
        f"the pinned build refused the dispatch outright: {receipt.detail}")
    assert (root / MARKER_DIR).is_dir(), "the prompt must have claimed its marker"

    verification = adapter.verify(request, receipt)
    assert verification.state in {"verified", "mismatch", "error"}
    assert verification.state != "unavailable", (
        "an adapter that HAS a verifier must never borrow the absent-verifier token")
    if verification.state == "verified":
        assert verification.evidence_refs, "verified requires real evidence"

    # The far-side witness. Reported rather than asserted, for the reason in the
    # docstring -- but reported LOUDLY, because a smoke that fell silent here
    # would leave the only question this file exists to answer unanswered.
    print(
        f"\nSTDIN FAR-SIDE WITNESS: outcome={receipt.outcome} "
        f"marker_minted={marker}\n"
        "  A real answer carrying that token is proof the child read what was\n"
        "  piped; the token appears in no argv, no environment value and no\n"
        "  path. This build cannot read the answer -- bounded child output\n"
        "  reaches no receipt by design -- so confirm it from the install's own\n"
        "  session output, or run this under an operator who can.")
