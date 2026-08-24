"""What a provider may DECLARE, proved at construction rather than at first spawn.

A ``HarnessProfile`` is code, written once per provider, so every fault in one is
a programming fault. They used to surface at the FIRST SPAWN instead: a malformed
``forced_env`` row reached ``dict()`` inside the transport's spawn and raised a
raw ``ValueError``, which sailed past the provider's own error type and reached a
caller under a sentence blaming the operator's pinned build. A code-owned mistake
reported as an operator's is worse than a crash, because the operator goes looking
at their install.

The relation that matters most is the home. ``home_env`` carries the value this
dispatch MINTS and DISCARDS -- the whole retention promise -- and ``forced_env``
is a set of literals this build sends alongside it. A pair named for ``home_env``
would relocate the child's home away from the minted one, so the tool would write
its config, sessions and credentials somewhere nothing sweeps. That is refused
here, at construction.

What a profile DECLARES also decides which seams its class owes, so the two
structural claims about those seams are held here rather than in a provider's
own suite: the stdin channel's argv builder cannot see a task, and the one
reading a provider gets of its attempt home happens while that home still
stands. Both are about the base, so neither belongs to whichever provider
happens to exercise it today.

The transport also writes the minted home LAST, after unpacking ``forced_env``,
so the promise would hold even if this validation were bypassed. No test can
catch an inversion of that ordering, and deliberately so: construction refuses
the only configuration in which the order could matter. The defence in depth is
therefore documented rather than pinned, and what IS pinned is the refusal.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from conductor.command.adapters.harness_profile import (
    TASK_CHANNEL_ARGV,
    TASK_CHANNEL_STDIN,
    TASK_CHANNELS,
    HarnessProfile,
    HeadlessCliError,
)
from conductor.command.adapters.harness_workspace import WORK_DIR
from conductor.command.adapters.headless_cli import HeadlessCliTransport
from conductor.command.adapters.process import ProcessOutcome, ProcessRunner
from conductor.command.providers import PROVIDER_CATALOG

#: Fields every profile below shares; only what a case is about varies.
BASE = dict(
    tool_noun="Probe", task_noun="Probe prompt", display_name="Probe (test)",
    vendor="nobody", docs_url="https://example.invalid/",
    reviewed_version="1.0.0", home_dir=".probe-home",
    marker_dir=".probe-marker", home_env="PROBE_HOME",
    version_argv=("--version",), exit_codes_published=False,
    home_id_kind="probe-home")


def a_profile(**changes) -> HarnessProfile:
    values = {**BASE, "forced_env": ()}
    values.update(changes)
    return HarnessProfile(**values)


def test_a_profile_that_declares_nothing_unusual_is_accepted():
    """The happy path, so every refusal below is about what it names."""
    profile = a_profile(forced_env=(("PROBE_TELEMETRY", "0"),))

    assert profile.forced_env == (("PROBE_TELEMETRY", "0"),)
    assert profile.home_env == "PROBE_HOME"


def test_forcing_the_home_variable_is_refused_because_it_would_relocate_the_home():
    """The one that would break the retention promise outright.

    A pair named for ``home_env`` overwrites the home this dispatch minted and
    discards, so the tool writes its config, sessions and credentials into a
    directory nothing sweeps -- and the receipt still says the home was taken
    back, because as far as the transport knows it discarded the one it made.
    """
    with pytest.raises(HeadlessCliError, match="relocate the child's home"):
        a_profile(forced_env=(("PROBE_HOME", "/somewhere/else"),))


def test_a_variable_forced_twice_is_refused_rather_than_silently_collapsed():
    """``dict()`` would keep the last and lose the first, saying nothing."""
    with pytest.raises(HeadlessCliError, match="forced twice"):
        a_profile(forced_env=(("PROBE_TELEMETRY", "0"), ("PROBE_TELEMETRY", "1")))


@pytest.mark.parametrize("name", ("", "9LEADING", "HAS-DASH", "HAS SPACE", "a=b"))
def test_a_forced_name_that_is_not_an_environment_variable_is_refused(name):
    with pytest.raises(HeadlessCliError, match="environment variable name"):
        a_profile(forced_env=((name, "0"),))


def test_a_home_variable_that_is_not_an_environment_variable_is_refused():
    with pytest.raises(HeadlessCliError, match="environment variable name"):
        a_profile(home_env="not a name")


@pytest.mark.parametrize("value", ("has\x00nul", 0, None, ("0",)))
def test_a_forced_value_that_is_not_nul_free_text_is_refused(value):
    with pytest.raises(HeadlessCliError, match="NUL-free text"):
        a_profile(forced_env=(("PROBE_TELEMETRY", value),))


@pytest.mark.parametrize("row", (
    ("ONLY_ONE",), ("A", "0", "extra"), "AB", ["A", "0"], None))
def test_a_row_that_is_not_a_name_value_pair_is_refused(row):
    """This is the shape that used to reach the first spawn as a ValueError."""
    with pytest.raises(HeadlessCliError, match="\\(name, value\\) pair"):
        a_profile(forced_env=(row,))


def test_every_catalogued_provider_carries_a_profile_this_module_would_accept():
    """The rules above are worth nothing if no shipped provider is held to them.

    Each catalogued transport's profile was built at import time, so it already
    passed; re-validating it here is what stops a future provider from being the
    one case nobody checked, and it fails at collection rather than at a spawn.
    """
    checked = 0
    for provider_id, entry in PROVIDER_CATALOG.items():
        profile = getattr(entry.adapter_class, "profile", None)
        if profile is None:
            continue  # a fixture adapter declares no transport profile
        rebuilt = HarnessProfile(**{
            field: getattr(profile, field)
            for field in profile.__dataclass_fields__})
        assert rebuilt == profile, f"{provider_id}'s profile did not survive a rebuild"
        assert profile.home_env not in dict(profile.forced_env), (
            f"{provider_id} forces its own home variable")
        checked += 1
    assert checked >= 3, f"only {checked} profiles were checked, so this proved little"


# --- where a task travels, and why that is a TYPE rather than a check --------


def test_a_profile_that_names_no_channel_takes_the_argv_one_it_always_had():
    """The three providers that shipped before this field must not notice it."""
    assert a_profile().task_channel == TASK_CHANNEL_ARGV
    for provider_id in ("deepseek-harness", "kimi-code", "grok-build"):
        entry = PROVIDER_CATALOG[provider_id]
        assert entry.adapter_class.profile.task_channel == TASK_CHANNEL_ARGV, (
            f"{provider_id} changed channel")


def test_a_task_travels_by_one_of_two_channels_and_a_third_word_is_refused():
    """A closed vocabulary, refused at construction like every other one here.

    Left open, a typo would fall through the transport's `== "stdin"` test and
    be served as the argv channel -- which for a provider that meant stdin puts
    the operator's whole instruction on the command line, silently.
    """
    assert TASK_CHANNELS == (TASK_CHANNEL_ARGV, TASK_CHANNEL_STDIN)

    for rejected in ("STDIN", "pipe", "argv ", "", None):
        with pytest.raises(HeadlessCliError, match="a task travels by one of"):
            a_profile(task_channel=rejected)


def test_a_provider_on_the_stdin_channel_cannot_be_handed_the_task_in_its_argv():
    """The structural claim, derived from the catalog rather than from a name.

    This is what replaced a check that did not work. The earlier seam called the
    argv builder twice with two probe texts and compared the answers; a review
    probe defeated it in one line by returning a constant for both probes and
    embedding the real instruction for anything else. The guard reported the
    argv safe while the operator's task rode it, because two observations are
    not independence.

    What IS independence is an absent parameter. So the assertion is about the
    SIGNATURE: on the stdin channel the argv builder is handed exactly the two
    values it is allowed to see, and the cheating shape is not something a
    provider can express.

    Both parameters are SPELLED, in order, rather than counted, and that is the
    whole difference between this claim and a weaker one. `home` is a project
    subtree the transport minted from an id mint moments earlier. `model` is the
    id the run's frozen configuration pinned for this action's instance, and it
    was added deliberately when deployments gained the right to route one -- a
    parameter added, and therefore a claim rewritten, rather than a guard left
    saying something that had stopped being true.

    A third parameter, or either of these under another name, is a seam somebody
    widened -- and widening it is the only way an instruction could arrive here.
    Where each value comes FROM is the other half, and it is held by the two
    tests below: one for the frame that hands the builder over uncalled, one for
    the frame that calls it.
    """
    on_stdin = [
        entry for entry in PROVIDER_CATALOG.values()
        if getattr(entry.adapter_class, "profile", None) is not None
        and entry.adapter_class.profile.task_channel == TASK_CHANNEL_STDIN]
    assert on_stdin, "no provider takes its task on stdin, so this proves nothing"

    for entry in on_stdin:
        for seam in ("_stdin_argv", "_review_argv"):
            builder = getattr(entry.adapter_class, seam, None)
            if builder is None:
                continue
            names = inspect.signature(builder).parameters
            assert [name for name in names if name != "self"] == [
                "home", "model"], (
                f"{entry.provider_id}'s {seam} can see more than its attempt "
                "home and the routed model")


class _Piped(HeadlessCliTransport):
    """A stdin-channel provider whose builder records what it was handed."""

    # A model flag of its own, because what the second test is about is that
    # the ROUTED value reaches the builder -- a profile declaring none would
    # render every model as nothing and the case would pass for the wrong
    # reason.
    profile = a_profile(
        task_channel=TASK_CHANNEL_STDIN, model_flag="--probe-model-flag")
    error = HeadlessCliError
    seen: list[object] = []

    def _stdin_argv(self, home, model):
        type(self).seen.append((home, model))
        return ("--flag", str(home), *self._model_argv(model))

    def _task_stdin(self, task_text):
        return task_text.encode("utf-8")


def _a_piped_transport() -> _Piped:
    _Piped.seen = []
    return _Piped(
        ProcessRunner("."), root=".", clock=lambda: "", ids=lambda p: p,
        adapter_id="probe")


def test_the_stdin_builder_is_handed_over_uncalled_by_the_frame_holding_the_task():
    """The parameter is proved harmless by WHERE its one value comes from.

    A signature says the task is not a parameter. It does not say what the
    parameters that ARE there hold, and a seam handed the task under the name
    `home` would satisfy the signature test above while defeating everything it
    stands for. Two frames settle that, and this is the first: `_task_command`
    is the only frame holding the task AND the builder, and it hands the builder
    over UNCALLED. Nothing in it can curry an argument, and the object it
    returns is the plain function the subclass declared.

    Driven against the real base rather than described, so a future edit that
    started calling the builder in the frame that holds the task reds here.
    """
    piped = _a_piped_transport()

    source, payload = piped._task_command("PROBE-INSTRUCTION-TEXT")

    assert _Piped.seen == [], "the frame holding the task called the builder"
    assert getattr(source, "__func__", None) is _Piped._stdin_argv
    assert payload == b"PROBE-INSTRUCTION-TEXT"


def test_the_stdin_builder_is_called_only_with_the_minted_home_and_the_model():
    """The second frame: `_tokens`, the only place a builder is ever called.

    The two values it has to call with are the home `_attempt` minted and the
    model the run's frozen configuration pinned. There is no `task_text` in that
    frame to pass even by accident, and what the builder SEES is asserted rather
    than assumed -- a transport that quietly dropped the routed value would
    otherwise leave every argv test above still green.

    The ready-argv road is the control, and it carries a fact of its own: a
    provider on the argv channel hands tokens straight through and is handed no
    model. The version preflight travels that road, and a preflight carrying a
    model would be a build asked to load one in order to print its version.
    """
    piped = _a_piped_transport()
    source, _payload = piped._task_command("PROBE-INSTRUCTION-TEXT")
    minted = Path("probe-home-1")

    assert HeadlessCliTransport._tokens(source, minted, None) == (
        "--flag", str(minted))
    assert _Piped.seen == [(minted, None)]
    assert HeadlessCliTransport._tokens(source, minted, "probe-model") == (
        "--flag", str(minted), "--probe-model-flag", "probe-model")
    assert _Piped.seen[-1] == (minted, "probe-model")
    assert HeadlessCliTransport._tokens(("--ready",), minted, None) == ("--ready",)
    assert HeadlessCliTransport._tokens(("--ready",), minted, "probe-model") == (
        "--ready",)


class _Recording(ProcessRunner):
    """A runner that starts nothing and answers every spec the same way.

    A real child is not what this claim is about: what is under test is WHERE
    the base calls a provider's reading of its own attempt home, and a spawn
    that really ran would only add ways for the test to fail for other reasons.
    """

    def run(self, spec):
        return ProcessOutcome(
            status="completed", exit_code=0, output=b"", output_truncated=False,
            output_limit=spec.output_limit, pid=0, token="probe-token")


def test_the_home_reading_a_provider_gets_happens_before_the_home_is_discarded(
        tmp_path):
    """The window is the point of the seam, so the window is what is asserted.

    A provider that asks its vendor to write an artefact into the profile home
    this build mints has exactly one moment to read it: the home is deleted the
    instant `_attempt` returns, and that deletion is the retention promise
    rather than tidiness. So a reading placed after it would find nothing, every
    time, and would look like a vendor that wrote nothing.

    Read from inside the seam, by an independent witness -- the filesystem --
    rather than by trusting the order the source is written in.
    """
    class _Reader(HeadlessCliTransport):
        profile = a_profile()
        error = HeadlessCliError
        readings: list[tuple[bool, bool]] = []

        def _argv_prefix(self):
            return ("probe",)

        def _env_allow(self):
            return ()

        def _read_attempt_home(self, home):
            # BOTH facts, from the disk: the home this spawn was given still
            # stands, and a file the child could have written inside it is
            # still readable. A reading after the discard sees neither.
            type(self).readings.append(
                (home.is_dir(), (home / "written-by-the-child").is_file()))

    reader = _Reader(
        _Recording(tmp_path), root=tmp_path, clock=lambda: "",
        ids=lambda purpose: f"{purpose}-1", adapter_id="probe")
    reader._workspace.work_root()
    spawn = reader._spawn

    def writing(argv, home, cwd, **kwargs):   # stand in for the vendor writing
        outcome = spawn(argv, home, cwd, **kwargs)
        (home / "written-by-the-child").write_text("x", encoding="utf-8")
        return outcome

    reader._spawn = writing
    reader._attempt(("--version",), WORK_DIR, timeout=30)

    assert _Reader.readings == [(True, True)], (
        "the provider's reading of its attempt home did not happen while the "
        "home stood, so nothing a vendor wrote there could ever be read")
    standing = sorted(p.name for p in reader._workspace.homes_root().iterdir())
    assert standing == [], f"A_HOME_OUTLIVED_ITS_SPAWN={standing}"


def test_the_base_reads_nothing_out_of_an_attempt_home_by_itself():
    """The default is empty, and a provider that asked for nothing sees nothing.

    Said as its own claim because the seam is a road INTO a directory this
    build promises to discard unread. The base names no artefact and must never
    grow a guess at one.
    """
    assert HeadlessCliTransport._read_attempt_home(
        object(), Path("nowhere-at-all")) is None


def test_a_profile_may_declare_the_stdin_channel_only_where_a_class_honours_it():
    """A declaration the class cannot keep is refused before any run stands on it.

    A profile can say `stdin`; only the concrete adapter can implement it. Left
    to the first dispatch, the mismatch would surface as `NotImplementedError`
    in the middle of an operator's authorized action.
    """
    class _Half(HeadlessCliTransport):
        profile = a_profile(task_channel=TASK_CHANNEL_STDIN)
        error = HeadlessCliError

        def _stdin_argv(self, home):
            return ("--probe", str(home))

    with pytest.raises(HeadlessCliError, match="owes its own _task_stdin"):
        _Half(ProcessRunner("."), root=".", clock=lambda: "", ids=lambda _p: "",
              adapter_id="probe")
