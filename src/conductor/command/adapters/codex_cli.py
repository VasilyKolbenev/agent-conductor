"""Codex CLI, driven headlessly: one pinned binary, one prompt, one attempt.

Codex is the first provider in this roster where BOTH a readable source tree and
a working local install were available, and the two do not agree. Three evidence
levels appear below and each fact says which it rests on, because a fact from one
of them has already been wrong about the others:

    OBSERVED  the installed native binary, run directly:
              `@openai/codex@0.112.0` vendors
              `vendor/x86_64-pc-windows-msvc/codex/codex.exe`
    SOURCE    github.com/openai/codex @ 343074d4207d572809bd8cea15f4be1d09d98e0b
    DOCS      developers.openai.com/codex/noninteractive, which 308-redirects to
              learn.chatgpt.com/docs/non-interactive-mode -- a page that can
              change under this citation, so its wording is QUOTED here

**The pinned tree is a LATER build than the reviewed one, and this is not a
footnote.** `codex-rs/exec/src/cli.rs` at that commit declares `--strict-config`,
`--ignore-rules` and `--ignore-user-config`; the reviewed binary rejects all
three outright -- `error: unexpected argument '--ignore-user-config' found`, exit
2 -- and a scan of the executable's own bytes finds no `ignore-user-config` in
it while finding every other name this module sends. So an argv written from that
tree would have failed EVERY dispatch, on a flag whose absence nothing else here
would have reported. Every argv fact below is therefore OBSERVED against the
binary, and SOURCE is used for what a binary cannot show: what a flag MEANS, and
what a default IS.

**The reviewed version is 0.112.0, and it comes from an observation rather than
from a pinned file** -- the first provider in this roster of which that is true.
There is nowhere else to read it: `codex-rs/Cargo.toml` carries
`version = "0.0.0"` for the whole workspace (releases are stamped at build), and
`CHANGELOG.md` is a single line pointing at the releases page. The number was
first established by the owner from the installed binary and is re-observed here
from the vendored native executable, which prints exactly 19 bytes:
`codex-cli 0.112.0\\r\\n`.

**The print carries the PACKAGE name, not the program name**, and that is the
trap this module exists on the far side of. `codex-rs/cli/src/main.rs` declares
`#[clap(author, version, bin_name = "codex")]`, so a parser written from the
source reads `codex 0.112.0` and refuses every real install -- while the catalog
row goes on advertising the provider as available. Clap renders the CRATE name
for `--version`, the crate is `codex-cli`, and the binary is `codex`. This is the
Grok defect exactly, avoided only by running the thing.

- **The one-shot mode** is `codex exec`, "Run Codex non-interactively" (OBSERVED,
  `codex --help`; alias `e`, which this build does not use -- the long spelling
  cannot be mistaken for anything else in an argv a person is reading).
- **The prompt travels on STDIN, and `-` says so out loud.** The positional is
  documented "If not provided as an argument (or if `-` is used), instructions
  are read from stdin" (OBSERVED, `codex exec --help`), and DOCS states "If you
  omit the prompt argument, Codex reads the prompt from stdin" and "Use
  `codex exec -` when you want to force that behavior explicitly". Both roads
  read stdin; the explicit one is taken, because a build that relied on the
  ABSENCE of an argument would be relying on something no reader of the argv can
  see. Not one byte of an instruction reaches the command line, and that is
  guaranteed BY CONSTRUCTION rather than by a check: this profile declares
  `task_channel="stdin"`, so the shared transport calls `_stdin_argv`, which is
  handed the attempt home and never the task.
- **`--sandbox workspace-write`** (OBSERVED; the three values are `read-only`,
  `workspace-write`, `danger-full-access`). DOCS: "By default, `codex exec` runs
  in a read-only sandbox", and it advises setting permissions explicitly, naming
  `--sandbox workspace-write` for edits and reserving `danger-full-access` for
  "only in a controlled environment (for example, an isolated CI runner or
  container)". `read-only` cannot serve a coding run;
  `--dangerously-bypass-approvals-and-sandbox` is NOT used and is not a knob this
  module exposes.

  **On Windows that flag is a policy and not an enforcement**, and this build
  runs on Windows. `WindowsSandboxLevel` defaults to `Disabled`
  (SOURCE, `codex-rs/protocol/src/config_types.rs`), so the OS-level backends
  that tree carries are off unless an operator turns one on. Nothing this build
  promises rests on it: the child's working directory is contained by the owned
  runner, and verification reads only what changed under the action's own
  authorized subtree. Said out loud because a reader who saw `workspace-write`
  and assumed containment would be assuming it from the wrong side.
- **`--skip-git-repo-check` is REQUIRED, not a convenience.** SOURCE
  (`codex-rs/exec/src/lib.rs:799`) refuses outright when it is absent and the
  working root is not a git repository -- "Not inside a trusted directory and
  --skip-git-repo-check was not specified.", then `exit(1)`. This build spawns
  the child in `work/<work_item_id>` under the project root, which is not a
  repository, so without this flag every dispatch would fail before the model
  was ever asked anything.
- **`--ephemeral`** -- "Run without persisting session files to disk" (OBSERVED).
  Belt and braces beside a home that is minted and discarded per spawn, and worth
  having as both: one of the two protects the disk if the other is ever wrong.
- **`--color never`** (OBSERVED), so nothing the transport captures carries
  terminal escapes.
- **The home** relocates with `CODEX_HOME`, and this vendor is stricter about it
  than any other in the roster: SOURCE (`codex-rs/utils/home-dir/src/lib.rs`)
  reads the variable, drops an empty value, and then requires that the path
  EXISTS and is a directory -- "CODEX_HOME points to {val:?}, but that path does
  not exist" is an error, not a fallback. The workspace door creates the home it
  mints, so the requirement is already met; it is recorded because it means a
  minted home is load-bearing here rather than merely tidy.
- **Credentials** come from the shell as `OPENAI_API_KEY` (SOURCE names it 174
  times; the reviewed binary carries the string). Env NAMES are pinned in
  operator config and values are read at spawn, never written down here.
- **No environment is FORCED at all**, and this provider is the first with an
  empty `forced_env`. It is not an omission: this vendor publishes its switches
  as CONFIG rather than as environment, so they travel where every other
  code-owned token this build sends travels -- in argv, through `-c`.

**Telemetry is switched off through five published config keys**, each of which
exists in the reviewed binary (its own bytes carry `analytics`,
`metrics_exporter`, `trace_exporter`, `log_user_prompt` and `statsig`) and each
of which SOURCE describes:

    analytics.enabled=false     `AnalyticsConfigToml.enabled`, "When `false`,
                                disables analytics across Codex product
                                surfaces in this machine. Defaults to `true`."
    otel.metrics_exporter       `OtelConfig`'s default is `Statsig`. THIS is the
    otel.trace_exporter         load-bearing one; the other two exporters
    otel.exporter               already default to `None` and are pinned so a
                                config that said otherwise could not turn them
                                back on. `"none"` is the exact spelling:
                                `OtelExporterKind` is `rename_all = "kebab-case"`
                                over a `None` variant.
    otel.log_user_prompt=false  defaults to `false` already, and is sent anyway
                                because it is the one switch whose non-default
                                value would put the OPERATOR'S OWN INSTRUCTION
                                into an exported trace.

A SIXTH switch exists and is deliberately NOT sent: `feedback.enabled`, "When
`false`, disables feedback collection across Codex product surfaces." It governs
an interactive flow `codex exec` never enters, and the owner's ruling named five.
Widening a code-owned environment is a review decision, so it is reported here
rather than added quietly -- which is the same reason the absence of
`--ignore-user-config` above is written down instead of worked around.

**`-o/--output-last-message` is a production channel**, and every condition on it
is structural:

- the path is MINTED BY THIS BUILD inside the attempt home, never taken from a
  task, a config or an operator, and it does not exist before the spawn;
- it never leaves: it is in argv, which reaches no receipt, journal, API, SSE
  frame or exception message, and no road below puts it in one;
- it is read only after the process has ended, and only through the workspace
  door, which answers with a KIND and never with contents. This module never
  opens the file, so not one byte of model text enters this process from it, and
  what a receipt may say is one of four CLOSED words;
- the file's mere existence is NOT read as the task having been read. DOCS says
  the flag "writes the final message to the file and still prints it to
  `stdout`", and SOURCE's `handle_last_message` writes an EMPTY file and warns on
  stderr when there was no agent message at all -- so absent, empty and written
  are three different facts about the CLI's own reporting and none of them is a
  fact about the work. The far side of the pipe is closed by the opt-in real
  smoke, which asks for a token that exists only in what was piped.

**No exit-code contract is published for this mode**, so the profile declares
`exit_codes_published=False` and every receipt says a zero is the process having
ended and nothing else. This was looked for and not found: DOCS states nothing
about exit status, and the nearest thing in SOURCE is a test --
`codex-rs/exec/tests/suite/server_error_exit.rs`, whose comment reads that the
CLI "exits with a non-zero status code so automation can detect failures" and
which asserts `code(1)` for ONE server-error path. A comment on one failure path
is not a statement of what a zero means, and that file is `cfg(not(windows))`
besides. Under this build's law a zero stops at an observation anyway, so the
weaker reading costs no capability.

Everything after the pin is the shared headless transport in `headless_cli`: one
fresh `CODEX_HOME` per attempt discarded when the spawn returns, an exact version
preflight before any prompt, code-owned argv down to the last token, bounded and
drained output that reaches no receipt, journal, API, SSE frame, evidence or
exception message, a marker that stops a crashed prompt from running twice, and
verification that reads only independent workspace evidence.

This module also still holds `CodexAdapter`, the fake-protocol fixture the shared
`_DeepAdapter` lifecycle suites drive. It is NOT catalogued any more -- the
catalog serves the transport below -- and it stays here because the identity gate
grants this module's rights to `codex`, so a class carrying that id belongs in
this file or in none.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType

from .deep_adapters import _DeepAdapter
from .deep_codecs import FakeCodexCodec
from .deep_contracts import DeepProtocol
from .harness_workspace import (
    HOME_LEAF_ABSENT,
    HOME_LEAF_EMPTY,
    HOME_LEAF_FILE,
    HOME_LEAF_OTHER,
    INSTRUCTION_DIR,
    WORK_DIR,
    WorkspaceNotContained,
)
from .headless_cli import (
    DISPATCH_CAPABILITY,
    TASK_CHANNEL_STDIN,
    ExecutablePin,
    HarnessProfile,
    HeadlessCliError,
    HeadlessCliTransport,
    _version_token,
)
from .process import ProcessRunner

#: The graph node this provider binds to; ``conductor.harnesses`` registers it.
CODEX_PROVIDER_ID = "codex"
#: The exact version this build was reviewed against, OBSERVED from the installed
#: native binary rather than read from a pinned file, because the pinned tree
#: carries a `0.0.0` placeholder and the changelog carries a link. A preflight
#: reading anything else refuses.
REVIEWED_CODEX_VERSION = "0.112.0"
#: The protocol token an operator pins to select this adapter.
CODEX_PROTOCOL = DeepProtocol.CODEX_HEADLESS_V1.value
#: Experimental is said in the one field the Cockpit projection carries.
CODEX_DISPLAY_NAME = "Codex CLI (headless, experimental)"
#: Observation, and the one control this adapter really implements. `review` is
#: deliberately ABSENT for the same reason it is absent from Claude Code: the
#: reviewed deep review body carries artifact REFERENCES and this build has no
#: resolver that turns one into the artifact's content. `codex exec review`
#: exists and reviews a GIT DIFF, which is a different thing than the control
#: this product means, so claiming it here would be claiming the wrong seam.
CODEX_CAPABILITIES = ("observe", DISPATCH_CAPABILITY)
CODEX_SCHEMA_PAIRS = ((DISPATCH_CAPABILITY, "deep-arguments-v1"),)
#: The four seams the registration door requires of every provider.
CODEX_LIFECYCLE = ("execute", "observe", "prepare", "verify")
#: The environment NAME whose VALUE is minted fresh per attempt.
CODEX_HOME_ENV = "CODEX_HOME"
#: EMPTY, and the first profile in the roster of which that is true. This vendor
#: publishes its switches as config keys rather than as environment variables, so
#: they are sent through `-c` below and there is nothing left for this field to
#: carry. An empty tuple says that; a pair invented to fill it would not.
CODEX_FORCED_ENV: tuple[tuple[str, str], ...] = ()
#: The code-owned flags, in the order they are sent. The subcommand stands first
#: because every flag after it is one `codex exec` owns rather than one the
#: top-level CLI does -- `-o` in particular is declared on `exec` and is not a
#: token the bare `codex` command would accept.
EXEC_ARGV = ("exec",)
#: REQUIRED: without it the CLI refuses a working root that is not a git
#: repository, which is every work subtree this build ever hands it.
SKIP_GIT_REPO_CHECK_ARGV = ("--skip-git-repo-check",)
EPHEMERAL_ARGV = ("--ephemeral",)
COLOR_ARGV = ("--color", "never")
SANDBOX_ARGV = ("--sandbox", "workspace-write")
#: The five published config keys that turn telemetry off, each sent as its own
#: `-c key=value` pair. The VALUE half is parsed by the CLI as TOML, which is why
#: `"none"` carries its quotes: it is a TOML string, and it is the kebab-case
#: spelling of the `None` exporter variant.
TELEMETRY_ARGV = (
    "-c", "analytics.enabled=false",
    "-c", 'otel.exporter="none"',
    "-c", 'otel.metrics_exporter="none"',
    "-c", 'otel.trace_exporter="none"',
    "-c", "otel.log_user_prompt=false",
)
#: Where the CLI is told to write the agent's last message. The flag takes a
#: FILE; the name below is a single route component and the directory it stands
#: in is the attempt home, so the whole path is minted, used and destroyed inside
#: one spawn.
LAST_MESSAGE_ARGV = ("-o",)
LAST_MESSAGE_NAME = "last-message.txt"
#: The documented sentinel that forces the prompt to be read from stdin. It
#: stands LAST, where the vendor's own usage puts a prompt.
STDIN_PROMPT = "-"
VERSION_ARGV = ("--version",)
#: Capture ceiling for either spawn; the pump drains past it and drops the rest.
CODEX_OUTPUT_LIMIT = 16 * 1024
#: The preflight is a version print, not work: it gets its own small budget.
VERSION_TIMEOUT_SECONDS = 30
#: The two subtrees THIS provider owns beneath the project root.
HOME_DIR = ".codex-home"
MARKER_DIR = ".codex-marker"

#: What this build may say about the file it asked the CLI to write. A CLOSED
#: vocabulary of four words, and never a byte of what the file held: the
#: workspace door answers with a KIND and a size and this module never opens the
#: file, so no model text enters this process through it at all.
#:
#: The three ordinary answers are three different facts, and flattening any two
#: of them would overstate the weaker one. SOURCE's `handle_last_message` writes
#: an EMPTY file and warns on stderr when a run produced no final agent message,
#: so `empty` is a run that finished and said nothing, while `absent` is a run
#: that never reached the point of reporting at all.
ANSWER_ABSENT = "absent"
ANSWER_EMPTY = "empty"
ANSWER_WRITTEN = "written"
#: A name that is not a plain file of this build's own making: a portal, a
#: directory, a second hard link onto bytes that answer elsewhere, or a name whose
#: kind the door could not establish. Never guessed at, never read as a message.
ANSWER_UNREADABLE = "unreadable"
ANSWER_STATES = (ANSWER_ABSENT, ANSWER_EMPTY, ANSWER_WRITTEN, ANSWER_UNREADABLE)
#: The door's closed vocabulary, translated into this module's. It is a mapping
#: rather than four comparisons because the door's words are about what STANDS
#: at a name and this module's are about what a receipt may SAY -- two questions
#: that happen to line up today and are not the same question. A kind absent from
#: here is not silently read as anything.
_ANSWER_BY_KIND = MappingProxyType({
    HOME_LEAF_ABSENT: ANSWER_ABSENT,
    HOME_LEAF_EMPTY: ANSWER_EMPTY,
    HOME_LEAF_FILE: ANSWER_WRITTEN,
    HOME_LEAF_OTHER: ANSWER_UNREADABLE,
})

#: What each answer adds to a receipt that already said what was observed. Every
#: one of them is about the CLI's own REPORTING and none claims anything about
#: the work, because the file says nothing about the work: the vendor writes it
#: whatever the model did, and writes it empty when the model said nothing.
ANSWER_DETAIL = MappingProxyType({
    ANSWER_WRITTEN: (
        " the pinned build also wrote a final message into the file this "
        "dispatch minted for it; that the file has content is a fact about the "
        "CLI's own reporting and is not evidence that the task was read or done"),
    ANSWER_EMPTY: (
        " the pinned build wrote an EMPTY final message file, which is what it "
        "does when a run produced no final agent message at all"),
    ANSWER_ABSENT: (
        " the pinned build wrote no final message file at all, so it never "
        "reached the point where it reports one"),
    ANSWER_UNREADABLE: (
        " what stands at the final message name this dispatch minted is not a "
        "plain file this build can read as one, so nothing about a final "
        "message may be read from it"),
})

#: The ONE closed form this module will read a version out of: the PACKAGE name,
#: then the semver. Anchored at both ends and closed at the front.
#:
#: `codex-cli ` is required and `codex ` is refused, and that is the whole of
#: what this pattern is for. The source declares `bin_name = "codex"`, so a
#: parser written from the source would spell the second and refuse every real
#: install -- while this provider went on advertising itself available and
#: failing every preflight. The form here is what the reviewed binary really
#: prints, observed as 19 bytes.
#:
#: The anchors buy the usual thing: an unanchored pattern finds `0.112.0` inside
#: a warning line and calls that the version. The closed prefix buys what this
#: roster has now paid for twice on another provider: a pattern that accepted a
#: bare semver would accept any executable at all that prints a number, and this
#: preflight is the one check standing between an operator's pin and a real
#: prompt.
_VERSION_FORM = re.compile(r"\Acodex-cli (?P<semver>\d+\.\d+\.\d+)\Z")

__all__ = [
    "ANSWER_ABSENT", "ANSWER_EMPTY", "ANSWER_STATES", "ANSWER_UNREADABLE",
    "ANSWER_WRITTEN", "CODEX_CAPABILITIES", "CODEX_DISPLAY_NAME",
    "CODEX_FORCED_ENV", "CODEX_HOME_ENV", "CODEX_LIFECYCLE", "CODEX_PROTOCOL",
    "CODEX_PROVIDER_ID", "CODEX_SCHEMA_PAIRS", "HOME_DIR", "INSTRUCTION_DIR",
    "LAST_MESSAGE_NAME", "MARKER_DIR", "REVIEWED_CODEX_VERSION", "STDIN_PROMPT",
    "WORK_DIR",
    "CodexAdapter", "CodexCliError", "CodexCliTransport", "codex_pin",
]

#: Every vendor fact above, gathered where the shared transport reads them.
CODEX_PROFILE = HarnessProfile(
    tool_noun="Codex CLI", task_noun="Codex CLI task",
    display_name=CODEX_DISPLAY_NAME, vendor="OpenAI",
    docs_url="https://developers.openai.com/codex/noninteractive",
    reviewed_version=REVIEWED_CODEX_VERSION,
    home_dir=HOME_DIR, marker_dir=MARKER_DIR,
    home_env=CODEX_HOME_ENV, forced_env=CODEX_FORCED_ENV,
    version_argv=VERSION_ARGV, exit_codes_published=False,
    capability=DISPATCH_CAPABILITY, output_limit=CODEX_OUTPUT_LIMIT,
    version_timeout_seconds=VERSION_TIMEOUT_SECONDS,
    home_id_kind="codex-home",
    task_channel=TASK_CHANNEL_STDIN)


class CodexCliError(HeadlessCliError):
    """Codex CLI cannot be driven without breaking one of this adapter's rules."""


def codex_pin(executable: str, env_allow: tuple[str, ...] = ()) -> ExecutablePin:
    """Codex CLI's pin: ONE absolute path, and Codex CLI's own refusal type.

    One, not two. The npm package installs a Node shim that spawns a vendored
    native `codex.exe`, and an operator may pin either that binary or one from a
    release archive; both are a single executable this build puts nothing in
    front of. The shim is a JavaScript file and pinning IT would be pinning the
    interpreter shape, which this provider is not -- so what an operator pins is
    the binary the shim would have run.
    """
    return ExecutablePin(
        executable=executable, error=CodexCliError, env_allow=env_allow)


class CodexCliTransport(HeadlessCliTransport):
    """Run one Codex CLI task per authorized action, and prove nothing more."""

    profile = CODEX_PROFILE
    error = CodexCliError

    def __init__(
            self, pin: ExecutablePin, runner: ProcessRunner, *,
            root: str | Path, clock: Callable[[], str],
            ids: Callable[[str], str],
            adapter_id: str = CODEX_PROVIDER_ID) -> None:
        if type(pin) is not ExecutablePin or pin.error is not CodexCliError:
            raise CodexCliError(
                "this adapter requires a single-executable pin of its own")
        self._pin = pin
        #: What the LAST spawn's final message file turned out to be, in the
        #: closed vocabulary above, or None before any spawn has been read. It is
        #: re-established on every attempt, so a receipt built after a task spawn
        #: is quoting that task's own file and never an earlier dispatch's.
        self._answer: str | None = None
        super().__init__(
            runner, root=root, clock=clock, ids=ids, adapter_id=adapter_id)

    def _argv_prefix(self) -> tuple[str, ...]:
        """One native binary, and nothing in front of it."""
        return (self._pin.executable,)

    def _last_message_path(self, home: Path) -> Path:
        """Where THIS attempt asks the CLI to write the agent's last message.

        Minted rather than configured, and inside the attempt home rather than
        anywhere else. Two roads were refused: the work tree, where the file
        would land in the very evidence snapshot verification reads and make
        "the task changed nothing" unobservable; and the marker namespace, which
        nothing sweeps, where it would be exactly the retained model text the
        home exists to prevent. The home is discarded when the spawn returns, so
        the file's whole lifetime is one spawn.
        """
        return home / LAST_MESSAGE_NAME

    def _stdin_argv(self, home: Path) -> tuple[str, ...]:
        """The code-owned flags. It receives no task, and `-` says where one is.

        That is the guarantee, and it is structural: this method cannot put an
        instruction in the command line because it is never handed one. The one
        thing it IS handed is the home this attempt minted, which is where the
        `-o` file has to stand.

        `-` stands LAST, where the vendor's own usage puts a prompt, and it is
        the documented sentinel for "read the instructions from stdin". Omitting
        the positional entirely reads stdin too, and that road is not taken: a
        build whose stdin channel depended on the ABSENCE of an argument would
        be depending on something no reader of the argv can see.
        """
        return (
            *EXEC_ARGV, *SKIP_GIT_REPO_CHECK_ARGV, *EPHEMERAL_ARGV,
            *COLOR_ARGV, *SANDBOX_ARGV, *TELEMETRY_ARGV,
            *LAST_MESSAGE_ARGV, str(self._last_message_path(home)),
            STDIN_PROMPT)

    def _task_stdin(self, task_text: str) -> bytes:
        """The whole task, piped -- the run's frame and the user's instruction.

        UTF-8, and no trailing newline is added: the bytes handed over are the
        bytes the task text is, so what the child reads is what this build
        composed and nothing it appended. The runner bounds this at the same
        64 KiB the workspace door bounds an instruction body at, and refuses a
        NUL, before any child exists.
        """
        return task_text.encode("utf-8")

    def _env_allow(self) -> tuple[str, ...]:
        return self._pin.env_allow

    def _read_attempt_home(self, home: Path) -> None:
        """Establish what became of the final message file, while the home stands.

        The home is deleted the moment the attempt returns, so this is the only
        moment the question can be asked at all -- and it is asked of the
        WORKSPACE DOOR, which is where every filesystem fact this package needs
        is established. This module never opens the file, never follows a name,
        and never learns a byte of what the child wrote.

        It cannot raise, because it runs on the road out of a spawn that already
        happened and an exception here would replace what the child did with a
        reading error. The door refuses -- with a path in its message -- when the
        route or the name cannot be established; that refusal is caught and
        turned into this module's own word for exactly that, and the message it
        carried goes no further.
        """
        failed = False
        try:
            kind = self._workspace.home_leaf_kind(home, LAST_MESSAGE_NAME)
        except (WorkspaceNotContained, OSError):  # noqa: BLE001 -- no path onward
            failed = True
        if failed:
            self._answer = ANSWER_UNREADABLE
            return
        self._answer = _ANSWER_BY_KIND.get(kind, ANSWER_UNREADABLE)

    def _zero_detail(self) -> str:
        """What an exit of zero is allowed to mean, plus what the CLI reported.

        The shared sentence is unchanged and still does the work: this vendor
        publishes no exit-code contract, so a zero is the process having ended.
        What is added is a SECOND observation of the same spawn -- whether the
        CLI wrote the final message it was told to write -- and it is added
        exactly here because this is the road where a receipt says the least and
        would most easily be read as saying more.

        A closed word chooses the clause, so nothing derived from the file's
        contents can travel with it. A spawn that was never read leaves the
        answer unset and the sentence exactly as the base wrote it.
        """
        detail = super()._zero_detail()
        clause = ANSWER_DETAIL.get(self._answer or "")
        return detail + clause if clause else detail

    def _parsed_version(self, output: bytes) -> str | None:
        r"""The semver this parser reads out of a version print, or ``None``.

        Separate from the yes/no answer, and that separation is the point. A
        BOOLEAN cannot say WHICH question it answered: ``False`` means either
        "a different build", which the adapter is right to refuse, or "this
        parser could not read the published form at all", which no refusal
        repairs -- and a parser accepting NOTHING refuses everything, which
        looks exactly like working correctly.

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
        every real install, because a real one always prints its package name
        first. So the reading is delegated to ``_parsed_version`` -- which reads
        the form the binary really prints, not the one the source's `bin_name`
        describes -- and this method only compares.
        """
        return self._parsed_version(output) == self.profile.reviewed_version


class CodexAdapter(_DeepAdapter):
    """The fake-protocol fixture; the catalog serves ``CodexCliTransport``.

    Kept because the shared ``_DeepAdapter`` lifecycle suites drive two concrete
    subclasses and this is one of them, and kept HERE because it carries the
    ``codex`` id and the identity gate grants that id's rights to this module
    alone.
    """

    ADAPTER_ID = CODEX_PROVIDER_ID
    DISPLAY_NAME = "Codex (fake protocol)"
    VENDOR = "OpenAI-compatible test fixture"
    PROTOCOL = DeepProtocol.FAKE_CODEX_V1
    CODEC = FakeCodexCodec


#: This module's own statement of which concrete type is reviewed for the fake
#: protocol above, read from the class's OWN ``__dict__`` and never inherited.
CodexAdapter.REVIEWED_TYPE = CodexAdapter
