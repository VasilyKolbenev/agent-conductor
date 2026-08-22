"""OPT-IN smoke against a REAL Kimi Code install. Skips honestly; never fakes a pass.

Nothing in this module runs unless an operator points it at a real install by
setting the pin in the environment, and nothing here installs, downloads or
searches for anything. A missing install is an honest skip, never a success:

    CONDUCT_KIMI_EXECUTABLE   absolute path to the kimi binary

The prompt smoke needs two more opt-ins and a real key, because it spends a real
model call. The key NAME is the vendor's own documented shell channel -- Kimi
Code reads credentials from the environment only through the ``KIMI_MODEL_*``
family, and ``KIMI_MODEL_NAME`` is its enable switch -- so both names are named:

    CONDUCT_KIMI_REAL_PROMPT=1
    CONDUCT_KIMI_KEY_NAME     the env NAME holding the key, itself set
    CONDUCT_KIMI_MODEL_NAME   the env NAME holding the model, itself set

Read the version smoke carefully before trusting it. It does NOT assert that the
installed build is the reviewed one -- an operator may legitimately have another
version, and the adapter's correct answer then is to refuse. What it asserts is
the RELATION between what the real binary says and what the adapter decides, so
it cannot pass by shrugging: the install must really answer ``--version``, and
the adapter must spawn a prompt exactly when that answer matches and never
otherwise.

That relation is why this file matters more for Kimi Code than for dsh. The
vendor publishes that a version number is printed and NOT the format it is
printed in, so the adapter demands an exact match against a token it has never
seen a real binary produce. This smoke is where that guess meets a real install:
if a reviewed build prints its number with a prefix, the version test below
fails with both strings in the message, and what changes is the reviewed
constant -- in review, not here.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from conductor.command.adapters.kimi_code import (
    KIMI_PROTOCOL,
    KIMI_PROVIDER_ID,
    MARKER_DIR,
    REVIEWED_KIMI_VERSION,
)
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers

from tests.test_command_kimi_transport import NOW, _Ids, a_request

EXECUTABLE_ENV = "CONDUCT_KIMI_EXECUTABLE"
PROMPT_ENV = "CONDUCT_KIMI_REAL_PROMPT"
KEY_NAME_ENV = "CONDUCT_KIMI_KEY_NAME"
MODEL_NAME_ENV = "CONDUCT_KIMI_MODEL_NAME"


def _pin() -> str:
    """The one pin, or an honest skip naming exactly what is missing."""
    value = os.environ.get(EXECUTABLE_ENV, "")
    if not value:
        pytest.skip(f"no real Kimi Code install: {EXECUTABLE_ENV} is not set")
    if not Path(value).is_absolute():
        pytest.skip(
            f"no real Kimi Code install: {EXECUTABLE_ENV} is not an absolute path")
    if not Path(value).is_file():
        pytest.skip(
            f"no real Kimi Code install: {EXECUTABLE_ENV} names no file on disk")
    return value


def _real_harness(tmp_path: Path, names: tuple[str, ...] = ()):
    executable = _pin()
    root = tmp_path / "root"
    root.mkdir()
    resolution = resolve_providers(
        [ProviderConfig(
            provider_id=KIMI_PROVIDER_ID, executable=executable,
            protocol=KIMI_PROTOCOL, env_allow=names)],
        root=root, clock=lambda: NOW, ids=_Ids())
    contract = next(
        row for row in resolution.contracts if row.provider_id == KIMI_PROVIDER_ID)
    assert contract.available is True, "the pin is on disk, so this must be available"
    return resolution.registry.resolve(KIMI_PROVIDER_ID), root


def test_a_real_install_answers_the_version_preflight_and_the_adapter_obeys_it(
        tmp_path):
    """The real binary speaks; the adapter's spawn decision must match what it said."""
    adapter, root = _real_harness(tmp_path)
    instructions = root / "instructions"
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        "Report the name of the current directory and change nothing.",
        encoding="utf-8", newline="\n")
    adapter._workspace.work_root()  # the contained route the child will stand in
    # Through the PRODUCTION retention path, never around it. `_spawn` with a
    # hand-minted home skips `_attempt`'s `finally: discard`, so a smoke written
    # that way leaves the very state it claims this build never keeps -- which is
    # what it did, deterministically, until this line changed.
    outcome = adapter._attempt(("--version",), "work", timeout=60)
    assert outcome.status == "completed", (
        "the pinned Kimi Code build did not exit within the preflight budget")
    assert outcome.exit_code == 0, "the pinned build failed to report a version"
    from conductor.command.adapters.headless_cli import _version_token

    observed = _version_token(outcome.output)
    assert observed, "the pinned Kimi Code build printed no version token at all"

    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))
    if observed == REVIEWED_KIMI_VERSION:
        # The reviewed build: the prompt was allowed to run, and whatever it did,
        # the receipt is an OBSERVATION -- this smoke claims nothing about it.
        assert receipt.outcome in {"succeeded", "failed", "unknown", "cancelled"}
    else:
        assert receipt.outcome == "failed", (
            f"an unreviewed build must be refused, not run (installed {observed!r}, "
            f"reviewed {REVIEWED_KIMI_VERSION!r})")
        assert REVIEWED_KIMI_VERSION in receipt.detail
        assert observed not in receipt.detail, (
            "the observed version is raw child output and must never be echoed")


def test_no_kimi_state_is_left_anywhere_a_real_install_would_have_put_it(tmp_path):
    """The retention promise, against the real binary rather than against a fake.

    ``KIMI_CODE_HOME`` relocates "the config file, sessions, logs, OAuth
    credentials, and all other data", so a real preflight is enough to make the
    tool write SOMETHING -- and after the spawn returns, none of it may still
    stand under this build's home root. Whatever the operator's own
    ``~/.kimi-code`` holds is not touched and not read: this asserts only about
    the tree this build owns.
    """
    adapter, root = _real_harness(tmp_path)
    adapter._workspace.work_root()

    # Through the PRODUCTION retention path, never around it. `_spawn` with a
    # hand-minted home skips `_attempt`'s `finally: discard`, so a smoke written
    # that way leaves the very state it claims this build never keeps -- which is
    # what it did, deterministically, until this line changed.
    outcome = adapter._attempt(("--version",), "work", timeout=60)

    assert outcome.status == "completed"
    homes = root / ".kimi-home"
    standing = sorted(path.name for path in homes.iterdir()) if homes.is_dir() else []
    assert standing == [], f"REAL_INSTALL_LEFT_STATE_STANDING={standing}"


def test_a_real_prompt_is_only_attempted_when_the_documented_channel_is_present(
        tmp_path):
    """The one test that spends a model call, and the strictest to reach."""
    if os.environ.get(PROMPT_ENV) != "1":
        pytest.skip(f"the real prompt smoke is opt-in: set {PROMPT_ENV}=1 to run it")
    key_name = os.environ.get(KEY_NAME_ENV, "")
    model_name = os.environ.get(MODEL_NAME_ENV, "")
    for label, name in ((KEY_NAME_ENV, key_name), (MODEL_NAME_ENV, model_name)):
        if not name:
            pytest.skip(f"no credential reference: {label} is not set")
        if not os.environ.get(name):
            # The NAME is configured but the live environment holds no value.
            # That is an honest unavailable, and running anyway proves nothing.
            pytest.skip(f"no value present: the environment holds none for {name}")
    adapter, root = _real_harness(tmp_path, names=(key_name, model_name))
    instructions = root / "instructions"
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        "Create a file named smoke.txt containing the word ok, and nothing else.",
        encoding="utf-8", newline="\n")

    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))

    assert receipt.action_id == request.action_id
    # Exit zero is an observation, and for Kimi Code it is the WEAKER
    # observation: the vendor publishes no exit-code contract for `--prompt`.
    # Verification is the separate seam and reads the workspace, so this asserts
    # the relation rather than a happy outcome.
    verification = adapter.verify(request, receipt)
    assert verification.state in {"verified", "mismatch", "error"}
    assert verification.state != "unavailable", (
        "an adapter that HAS a verifier must never borrow the absent-verifier token")
    if verification.state == "verified":
        assert verification.evidence_refs, "verified requires real evidence"
    assert (root / MARKER_DIR).is_dir(), "the prompt must have claimed its marker"
