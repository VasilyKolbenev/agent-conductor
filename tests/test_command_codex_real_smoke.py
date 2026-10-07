"""OPT-IN smoke against a REAL Codex CLI install. Skips honestly; never fakes a pass.

Nothing here runs unless an operator points it at a real install, and nothing
installs, downloads or searches for anything. A missing install is an honest
skip, never a success:

    CONDUCT_CODEX_EXECUTABLE    absolute path to the codex binary

The npm package ships a Node shim that spawns a vendored native binary; what this
build pins is the BINARY, which on Windows stands at
``node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/codex/codex.exe``
under the global npm root. A release archive's binary is the same shape.

The prompt smoke needs one more opt-in and a real key, because it spends a real
model call:

    CONDUCT_CODEX_REAL_PROMPT=1
    CONDUCT_CODEX_KEY_NAME      the env NAME holding the key, itself set
                                (``OPENAI_API_KEY`` unless a deployment renames
                                it)

**Two things this file settles that nothing else can.**

The VERSION FORM. This adapter parses `codex-cli <semver>`, and the reason that
is not obvious is written out in `tests/test_command_codex_version.py`: the
source declares `bin_name = "codex"`, so the form a reader of the entry point
would write is the one no install prints. The reviewed number itself came from
running the binary, because the pinned tree carries a `0.0.0` placeholder. So
this smoke is where the parser meets the thing it was written for. It does NOT
assert the installed build is the reviewed one -- an operator may legitimately
have another, and the adapter's correct answer then is to refuse -- it asserts
the RELATION between what the real binary prints and what the adapter decides,
and it says which of the two possible refusals happened.

The FAR SIDE OF THE PIPE. The runner can report that a payload was written,
flushed and ended on the parent's side; no parent can see whether the child read
it. Below the operating system's pipe buffer the two are indistinguishable. So
the prompt smoke asks a real Codex CLI for something it could only know from what
was piped: a marker that appears in the instruction and NOWHERE in argv, the
environment or the working directory.

**The PROJECT LAYER.** The CLI reads a `.codex/config.toml` it finds in its
working root's ancestry, and this build spawns the child inside the run's own
work subtree -- which an earlier action's model may have written into, and which
the workspace sweep does not touch because `.codex/` stands outside the home
root. Whether an untrusted layer can reach the child is a fact about the
INSTALL, and the pinned source may not answer it: that tree declares three flags
this binary rejects. So it is asked here, of the binary, twice -- once on the
production road with a poisoned layer and once with the same layer TRUSTED --
and neither half means anything without the other.

**And it collects the model's answer from the file this build told the CLI to
write.**
`-o` names a path inside the attempt home, so the answer is there and nowhere
else -- this build discards bounded child output by design, and the home itself
goes when the spawn returns. The file is therefore read from inside the
transport's own reading seam, which is the one moment it exists. What is asserted
is the TOKEN inside it, never the file's existence: the vendor writes that file
on every completed run, empty when the model said nothing, so its presence proves
only that the CLI finished.

Everything the module reaches the child through goes via the production retention
path; ``tests/test_real_smoke_retention.py`` guards that with tests that cannot
skip.
"""
from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path

import pytest

from conductor.command.adapters.codex_cli import (
    CODEX_PROTOCOL,
    CODEX_PROVIDER_ID,
    HOME_DIR,
    LAST_MESSAGE_NAME,
    MARKER_DIR,
    REVIEWED_CODEX_VERSION,
)
from conductor.command.adapters.headless_cli import _version_token
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers

from tests.test_command_codex_transport import NOW, _Ids, a_request

EXECUTABLE_ENV = "CONDUCT_CODEX_EXECUTABLE"
PROMPT_ENV = "CONDUCT_CODEX_REAL_PROMPT"
KEY_NAME_ENV = "CONDUCT_CODEX_KEY_NAME"

#: The observed form, SPELLED here rather than imported from the adapter: a check
#: that read the shipped pattern would move with it, and the whole point of this
#: file is to be the one place that does not.
_OBSERVED_FORM = re.compile(r"\Acodex-cli (?P<semver>\d+\.\d+\.\d+)\Z")


def _pin() -> str:
    """The one pin, or an honest skip naming exactly what is missing."""
    value = os.environ.get(EXECUTABLE_ENV, "")
    if not value:
        pytest.skip(f"no real Codex CLI install: {EXECUTABLE_ENV} is not set")
    if not Path(value).is_absolute():
        pytest.skip(
            f"no real Codex CLI install: {EXECUTABLE_ENV} is not an absolute path")
    if not Path(value).is_file():
        pytest.skip(
            f"no real Codex CLI install: {EXECUTABLE_ENV} names no file on disk")
    return value


def _real_harness(tmp_path: Path, names: tuple[str, ...] = ()):
    executable = _pin()
    root = tmp_path / "root"
    root.mkdir()
    resolution = resolve_providers(
        [ProviderConfig(
            provider_id=CODEX_PROVIDER_ID, executable=executable,
            protocol=CODEX_PROTOCOL, env_allow=names)],
        root=root, clock=lambda: NOW, ids=_Ids())
    contract = next(
        row for row in resolution.contracts if row.provider_id == CODEX_PROVIDER_ID)
    assert contract.available is True, "the pin is on disk, so this must be available"
    return resolution.registry.resolve(CODEX_PROVIDER_ID), root


def _seed_instruction(root: Path, text: str) -> None:
    instructions = root / "instructions"
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        text, encoding="utf-8", newline="\n")


def _assert_the_production_parser_read_it(
        adapter, output: bytes, observed: str) -> None:
    """The production parser read the SAME semver this file read independently.

    This is the question a boolean cannot answer. `_version_matches` returning
    False means either "a different build" or "this parser read nothing at all",
    and a smoke that checked the form itself and then accepted any False could
    not tell them apart -- a production parser replaced with one that matches
    NOTHING passes that shape, against a valid form at a non-reviewed version.

    So the two parses are compared to each other. The expected semver comes from
    this file's own literal pattern, which is the whole reason that pattern is
    spelled here instead of imported from the adapter it exists to check.
    """
    described = _OBSERVED_FORM.match(observed)
    assert described is not None
    expected = described.group("semver")
    produced = adapter._parsed_version(output)
    assert produced == expected, (
        f"the production parser did not read the form this install printed: it "
        f"made {produced!r} of {observed!r}, where an independent reading of the "
        f"same form gives {expected!r}. A parser that reads nothing is "
        f"indistinguishable from a correct refusal unless this is checked")


def _assert_form_is_readable(observed: str) -> None:
    """The FORM question, asked separately from the version question.

    They fail differently and mean different things: a different version is an
    operator running another build, which the adapter is right to refuse; an
    unreadable form is this parser being wrong about the vendor, which no
    refusal can fix.

    For this provider the likeliest wrong form is a NAMED one: the source
    declares `bin_name = "codex"`, so an install printing `codex 0.112.0` would
    mean the crate was renamed and this pattern must follow it. That is a
    finding about the PARSER, and it is widened in review.
    """
    assert _OBSERVED_FORM.match(observed) is not None, (
        f"the install prints a form this parser cannot read at all: "
        f"{observed!r} -- expected `codex-cli <semver>`. This is a finding "
        f"about the PARSER, not about the build, and it is widened in review")


def test_a_real_install_prints_a_form_this_adapter_can_parse(tmp_path):
    """The parser meets a real binary, which is the only place it can be settled.

    It carries more weight here than for any other provider: the reviewed number
    was READ from a binary rather than from a file, so this print is the only
    statement of it that exists. If a real install prints a shape this parser
    refuses, this fails with both strings in the message.
    """
    adapter, root = _real_harness(tmp_path)
    _seed_instruction(root, "Report the current directory and change nothing.")
    adapter._workspace.work_root()
    outcome = adapter._attempt(("--version",), "work", timeout=60)

    assert outcome.status == "completed", (
        "the pinned Codex CLI did not exit within the preflight budget")
    assert outcome.exit_code == 0, "the pinned build failed to report a version"

    observed = _version_token(outcome.output)
    assert observed, "the pinned Codex CLI printed no version token at all"

    _assert_form_is_readable(observed)
    _assert_the_production_parser_read_it(adapter, outcome.output, observed)
    parsed = adapter._version_matches(outcome.output)

    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))
    if parsed:
        # The reviewed build: the task was allowed to run, and whatever it did
        # the receipt is an OBSERVATION -- this smoke claims nothing about it.
        assert receipt.outcome in {"succeeded", "failed", "unknown", "cancelled"}
    else:
        assert receipt.outcome == "failed", (
            f"an unreviewed build must be refused, not run (installed "
            f"{observed!r}, reviewed {REVIEWED_CODEX_VERSION!r})")
        assert REVIEWED_CODEX_VERSION in receipt.detail
        assert observed not in receipt.detail, (
            "the observed version is raw child output and must never be echoed")
        # The form already matched above, so reaching here means one thing only:
        # a build that is not the reviewed one, refused correctly.
        assert REVIEWED_CODEX_VERSION not in observed, (
            f"the form matched and the version did too, yet the parser refused: "
            f"{observed!r} -- this is a parser defect, not an unreviewed build")


def test_no_codex_state_is_left_anywhere_a_real_install_would_have_put_it(tmp_path):
    """`CODEX_HOME` relocates the config directory, and this vendor REQUIRES it
    to exist -- so a real preflight runs inside a directory this build made, and
    after the spawn returns none of it may still stand under this build's home
    root. The operator's own ``~/.codex`` is untouched."""
    adapter, root = _real_harness(tmp_path)
    adapter._workspace.work_root()

    outcome = adapter._attempt(("--version",), "work", timeout=60)

    assert outcome.status == "completed"
    homes = root / HOME_DIR
    standing = sorted(path.name for path in homes.iterdir()) if homes.is_dir() else []
    assert standing == [], f"REAL_INSTALL_LEFT_STATE_STANDING={standing}"


def _collecting_final_messages(adapter) -> list[str]:
    """Read each spawn's final message from inside the transport's own seam.

    The file stands inside the attempt home, which is discarded the instant
    `_attempt` returns, so this is the one moment it exists. The production
    reading still runs: what is added is a copy taken for this process only,
    and it never leaves the test.
    """
    answers: list[str] = []
    read_home = adapter._read_attempt_home

    def watched(home):
        target = home / LAST_MESSAGE_NAME
        if target.is_file():
            answers.append(target.read_text(encoding="utf-8", errors="replace"))
        return read_home(home)

    adapter._read_attempt_home = watched
    return answers


# --- the project layer a previous action could leave in the work tree ---------

#: A `.codex/config.toml` that is VALID TOML and names a provider that does not
#: exist. Admitted, it kills the CLI at config load with a message naming it;
#: ignored, it is inert. Valid TOML on purpose: a malformed file would also fire,
#: and then a reader could not tell "the layer was read" from "the file was
#: unparseable", which are different findings.
POISON = 'model_provider = "PROBE_NO_SUCH_PROVIDER"\n'
#: What the trust store looks like. Spelled here rather than derived, because
#: this is the vendor's shape and this file is where a change to it must show.
TRUST = '[projects."{key}"]\ntrust_level = "trusted"\n'


def _plant_project_layer(work: Path) -> Path:
    """Leave a `.codex/config.toml` where a previous action's model could."""
    layer = work / ".codex"
    layer.mkdir(parents=True, exist_ok=True)
    (layer / "config.toml").write_text(POISON, encoding="utf-8", newline="\n")
    return layer


def test_a_project_layer_in_the_work_tree_changes_nothing_on_the_production_road(
        tmp_path):
    """The containment claim, asked of the REVIEWED binary rather than of source.

    This build spawns the child inside the run's own work subtree, and a
    `.codex/` left there by an earlier action is not swept: it stands outside
    the home root, so nothing this build discards reaches it. Whether it can
    reach the CHILD is therefore a vendor question, and the pinned source is not
    allowed to answer it -- that tree declares three flags this binary rejects,
    which is exactly how much its statements are worth here.

    So the question is put to the install, twice, through the production road,
    and the answer is read through the one thing that road observes: the KIND of
    the file `-o` named. A clean tree and a poisoned tree must give the SAME
    word. The other half -- that the poison can fire at all -- is the control
    below, and neither claim means anything without it.

    No model call: no credential is forwarded, so both runs end at auth.
    """
    adapter, root = _real_harness(tmp_path)
    _seed_instruction(root, "Report the current directory and change nothing.")
    request = a_request()

    clean = adapter.execute(adapter.prepare(request))
    baseline = adapter._answer

    _plant_project_layer(root / "work" / request.arguments["work_item_id"])
    poisoned = adapter.execute(adapter.prepare(
        a_request(action_id="act-project-layer")))

    assert baseline is not None, clean.detail
    assert adapter._answer == baseline, (
        f"a `.codex/` in the work tree changed what the CLI did: the same "
        f"dispatch reported {baseline!r} without it and {adapter._answer!r} "
        f"with it. Either this install admits an untrusted project layer, or "
        f"something else about the run moved; {poisoned.detail}")


def test_the_poisoned_layer_really_fires_when_the_directory_is_trusted(tmp_path):
    """The control for the control: planted and TRUSTED, the layer takes effect.

    Without it the claim above is empty -- a `.codex/config.toml` that could
    never change anything would satisfy it on any install, including one that
    reads every project layer it finds.

    This one cannot go through the production road, and that is the point rather
    than a shortcut: the road mints a fresh `CODEX_HOME` per spawn and discards
    it, so a trust store is precisely the thing it can never produce. What is
    asked here is a question about the VENDOR -- given a trusted directory, does
    the layer take effect -- so it is asked of the same binary, with the same
    argv this transport builds, in a home that stands OUTSIDE the project root.
    The project's own home root is asserted untouched afterwards.
    """
    adapter, root = _real_harness(tmp_path)
    work = root / "work" / "work-001"
    work.mkdir(parents=True, exist_ok=True)
    _plant_project_layer(work)
    home = tmp_path / "trusted-home-outside-the-project"
    home.mkdir()
    (home / "config.toml").write_text(
        TRUST.format(key=str(work).replace("\\", "\\\\")),
        encoding="utf-8", newline="\n")

    done = subprocess.run(
        # No model is routed: this claim is about a poisoned project layer,
        # and a `--model` token would be a second reason for the run to end.
        [adapter._pin.executable, *adapter._stdin_argv(home, None)],
        cwd=str(work),
        env={"CODEX_HOME": str(home)},
        input=b"Reply with the word ok and nothing else.",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    said = done.stdout.decode("utf-8", errors="replace")

    assert done.returncode != 0, "a trusted poisoned layer must not be shrugged off"
    assert "PROBE_NO_SUCH_PROVIDER" in said, (
        f"the trusted project layer did not take effect, so the claim next door "
        f"rests on a poison that fires nowhere: {said[:400]!r}")
    assert not (home / LAST_MESSAGE_NAME).exists(), (
        "the CLI reached its output file, so it did not die at config load")
    homes = root / HOME_DIR
    standing = sorted(path.name for path in homes.iterdir()) if homes.is_dir() else []
    assert standing == [], f"THE_CONTROL_LEFT_STATE_STANDING={standing}"


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
        # an honest unavailable, and running anyway would prove nothing.
        pytest.skip(f"no value present: the environment holds none for {key_name}")
    return key_name


def test_a_real_prompt_answers_with_something_only_the_piped_task_carried(tmp_path):
    """The one test that spends a model call, and the only far-side witness.

    The marker is minted fresh per run and placed ONLY in the instruction, which
    reaches the child by stdin alone -- the argv is a fixed list of code-owned
    flags plus one minted path, the environment carries the pin's allowlist, and
    the working directory is a temporary path. So an answer containing it cannot
    have come from anywhere else, and it is the one piece of evidence this build
    can obtain that the child really read what it was piped rather than merely
    being handed it.

    It is collected from the file `-o` names, because that is where this
    provider's answer goes and because the file dies with the home: the read
    happens inside the transport's own seam, which is the one moment it exists.
    What is asserted is the TOKEN, never the file -- the vendor writes that file
    on every completed run, EMPTY when the model said nothing, so its presence
    would prove only that the CLI reached the end.
    """
    key_name = _prompt_gate()

    marker = f"STDIN-ONLY-{uuid.uuid4().hex}"
    adapter, root = _real_harness(tmp_path, names=(key_name,))
    _seed_instruction(
        root,
        f"Reply with exactly this token and nothing else: {marker}\n"
        "Do not run any command, and do not create or modify any file.")
    answers = _collecting_final_messages(adapter)
    request = a_request()
    receipt = adapter.execute(adapter.prepare(request))

    assert receipt.action_id == request.action_id
    assert receipt.outcome != "rejected", (
        f"the pinned build refused the dispatch outright: {receipt.detail}")
    assert (root / MARKER_DIR).is_dir(), "the task must have claimed its marker"

    verification = adapter.verify(request, receipt)
    assert verification.state in {"verified", "mismatch", "error"}
    assert verification.state != "unavailable", (
        "an adapter that HAS a verifier must never borrow the absent-verifier token")

    # THE far-side witness, and it is an ASSERTION rather than advice.
    assert any(marker in answer for answer in answers), (
        "no final message carried the piped token. Either the child never read "
        "its stdin -- which is what this assertion exists to catch, and which no "
        "parent-side check can see below the pipe buffer -- or it answered "
        f"something else. Final messages seen: {[len(a) for a in answers]} bytes")
