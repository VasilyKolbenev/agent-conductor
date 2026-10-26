"""A2: the pinned Claude Code build starts and is let go through the relay lifecycle (D13).

One attempt per boundary mode (dispatch, review) over the product's own transport: the shared login
lease, a relay home minted, filled from a synthetic login and discarded (`login_relay`,
`claude_relay`), a real AppContainer (`ProcessRunner.container_profile`) and the real owned-process
runner. The only child is the protected `claude.exe` 2.1.239 asked for its version: its argv is the
pin and `--version`, with no `-p`, no prompt and no stdin, and its timeout is 60 s. The login is a
synthetic home of the right form in the test's own root (`tests/relay_credentials.py`): the real
logins, the owner's profile and the network are not involved.

Opt-in. The pinned file comes from `CONDUCT_A2_CLAUDE_EXE` and must be exactly
`%USERPROFILE%\\DecemberCommand\\harnesses\\claude-code\\2.1.239\\claude.exe`. Without it the whole
module is skipped (CI has no personal install), and a skipped run is NOT a passed A2. One native
file per process, so one process per code page; a process that holds more than this file starts
nothing. The second attempt starts only when every observation before it is green.

The observations are separate tests and none of them is a successful action or a verdict. What they
show is launch and release: the child completed with exit 0 and printed the version, the spec
carried the boundary and the new relay home, nothing of the login changed, the relay and the
profile are gone, and the lease and the owner are free again. What was left behind is told even
when the child did not complete. They do NOT show that the CLI read the credential (a spec naming
the relay home proves what the child was told), a subscription, the absence of a refresh during a
task, a model, a prompt, the checker, or the public transport road; that is the first B. A child
that does not complete, a launch that is lost or a release that is not clean is a named failure and
the run is not repeated. A spec that is not the bare version print is refused before the child.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conductor import ownership, ownership_login, ownership_transition
from conductor.command.adapters import process_boundary, process_loans
from conductor.command.adapters.claude_code import CLAUDE_PROTOCOL, CLAUDE_PROVIDER_ID
from conductor.command.adapters.process import STDIN_NOT_PROVIDED, ProcessRunner
from conductor.command.adapters.process_boundary import WindowsContainer
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.adapters.relay_attempt import RelayNotStarted
from conductor.command.adapters.relay_home import relay_key, relay_root_for
from conductor.command.providers import resolve_providers
from conductor.command.work_layout import work_route
from conductor.ownership_native import identity
from tests.relay_credentials import claude_leaf, claude_profile, millis, put
from tests.relay_roads import digests
from tests.test_command_claude_transport import a_request
from tests.test_process_login_native import snapshot_of
from tests.test_process_loans_native import entries_naming, same_acl

EXE_VARIABLE = "CONDUCT_A2_CLAUDE_EXE"
EXE = os.environ.get(EXE_VARIABLE, "")
pytestmark = [
    pytest.mark.skipif(os.name != "nt", reason="native AppContainer launch"),
    pytest.mark.skipif(not EXE, reason=f"A2 needs {EXE_VARIABLE}: the protected claude.exe"),
]

VERSION_PRINT = b"2.1.239 (Claude Code)"
VERSION_ARGV = ("--version",)
PINNED = ("DecemberCommand", "harnesses", "claude-code", "2.1.239", "claude.exe")
WORK_ITEM = "work-001"  # the item `a_request` names: one item of the work tree, as a child stands
TIMEOUT_SECONDS = 60
RELAY_HOME = re.compile(r"c-[0-9a-f]{16}\Z")


def _now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Site:
    """An activated project, a synthetic login home and the transport pinned to the real build."""

    def __init__(self, base: Path):
        self.exe = Path(EXE)
        self.install = self.exe.parent
        self.root = (base / "project").resolve()
        (self.root / "conductor").mkdir(parents=True)
        ownership_transition.activate(self.root, legacy_writers_stopped=True)
        self.logins = (base / "DecemberCommand").resolve() / "logins"
        self.login = self.logins / "x"
        life = datetime.now(timezone.utc) + timedelta(hours=4)
        put(self.login, ".credentials.json", claude_leaf(expiresAt=millis(life)))
        put(self.login, ".claude.json", claude_profile())
        system = os.environ["SystemRoot"]
        config = ProviderConfig(
            provider_id=CLAUDE_PROVIDER_ID, executable=str(self.exe), protocol=CLAUDE_PROTOCOL,
            env_allow=("SystemRoot", "windir"), auth="subscription", auth_home=str(self.login))
        counter = iter(range(1, 1000))
        # The runner sees the profile folder, as the install check of a loan reads it; the child is
        # allowed two names and gets nothing else of it.
        runner_environ = {"SystemRoot": system, "windir": system,
                          "USERPROFILE": os.environ["USERPROFILE"]}
        resolved = resolve_providers(
            [config], root=self.root, clock=_now_text, ids=lambda kind: f"{kind}-{next(counter)}",
            environ=runner_environ, confine_platform="win32")
        self.adapter = resolved.registry.resolve(CLAUDE_PROVIDER_ID)
        self.relay_root = relay_root_for(self.login)
        self.key = self.relay_root / relay_key(identity(self.root))

    def places(self) -> dict[str, Path]:
        """The folders whose DACL the attempt must leave exactly as it found it."""
        return {"relay": self.relay_root, "login": self.login, "logins": self.logins,
                "install": self.install, "work": self.root / work_route(WORK_ITEM)}


class Observed:
    """What one attempt left behind, read once; `stop` names the fact that ended it early."""

    def __init__(self, mode: str):
        self.mode, self.stop, self.site, self.refusal = mode, None, None, None
        self.outcome = self.spec = self.entry = self.paths = self.sid = None
        self.before, self.after, self.naming = {}, {}, {}
        self.login_before, self.login_after = {}, {}
        self.tokens, self.retained, self.residue = (), None, None


class NotTheVersionPrint(Exception):
    """The spec the runner was given is not the bare version print: its child is never started."""


def _attempt(site: Site, seen: Observed) -> None:
    """Make the readiness, run the one attempt and read the folders; any early end is `stop`."""
    adapter, request = site.adapter, a_request(timeout=TIMEOUT_SECONDS)
    pin = (str(site.exe),)  # before any lease, folder or profile: what the argv is made of
    if (tuple(adapter.profile.version_argv) != VERSION_ARGV or tuple(adapter._argv_prefix()) != pin
            or tuple(adapter._boundary_prefix()) != pin):
        seen.stop = "A2 STOP, the pin and the version print are not what A2 starts: not started"
        return
    runner = adapter._runner
    real_profile, real_run = runner.container_profile, runner.run

    @contextlib.contextmanager
    def profile(**entry):
        seen.entry = entry
        try:
            with real_profile(**entry) as (boundary, paths):
                seen.paths, seen.sid = dict(paths), boundary.sid
                yield boundary, paths
        except Exception as error:  # what the boundary said, for the name of the stop
            seen.refusal = f"{type(error).__name__}: {error}"
            raise

    def run(spec):
        seen.spec = spec
        if tuple(spec.argv) != (str(site.exe), *VERSION_ARGV) or spec.stdin_bytes:
            seen.stop = "A2 STOP, the spec is not the bare version print: its child is not started"
            raise NotTheVersionPrint(seen.stop)
        return real_run(spec)

    with pytest.MonkeyPatch.context() as patch:
        # the project's providers.json would name the login home; its reading has its own tests
        patch.setattr(process_loans, "configured_login_homes", lambda data_root: (site.login,))
        patch.setattr(runner, "container_profile", profile)
        patch.setattr(runner, "run", run)
        with ownership.acquire_owner(site.root):
            adapter._workspace.work_dir(WORK_ITEM)
            code = adapter._relay_start(seen.mode)
            if code is not None:
                seen.stop = f"A2 STOP, the relay folder was refused before the attempt: {code}"
                return
            refused = adapter._relay_preflight(request)
            if refused is not None:
                seen.stop = f"A2 STOP, the readiness refused the synthetic login: {refused.detail}"
                return
            seen.before = {name: snapshot_of(path) for name, path in site.places().items()}
            seen.login_before = digests(site.login)
            try:
                seen.outcome = adapter._attempt(
                    adapter.profile.version_argv, work_route(WORK_ITEM), mode=seen.mode,
                    claim=adapter._claim_of(request), timeout=TIMEOUT_SECONDS,
                    separate_stderr=True)
            except RelayNotStarted as refusal:
                seen.stop = (f"A2 STOP, the attempt was refused before its claim: {refusal.code}"
                             f" ({seen.refusal})")
            except Exception as error:  # a lost launch is unknown, and the run is not repeated
                seen.stop = seen.stop or (f"A2 STOP, the launch is lost or unknown, not repeated: "
                                          f"{type(error).__name__} ({seen.refusal})")
    seen.retained, seen.residue = adapter._retained, adapter._login_residue
    seen.tokens = tuple(runner.active_tokens())
    seen.login_after = digests(site.login)
    seen.after = {name: snapshot_of(path) for name, path in site.places().items()}
    if seen.sid is not None:
        seen.naming = {name: entries_naming(path, seen.sid)
                       for name, path in site.places().items()}


def _not_to_start(request) -> str | None:
    """Why the attempt of this mode must not be started, or None; nothing here spawns a child."""
    exe, pinned = Path(EXE), Path(os.environ.get("USERPROFILE", ""), *PINNED)
    if os.path.normcase(exe) != os.path.normcase(pinned) or not exe.is_file():
        return (f"A2 STOP, {EXE_VARIABLE} is not the pinned build: it must be the file "
                f"{pinned}, and the pinned build is not available")
    if len({item.nodeid.split("::")[0] for item in request.session.items}) != 1:
        return ("A2 STOP, this process holds another test file: one native file per process, "
                f"so the {request.param} attempt was not started")
    if request.session.testsfailed:
        return (f"A2 STOP, the {request.param} attempt was not started: an earlier observation "
                "of this run is red, and a run is not repeated")
    return None


@pytest.fixture(scope="module", params=("dispatch", "review"))
def observed(request, tmp_path_factory):
    seen = Observed(request.param)
    seen.stop = _not_to_start(request)
    if seen.stop is None:
        seen.site = Site(tmp_path_factory.mktemp(f"a2-{request.param}"))
        _attempt(seen.site, seen)
    return seen


def completed(seen: Observed) -> Observed:
    """The attempt ran to a completed child; the failure that ended it early otherwise."""
    assert seen.stop is None, seen.stop
    assert seen.outcome.status == "completed", (
        f"A2 STOP, the child did not complete ({seen.outcome.status}): its outcome is unknown "
        "and the run is not repeated")
    return seen


def attempted(seen: Observed) -> Observed:
    """The attempt was made, whatever became of its child: what it left behind is told anyway."""
    assert seen.site is not None and seen.before, seen.stop
    return seen


def test_the_pinned_build_completed_with_exit_zero_and_printed_its_version(observed):
    outcome = completed(observed).outcome
    assert outcome.exit_code == 0, f"exit {outcome.exit_code}"
    assert VERSION_PRINT in outcome.output, "the version print is not in the child's stdout"
    assert outcome.stdin_state == STDIN_NOT_PROVIDED
    assert outcome.output_contains_env_value is False


def test_the_spec_is_the_pin_and_version_with_the_real_boundary_and_no_prompt_or_stdin(observed):
    spec = completed(observed).spec
    assert tuple(spec.argv) == (str(observed.site.exe), *VERSION_ARGV)
    assert isinstance(spec.boundary, WindowsContainer) and spec.boundary.sid == observed.sid
    assert not spec.stdin_bytes and spec.timeout_seconds == TIMEOUT_SECONDS
    assert observed.entry["mode"] == observed.mode, "the boundary was entered for another mode"


def test_the_child_was_told_the_new_relay_home_and_the_runtime_of_the_attempt(observed):
    site, spec = completed(observed).site, observed.spec
    home = Path(spec.env["CLAUDE_CONFIG_DIR"])
    assert RELAY_HOME.fullmatch(home.name) and home.parent == site.key
    assert home != site.login and site.login not in home.parents
    runtime = str(observed.paths["runtime"])
    assert {spec.env[name] for name in ("TEMP", "TMP", "LOCALAPPDATA")} == {runtime}
    assert Path(runtime).is_absolute() and runtime != os.environ.get("TEMP")


def test_the_synthetic_login_is_byte_for_byte_what_it_was(observed):
    attempted(observed)
    assert observed.login_before and observed.login_after == observed.login_before


def test_the_relay_home_is_gone_and_the_attempt_counted_no_leftover(observed):
    site = attempted(observed).site
    if observed.spec is not None:
        assert not Path(observed.spec.env["CLAUDE_CONFIG_DIR"]).exists(), "the relay home is there"
    assert not site.key.exists() or list(site.key.iterdir()) == [], "the key folder holds something"
    assert (observed.retained, observed.residue) == (0, 0)


def test_every_dacl_is_as_it_was_and_the_profile_is_named_nowhere(observed):
    attempted(observed)
    for name in observed.before:
        assert same_acl(observed.after[name], observed.before[name]), f"the DACL of {name} changed"
        assert observed.naming.get(name, []) == [], f"an entry for the profile is left in {name}"
    assert process_boundary.LOGIN_LOAN_OPEN is False
    assert process_boundary.login_loan_provided() is False


def test_the_profile_and_its_grants_and_loans_are_retired_in_the_journal(observed):
    site = attempted(observed).site
    journal = site.root / "conductor.v3" / "process-profiles"
    phases = {path.name.split("-")[0]: json.loads(path.read_text(encoding="utf-8"))["phase"]
              for path in (journal.iterdir() if journal.is_dir() else ())}
    assert phases == {"profile": "retired", "acl": "retired", "loan": "retired"}


def test_the_profile_is_no_longer_known_to_the_system(observed):
    from conductor.command.adapters import _winlaunch  # the native helper, only to read the mapping

    assert attempted(observed).sid is not None, observed.stop or "no profile was made"
    assert _winlaunch.inspect_profile(observed.sid) is None, "the profile mapping is still there"


def test_the_runner_holds_no_child_token(observed):
    assert attempted(observed).tokens == ()


def test_the_owner_and_the_login_lease_are_taken_again_the_usual_way(observed):
    assert observed.site is not None, observed.stop
    site = observed.site
    try:
        with ownership.acquire_owner(site.root):
            with ProcessRunner.login_write_guard(site.root, str(site.login)):
                pass
    except Exception as error:  # an uncertain lease is refused here, by name, and not cleared
        pytest.fail(f"A2 STOP, the owner or the login lease cannot be taken again "
                    f"({type(error).__name__}): not cleared by hand")
    box = ownership_login.box_key(str(site.login))[1]
    assert not (box / "active.json").exists() and list(box.glob("closed-*.json"))
