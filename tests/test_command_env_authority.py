"""What an operator's `env_allow` may and may not carry, and why the line is there.

`env_allow` is operator authority: a name written into `conductor/providers.json`
reaches the child of a pinned vendor build with the parent's value. That is the
right shape for a credential and for tool discovery, and the wrong shape for a
variable the child's own runtime reads BEFORE the reviewed entrypoint runs.

The distinction this suite pins is not "dangerous-sounding name" but a relation:

- `PATH` and its kin select a SEPARATE program that the child may choose to
  start. The reviewed entrypoint still runs first, and still decides.
- `LD_PRELOAD`, `PYTHONPATH`, `NODE_OPTIONS` and the rest select code loaded
  INTO the reviewed process. The pin says which build runs; these say what runs
  inside it, ahead of the build's own first instruction. Pinning an absolute
  executable and then letting an operator name one of these hands back exactly
  the authority the pin was taken to hold.

Both halves are tested, per name, in both directions -- a refusal suite that
only lists banned spellings stays green against a validator that bans
everything, and a permit suite that only lists benign ones stays green against a
validator that bans nothing.

The ruling and its stated limits are `docs/adr/0007-env-allow-trust-boundary.md`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from conductor.command.adapters.base import AdapterContractError
from conductor.command.adapters.process import (
    INJECTING_ENV,
    CommandSpec,
    CommandSpecError,
    OwnershipError,
    ProcessAdapter,
    ProcessRunner,
    injecting_env_reason,
)
from conductor.command.contracts import ActionRequest

NOW = "2026-08-28T10:00:00Z"
DIGEST = "sha256:" + "0" * 64

#: Every name this build refuses in `env_allow`, written out literally rather
#: than imported from the module under test: a roster read back from its own
#: source proves only that the source is self-consistent. Set equality against
#: the production table is asserted below, so an addition on either side reds.
REFUSED = (
    # the ELF dynamic loader, ahead of any native entrypoint
    "LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH",
    # macOS dyld, likewise
    "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FALLBACK_FRAMEWORK_PATH",
    # CPython, which is half of every interpreter+entrypoint pin
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONEXECUTABLE",
    # node
    "NODE_OPTIONS", "NODE_PATH", "NODE_REPL_EXTERNAL_MODULE",
    # the JVM
    "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH",
    # the .NET host
    "DOTNET_STARTUP_HOOKS", "CORECLR_ENABLE_PROFILING", "CORECLR_PROFILER",
    "CORECLR_PROFILER_PATH", "COR_ENABLE_PROFILING", "COR_PROFILER",
    "COR_PROFILER_PATH",
    # ruby and perl
    "RUBYOPT", "RUBYLIB", "PERL5OPT", "PERL5LIB", "PERLLIB",
)

#: Names an operator has a real reason to write and this build must keep
#: admitting. Credentials are the whole point of the mechanism; the discovery
#: variables are what a vendor CLI needs to find `git`, `node` or a helper it
#: shells out to; the platform trio is what a real Windows child needs to run
#: at all. None of them chooses code that loads into the reviewed process.
ADMITTED = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDE_API_KEY",
    "KIMI_MODEL_API_KEY", "DSH_API_KEY", "XAI_API_KEY", "MOONSHOT_API_KEY",
    "PATH", "PATHEXT", "COMSPEC",
    "SystemRoot", "TEMP", "HOME", "USERPROFILE", "LANG", "HTTPS_PROXY",
)

#: Names that CONTAIN a refused one, or are contained by it. A substring or
#: prefix rule -- the shape a deny-list drifts into -- refuses every row here
#: while still passing every assertion in the refusal test above it.
LOOKALIKES = (
    "PATHEXT", "PATH_TO_TOOL", "LD_PRELOADS", "MY_LD_PRELOAD",
    "LD_PRELOAD_NOTES", "PRELOAD", "PYTHONPATHX", "MY_PYTHONPATH",
    "NODE_OPTIONS_FILE", "CLASSPATH_FILE", "RUBYOPTIONS",
)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "project" / "work").mkdir(parents=True)
    return tmp_path / "project"


@pytest.fixture
def runners():
    """A factory that drains every runner it built, so no child outlives a test."""
    built = []

    def make(project_root, **kwargs):
        runner = ProcessRunner(project_root, **kwargs)
        built.append(runner)
        return runner

    yield make
    for runner in built:
        for token in runner.active_tokens():
            try:
                runner.stop(token)
            except OwnershipError:
                pass


def _ids():
    counters: dict[str, int] = {}

    def mint(purpose: str) -> str:
        counters[purpose] = counters.get(purpose, 0) + 1
        return f"{purpose}-{counters[purpose]}"

    return mint


def _request(arguments: dict) -> ActionRequest:
    return ActionRequest(
        action_id="act-1", run_id="run-1", attempt_id="att-1",
        instance_id="inst-1", capability="dispatch", arguments=arguments,
        scope=("work",), requested_by="tester", requested_at=NOW,
        idempotency_key="idem-1", timeout_seconds=10, preview_digest=DIGEST,
        mode="confirm")


# --- the refusal, per name, at the process boundary ---


@pytest.mark.parametrize("name", REFUSED)
def test_a_variable_that_loads_code_into_the_reviewed_process_is_refused(name):
    """Named one at a time, because a class assertion hides a missing member.

    The message must carry BOTH the name and the reason: an operator reading
    "invalid variable" learns that they typed something wrong, which is the one
    thing that did not happen here.
    """
    with pytest.raises(CommandSpecError, match="may not name") as caught:
        CommandSpec(argv=["python"], cwd="work", env_allow=(name,))
    assert name in str(caught.value)
    assert len(str(caught.value)) > len(name) + 32  # a reason, not just a verdict


def test_the_refusal_survives_being_hidden_among_names_that_are_fine():
    """A per-name scan, not a check of the first or the last row."""
    with pytest.raises(CommandSpecError, match="may not name"):
        CommandSpec(
            argv=["python"], cwd="work",
            env_allow=("ANTHROPIC_API_KEY", "PATH", "LD_PRELOAD", "TEMP"))


# --- the positive controls: what the mechanism exists for still works ---


@pytest.mark.parametrize("name", ADMITTED)
def test_a_name_an_operator_legitimately_needs_is_still_admitted(name):
    """Credentials and tool discovery are the reason `env_allow` exists at all."""
    spec = CommandSpec(argv=["python"], cwd="work", env_allow=(name,))
    assert spec.env_allow == (name,)


@pytest.mark.parametrize("name", LOOKALIKES)
def test_a_name_that_merely_resembles_a_refused_one_is_admitted(name):
    """The over-correction control: the match is the whole name, not a substring.

    `PATHEXT` is the row that matters most. It is a real Windows variable an
    operator may need, it begins with `PATH`, and a rule written as "starts
    with" or "contains" would refuse it while every refusal assertion above
    stayed green.
    """
    spec = CommandSpec(argv=["python"], cwd="work", env_allow=(name,))
    assert spec.env_allow == (name,)


def test_a_code_owned_literal_is_not_bound_by_the_operator_facing_refusal():
    """The boundary is about AUTHORITY, and `env` is not the operator's road.

    Literal `env` pairs are written by adapter code -- forced switches and the
    minted home -- and never by an operator: the public dispatch body refuses
    the key outright, and the operator config file has no such field. Refusing
    injecting names there too would bind this build's own future adapters,
    which may legitimately need to point a vendor at a library directory it
    ships. So the literal road stays open, and the road an operator can reach
    is closed. Both halves are asserted, because only the pair is the claim.
    """
    spec = CommandSpec(
        argv=["python"], cwd="work", env={"LD_LIBRARY_PATH": "/opt/vendor/lib"})
    assert spec.env["LD_LIBRARY_PATH"] == "/opt/vendor/lib"


# --- the refusal on the public argument road, which never sees a pin ---


def test_the_refusal_holds_on_the_public_dispatch_argument_road(root, runners):
    """A browser-submitted dispatch carries its own `env_allow` and no pin.

    It never passes an operator config file, so a refusal that lived only there
    would leave this road open. Both directions in one test: the injecting name
    is refused, the discovery name prepares.
    """
    adapter = ProcessAdapter(
        "owned-process", runners(root), clock=lambda: NOW, ids=_ids())
    argv = [sys.executable, "-c", "pass"]
    with pytest.raises(AdapterContractError, match="not a valid command"):
        adapter.prepare(_request({
            "argv": argv, "cwd": "work", "env_allow": ["NODE_OPTIONS"]}))
    prepared = adapter.prepare(_request({
        "argv": argv, "cwd": "work", "env_allow": ["PATH"]}))
    assert tuple(prepared.adapter_payload["env_allow"]) == ("PATH",)


def test_the_public_dispatch_road_admits_no_literal_environment_at_all():
    """The other half of the code-owned carve-out, stated where it is enforced."""
    from conductor.command.dispatch import (
        DispatchArgumentError,
        validate_dispatch_arguments,
    )

    with pytest.raises(DispatchArgumentError, match="env_allow"):
        validate_dispatch_arguments({
            "argv": ["python"], "cwd": "work", "env": {"LD_PRELOAD": "/x.so"}})


# --- the case rule, exercised on both platforms rather than on this one ---


@pytest.mark.parametrize("name", ["LD_PRELOAD", "PYTHONPATH", "NODE_OPTIONS"])
def test_the_canonical_spelling_is_refused_on_either_platform(name):
    assert injecting_env_reason(name, windows=True) is not None
    assert injecting_env_reason(name, windows=False) is not None


@pytest.mark.parametrize("name", ["ld_preload", "Ld_Preload", "PythonPath",
                                  "node_options"])
def test_a_mixed_spelling_is_the_same_variable_on_windows_and_a_different_one_on_posix(
        name):
    """Both directions per name, which is the only way this rule is provable.

    A single case-sensitive rule is bypassed on Windows by the shift key, since
    the operating system resolves `Ld_Preload` and `LD_PRELOAD` to one variable.
    A single case-insensitive rule refuses `ld_preload` on POSIX, where it is a
    different variable that no loader reads and that can therefore inject
    nothing. So the rule takes the platform as an argument and is checked at
    both values here -- the running machine can only ever witness one of them,
    and a test that asked the platform would assert whatever the code did.
    """
    assert injecting_env_reason(name, windows=True) is not None
    assert injecting_env_reason(name, windows=False) is None


@pytest.mark.parametrize("name", ["PATH", "PATHEXT", "ANTHROPIC_API_KEY",
                                  "Path", "path"])
def test_an_admitted_name_stays_admitted_under_either_case_rule(name):
    assert injecting_env_reason(name, windows=True) is None
    assert injecting_env_reason(name, windows=False) is None


def test_the_refusal_table_is_exactly_the_roster_this_suite_names_and_states_why():
    """An auditor owes its own witness: the table must not be silently empty.

    Set equality in BOTH directions, against a roster written out literally at
    the top of this file. A test that only checked "every refused name is in the
    table" passes against a table that refuses the whole alphabet; one that only
    checked the reverse passes against a table missing half the runtimes. And
    every entry owes a reason long enough to be one, because the refusal message
    quotes it to an operator who has to decide what to do next.
    """
    assert set(INJECTING_ENV) == set(REFUSED)
    assert len(REFUSED) == len(set(REFUSED))
    for name, reason in INJECTING_ENV.items():
        assert isinstance(reason, str) and len(reason) > 40, name
        assert not set(REFUSED).isdisjoint({name})
    assert set(INJECTING_ENV).isdisjoint(set(ADMITTED))
    assert set(INJECTING_ENV).isdisjoint(set(LOOKALIKES))


# --- the facts the ruling rests on, witnessed by real children ---


_DISCOVER = (
    "import os, subprocess, sys\n"
    "found = None\n"
    "for entry in os.environ.get('PATH', '').split(os.pathsep):\n"
    "    candidate = os.path.join(entry, 'conduct_probe_tool.py')\n"
    "    if os.path.isfile(candidate):\n"
    "        found = candidate\n"
    "        break\n"
    "if found is None:\n"
    "    print('NOTHING-FOUND')\n"
    "else:\n"
    "    done = subprocess.run([sys.executable, found], capture_output=True)\n"
    "    sys.stdout.buffer.write(done.stdout)\n"
)


def test_an_allowlisted_path_still_carries_real_tool_discovery_to_a_real_child(
        root, runners, tmp_path):
    """The mandatory operational control, end to end through a real spawn.

    A refusal list that breaks tool discovery is a worse defect than the one it
    fixes, and the product spawns vendor CLIs that shell out. So the child is
    told nothing but `PATH`, walks it the way any tool does, finds a helper
    whose location it was never given, and RUNS it -- the helper's own marker on
    stdout is the witness. The before/after is in the same test: with `PATH`
    withheld the identical child reports that it found nothing.
    """
    toolbox = tmp_path / "toolbox"
    toolbox.mkdir()
    (toolbox / "conduct_probe_tool.py").write_text(
        "print('DISCOVERED-AND-RAN')\n", encoding="utf-8")
    runner = runners(root, environ={"PATH": str(toolbox)})
    argv = [sys.executable, "-c", _DISCOVER]

    with_path = runner.run(CommandSpec(
        argv=argv, cwd="work", env_allow=("PATH",), timeout_seconds=60))
    without = runner.run(CommandSpec(argv=argv, cwd="work", timeout_seconds=60))

    assert b"DISCOVERED-AND-RAN" in with_path.output
    assert b"NOTHING-FOUND" in without.output


def test_an_allowlisted_path_cannot_displace_the_pinned_absolute_entrypoint(
        root, runners, tmp_path):
    """Why admitting `PATH` costs the pin nothing: nothing here resolves by name.

    `argv[0]` is an absolute path every provider proved absolute before this
    point, and neither `execve` nor `CreateProcess` searches for an absolute
    program. The witness is a decoy of the SAME basename standing first on the
    child's `PATH`: a build that resolved by name would start the decoy and die,
    because the decoy is not an executable at all.
    """
    decoy_dir = tmp_path / "decoys"
    decoy_dir.mkdir()
    (decoy_dir / Path(sys.executable).name).write_bytes(b"not an executable\n")
    runner = runners(root, environ={"PATH": str(decoy_dir)})
    outcome = runner.run(CommandSpec(
        argv=[sys.executable, "-c", "print('REAL-PIN-RAN')"], cwd="work",
        env_allow=("PATH",), timeout_seconds=60))

    assert outcome.status == "completed" and outcome.exit_code == 0
    assert outcome.output.strip() == b"REAL-PIN-RAN"


def test_windows_upper_cases_its_environment_so_a_mixed_spelling_never_matches(
        root, runners):
    """The platform fact the case rule is derived from, read from the platform.

    `_child_env` looks a name up in the ambient snapshot with an exact dict
    lookup. On Windows CPython upper-cases every key of `os.environ`, so the
    two spellings are the same variable; on POSIX they are two variables and a
    mixed one is simply absent. Either way the ASSERTION here is the same, and
    it is read from the running platform rather than assumed.
    """
    expected = "folded" if os.name == "nt" else None
    key = "Conduct_Case_Probe"
    os.environ[key] = "folded"
    try:
        runner = runners(root, environ=None)
        outcome = runner.run(CommandSpec(
            argv=[sys.executable, "-c",
                  "import os,sys; sys.stdout.write("
                  "os.environ.get('CONDUCT_CASE_PROBE', 'ABSENT'))"],
            cwd="work", env_allow=("CONDUCT_CASE_PROBE",), timeout_seconds=60))
    finally:
        os.environ.pop(key, None)
        os.environ.pop(key.upper(), None)
    assert outcome.output.decode() == (expected or "ABSENT")
