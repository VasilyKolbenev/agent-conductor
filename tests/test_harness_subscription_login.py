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
    SAFE_MODE_ARGV,
    ClaudeCodeError,
)
from conductor.command.adapters.codex_cli import (
    CODEX_HOME_ENV,
    CODEX_PROVIDER_ID,
    LAST_MESSAGE_NAME,
)
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


def a_harness(tmp_path: Path, *, auth: str = "api_key", auth_home: str = ""):
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
    environ = {_fakeclaude.SPAWN_LOG: str(log)}
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


def test_the_login_a_row_pinned_reaches_the_transport_that_would_use_it():
    """The defect this closes: a mode written, admitted, shown, and read by
    nothing at all."""
    pin = ExecutablePin(
        executable="/opt/claude/bin/claude", error=ClaudeCodeError,
        auth="subscription", auth_home=AUTH_HOME)
    assert (pin.auth, pin.auth_home) == ("subscription", AUTH_HOME)


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
    assert kept.parent != root / ".claude-home"


def test_codex_moves_its_home_and_keeps_the_model_text_out_of_it(tmp_path):
    """Codex needs no second argv: its whole login lives in the one variable the
    API-key road points at a doomed directory. What must NOT move with it is the
    file the vendor writes the agent's last message into."""
    from conductor.command.adapters.codex_cli import CodexCliError

    pin = ExecutablePin(
        executable="/opt/codex/bin/codex", error=CodexCliError,
        auth="subscription", auth_home=AUTH_HOME)
    transport = _codex(pin, tmp_path)

    assert transport._login() == ("subscription", AUTH_HOME)
    assert transport._home_value(Path(tmp_path / "minted")) == AUTH_HOME
    minted = Path(tmp_path / "minted")
    assert transport._last_message_path(minted) == minted / LAST_MESSAGE_NAME


def _codex(pin, tmp_path: Path):
    from conductor.command.adapters.codex_cli import CodexCliTransport
    from conductor.command.adapters.process import ProcessRunner

    root = tmp_path / "codex-root"
    root.mkdir(parents=True, exist_ok=True)
    return CodexCliTransport(
        pin, ProcessRunner(root), root=root, clock=lambda: NOW, ids=_Ids(),
        adapter_id=CODEX_PROVIDER_ID)


def test_both_harnesses_read_their_login_from_the_variable_they_already_owned():
    """No new environment name is invented for a login: the directory a login
    lives in is the same one the API-key road minted."""
    assert CLAUDE_HOME_ENV == "CLAUDE_CONFIG_DIR"
    assert CODEX_HOME_ENV == "CODEX_HOME"
