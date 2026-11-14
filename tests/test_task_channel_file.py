"""A third task channel, `file`, and the one place the task is written for it (I1).

Nothing in the roster uses the channel yet, so every witness here is a TEST profile that declares
it, or Claude Code with its profile and its argv builders replaced for the length of one test (a
witness, never a provider). What is held:

- the vocabulary: three channels, two of them off the command line, one fixed ASCII file name that
  is never `.json`, and a profile that refuses a login list carrying that name;
- the seams a class owes for a channel off the command line are owed for this one too, and the
  argv builder of such a class is still handed no task;
- `attempt_spec` is the ONE place the task is written: for a task attempt (dispatch or review) on
  a file-channel profile the child gets no stdin and the argv names a file that holds the task AT
  THE MOMENT THE CHILD IS RUN; a version print or a status question is not touched, and a profile
  on any other channel is not touched;
- on the project road a refusal is the transport's own "could not start" error, with nothing run
  and no home left; on the relay road it is `NotStarted("spec")` -- no claim, no child, no home,
  and a login lease that is not poisoned;
- the order on the relay road: copy in, the file placed, the boundary entered, the claim, the run;
- the file goes with the copy of the login, first, even when the whole home cannot be removed;
- the grant: the channel is a fact of the digest, with the same bound and unit as stdin.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path

import pytest

from conductor.command.adapters import harness_profile, login_relay, task_file
from conductor.command.adapters.artifact_transport import ArtifactAwareTransport
from conductor.command.adapters.claude_code import CLAUDE_PROFILE, ClaudeCodeTransport
from conductor.command.adapters.claude_relay import CLAUDE_RELAY
from conductor.command.adapters.harness_profile import HeadlessCliError
from conductor.command.adapters.harness_workspace import WORK_DIR
from conductor.command.adapters.headless_cli import HeadlessCliTransport
from conductor.command.adapters.process import STDIN_LIMIT, ProcessOutcome, ProcessRunner
from conductor.command.policy_providers import task_channel_fact

from tests import _fakeclaude
from tests import test_command_claude_transport as claude_t
from tests.relay_roads import CLAUDE, Site
from tests.test_harness_profile import a_profile
from tests.test_relay_profiles import an_authority

NAME = "conduct-task.txt"
FILE_FACT = {"channel": "file", "limit": 262144, "unit": "utf8_bytes", "scope": "task"}
SPEC_SENTENCE = ("the Claude Code attempt could not start in isolation: the command of the "
                 "attempt could not be built for its relay home, so no task was spawned")


# -- 1. the vocabulary ---------------------------------------------------------------------------


def test_the_channels_the_profile_knows_and_the_name_the_file_is_given():
    assert getattr(harness_profile, "TASK_CHANNEL_FILE", None) == "file"
    assert getattr(harness_profile, "TASK_CHANNELS", None) == ("argv", "stdin", "file")
    assert getattr(harness_profile, "OFF_ARGV_CHANNELS", None) == ("stdin", "file")
    name = getattr(harness_profile, "TASK_FILE_NAME", None)
    assert name == NAME
    assert name.isascii() and not name.endswith(".json"), "the vendor reads .json differently"


def test_a_profile_may_declare_the_file_channel_and_a_fourth_word_is_still_refused():
    profile = a_profile(task_channel="file")

    assert profile.task_channel == "file"
    assert replace(profile) == profile
    for rejected in ("FILE", "files", "pipe", "", None):
        with pytest.raises(HeadlessCliError, match="a task travels by one of"):
            a_profile(task_channel=rejected)


@pytest.mark.parametrize("field", [
    "login_scratch", "login_expected", "login_credentials", "login_forbidden"])
@pytest.mark.parametrize("channel", ["file", "argv"])
def test_no_login_list_may_carry_the_name_the_task_file_is_given(field, channel):
    with pytest.raises(HeadlessCliError, match="task file"):
        a_profile(task_channel=channel, **{field: (NAME,)})


def test_the_files_of_a_relay_may_not_carry_the_name_either():
    files = (*CLAUDE_RELAY.files, NAME)

    with pytest.raises(HeadlessCliError, match="task file"):
        replace(CLAUDE_PROFILE, login_relay=replace(CLAUDE_RELAY, files=files))


# -- 2. the seams a class owes, and the argv builder that is handed no task ---------------------


def _a_file_class(channel: str = "file"):
    """A provider on a channel off the command line, whose builder names the file and sees no
    task. A function, so a profile that cannot be built fails in the test that asked for it."""
    class _File(HeadlessCliTransport):
        profile = a_profile(task_channel=channel)
        error = HeadlessCliError
        seen: list = []

        def _argv_prefix(self):
            return ("probe",)

        def _env_allow(self):
            return ()

        def _stdin_argv(self, home, model):
            type(self).seen.append((home, model))
            return ("--prompt-file", task_file.path_in(home))

        def _task_stdin(self, task_text):
            return task_text.encode("utf-8")
    return _File


class _Reading(ProcessRunner):
    """Starts nothing; reads the file the argv names at the moment a child would be started."""

    def __init__(self, root) -> None:
        super().__init__(root)
        self.runs: list[dict] = []

    def run(self, spec):  # type: ignore[override]
        row = {"argv": spec.argv, "stdin": spec.stdin_bytes, "file": None, "standing": None}
        if "--prompt-file" in spec.argv:
            path = Path(spec.argv[spec.argv.index("--prompt-file") + 1])
            row["file"] = path.read_bytes() if path.is_file() else None
            row["standing"] = sorted(os.listdir(path.parent)) if path.parent.is_dir() else None
        self.runs.append(row)
        return ProcessOutcome(
            status="completed", exit_code=0, output=b"", output_truncated=False,
            output_limit=spec.output_limit, pid=0, token="probe")


def _a_file_transport(tmp_path: Path, channel: str = "file"):
    runner = _Reading(tmp_path)
    transport = _a_file_class(channel)(
        runner, root=tmp_path, clock=lambda: "", ids=lambda kind: f"{kind}-1", adapter_id="probe")
    transport._workspace.work_root()
    return transport, runner


def test_a_class_on_the_file_channel_owes_the_two_seams_a_stdin_class_owes():
    class _Half(HeadlessCliTransport):
        profile = a_profile(task_channel="file")
        error = HeadlessCliError

        def _stdin_argv(self, home, model):
            return ("--probe", str(home))

    with pytest.raises(HeadlessCliError, match="owes its own _task_stdin"):
        _Half(ProcessRunner("."), root=".", clock=lambda: "", ids=lambda _p: "",
              adapter_id="probe")


def test_the_file_builder_is_handed_over_uncalled_by_the_frame_holding_the_task(tmp_path):
    transport, _runner = _a_file_transport(tmp_path)

    source, payload = transport._task_command("PROBE-INSTRUCTION-TEXT")

    assert type(transport).seen == [], "the frame holding the task called the builder"
    assert getattr(source, "__func__", None) is type(transport)._stdin_argv
    assert payload == b"PROBE-INSTRUCTION-TEXT"


def test_a_review_provider_may_take_its_task_by_file_and_may_not_take_it_on_the_command_line(
        tmp_path):
    def reviewer(channel):
        class _Reviewer(ArtifactAwareTransport):
            profile = a_profile(task_channel=channel)
            error = HeadlessCliError
            review_enabled = True

            def _argv_prefix(self):
                return ("probe",)

            def _env_allow(self):
                return ()

            def _stdin_argv(self, home, model):
                return ()

            def _review_argv(self, home, model):
                return ()

            def _task_stdin(self, task_text):
                return task_text.encode("utf-8")

            def _task_argv(self, task_text):
                return (task_text,)
        return _Reviewer(ProcessRunner(tmp_path), root=tmp_path, clock=lambda: "",
                         ids=lambda kind: f"{kind}-1", adapter_id="probe")

    assert "review" in reviewer("file").manifest.capabilities
    with pytest.raises(HeadlessCliError, match="requires the stdin or file channel"):
        reviewer("argv")


# -- 3. attempt_spec: the one place the task is written -----------------------------------------


@pytest.mark.parametrize("mode", ["dispatch", "review"])
def test_a_task_attempt_gets_no_stdin_and_a_file_that_holds_the_task_when_the_child_runs(
        tmp_path, mode):
    transport, runner = _a_file_transport(tmp_path)
    argv, payload = transport._task_command("The task, with Cyrillic: Привет")

    transport._attempt(argv, WORK_DIR, timeout=30, stdin_bytes=payload, mode=mode)

    home = tmp_path.resolve() / ".probe-home" / "probe-home-1"
    (row,) = runner.runs
    assert row["argv"] == ("probe", "--prompt-file", str(home / NAME))
    assert row["stdin"] is None
    assert row["file"] == "The task, with Cyrillic: Привет".encode("utf-8")
    assert row["standing"] == [NAME]
    assert not home.exists(), "the home, and the task file in it, outlived the spawn"


def test_a_question_to_the_vendor_is_not_a_task_and_keeps_what_it_was_given(tmp_path):
    transport, runner = _a_file_transport(tmp_path)

    transport._attempt(("--version",), WORK_DIR, timeout=30)
    transport._attempt(transport._stdin_argv, WORK_DIR, timeout=30, stdin_bytes=b"kept as is")

    version, status = runner.runs
    assert (version["argv"], version["stdin"], version["file"]) == (
        ("probe", "--version"), None, None)
    assert status["stdin"] == b"kept as is" and status["file"] is None


def test_a_task_attempt_without_a_payload_places_no_file(tmp_path):
    transport, runner = _a_file_transport(tmp_path)

    transport._attempt(transport._stdin_argv, WORK_DIR, timeout=30, mode="dispatch")

    (row,) = runner.runs
    assert row["stdin"] is None and row["file"] is None


def test_a_provider_on_the_stdin_channel_is_handed_its_stdin_and_no_file(tmp_path):
    transport, runner = _a_file_transport(tmp_path, "stdin")

    transport._attempt(transport._stdin_argv, WORK_DIR, timeout=30, stdin_bytes=b"piped",
                       mode="dispatch")

    (row,) = runner.runs
    assert row["stdin"] == b"piped" and row["file"] is None


@pytest.mark.parametrize("payload", [b"\xff\xfe", b" \n "], ids=["not-utf8", "blank"])
def test_a_task_the_file_cannot_hold_is_the_transports_own_error_with_nothing_run(
        tmp_path, payload):
    transport, runner = _a_file_transport(tmp_path)

    with pytest.raises(HeadlessCliError, match="could not start the pinned build"):
        transport._attempt(transport._stdin_argv, WORK_DIR, timeout=30, stdin_bytes=payload,
                           mode="dispatch")

    assert runner.runs == []
    assert list((tmp_path / ".probe-home").iterdir()) == [], "a home outlived a refused spawn"


# -- 4. the relay road, driven end to end over Claude Code on a file channel --------------------


def _claude_on_the_file_channel(monkeypatch):
    """Claude Code, for one test, as a provider whose task travels by file. Never shipped."""
    monkeypatch.setattr(
        ClaudeCodeTransport, "profile", replace(CLAUDE_PROFILE, task_channel="file"))
    monkeypatch.setattr(
        ClaudeCodeTransport, "_stdin_argv",
        lambda self, home, model: ("--prompt-file", task_file.path_in(home)))


def _answers(site: Site) -> None:
    """The child of a task is answered, not started; the questions before it still run."""
    site.runner.outcome = ProcessOutcome(
        status="completed", exit_code=0, output=b"done", output_truncated=False,
        output_limit=16 * 1024, pid=0, token="answered")


def test_the_relay_road_places_the_file_after_the_copy_and_before_the_boundary(
        monkeypatch, tmp_path):
    _claude_on_the_file_channel(monkeypatch)
    site = Site(tmp_path, CLAUDE)
    _answers(site)
    request, seen = site.request(), {}

    def at_entry(entry):
        home = Path(entry.folders.home)
        seen["entry"] = (sorted(path.name for path in home.iterdir()), site.claimed(request))

    def at_run(spec):
        path = Path(spec.argv[spec.argv.index("--prompt-file") + 1])
        seen["run"] = (path.parent.parent, path.name, hashlib.sha256(path.read_bytes()).hexdigest(),
                       spec.stdin_bytes, site.claimed(request))

    site.runner.hooks["enter"], site.runner.hooks["run"] = at_entry, at_run
    receipt = site.run(request)

    task = site.adapter._task_text(
        site.adapter._dispatch_args(request.arguments), claude_t.INSTRUCTION_BODY)
    assert receipt.outcome == "succeeded", receipt.detail
    assert seen["entry"] == ([".claude.json", ".credentials.json", NAME], False)
    assert seen["run"] == (site.relay_dir, NAME, hashlib.sha256(task.encode("utf-8")).hexdigest(),
                           None, True)
    assert site.leftovers() == [], "the relay home, and the task in it, outlived the attempt"
    assert not any(path.name == NAME for path in tmp_path.rglob("*"))


def test_a_task_file_that_cannot_be_placed_stops_the_relay_road_before_the_claim(
        monkeypatch, tmp_path):
    _claude_on_the_file_channel(monkeypatch)

    def refused(home, payload, homes_root):
        raise task_file.TaskFileRefused("home")
    monkeypatch.setattr(task_file, "place", refused)
    site = Site(tmp_path, CLAUDE)
    request = site.request()

    receipt = site.run(request)

    assert (receipt.outcome, receipt.detail) == ("failed", SPEC_SENTENCE)
    assert site.tasks() == [] and site.runner.entries == [] and not site.claimed(request)
    assert site.leftovers() == [] and site.lease_is_free()


def test_an_os_error_of_the_disk_never_reaches_the_login_lease(monkeypatch, tmp_path):
    """A raw error raised inside the lease would poison the login until the machine restarts."""
    _claude_on_the_file_channel(monkeypatch)

    def denied(*arguments, **options):
        raise PermissionError(13, "the disk said no")

    class _Denying:
        def __getattr__(self, name):
            return denied if name == "open" else getattr(os, name)
    monkeypatch.setattr(task_file, "os", _Denying())
    site = Site(tmp_path, CLAUDE)
    request = site.request()

    receipt = site.run(request)

    assert (receipt.outcome, receipt.detail) == ("failed", SPEC_SENTENCE)
    assert not site.claimed(request) and site.leftovers() == []
    assert site.lease_is_free(), "the login lease was left uncertain by a disk error"


def _recording_sweeps(monkeypatch):
    names = {"sweep": [], "discard": []}
    real_sweep, real_discard = login_relay.sweep, login_relay.discard

    def sweep(root, key, kind, files=()):
        names["sweep"].append(tuple(files))
        return real_sweep(root, key, kind, files)

    def discard(home, files=()):
        names["discard"].append(tuple(files))
        return real_discard(home, files)
    monkeypatch.setattr(login_relay, "sweep", sweep)
    monkeypatch.setattr(login_relay, "discard", discard)
    return names


def test_the_task_file_goes_with_the_copy_of_the_login_in_the_first_names_taken_away(
        monkeypatch, tmp_path):
    _claude_on_the_file_channel(monkeypatch)
    names = _recording_sweeps(monkeypatch)
    site = Site(tmp_path, CLAUDE)
    _answers(site)

    site.run()

    first = (".credentials.json", ".claude.json", NAME)
    assert names["sweep"] and set(names["sweep"]) == {first}
    assert names["discard"] and set(names["discard"]) == {first}


def test_a_provider_that_takes_its_task_another_way_is_taken_back_by_the_names_it_always_was(
        monkeypatch, tmp_path):
    names = _recording_sweeps(monkeypatch)
    site = Site(tmp_path, CLAUDE, **{_fakeclaude.WRITE_FILE: "result.txt:done"})

    assert site.run().outcome == "succeeded"

    always = (".credentials.json", ".claude.json")
    assert names["sweep"] and set(names["sweep"]) == {always}
    assert names["discard"] and set(names["discard"]) == {always}


def test_the_task_file_is_gone_even_when_the_whole_home_cannot_be_removed(monkeypatch, tmp_path):
    _claude_on_the_file_channel(monkeypatch)
    real = login_relay._remove_tree
    left = []

    def tree(top):
        if Path(top).name.startswith("c-") and Path(top).parent.parent.name == "relay":
            left.append(sorted(os.listdir(top)))
            raise PermissionError(13, "a file the child still holds")
        return real(top)
    monkeypatch.setattr(login_relay, "_remove_tree", tree)
    site = Site(tmp_path, CLAUDE)
    _answers(site)

    site.run()

    (standing,) = site.leftovers()
    assert left == [[]], "the credential copy and the task file were not taken first"
    assert sorted(os.listdir(site.relay_dir / standing)) == []


# -- 5. what a grant binds -----------------------------------------------------------------------


def test_the_file_channel_is_a_bound_with_the_unit_and_scope_of_stdin():
    assert task_channel_fact(a_profile(task_channel="file")) == FILE_FACT
    assert task_channel_fact(a_profile(task_channel="stdin")) == {**FILE_FACT, "channel": "stdin"}
    assert FILE_FACT["limit"] == STDIN_LIMIT


def test_a_provider_on_the_file_channel_changes_the_digest_of_a_grant_and_says_so(
        monkeypatch, tmp_path):
    authority, run_config = an_authority(tmp_path, "claude")
    before = authority.digest(run_config)
    _claude_on_the_file_channel(monkeypatch)

    facts = authority.facts(run_config)["providers"][0]

    assert facts["task_channel"] == FILE_FACT
    assert facts["transport"]["task_channel"] == "file"
    assert authority.digest(run_config) != before
