"""OPT-IN smoke against a REAL Grok Build install. Skips honestly; never fakes a pass.

Nothing here runs unless an operator points it at a real install, and nothing
installs, downloads or searches for anything. A missing install is an honest
skip, never a success:

    CONDUCT_GROK_EXECUTABLE   absolute path to the grok binary

The prompt smoke needs one more opt-in and a real key, because it spends a real
model call. The key NAME is the vendor's own documented shell channel:

    CONDUCT_GROK_REAL_PROMPT=1
    CONDUCT_GROK_KEY_NAME     the env NAME holding the key, itself set
                              (``XAI_API_KEY`` unless a deployment renames it)

Read the version smoke carefully before trusting it. It does NOT assert the
installed build is the reviewed one -- an operator may legitimately have another
version, and the adapter's correct answer then is to refuse. What it asserts is
the RELATION between what the real binary prints and what the adapter decides.

For Grok Build that relation carries the most weight of any provider in the
roster, because this adapter PARSES rather than compares. The published print is
a semver with an optional short commit and an optional channel, and the parser
was written against the vendor's version module rather than against any observed
output. If a real install prints a shape the parser refuses, this test fails with
both strings in the message and what changes is the parser -- in review, not here.

Everything the module reaches the child through goes via the production retention
path; `tests/test_real_smoke_retention.py` guards that with tests that cannot
skip.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from conductor.command.adapters.grok_build import (
    GROK_PROTOCOL,
    GROK_PROVIDER_ID,
    HOME_DIR,
    MARKER_DIR,
    REVIEWED_GROK_VERSION,
)
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers

from tests.test_command_grok_transport import NOW, _Ids, a_request

#: The published form, SPELLED here rather than imported from the adapter: a
#: check that read the shipped pattern would move with it, and the whole point
#: of this file is to be the one place that does not. Only the semver is
#: captured; the commit and the channel are the vendor's and not this check's.
_DESCRIBED_FORM = re.compile(
    r"\Agrok (?P<semver>\d+\.\d+\.\d+) \((?:[0-9a-f]{4,40}|unknown)\)"
    r"(?: \[(?:stable|alpha)\])?\Z")

EXECUTABLE_ENV = "CONDUCT_GROK_EXECUTABLE"
PROMPT_ENV = "CONDUCT_GROK_REAL_PROMPT"
KEY_NAME_ENV = "CONDUCT_GROK_KEY_NAME"


def _pin() -> str:
    """The one pin, or an honest skip naming exactly what is missing."""
    value = os.environ.get(EXECUTABLE_ENV, "")
    if not value:
        pytest.skip(f"no real Grok Build install: {EXECUTABLE_ENV} is not set")
    if not Path(value).is_absolute():
        pytest.skip(
            f"no real Grok Build install: {EXECUTABLE_ENV} is not an absolute path")
    if not Path(value).is_file():
        pytest.skip(
            f"no real Grok Build install: {EXECUTABLE_ENV} names no file on disk")
    return value


def _real_harness(tmp_path: Path, names: tuple[str, ...] = ()):
    executable = _pin()
    root = tmp_path / "root"
    root.mkdir()
    resolution = resolve_providers(
        [ProviderConfig(
            provider_id=GROK_PROVIDER_ID, executable=executable,
            protocol=GROK_PROTOCOL, env_allow=names)],
        root=root, clock=lambda: NOW, ids=_Ids())
    contract = next(
        row for row in resolution.contracts if row.provider_id == GROK_PROVIDER_ID)
    assert contract.available is True, "the pin is on disk, so this must be available"
    return resolution.registry.resolve(GROK_PROVIDER_ID), root


def _seed_instruction(root: Path, text: str) -> None:
    instructions = root / "instructions"
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        text, encoding="utf-8", newline="\n")


def _assert_the_production_parser_read_it(
        adapter, output: bytes, observed: str) -> None:
    """The production parser read the SAME semver this file reads independently.

    The question a boolean cannot answer. `_version_matches` returning False
    means either "a different build" or "this parser read nothing at all", and
    those are opposite findings with opposite owners: the first is an operator's
    install, the second is this module being wrong about the vendor.

    Reproduced before this existed: replacing the module's pattern with one that
    matches NOTHING, against a valid published form at an unreviewed version,
    passed this smoke -- a parser that reads nothing refuses everything, which
    looks exactly like working correctly.

    So the two parses are compared to each other. The expected semver comes from
    this file's own literal pattern, which is why that pattern is SPELLED here
    instead of imported from the adapter it exists to check.
    """
    described = _DESCRIBED_FORM.match(observed)
    if described is None:
        # An unreadable form is a finding about the PARSER, and it is reported
        # by the assertion further down which knows whether the semver matched.
        # Saying it twice, differently, would give an operator two verdicts.
        return
    expected = described.group("semver")
    produced = adapter._parsed_version(output)
    assert produced == expected, (
        f"the production parser did not read the form this install printed: it "
        f"made {produced!r} of {observed!r}, where an independent reading of the "
        f"same published form gives {expected!r}. A parser that reads nothing is "
        f"indistinguishable from a correct refusal unless this is checked")


def test_a_real_install_prints_a_form_this_adapter_can_parse(tmp_path):
    """The parser meets a real binary, which is the only place it can be settled."""
    adapter, root = _real_harness(tmp_path)
    _seed_instruction(root, "Report the current directory and change nothing.")
    adapter._workspace.work_root()
    outcome = adapter._attempt(("--version",), "work", timeout=60)

    assert outcome.status == "completed", (
        "the pinned Grok Build did not exit within the preflight budget")
    assert outcome.exit_code == 0, "the pinned build failed to report a version"
    from conductor.command.adapters.headless_cli import _version_token

    observed = _version_token(outcome.output)
    assert observed, "the pinned Grok Build printed no version token at all"
    _assert_the_production_parser_read_it(adapter, outcome.output, observed)
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
            f"{observed!r}, reviewed {REVIEWED_GROK_VERSION!r})")
        assert REVIEWED_GROK_VERSION in receipt.detail
        assert observed not in receipt.detail, (
            "the observed version is raw child output and must never be echoed")
        # A refusal is correct for a DIFFERENT version and wrong for a shape the
        # parser cannot read. Tell the operator which, since only one is a bug
        # here: if the semver really is the reviewed one, the parser is too narrow.
        # CONTAINMENT, not a prefix. A prefix test could never fire on the very
        # defect it was written for: a real install prints `grok 1.0.5 ...`, so
        # `startswith("1.0.5")` was False and the one tripwire for a too-narrow
        # parser stayed silent on the parser's actual failure shape.
        assert REVIEWED_GROK_VERSION not in observed, (
            f"the install prints the reviewed semver in a shape this parser "
            f"refuses: {observed!r} -- widen the parser in review")


def test_no_grok_state_is_left_anywhere_a_real_install_would_have_put_it(tmp_path):
    """``GROK_HOME`` overrides the config directory, so a real preflight writes
    something -- and after the spawn returns none of it may still stand under
    this build's home root. The operator's own ``~/.grok`` is not touched."""
    adapter, root = _real_harness(tmp_path)
    adapter._workspace.work_root()

    outcome = adapter._attempt(("--version",), "work", timeout=60)

    assert outcome.status == "completed"
    homes = root / HOME_DIR
    standing = sorted(path.name for path in homes.iterdir()) if homes.is_dir() else []
    assert standing == [], f"REAL_INSTALL_LEFT_STATE_STANDING={standing}"


def test_a_real_prompt_is_only_attempted_when_the_documented_channel_is_present(
        tmp_path):
    """The one test that spends a model call, and the strictest to reach."""
    if os.environ.get(PROMPT_ENV) != "1":
        pytest.skip(f"the real prompt smoke is opt-in: set {PROMPT_ENV}=1 to run it")
    key_name = os.environ.get(KEY_NAME_ENV, "")
    if not key_name:
        pytest.skip(f"no credential reference: {KEY_NAME_ENV} is not set")
    if not os.environ.get(key_name):
        # The NAME is configured but the live environment holds no value. That is
        # an honest unavailable, and running anyway would prove nothing.
        pytest.skip(f"no value present: the environment holds none for {key_name}")
    adapter, root = _real_harness(tmp_path, names=(key_name,))
    _seed_instruction(
        root, "Create a file named smoke.txt containing the word ok, and nothing else.")

    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))

    assert receipt.action_id == request.action_id
    # Exit zero is an observation, and for Grok Build it is the WEAKER one: the
    # vendor publishes no exit-code contract for the one-shot mode.
    verification = adapter.verify(request, receipt)
    assert verification.state in {"verified", "mismatch", "error"}
    assert verification.state != "unavailable", (
        "an adapter that HAS a verifier must never borrow the absent-verifier token")
    if verification.state == "verified":
        assert verification.evidence_refs, "verified requires real evidence"
    assert (root / MARKER_DIR).is_dir(), "the prompt must have claimed its marker"
