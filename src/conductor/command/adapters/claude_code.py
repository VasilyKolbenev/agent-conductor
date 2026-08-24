"""Claude Code, driven headlessly: one pinned binary, one prompt, one attempt.

Every vendor fact below was read from Anthropic's own published sources. Two
kinds of source appear, and each fact says which it rests on, because they are
not worth the same:

    REPO   github.com/anthropics/claude-code       @ 16440d0f6ee8c47f34169687044b89eafa8b0f8d
    ACTION github.com/anthropics/claude-code-action @ dcb57747bfceeaa1fa72638cae52295d1d853d4a
    DOCS   code.claude.com/docs/en/<page>          -- a page that can change under this citation

A REPO citation is a permalink: the exact bytes are recoverable at that commit.
A DOCS citation is not, so wherever one is load-bearing its WORDING is quoted
here rather than merely referenced -- a page that can change under a citation is
re-checkable only if what it said is written down.

**The reviewed version is 2.1.239**, the head entry of ``REPO:CHANGELOG.md``.

- **The version command** is ``claude --version``, named in five places in REPO:
  ``.github/ISSUE_TEMPLATE/bug_report.yml`` lines 13 and 123,
  ``.github/ISSUE_TEMPLATE/model_behavior.yml`` line 187,
  ``.claude/commands/triage-issue.md`` line 34,
  ``plugins/security-guidance/README.md`` line 113, and
  ``scripts/issue-lifecycle.ts`` line 20.
- **The one-shot transport** is ``-p``/``--print`` -- one flag, proved so by
  ``REPO:CHANGELOG.md:1100``, which rejects ``--bg`` "combined with
  ``--print``/``-p``". DOCS (cli-reference) gives ``claude -p "query"``.
- **``--output-format``** takes "``text``, ``json``, or ``stream-json``"
  (DOCS cli-reference); ``text`` is the default and is what this build pins, so
  nothing has to parse a structure this build never agreed a schema for.
- **``--input-format``** takes "``text``, ``stream-json``" -- only two, and NOT
  ``json`` (DOCS cli-reference). ``text`` is pinned.
- **``--no-session-persistence``**: "Disable session persistence so sessions are
  not saved to disk and cannot be resumed. Print mode only." (DOCS
  cli-reference). This build never resumes anything, and a session written to
  disk would be exactly the retention the workspace door exists to prevent.
- **``--permission-mode acceptEdits``**. DOCS (cli-reference) lists ``default``,
  ``acceptEdits``, ``plan``, ``auto``, ``dontAsk``, ``bypassPermissions`` and
  ``manual``, and says that for ``-p`` the starting mode "is ``default`` when
  nothing is configured". So the mode is PINNED rather than inherited: a mode
  taken from settings could stop a real coding run on a prompt no one can
  answer. ``acceptEdits`` is the reviewed choice -- DOCS (headless) says under it
  "Claude writes files without prompting, and Claude Code auto-approves common
  filesystem commands", while "other shell commands and network requests still
  need an ``--allowedTools`` entry or a ``permissions.allow`` rule".
  ``bypassPermissions`` is NOT used and is not a knob this module exposes.
- **``--model`` carries the operator's pinned model, and a FULL NAME rather
  than an alias.** DOCS (cli-reference) states it verbatim: "Sets the model for
  the current session with an alias for the latest model (``sonnet``, ``opus``,
  ``haiku``, or ``fable``) or a model's full name. Overrides the ``model``
  setting and ``ANTHROPIC_MODEL``", with the example ``claude --model
  claude-sonnet-5``. Three things follow, and each is why this is the seam:

  the sentence names two accepted forms and this build sends only the second. An
  alias is defined as "the latest model", which is a MOVING target -- a
  configuration that said ``opus`` would mean one model this month and another
  the next, while the journal recorded the same word both times. A full name is
  the fact a receipt can be read against;

  it OVERRIDES the settings file and ``ANTHROPIC_MODEL``, so what an operator
  pinned in this build's own configuration cannot be displaced by a settings
  file that arrived in the work tree or by an environment an operator allowed
  through. That is the same reason ``--bare`` stands first;

  the flag is documented for the CLI and the page says nothing about combining
  it with ``-p``. That limit is written down rather than smoothed over: the
  form is DOCS-described and locally unobserved, exactly like the version print
  above, and the opt-in real smoke is where an install would show otherwise.
- **``--permission-mode plan``** is the separate review boundary. DOCS
  (permission-modes) calls plan mode a read-only mode for analysis and says it
  can read files and run read-only exploration commands but cannot modify files.
  DOCS (permissions) gives ``claude --permission-mode plan`` and says the same
  flag works with ``-p``. The review road pins that mode, then independently
  refuses verification if the authorized tree changed anyway.
- **``--bare`` is mandatory, and it is a containment fact rather than a speed
  one.** DOCS (headless): "Without ``--bare``, a ``-p`` session runs the hooks
  in a project's ``.claude/settings.json`` and connects the servers in its
  ``.mcp.json``, even in a folder you've never trusted. A ``-p`` session shows no
  workspace trust dialog and no per-server approval prompt." This build spawns
  the child INSIDE the work tree the workspace door handed the run, so without
  ``--bare`` a settings file that arrived in that tree would execute. The same
  page states the consequence this build then accepts: in bare mode Claude Code
  "never reads OAuth credentials or the system keychain", so an operator must
  allow ``ANTHROPIC_API_KEY`` through for the provider to be usable at all.
- **The home** relocates with ``CLAUDE_CONFIG_DIR``, and this is the strongest
  fact in the module because it is DEMONSTRATED with a value three times in REPO
  rather than merely described: ``.devcontainer/devcontainer.json:50`` sets it to
  ``/home/node/.claude``, and ``examples/gateway/aws/Dockerfile:60`` and
  ``examples/gateway/gcp/Dockerfile:30`` both set it to ``/tmp/.claude``.
  ``REPO:CHANGELOG.md:5544`` states the rule -- "Respect CLAUDE_CONFIG_DIR
  everywhere" -- and lines 858, 2190 and 2686 name subsystems that honour it.
- **Two switches are forced off**, and both must hold across BOTH spawns:
  ``DISABLE_AUTOUPDATER`` (``REPO:CHANGELOG.md`` lines 2908 and 4843) and
  ``CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`` (lines 2463, 2740, 2817, 4964).
  The updater one is a VERSION invariant, not a privacy one: an update between
  the version preflight and the task would mean this build proved one binary and
  ran another.
- **Credentials** come from the shell as ``ANTHROPIC_API_KEY``; ``REPO`` names it
  eighteen times and ``CHANGELOG.md:1540`` shows ``claude -p`` failing without
  one. Env NAMES are pinned in operator config and values are read at spawn,
  never written down here.
- Claude Code installs as a native binary, so the operator pins ONE absolute
  path and this module puts nothing in front of it.

Four things the sources settle LESS well than the above, each bounding what may
be claimed:

**The version print's FORM is vendor-described and locally unobserved.** Two
REPO issue templates carry ``placeholder: "e.g., 1.0.123 (Claude Code)"`` --
``bug_report.yml:124`` and ``model_behavior.yml:188`` -- each directly beneath
"Run ``claude --version`` and paste the output". So the semver comes FIRST and
the product name follows in parentheses, which is the opposite order from Grok
Build, where the program name leads. But a placeholder DESCRIBES the output; it
is not the statement that writes it. Claude Code is not open source, so there is
no entry point to trace as there was for Grok, and no installed binary was
available to observe. The parser below therefore reads exactly the described
form and nothing wider, and the opt-in real smoke is the tripwire: it refuses an
install whose print this parser cannot read, and says to widen the parser in
review rather than widening it here.

**Where the prompt goes is settled only in part.** DOCS (headless) states "
Non-interactive mode reads stdin, so you can pipe data in", and every piped
example on that page ALSO carries a positional prompt --
``cat build-error.txt | claude -p 'concisely explain the root cause of this
build error'``. So stdin is a demonstrated DATA channel beside a positional
prompt, and ``-p`` with no positional prompt is a form no page shows. This build
therefore uses only the demonstrated shape: a CONSTANT, code-owned sentence
stands in the positional prompt, and the whole task -- the run's frame and the
operator's materialized instruction -- is piped. Not one byte of an instruction
reaches argv, where any process lister on the machine could read it, and that is
guaranteed BY CONSTRUCTION rather than by a check: this profile declares
``task_channel="stdin"``, so the shared transport calls ``_stdin_argv``, which is
handed no task and therefore cannot put one anywhere. What it IS handed is the
attempt home, which this provider ignores; see that method.

An earlier draft did try to check it, by calling the argv builder twice with two
probe texts and comparing the answers. A review probe defeated that in one line
-- return a constant for both probes and embed the real instruction for anything
else -- and the guard reported the argv safe while the operator's task rode it.
Two observations are not independence; an absent parameter is.

**Exit codes ARE published for this mode.** DOCS (headless): "Claude Code exits
with code 0 on success and a non-zero code when the run fails, so your scripts
can branch on the exit status." The next sentence -- "When a failure happens
inside the run, such as missing authentication, Claude Code prints the failure
as the result on stdout" -- says where a failure is REPORTED and does not
withdraw the code's meaning, so ``exit_codes_published=True``. Under this
build's law that still buys only an observation of the process: verification
reads independent workspace evidence, and a zero never becomes one.

**A payload that this side delivered is not a payload the child read.** The
runner reports ``stdin_state``, and ``delivered`` means written, flushed and
ended on the parent's side -- no parent can see the far end of a pipe. The
shared transport refuses to call an undelivered run a success, which closes the
near side; the far side is closed only by the opt-in real smoke, which asks for
a marker that exists ONLY in what was piped.

Everything after the pin is the shared headless transport in ``headless_cli``:
one fresh ``CLAUDE_CONFIG_DIR`` per attempt discarded when the spawn returns, an
exact version preflight before any prompt, code-owned argv down to the last
token, bounded and drained output that reaches no receipt, journal, API, SSE
frame, evidence or exception message, a marker that stops a crashed prompt from
running twice, and verification that reads only independent workspace evidence.

This module also still holds ``ClaudeCodeAdapter``, the fake-protocol fixture
the shared ``_DeepAdapter`` lifecycle suites drive. It is NOT catalogued any
more -- the catalog serves the transport below -- and it stays here because the
identity gate grants this module's rights to ``claude-code``, so a class
carrying that id belongs in this file or in none.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from .deep_adapters import _DeepAdapter
from .deep_codecs import FakeClaudeCodec
from .deep_contracts import DeepProtocol
from .artifact_transport import ArtifactAwareTransport, REVIEW_CAPABILITY
from .harness_workspace import INSTRUCTION_DIR, WORK_DIR
from .headless_cli import (
    DISPATCH_CAPABILITY,
    TASK_CHANNEL_STDIN,
    ExecutablePin,
    HarnessProfile,
    HeadlessCliError,
    _version_token,
)
from .process import ProcessRunner

#: The graph node this provider binds to; ``conductor.harnesses`` registers it.
CLAUDE_PROVIDER_ID = "claude-code"
#: The exact published version this build was reviewed against: the head entry
#: of the pinned CHANGELOG. A preflight reading anything else refuses.
REVIEWED_CLAUDE_VERSION = "2.1.239"
#: The protocol token an operator pins to select this adapter.
CLAUDE_PROTOCOL = DeepProtocol.CLAUDE_HEADLESS_V1.value
#: Experimental is said in the one field the Cockpit projection carries.
CLAUDE_DISPLAY_NAME = "Claude Code (headless, experimental)"
#: Both controls are real: dispatch edits under acceptEdits; review resolves
#: durable artifact bytes and runs under the separately pinned read-only mode.
CLAUDE_CAPABILITIES = ("observe", DISPATCH_CAPABILITY, REVIEW_CAPABILITY)
CLAUDE_SCHEMA_PAIRS = (
    (DISPATCH_CAPABILITY, "deep-arguments-v1"),
    (REVIEW_CAPABILITY, "deep-arguments-v1"),
)
#: The four seams the registration door requires of every provider.
CLAUDE_LIFECYCLE = ("execute", "observe", "prepare", "verify")
#: The environment NAME whose VALUE is minted fresh per attempt.
CLAUDE_HOME_ENV = "CLAUDE_CONFIG_DIR"
#: The two switches, and the value that sets each. Both are DISABLE flags, so
#: `1` turns the behaviour off -- the opposite polarity from Grok Build's four
#: ENABLED flags, which is why the profile carries a literal value per pair
#: instead of one shared notion of "off".
CLAUDE_AUTOUPDATER_ENV = "DISABLE_AUTOUPDATER"
CLAUDE_NONESSENTIAL_ENV = "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"
SWITCHED_OFF = "1"
CLAUDE_FORCED_ENV = (
    (CLAUDE_AUTOUPDATER_ENV, SWITCHED_OFF),
    (CLAUDE_NONESSENTIAL_ENV, SWITCHED_OFF),
)
#: The code-owned flags, in the order they are sent.
#:
#: ``--bare`` stands FIRST because it is the containment flag: it is what stops
#: a `.claude/settings.json` inside the run's own work tree from executing.
BARE_ARGV = ("--bare",)
PRINT_FLAG = "-p"
#: The CONSTANT positional prompt. It is the entire prompt argument this build
#: ever passes, identical on every dispatch for every operator and every run, so
#: it carries no run identifier, no work item, no instruction and no name. What
#: to do arrives on stdin; this sentence only tells the child to go and read it.
CONSTANT_PROMPT = "Execute the complete task supplied on standard input."
REVIEW_PROMPT = "Produce the complete review artifact supplied on standard input."
INPUT_FORMAT_ARGV = ("--input-format", "text")
OUTPUT_FORMAT_ARGV = ("--output-format", "text")
NO_SESSION_ARGV = ("--no-session-persistence",)
#: The flag this vendor names a model with. A FULL NAME is what this build
#: ever sends through it; see the module docstring for why an alias is not
#: a thing a durable record can be read against.
MODEL_FLAG = "--model"
#: The four names DOCS (cli-reference) defines as "an alias for the latest
#: model", quoted in the module docstring above. Each resolves to whatever this
#: vendor ships at the moment it is read, so none of them names one build.
#:
#: Declared HERE because it is a fact about ANTHROPIC's naming, and the routing
#: seam that refuses them holds no model name of its own. It is not a catalogue
#: of Claude models -- this build keeps none and could not keep one current --
#: only the vendor's own statement about which of its names move.
CLAUDE_UNSTABLE_MODELS = ("sonnet", "opus", "haiku", "fable")
PERMISSION_MODE_ARGV = ("--permission-mode", "acceptEdits")
REVIEW_PERMISSION_MODE_ARGV = ("--permission-mode", "plan")
VERSION_ARGV = ("--version",)
#: Capture ceiling for either spawn; the pump drains past it and drops the rest.
CLAUDE_OUTPUT_LIMIT = 16 * 1024
#: The preflight is a version print, not work: it gets its own small budget.
VERSION_TIMEOUT_SECONDS = 30
#: The two subtrees THIS provider owns beneath the project root.
HOME_DIR = ".claude-home"
MARKER_DIR = ".claude-marker"
#: The ONE closed form this module will read a version out of: the semver, then
#: the product name in parentheses. Anchored at BOTH ends, and closed at the
#: front as well as the back.
#:
#: The anchors buy the usual thing -- an unanchored pattern finds ``2.1.239``
#: inside a warning line and calls that the version. The closed suffix buys
#: something this roster has already paid for twice on another provider: a form
#: that accepted a bare semver would accept any executable at all that prints a
#: number, and this preflight is the one check standing between an operator's
#: pin and a real prompt.
#:
#: The evidence level is written down beside the pattern on purpose:
#: VENDOR-DESCRIBED, LOCALLY UNOBSERVED. See the module docstring -- two issue
#: templates state this form, no source was readable and no binary was
#: available. Widening it is a review decision, not a quiet edit, and the opt-in
#: real smoke is what would show it needs widening.
_VERSION_FORM = re.compile(
    r"\A(?P<semver>\d+\.\d+\.\d+) \(Claude Code\)\Z")

__all__ = [
    "BARE_ARGV", "CLAUDE_CAPABILITIES", "CLAUDE_DISPLAY_NAME",
    "CLAUDE_FORCED_ENV", "CLAUDE_HOME_ENV", "CLAUDE_LIFECYCLE",
    "CLAUDE_PROTOCOL", "CLAUDE_PROVIDER_ID", "CLAUDE_SCHEMA_PAIRS",
    "CONSTANT_PROMPT", "HOME_DIR", "INSTRUCTION_DIR", "MARKER_DIR",
    "CLAUDE_UNSTABLE_MODELS", "MODEL_FLAG",
    "REVIEWED_CLAUDE_VERSION", "REVIEW_PERMISSION_MODE_ARGV",
    "REVIEW_PROMPT", "WORK_DIR",
    "ClaudeCodeAdapter", "ClaudeCodeError", "ClaudeCodeTransport", "claude_pin",
]

#: Every vendor fact above, gathered where the shared transport reads them.
CLAUDE_PROFILE = HarnessProfile(
    tool_noun="Claude Code", task_noun="Claude Code prompt",
    display_name=CLAUDE_DISPLAY_NAME, vendor="Anthropic",
    docs_url="https://code.claude.com/docs/en/headless",
    reviewed_version=REVIEWED_CLAUDE_VERSION,
    home_dir=HOME_DIR, marker_dir=MARKER_DIR,
    home_env=CLAUDE_HOME_ENV, forced_env=CLAUDE_FORCED_ENV,
    version_argv=VERSION_ARGV, exit_codes_published=True,
    capability=DISPATCH_CAPABILITY, output_limit=CLAUDE_OUTPUT_LIMIT,
    version_timeout_seconds=VERSION_TIMEOUT_SECONDS,
    home_id_kind="claude-home",
    task_channel=TASK_CHANNEL_STDIN,
    model_flag=MODEL_FLAG, unstable_models=CLAUDE_UNSTABLE_MODELS)


class ClaudeCodeError(HeadlessCliError):
    """Claude Code cannot be driven without breaking one of this adapter's rules."""


def claude_pin(executable: str, env_allow: tuple[str, ...] = ()) -> ExecutablePin:
    """Claude Code's pin: ONE absolute path, and Claude Code's own refusal type.

    One, not two: Claude Code installs as a native binary and runs no
    interpreter, so there is no second half for this build to guess at.
    """
    return ExecutablePin(
        executable=executable, error=ClaudeCodeError, env_allow=env_allow)


class ClaudeCodeTransport(ArtifactAwareTransport):
    """Run one Claude Code prompt per authorized action, and prove nothing more."""

    profile = CLAUDE_PROFILE
    error = ClaudeCodeError
    review_enabled = True

    def __init__(
            self, pin: ExecutablePin, runner: ProcessRunner, *,
            root: str | Path, clock: Callable[[], str],
            ids: Callable[[str], str],
            adapter_id: str = CLAUDE_PROVIDER_ID) -> None:
        if type(pin) is not ExecutablePin or pin.error is not ClaudeCodeError:
            raise ClaudeCodeError(
                "this adapter requires a single-executable pin of its own")
        self._pin = pin
        super().__init__(
            runner, root=root, clock=clock, ids=ids, adapter_id=adapter_id)

    def _argv_prefix(self) -> tuple[str, ...]:
        """One native binary, and nothing in front of it."""
        return (self._pin.executable,)

    def _stdin_argv(self, home: Path, model: str | None) -> tuple[str, ...]:
        """The code-owned flags and the CONSTANT prompt. It receives no task.

        That is the guarantee, and it is structural: this method cannot put an
        instruction in the command line because it is never handed one. Nothing
        here has to be trusted, checked afterwards, or remembered by the next
        person to edit it -- the task parameter does not exist.

        ``home`` is the attempt home the transport minted for this spawn, and
        Claude Code asks nothing of it: it is offered on this seam because
        another provider's vendor writes an artefact into its own profile home
        and needs the path on its command line.

        ``model`` is the one token here an operator's configuration decides, and
        it is the reason this list is no longer identical on every dispatch. It
        was, and the suite asserted it by spelling the whole list; that claim is
        now split in two, because "every token is code-owned" and "every token
        is the same for every operator" stopped being the same sentence when a
        deployment gained the right to pin a model. What has NOT changed is the
        first half: the VALUE comes from the run's frozen configuration and the
        FLAG from this module, and no byte of a task can reach either.

        It stands before the permission mode so that the mode -- the flag that
        decides what the child may do -- is the last word in the list, where a
        reader looks for it.

        The task itself goes to stdin, where a process lister cannot read it.
        See ``_task_stdin``.
        """
        return (
            *BARE_ARGV, PRINT_FLAG, CONSTANT_PROMPT,
            *INPUT_FORMAT_ARGV, *OUTPUT_FORMAT_ARGV,
            *NO_SESSION_ARGV, *self._model_argv(model),
            *PERMISSION_MODE_ARGV)

    def _task_stdin(self, task_text: str) -> bytes:
        """The whole task, piped -- the run's frame and the user's instruction.

        UTF-8, and no trailing newline is added: the bytes handed over are the
        bytes the task text is, so what the child reads is what this build
        composed and nothing it appended. The runner bounds this at the same
        64 KiB the workspace door bounds an instruction body at, and refuses a
        NUL, before any child exists.
        """
        return task_text.encode("utf-8")

    def _review_argv(self, home: Path, model: str | None) -> tuple[str, ...]:
        """The read-only review argv; its durable inputs still arrive on stdin.

        The routed model reaches a review exactly as it reaches a dispatch, and
        in the same position. A reviewer an operator pinned a model for is a
        reviewer that model reviews with -- routing that stopped at the dispatch
        road would mean the two halves of one cycle ran on different models
        while one configuration described both.
        """
        return (
            *BARE_ARGV, PRINT_FLAG, REVIEW_PROMPT,
            *INPUT_FORMAT_ARGV, *OUTPUT_FORMAT_ARGV,
            *NO_SESSION_ARGV, *self._model_argv(model),
            *REVIEW_PERMISSION_MODE_ARGV)

    def _env_allow(self) -> tuple[str, ...]:
        return self._pin.env_allow

    def _parsed_version(self, output: bytes) -> str | None:
        r"""The semver this parser reads out of a version print, or ``None``.

        Separate from the yes/no answer, and that separation is the point. A
        BOOLEAN cannot say WHICH question it answered: ``False`` means either
        "a different build" or "this parser could not read the form at all",
        and those are opposite findings. The first is an operator running
        another version, which the adapter is right to refuse. The second is
        this parser being wrong about a vendor whose print nothing here could
        observe -- and no refusal repairs that.

        The opt-in smoke reads THIS, so a real install's print is compared
        against what the production pattern made of it rather than against a
        yes/no that a dead parser and an unreviewed build produce alike. A
        parser accepting nothing at all used to pass that smoke.

        **What may be done with the answer.** It is a substring of child output,
        so it stays inside this class and inside tests: no production path puts
        it in a receipt, a journal record, an API response or an exception
        message. What makes that bearable rather than merely promised is the
        pattern -- the group is ``\d+\.\d+\.\d+`` and can carry digits and dots
        and nothing else, so unlike a whole line it cannot hold a secret a
        hostile build planted where a version belongs.
        """
        found = _VERSION_FORM.match(_version_token(output))
        return None if found is None else found.group("semver")

    def _version_matches(self, output: bytes) -> bool:
        """Whether the pinned build's print IS the reviewed version.

        The shared default compares the whole first line, which would refuse
        every install that prints its product name -- and every published
        description of this print says it does. So the reading is delegated to
        ``_parsed_version`` and this method only compares, which keeps the
        BOOLEAN the transport needs while leaving the parse itself observable.
        """
        return self._parsed_version(output) == self.profile.reviewed_version


class ClaudeCodeAdapter(_DeepAdapter):
    """The fake-protocol fixture; the catalog serves ``ClaudeCodeTransport``.

    Kept because the shared ``_DeepAdapter`` lifecycle suites drive two concrete
    subclasses and this is one of them, and kept HERE because it carries the
    ``claude-code`` id and the identity gate grants that id's rights to this
    module alone.
    """

    ADAPTER_ID = CLAUDE_PROVIDER_ID
    DISPLAY_NAME = "Claude Code (fake protocol)"
    VENDOR = "Anthropic-compatible test fixture"
    PROTOCOL = DeepProtocol.FAKE_CLAUDE_V1
    CODEC = FakeClaudeCodec


#: This module's own statement of which concrete type is reviewed for the fake
#: protocol above, read from the class's OWN ``__dict__`` and never inherited.
ClaudeCodeAdapter.REVIEWED_TYPE = ClaudeCodeAdapter
