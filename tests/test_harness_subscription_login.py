"""What changes, and what may not change, when a harness is pinned to a login.

The API-key road is the one that shipped: `--bare`, which the vendor's own help
says never reads an OAuth credential or the system keychain, and a config
directory minted fresh for every spawn and destroyed when it returns. That road
works only for an operator holding an API credential, and the owner rejected an
API key as the prerequisite for the first acceptance.

The subscription road changes exactly two things and is held here to changing
nothing else. Claude Code swaps ONE argv token -- `--safe-mode` for `--bare` --
and both harnesses point their home variable at the directory the operator
pinned instead of at the doomed one. The task still arrives on stdin, the
permission mode is still the road's own, the model is still the run's, the
telemetry switches are still forced, and the attempt home is still minted, read
and discarded for everything that is not the login.

Driven against the fake harness, which records the argv, the config directory
and the environment NAMES it was handed. Nothing here logs in, and nothing here
needs a credential: what is proved is which directory the child is pointed at
and which flag it is given, both of which are facts about this build.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.command.adapters.claude_code import (
    BARE_ARGV,
    CLAUDE_HOME_ENV,
    CLAUDE_PROTOCOL,
    CLAUDE_PROVIDER_ID,
    LOGIN_STATUS_ARGV,
    SAFE_MODE_ARGV,
    ClaudeCodeError,
)
from conductor.command.adapters.codex_cli import (
    CODEX_HOME_ENV,
    CODEX_PROVIDER_ID,
    LAST_MESSAGE_NAME,
)
from conductor.command.adapters.harness_workspace import WORK_DIR
from conductor.command.adapters.headless_cli import ExecutablePin
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import resolve_providers

from tests import _fakeclaude
from tests.test_command_claude_transport import (
    NOW,
    _Ids,
    _executable,
    a_request,
    run_once,
)

AUTH_HOME = "/var/lib/conduct/auth/claude-code"


def a_harness(tmp_path: Path, *, auth: str = "api_key", auth_home: str = "",
              **knobs: str):
    """One Claude harness pinned to a login, driven through the real factory."""
    from conductor.command.adapters.harness_workspace import INSTRUCTION_DIR

    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir(parents=True, exist_ok=True)
    instructions = root / INSTRUCTION_DIR
    instructions.mkdir(exist_ok=True)
    (instructions / "instr-001.md").write_text(
        "Add the missing guard.", encoding="utf-8", newline="\n")
    log = tmp_path / "spawns.log"
    environ = {_fakeclaude.SPAWN_LOG: str(log), **knobs}
    config = ProviderConfig(
        provider_id=CLAUDE_PROVIDER_ID, executable=str(exe),
        protocol=CLAUDE_PROTOCOL, env_allow=tuple(sorted(environ)),
        auth=auth, auth_home=auth_home)
    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ=environ)
    return resolution.registry.resolve(CLAUDE_PROVIDER_ID), root, log


def prompt_row(log: Path) -> dict:
    rows = _fakeclaude.prompt_spawns(log)
    assert len(rows) == 1, f"EXPECTED_ONE_PROMPT_SPAWN={len(rows)}"
    return rows[0]


def test_the_login_a_row_pinned_reaches_the_transport_that_would_use_it(tmp_path):
    """The defect this closes: a mode written, admitted, shown, and read by
    nothing at all. Measured on the TRANSPORT the factory built, not on the pin
    it was built from -- a pin that carries the pair and a transport that
    ignores it is exactly the defect."""
    adapter = a_harness(
        tmp_path, auth="subscription", auth_home=AUTH_HOME)[0]

    assert adapter._login() == ("subscription", AUTH_HOME)
    assert adapter._home_value(Path(tmp_path / "minted")) == AUTH_HOME
    assert adapter._isolation_argv() == SAFE_MODE_ARGV


@pytest.mark.parametrize("auth,auth_home,why", [
    ("oauth", AUTH_HOME, "login mode"),
    ("subscription", "", "directory"),
    ("subscription", "auth/claude", "absolute"),
    ("api_key", AUTH_HOME, "subscription login"),
])
def test_a_pin_refuses_a_login_pair_the_config_door_would_refuse(
        auth, auth_home, why):
    """Proved AGAIN here, as the executable path is: a transport can be built
    without passing the operator's file, and a login it would act on may not
    depend on somebody else having checked it."""
    with pytest.raises(ClaudeCodeError, match=why):
        ExecutablePin(
            executable="/opt/claude/bin/claude", error=ClaudeCodeError,
            auth=auth, auth_home=auth_home)


def test_the_subscription_road_swaps_one_token_and_leaves_the_rest_alone(tmp_path):
    """Token by token, because "the same except for the login" is the claim."""
    api_key, _root, api_log = a_harness(tmp_path / "one")
    subscription, _root2, sub_log = a_harness(
        tmp_path / "two", auth="subscription", auth_home=AUTH_HOME)

    assert run_once(api_key, a_request()).outcome == "succeeded"
    assert run_once(subscription, a_request()).outcome == "succeeded"

    plain = prompt_row(api_log)["argv"]
    signed = prompt_row(sub_log)["argv"]
    assert plain[:1] == list(BARE_ARGV)
    assert signed[:1] == list(SAFE_MODE_ARGV)
    assert plain[1:] == signed[1:], "a login changed more than its own token"
    assert "--bare" not in signed and "--safe-mode" not in plain


def test_every_read_only_road_carries_the_same_isolation_flag(tmp_path):
    """Three roads, one login. The two read-only argvs are built by their own
    methods, so a login wired into the dispatch alone would leave a review and
    an independent check reading a credential this build did not pin."""
    from conductor.command.adapters.claude_code import ClaudeCodeTransport

    signed = a_harness(
        tmp_path / "signed", auth="subscription", auth_home=AUTH_HOME)[0]
    plain = a_harness(tmp_path / "plain")[0]

    for road in (ClaudeCodeTransport._stdin_argv,
                 ClaudeCodeTransport._review_argv,
                 ClaudeCodeTransport._verdict_argv):
        home = Path(tmp_path / "minted")
        assert road(signed, home, None)[:1] == SAFE_MODE_ARGV, road.__name__
        assert road(plain, home, None)[:1] == BARE_ARGV, road.__name__
        assert road(signed, home, None)[1:] == road(plain, home, None)[1:]


def test_a_subscription_child_is_pointed_at_the_directory_the_operator_pinned(
        tmp_path):
    """The whole of the login contract at the environment seam."""
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=AUTH_HOME)

    assert run_once(adapter, a_request()).outcome == "succeeded"

    assert prompt_row(log)["claude_home"] == AUTH_HOME


def test_an_api_key_child_still_gets_a_minted_home_it_will_never_see_again(
        tmp_path):
    """The road that shipped, unchanged: the directory is under this build's own
    homes root, and it is gone when the spawn returns."""
    adapter, root, log = a_harness(tmp_path)

    assert run_once(adapter, a_request()).outcome == "succeeded"

    home = Path(prompt_row(log)["claude_home"])
    assert home.parent == root / ".claude-home"
    assert not home.exists(), "the attempt home outlived its spawn"


def test_a_subscription_login_directory_is_not_swept_with_the_attempt_homes(
        tmp_path):
    """A login deleted after every attempt would have to be performed again
    before every run, which is not a supported login at all."""
    kept = tmp_path / "auth" / "claude-code"
    kept.mkdir(parents=True)
    (kept / ".credentials.json").write_text("{}", encoding="utf-8", newline="\n")
    adapter, root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(kept))

    assert run_once(adapter, a_request()).outcome == "succeeded"

    assert (kept / ".credentials.json").exists()
    # The homes root really was swept during this dispatch -- so the survival
    # above is the login directory being OUTSIDE that road, not the sweep having
    # done nothing.
    assert list((root / ".claude-home").iterdir()) == []


def a_codex_harness(tmp_path: Path, *, auth: str = "api_key",
                    auth_home: str = "", **knobs: str):
    """One Codex harness pinned to a login, driven through the real factory."""
    from conductor.command.adapters.codex_cli import CODEX_PROTOCOL
    from conductor.command.adapters.harness_workspace import INSTRUCTION_DIR
    from tests import _fakecodex
    from tests.test_command_codex_transport import _executable as codex_exe

    exe = codex_exe(tmp_path)
    root = tmp_path / "codex-root"
    root.mkdir(parents=True, exist_ok=True)
    (root / INSTRUCTION_DIR).mkdir(exist_ok=True)
    (root / INSTRUCTION_DIR / "instr-001.md").write_text(
        "Add the missing guard.", encoding="utf-8", newline="\n")
    log = tmp_path / "codex-spawns.log"
    environ = {_fakecodex.SPAWN_LOG: str(log), **knobs}
    config = ProviderConfig(
        provider_id=CODEX_PROVIDER_ID, executable=str(exe),
        protocol=CODEX_PROTOCOL, env_allow=tuple(sorted(environ)),
        auth=auth, auth_home=auth_home)
    resolution = resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ=environ)
    return resolution.registry.resolve(CODEX_PROVIDER_ID), root, log


def test_codex_moves_its_home_and_keeps_the_model_text_out_of_it(tmp_path):
    """Codex needs no second argv: its whole login lives in the one variable the
    API-key road points at a doomed directory. What must NOT move with it is the
    file the vendor writes the agent's last message into -- that is model text,
    and it belongs in the directory that dies with the spawn.

    Driven through a REAL spawn rather than by calling the seams: the seams are
    the shared mixin's, so calling them proves the mixin and not this vendor's
    own argv, which is where `-o` stands.
    """
    from tests import _fakecodex

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    adapter, root, log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    assert run_once(adapter, a_request()).outcome == "succeeded"

    rows = _fakecodex.task_spawns(log)
    assert len(rows) == 1, rows
    assert rows[0]["codex_home"] == str(home)
    assert rows[0]["codex_home_is_dir"] is True
    minted = [token for token in rows[0]["argv"]
              if token.endswith(LAST_MESSAGE_NAME)]
    assert len(minted) == 1, rows[0]["argv"]
    assert Path(minted[0]).parent.parent == root / ".codex-home", (
        "the agent's last message was written where the login lives")
    asked = [row for row in _fakecodex.spawns(log)
             if _fakecodex.login_question(row["argv"])]
    assert [row["argv"] for row in asked] == [["login", "status"]]


def test_codex_refuses_a_run_whose_login_is_missing(tmp_path):
    """The same refusal on the other harness, driven by the vendor's own exit."""
    from tests import _fakecodex

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    adapter, _root, log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakecodex.LOGIN_FAILS: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "no usable subscription login" in receipt.detail
    assert "CODEX_HOME" in receipt.detail
    assert "run login --" in receipt.detail, receipt.detail
    assert _fakecodex.task_spawns(log) == []


def test_a_missing_login_refuses_before_any_task_is_spawned(tmp_path):
    """The refusal a person can act on, and the one this build owes them.

    It names the variable and says who signs in; it quotes no byte of what the
    vendor's status command printed, because that answer describes an account.
    """
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=AUTH_HOME,
        **{_fakeclaude.LOGIN_FAILS: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "no usable subscription login" in receipt.detail
    assert "no task was spawned" in receipt.detail
    assert CLAUDE_HOME_ENV in receipt.detail
    # The COMMAND, not just the variable. A refusal that says "sign in" without
    # saying how leaves a person to guess which of the vendor's two login roads
    # this build meant -- and one of them bills an API account.
    assert "auth login --claudeai" in receipt.detail
    assert "never runs a login" in receipt.detail
    assert "loggedIn" not in receipt.detail, "the child's answer was repeated"
    assert _fakeclaude.prompt_spawns(log) == [], "a task ran without a login"


def test_a_login_that_answers_lets_the_task_run(tmp_path):
    """The positive control, so the refusal above is not passing for a second
    reason: the same road with a login that answers spawns the task."""
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=AUTH_HOME)

    assert run_once(adapter, a_request()).outcome == "succeeded"

    assert len(_fakeclaude.prompt_spawns(log)) == 1


def test_the_api_key_road_is_never_asked_about_a_login(tmp_path):
    """A build that asked would be inventing a second thing that can fail for
    an operator who pinned no login at all."""
    adapter, _root, log = a_harness(tmp_path, **{_fakeclaude.LOGIN_FAILS: "1"})

    assert run_once(adapter, a_request()).outcome == "succeeded"

    argvs = [row["argv"] for row in _fakeclaude.spawns(log)]
    assert not [row for row in argvs if row[:1] == ["auth"]], argvs


def test_the_status_command_this_build_asks_is_the_vendors_own(tmp_path):
    """Read for its EXIT CODE, and asked with the login directory in place."""
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=AUTH_HOME)

    run_once(adapter, a_request())

    asked = [row for row in _fakeclaude.spawns(log)
             if row["argv"][-1:] == ["--json"]]
    assert len(asked) == 1, asked
    # Spelled out rather than read from the adapter: the constant, the fake that
    # answers it and this test would otherwise move together, and a question the
    # vendor does not implement would look exactly like one it does. These
    # tokens are a claim about `claude --safe-mode auth status --json` on
    # 2.1.239, which a person can check against the binary's own help.
    #
    # The isolation flag stands in front for a reason this test is the only
    # witness of: asking the status question is a full startup of the vendor's
    # CLI, standing in the run's own work root, so without the flag it would
    # read whatever a previous task left under `.claude/` there.
    assert asked[0]["argv"] == ["--safe-mode", "auth", "status", "--json"]
    assert list(LOGIN_STATUS_ARGV) == ["auth", "status", "--json"]
    assert asked[0]["claude_home"] == AUTH_HOME


# -- what a spawn may leave in a directory this build cannot delete ------------


def a_login_home(tmp_path: Path) -> Path:
    """A login directory as the vendor's own command would leave it."""
    home = tmp_path / "auth" / "claude-code"
    home.mkdir(parents=True)
    (home / ".credentials.json").write_text(
        '{"token": "SYNTHETIC"}', encoding="utf-8", newline="\n")
    return home


def test_per_run_state_a_spawn_leaves_in_the_login_directory_is_taken_back(
        tmp_path):
    """The API-key road keeps its promise by deleting the whole directory. This
    one cannot, so it takes back exactly the names measured as per-run -- and
    only the ones this spawn itself created."""
    home = a_login_home(tmp_path)
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.HOME_FILE: "sessions:{}"})

    assert run_once(adapter, a_request()).outcome == "succeeded"

    assert not (home / "sessions").exists(), "a run's own session state survived"
    assert (home / ".credentials.json").exists(), "the login itself was deleted"


def test_per_run_state_that_was_already_there_is_a_persons_own_and_survives(
        tmp_path):
    """A login directory can be one a person also uses themselves, and their own
    transcripts stand under a name this build calls per-run. Taking those back
    would be destroying somebody's work to keep a promise about this build's own
    leavings, so the deletion is bounded to what THIS spawn added."""
    home = a_login_home(tmp_path)
    (home / "sessions").mkdir()
    (home / "sessions" / "mine.json").write_text(
        '{"transcript": "a person\'s own"}', encoding="utf-8", newline="\n")
    (home / ".last-cleanup").write_text("stamp", encoding="utf-8", newline="\n")
    # The spawn leaves something of its own, so the cleanup really runs: a
    # directory where nothing appeared is taken back by an early return, and a
    # prune that reached too far would pass under it unseen.
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.HOME_FILE: "backups:{}"})

    assert run_once(adapter, a_request()).outcome == "succeeded"

    assert (home / "sessions" / "mine.json").exists(), "a person's own work went"
    assert (home / ".last-cleanup").exists()
    assert (home / "backups").exists(), "vendor state this build declares was taken"


def test_a_name_no_declaration_accounts_for_is_reported_on_every_receipt(
        tmp_path):
    """Not deleted, not ignored, and not named: the directory holds an
    operator's credential, and a receipt is the wrong place to list it."""
    home = a_login_home(tmp_path)
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.HOME_FILE: "stowaway.txt:PROBE"})

    receipt = run_once(adapter, a_request())

    assert (home / "stowaway.txt").exists(), "the fixture wrote nothing to find"
    # The OUTCOME, not a sentence after a success. A task that ran and left
    # state nobody declared in a directory this build cannot clean has not met
    # the promise it makes about that directory, and a run whose own record said
    # `succeeded` with the sentence appended would be saying both things.
    assert receipt.outcome == "failed"
    assert "left state this build does not declare" in receipt.detail
    assert "stowaway" not in receipt.detail, "a receipt named operator state"


def test_declared_state_a_spawn_leaves_is_taken_back_and_never_reported(tmp_path):
    """The other half of the rule, and the one a list that excused nothing would
    break: a name this build DECLARES is per-run is taken back in silence."""
    home = a_login_home(tmp_path)
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.HOME_FILE: "sessions:{}"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    assert "login directory gained state" not in receipt.detail
    assert not (home / "sessions").exists(), "declared per-run state survived"


def test_a_directory_no_operator_pinned_is_never_read_or_pruned(
        tmp_path, monkeypatch):
    """Closure rather than a check, and measured where it would BITE.

    An empty value resolves to the process's own working directory and a
    relative one to whatever the child was standing in, so a prune that took
    either at face value would delete a directory of that name wherever the
    server happened to be running. The test stands in such a place, with such a
    directory, and both survive.
    """
    from conductor.command.adapters import login_home

    monkeypatch.chdir(tmp_path)
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "mine.json").write_text(
        "{}", encoding="utf-8", newline="\n")

    added = frozenset({"sessions"})
    assert login_home.entries("") == frozenset()
    assert login_home.entries("sessions") == frozenset()
    login_home.take_back("", ("sessions",), added)
    login_home.take_back(".", ("sessions",), added)
    assert (tmp_path / "sessions" / "mine.json").exists(), (
        "a prune reached a directory no operator pinned")
    absent = tmp_path / "never-created"
    login_home.take_back(str(absent), ("sessions",), added)
    assert not absent.exists()
    # The reading road is closed the same way and for a sharper reason: an
    # unpinned value would make this build open a file of that name wherever the
    # server happened to be standing, and call whatever it found a credential.
    (tmp_path / ".credentials.json").write_text(
        '{"token": "NOT-THIS-BUILDS-BUSINESS-AT-ALL"}',
        encoding="utf-8", newline="\n")
    assert login_home.credential_values("", (".credentials.json",)) == ()
    assert login_home.credential_values(".", (".credentials.json",)) == ()


def test_state_that_stood_before_the_spawn_is_nobodys_business(tmp_path):
    """Only what APPEARED is judged. A build that refused over whatever the
    operator's own login had put there would refuse over the credential."""
    home = a_login_home(tmp_path)
    (home / "notes-from-elsewhere.txt").write_text(
        "mine", encoding="utf-8", newline="\n")
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded"
    assert "login directory gained state" not in receipt.detail
    assert (home / "notes-from-elsewhere.txt").exists()


def test_the_api_key_road_never_looks_at_a_login_directory(tmp_path):
    """There is none to look at, and a build that read one anyway would be
    reading a directory no configuration pointed it at."""
    home = a_login_home(tmp_path)
    (home / "sessions").mkdir()
    adapter, _root, _log = a_harness(tmp_path)

    assert run_once(adapter, a_request()).outcome == "succeeded"

    assert (home / "sessions").exists(), "an unpinned directory was pruned"


def test_every_road_re_derives_the_residue_it_reports(tmp_path):
    """One adapter instance serves every action of its provider, so a count left
    standing by a dispatch would be reported on a review whose own spawns left
    nothing -- and on a verification that never touched a login directory."""
    from conductor.command.adapters.deep_commands import DeepReviewArgs
    from conductor.command.adapters.deep_contracts import OMITTED

    adapter = a_harness(tmp_path, auth="subscription", auth_home=AUTH_HOME)[0]
    adapter._login_residue = 1

    receipt = adapter._review(
        a_request(capability="review"),
        DeepReviewArgs(
            work_item_id="work-001", target_artifact_refs=("in",),
            result_artifact_ref=OMITTED, review_profile="quality"))

    assert "login directory" not in receipt.detail, receipt.detail
    assert adapter._login_residue == 0


def test_an_unreadable_login_directory_counts_as_residue(monkeypatch, tmp_path):
    """"I could not establish what is there" is not "nothing is there". A build
    that flattened them would report a promise as kept because it had been
    unable to check it."""
    from conductor.command.adapters import login_home

    home = a_login_home(tmp_path)
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))
    monkeypatch.setattr(login_home, "entries", lambda _home: None)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "does not declare" in receipt.detail


def test_a_cleanup_that_cannot_read_a_name_never_raises(monkeypatch, tmp_path):
    """It runs in a ``finally``. An exception escaping there would skip the
    attempt home's own discard and replace the outcome of a spawn that already
    happened -- and the workspace door it borrows refuses an unreadable name
    with a RuntimeError, which no OSError guard would catch."""
    from conductor.command.adapters import harness_workspace, login_home

    home = a_login_home(tmp_path)
    (home / "sessions").mkdir()

    def refuse(_path):
        raise harness_workspace.WorkspaceNotContained("unreadable")

    monkeypatch.setattr(harness_workspace, "_leaf", refuse)
    login_home.take_back(str(home), ("sessions",), frozenset({"sessions"}))

    assert (home / "sessions").exists(), "a name it could not read was removed"


def test_absolute_is_the_same_word_here_as_at_the_door():
    """A POSIX pin read on Windows is absolute to both, or to neither. Two
    notions would silently leave a directory the door admitted un-measured and
    un-cleaned."""
    from conductor.command.adapters import login_home
    from conductor.command.adapters.harness_profile import is_absolute

    for path in ("/var/lib/conduct/auth", "C:\\conduct\\auth", "auth/x", ""):
        assert login_home._pinned(path) == (bool(path) and is_absolute(path))


# -- the login joins the leak scan it was never in --------------------------


SECRET = "sk-ant-oat01-SYNTHETIC-LOGIN-VALUE-NOT-A-REAL-CREDENTIAL"


def a_signed_in_home(tmp_path: Path) -> Path:
    """A login directory holding a credential file the vendor's login wrote."""
    home = tmp_path / "auth" / "claude-code"
    home.mkdir(parents=True)
    (home / ".credentials.json").write_text(
        '{"claudeAiOauth": {"accessToken": "' + SECRET + '", "scopes": ["a"]}}',
        encoding="utf-8", newline="\n")
    return home


def test_a_child_that_echoes_its_own_login_is_seen_doing_it(tmp_path):
    """The gap this closes: every credential the scan knew about arrived through
    an allowed environment name, and a vendor login arrives in a file.

    Measured at the flag the publication road reads. A review output becomes
    durable artifact content unless that flag is set, so a login the scan had
    never heard of would have been written into the run's own record.
    """
    home = a_signed_in_home(tmp_path)
    adapter = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.EMIT_HEX: SECRET.encode("utf-8").hex()})[0]

    adapter._workspace.work_root()
    outcome = adapter._attempt(
        adapter._stdin_argv, WORK_DIR, timeout=30, stdin_bytes=b"probe")

    assert outcome.output_contains_env_value is True


def test_the_same_output_is_unremarkable_when_no_login_was_pinned(tmp_path):
    """The positive control: the flag above is the LOGIN being scanned for, not
    this build flagging every output that looks like a token."""
    # The child is told what to emit as HEX, so the value the knob carries
    # through the allowed environment is not the value it writes: without that,
    # the control would be flagged for the ENVIRONMENT reason and would prove
    # nothing about a login at all.
    adapter = a_harness(
        tmp_path, **{_fakeclaude.EMIT_HEX: SECRET.encode("utf-8").hex()})[0]

    adapter._workspace.work_root()
    outcome = adapter._attempt(
        adapter._stdin_argv, WORK_DIR, timeout=30, stdin_bytes=b"probe")

    assert outcome.output_contains_env_value is False


def test_a_login_value_reaches_the_scan_and_nothing_else(tmp_path):
    """Read to protect, never to report: the values are bytes for one substring
    test, and no receipt, journal row or exception carries them."""
    from conductor.command.adapters import login_home

    home = a_signed_in_home(tmp_path)
    adapter = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))[0]

    assert SECRET.encode("utf-8") in adapter._login_secrets()
    assert SECRET.encode("utf-8") in adapter._sensitive_values()
    # The scopes entry is a real string in that file and far too short to scan
    # for: a two-character value would flag every output containing it.
    assert b"a" not in adapter._login_secrets()
    assert login_home.credential_values(str(home), ()) == ()


def test_only_the_declared_login_file_is_ever_read(tmp_path):
    """Read from the DECLARED names, never by looking at what a directory
    happens to hold: a build that scanned every file it found would be reading
    an operator's unrelated documents in order to protect them."""
    home = a_signed_in_home(tmp_path)
    (home / "notes-of-my-own.txt").write_text(
        '{"diary": "SOMETHING-ELSE-ENTIRELY-AND-QUITE-LONG"}',
        encoding="utf-8", newline="\n")
    adapter = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))[0]

    values = adapter._login_secrets()

    assert SECRET.encode("utf-8") in values
    assert b"SOMETHING-ELSE-ENTIRELY-AND-QUITE-LONG" not in values


def test_the_value_channel_carries_bytes_and_refuses_anything_else():
    """The one field of a command spec that holds a VALUE. A string here would
    be a text credential compared against a byte stream and never matching."""
    from conductor.command.adapters.process import CommandSpec, CommandSpecError

    with pytest.raises(CommandSpecError, match="VALUES as bytes"):
        CommandSpec(argv=("/bin/true",), cwd="work",
                    sensitive_extra=("a string",))
    spec = CommandSpec(argv=("/bin/true",), cwd="work",
                       sensitive_extra=(b"kept", b"", b"kept"))
    assert spec.sensitive_extra == (b"kept",)
    assert "kept" not in repr(spec)


def test_a_login_this_build_cannot_read_widens_nothing_and_refuses_nothing(
        tmp_path):
    """A login that cannot be read is a scan that cannot be widened, not a
    reason to refuse a run the login preflight already admitted."""
    from conductor.command.adapters import login_home

    home = a_login_home(tmp_path)
    (home / ".credentials.json").write_text(
        "not json at all", encoding="utf-8", newline="\n")
    adapter, _root, _log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    assert adapter._login_secrets() == ()
    assert run_once(adapter, a_request()).outcome == "succeeded"
    assert login_home.credential_values(
        str(home), (".credentials.json",)) == ()


def test_the_two_declared_lists_are_the_measured_ones():
    """Spelled out WHOLE as an independent claim about each pinned build.

    Both halves matter and a spot check covers neither: dropping a name from
    `login_scratch` leaves per-run state standing in an operator's directory,
    and dropping one from `login_expected` turns ordinary vendor state into a
    reported residue that fails every run.
    """
    from conductor.command.adapters.claude_code import CLAUDE_PROFILE
    from conductor.command.adapters.codex_cli import CODEX_PROFILE

    assert CLAUDE_PROFILE.login_scratch == ("sessions", ".last-cleanup")
    assert CLAUDE_PROFILE.login_expected == (
        ".claude.json", "backups", ".credentials.json")
    assert CODEX_PROFILE.login_scratch == ("tmp",)
    assert CODEX_PROFILE.login_expected == (
        "skills", "auth.json", "config.toml", "version.json")


@pytest.mark.parametrize("bad", [
    "/etc", "C:\\Windows", "..", ".", "", "sessions/inner", "a\\b", 7])
def test_a_declared_login_name_is_one_component_and_never_a_path(bad):
    """These lists are joined to a directory an operator pinned and one of them
    is then DELETED, so a name carrying a separator, a parent segment or a drive
    would reach outside the directory they pointed at."""
    from conductor.command.adapters.claude_code import CLAUDE_PROFILE
    from conductor.command.adapters.harness_profile import HeadlessCliError
    from dataclasses import replace

    with pytest.raises(HeadlessCliError):
        replace(CLAUDE_PROFILE, login_scratch=(bad,))


def test_a_name_cannot_be_both_taken_back_and_left_alone():
    from conductor.command.adapters.claude_code import CLAUDE_PROFILE
    from conductor.command.adapters.harness_profile import HeadlessCliError
    from dataclasses import replace

    with pytest.raises(HeadlessCliError, match="never both"):
        replace(CLAUDE_PROFILE, login_scratch=("sessions",),
                login_expected=("sessions",))


def test_a_provider_that_can_be_asked_about_a_login_says_how_to_perform_one():
    """The refusal has to print a command, so a profile that could be asked and
    could not answer would leave a person told to sign in and not told how."""
    from conductor.command.adapters.claude_code import CLAUDE_PROFILE
    from conductor.command.adapters.harness_profile import HeadlessCliError
    from dataclasses import replace

    with pytest.raises(HeadlessCliError, match="how"):
        replace(CLAUDE_PROFILE, login_command=())


def test_both_harnesses_read_their_login_from_the_variable_they_already_owned():
    """No new environment name is invented for a login: the directory a login
    lives in is the same one the API-key road minted."""
    assert CLAUDE_HOME_ENV == "CLAUDE_CONFIG_DIR"
    assert CODEX_HOME_ENV == "CODEX_HOME"
