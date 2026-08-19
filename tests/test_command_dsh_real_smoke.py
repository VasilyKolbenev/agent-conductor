"""OPT-IN smoke against a REAL dsh install. Skips honestly; never fakes a pass.

Nothing in this module runs unless an operator points it at a real install by
setting BOTH pins in the environment, and nothing here installs, downloads or
searches for anything. A missing install is an honest skip, never a success:

    CONDUCT_DSH_NODE        absolute path to the node executable
    CONDUCT_DSH_ENTRYPOINT  absolute path to the dsh entrypoint (lib/bin.js)

The task smoke needs one more opt-in and a real key, because it spends a real
model call:

    CONDUCT_DSH_REAL_TASK=1
    CONDUCT_DSH_KEY_NAME    the env NAME holding the key, which must itself be set

Read the version smoke carefully before trusting it. It does NOT assert that the
installed build is the reviewed one -- an operator may legitimately have another
version, and the adapter's correct answer then is to refuse. What it asserts is
the RELATION between what the real binary says and what the adapter decides, so
it cannot pass by shrugging: the install must really answer ``--version``, and
the adapter must spawn a task exactly when that answer matches and never
otherwise.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from conductor.command.adapters.dsh_harness import DSH_PROTOCOL, REVIEWED_DSH_VERSION
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers

from tests.test_command_dsh_harness import NOW, PROVIDER_ID, _Ids, a_request

NODE_ENV = "CONDUCT_DSH_NODE"
ENTRYPOINT_ENV = "CONDUCT_DSH_ENTRYPOINT"
TASK_ENV = "CONDUCT_DSH_REAL_TASK"
KEY_NAME_ENV = "CONDUCT_DSH_KEY_NAME"


def _pins() -> tuple[str, str]:
    """Both pins, or an honest skip naming exactly what is missing."""
    node = os.environ.get(NODE_ENV, "")
    entrypoint = os.environ.get(ENTRYPOINT_ENV, "")
    for name, value in ((NODE_ENV, node), (ENTRYPOINT_ENV, entrypoint)):
        if not value:
            pytest.skip(f"no real dsh install: {name} is not set")
        if not Path(value).is_absolute():
            pytest.skip(f"no real dsh install: {name} is not an absolute path")
        if not Path(value).is_file():
            pytest.skip(f"no real dsh install: {name} does not name a file on disk")
    return node, entrypoint


def _real_harness(tmp_path: Path, key_name: str = ""):
    node, entrypoint = _pins()
    root = tmp_path / "root"
    root.mkdir()
    names = (key_name,) if key_name else ()
    resolution = resolve_providers(
        [ProviderConfig(
            provider_id=PROVIDER_ID, executable=node, protocol=DSH_PROTOCOL,
            env_allow=names, entrypoint=entrypoint)],
        root=root, clock=lambda: NOW, ids=_Ids())
    contract = next(row for row in resolution.contracts if row.provider_id == PROVIDER_ID)
    assert contract.available is True, "both pins are on disk, so this must be available"
    return resolution.registry.resolve(PROVIDER_ID), root


def test_a_real_install_answers_the_version_preflight_and_the_adapter_obeys_it(tmp_path):
    """The real binary speaks; the adapter's spawn decision must match what it said."""
    adapter, _root = _real_harness(tmp_path)
    adapter._workspace.work_root()  # the contained route the child will stand in
    outcome = adapter._spawn(
        ("--version",), adapter._mint_home(), "work", timeout=60)
    assert outcome.status == "completed", (
        "the pinned dsh build did not exit on its own within the preflight budget")
    assert outcome.exit_code == 0, "the pinned dsh build failed to report a version"
    from conductor.command.adapters.dsh_harness import _version_token

    observed = _version_token(outcome.output)
    assert observed, "the pinned dsh build printed no version token at all"

    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))
    if observed == REVIEWED_DSH_VERSION:
        # The reviewed build: the task was allowed to run, and whatever it did,
        # the receipt is an OBSERVATION -- this smoke claims nothing about it.
        assert receipt.outcome in {"succeeded", "failed", "unknown", "cancelled"}
    else:
        assert receipt.outcome == "failed", (
            f"an unreviewed build must be refused, not run (installed {observed!r}, "
            f"reviewed {REVIEWED_DSH_VERSION!r})")
        assert REVIEWED_DSH_VERSION in receipt.detail
        assert observed not in receipt.detail, (
            "the observed version is raw child output and must never be echoed")


def test_a_real_headless_task_is_only_attempted_when_a_key_is_really_present(tmp_path):
    """The one test that spends a model call, and the strictest to reach."""
    if os.environ.get(TASK_ENV) != "1":
        pytest.skip(f"the real task smoke is opt-in: set {TASK_ENV}=1 to run it")
    key_name = os.environ.get(KEY_NAME_ENV, "")
    if not key_name:
        pytest.skip(f"no key reference: {KEY_NAME_ENV} is not set")
    if not os.environ.get(key_name):
        # The NAME is configured but the live environment holds no value. That is
        # an honest unavailable, and running anyway would prove nothing.
        pytest.skip(f"no key present: the environment holds no value for {key_name}")
    adapter, root = _real_harness(tmp_path, key_name=key_name)
    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))
    assert receipt.action_id == request.action_id
    # Exit zero is an observation. Verification is the separate seam, and it
    # reads the workspace -- so this asserts the relation, not a happy outcome.
    verification = adapter.verify(request, receipt)
    assert verification.state in {"verified", "unavailable", "mismatch", "error"}
    if verification.state == "verified":
        assert verification.evidence_refs, "verified requires real evidence"
    assert (root / ".dsh-marker").is_dir(), "the task must have claimed its marker"
