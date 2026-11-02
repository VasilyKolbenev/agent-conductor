"""Which login the wizard asks about, and what it hands a person to run.

Split out of `test_provider_setup` when that module crossed the 800-line cap.
The seam is a subject: next door proves the dialogue's paths, its refusals and
the file it writes; this proves the one question that is asked only where there
is a choice, and the two lines it prints for a person to paste.

Nothing here performs a login. What is measured is the dialogue: which questions
are put, which row is written, and whether the command printed is one a shell
would really run.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

import pytest

from conductor.provider_setup import _login_lines

from tests.test_provider_setup import (
    LOGIN_ASKED,
    configure,
    menu_choice,
    pin_answers,
    pinned_files,
    project,
    written,
)

__all__ = ["project"]


@pytest.mark.parametrize("provider_id", sorted(LOGIN_ASKED))
def test_the_login_question_is_put_only_where_a_login_is_driven(
        project, tmp_path, capsys, provider_id):
    """A question with one acceptable answer is a way to get it wrong.

    So a provider whose transport drives no vendor login is TOLD which login it
    uses, and the two that do are asked. Measured on the dialogue rather than on
    the row, because both roads write the same `api_key` and only one of them
    put a choice to a person.
    """
    executable, entrypoint = pinned_files(tmp_path, provider_id)
    assert configure(project, *pin_answers(provider_id, executable, entrypoint),
                     "MY_TOKEN_NAME", "y") == 0

    said = capsys.readouterr().err
    if LOGIN_ASKED[provider_id]:
        assert f"How does {provider_id} sign in?" in said, said
        assert "only 2 runs tasks inside the execution boundary" not in said, said
    else:
        assert "sign in?" not in said, said
        assert "execution boundary" not in said, said
        assert "drives no vendor login" in said, said
    assert written(project)["providers"][0].get("auth", "api_key") == "api_key"


#: Which harness has a relay (`HarnessProfile.login_relay`), stated here by hand: the login with a
#: relay is kept in the product's folder and runs a task inside the boundary; the other is read for
#: quotas and refused a task (a subscription login for it is not supported there yet).
RELAYED = {"claude-code": True, "codex": True, "grok-build": True, "kimi-code": False}
RELAY_NOTE = ("On Windows, with 1 a task runs inside the execution boundary on a copy of that "
              "login that has no refresh token; the login folder itself is never given to a task.")
NO_RELAY_NOTE = ("With 1 the quotas are read and every task is refused before it starts: a "
                 "subscription login for this harness is not supported inside the execution "
                 "boundary yet.")


def product_login(base, provider_id):
    """Where the product keeps the login of one harness: the folder a relay is derived from."""
    return base / "DecemberCommand" / "logins" / provider_id


@pytest.mark.parametrize("provider_id", sorted(RELAYED))
def test_the_menu_says_what_a_subscription_login_does_for_this_harness_and_not_for_another(
        project, tmp_path, capsys, provider_id):
    executable, _ = pinned_files(tmp_path, provider_id)

    assert configure(project, *pin_answers(provider_id, executable, None), "", "y") == 0

    said = capsys.readouterr().err
    assert (RELAY_NOTE in said) is RELAYED[provider_id], said
    assert (NO_RELAY_NOTE in said) is (not RELAYED[provider_id]), said
    assert ("DecemberCommand\\logins\\<id>" in said) is RELAYED[provider_id], said


#: Where a login with a relay is NOT kept: the wrong forms the doors refuse
#: (`tests/test_subscription_road_boundary.WRONG_FOLDERS`), spelled by hand under a base folder.
#: ``{id}`` is the id of the harness.
WRONG_FORMS = [
    pytest.param(("login",), id="a-bare-folder"),
    pytest.param(("auth", "{id}"), id="another-folder-named-for-the-harness"),
    pytest.param(("logins", "{id}"), id="logins-without-the-product-folder"),
    pytest.param(("DecemberCommand", "{id}"), id="the-product-folder-without-logins"),
    pytest.param(("DecemberCommand", "logins"), id="logins-itself"),
    pytest.param(("DecemberCommand", "other", "{id}"), id="another-folder-beside-logins"),
]


@pytest.mark.parametrize("form", WRONG_FORMS)
@pytest.mark.parametrize("provider_id", ["claude-code", "codex", "grok-build"])
def test_a_login_with_a_relay_is_asked_for_the_product_folder_and_another_is_asked_again(
        project, tmp_path, capsys, provider_id, form):
    """The relay is derived from `<anything>/DecemberCommand/logins/<name>` alone, so a login kept
    anywhere else could not run a task: the dialogue says so while the folder is being chosen,
    names the folder to use, and asks again, instead of writing a row every task is refused for.
    Every wrong form the doors refuse is refused here, and the row it finally writes is one the
    doors admit (`relay_root_for`, the one function both ask)."""
    from conductor.command.adapters.relay_home import relay_root_for

    executable, _ = pinned_files(tmp_path, provider_id)
    elsewhere = tmp_path.joinpath(*(part.format(id=provider_id) for part in form))
    home = product_login(tmp_path, provider_id)

    assert configure(project, menu_choice(provider_id), str(executable), "1", str(elsewhere),
                     str(home), "", "y") == 0

    row = written(project)["providers"][0]
    assert row["auth"] == "subscription" and row["auth_home"] == str(home)
    assert relay_root_for(row["auth_home"]) is not None
    said = capsys.readouterr().err
    refusals = [line for line in said.splitlines() if "is not a folder named" in line]
    assert len(refusals) == 1 and "<something>\\DecemberCommand\\logins\\<name>" in refusals[0]
    assert f"%USERPROFILE%\\DecemberCommand\\logins\\{provider_id}" in said, said
    assert "Type the whole path: %USERPROFILE% is your user folder" in said, said
    assert str(elsewhere) not in refusals[0], "the refusal repeats the path that was typed"
    if not str(home).startswith(str(elsewhere)):   # a wrong form can be the front of the right one
        assert str(elsewhere) not in said, "the dialogue repeats the path that was typed"


@pytest.mark.skipif(os.name != "nt", reason="a path with no drive is absolute off Windows only")
@pytest.mark.parametrize("provider_id", ["claude-code", "codex", "grok-build"])
def test_a_path_that_names_the_product_folder_but_is_not_absolute_here_is_asked_again(
        project, tmp_path, capsys, provider_id):
    """The wizard reads a path as absolute in either spelling, and the doors judge it by the host.

    ``/Users/you/DecemberCommand/logins/<id>`` is absolute in the POSIX spelling and names the
    product folder, so the check of the written names passes; on a Windows host it is no absolute
    path, so the relay has no home for it and every task on a row that kept it would be refused.
    The wizard asks the very function the doors ask, and asks again."""
    from conductor.command.adapters import process_boundary
    from conductor.command.adapters.relay_home import relay_root_for

    posix = f"/Users/you/DecemberCommand/logins/{provider_id}"
    assert process_boundary.login_home_named(posix) and relay_root_for(posix) is None
    executable, _ = pinned_files(tmp_path, provider_id)
    home = product_login(tmp_path, provider_id)

    assert configure(project, menu_choice(provider_id), str(executable), "1", posix, str(home),
                     "", "y") == 0

    assert written(project)["providers"][0]["auth_home"] == str(home)
    said = capsys.readouterr().err
    assert said.count("is not a folder named <something>\\DecemberCommand\\logins\\<name>") == 1
    assert posix not in said, "the refusal repeats the path that was typed"


@pytest.mark.parametrize("provider_id,variable", [
    ("claude-code", "CLAUDE_CONFIG_DIR"), ("codex", "CODEX_HOME"), ("grok-build", "GROK_HOME")])
def test_the_sign_in_lines_point_the_vendors_variable_at_the_product_folder(
        project, tmp_path, capsys, provider_id, variable):
    executable, _ = pinned_files(tmp_path, provider_id)
    home = product_login(tmp_path, provider_id)

    assert configure(project, menu_choice(provider_id), str(executable), "1", str(home), "",
                     "y") == 0

    said = capsys.readouterr().err
    first = next(line for line in said.splitlines() if variable in line and str(home) in line)
    assert first.strip().startswith(("$env:", "export ")), first
    assert f"{variable} must point at that folder" in said, said


@pytest.mark.parametrize("provider_id", ["kimi-code"])
def test_a_login_without_a_relay_is_still_kept_in_any_absolute_folder(
        project, tmp_path, capsys, provider_id):
    executable, _ = pinned_files(tmp_path, provider_id)
    anywhere = tmp_path / "auth" / provider_id

    assert configure(project, menu_choice(provider_id), str(executable), "1", str(anywhere), "",
                     "y") == 0

    assert written(project)["providers"][0]["auth_home"] == str(anywhere)
    said = capsys.readouterr().err
    assert "DecemberCommand" not in said and "%USERPROFILE%" not in said, said


def test_the_vendor_login_writes_a_directory_and_prints_the_command_to_run(
        project, tmp_path, capsys):
    """The dialogue asks WHERE the login is kept and never for the login itself.

    A relative answer is re-asked, as every other path is. What the person is
    given back is the exact command to run in their own shell: this build never
    performs a login, and a product that did would be holding an account.
    """
    executable, _ = pinned_files(tmp_path, "claude-code")
    home = product_login(tmp_path, "claude-code")

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "1", "auth/claude-code", str(home), "", "y") == 0

    row = written(project)["providers"][0]
    assert row["auth"] == "subscription"
    assert row["auth_home"] == str(home)
    said = capsys.readouterr().err
    # The two lines a person really runs, in the shell this command runs in:
    # an assignment PowerShell performs, and a call to the binary they already
    # named. A `NAME=value` line and a literal `<executable>` were neither.
    for line in _login_lines(
            str(home), str(executable),
            ("CLAUDE_CONFIG_DIR", ("auth", "login", "--claudeai"))):
        assert line in said, said
    assert "<executable>" not in said, said
    assert "this build never runs a login" in said, said
    assert "login       subscription" in said, said
    assert f"login dir   {home}" in said, said


@pytest.mark.parametrize("parent", ["Conduct Login", "O'Brien"])
def test_the_printed_login_command_survives_a_real_machine_path(
        project, tmp_path, capsys, parent):
    """A space splits an unquoted argument and an apostrophe ends the quoting a
    naive printer opened. Both are ordinary in a Windows path, and a command a
    person cannot paste is not a command. The folder is the product's own form, kept
    under a native parent that carries the space or the apostrophe."""
    executable, _ = pinned_files(tmp_path, "claude-code")
    where = str(product_login(tmp_path / parent, "claude-code"))

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "1", where, "", "y") == 0

    said = capsys.readouterr().err
    # Asked of the platform this is running on, because that is what the wizard
    # asks: a fixed expectation here would red on the two other operating
    # systems the release CI runs, which is the same defect in a test.
    expected = _login_lines(
        where, str(executable),
        ("CLAUDE_CONFIG_DIR", ("auth", "login", "--claudeai")))
    for line in expected:
        assert line in said, said
    assert written(project)["providers"][0]["auth_home"] == where


@pytest.mark.parametrize(("provider_id", "expected"), [
    ("codex", ["-c", 'cli_auth_credentials_store="file"', "login"]),
    ("grok-build", ["--no-auto-update", "login"]),
])
def test_pasted_login_passes_the_pinned_arguments_to_the_native_process(
        project, tmp_path, capsys, provider_id, expected):
    executable, _ = pinned_files(tmp_path, provider_id)
    login = product_login(tmp_path, provider_id)
    assert configure(project, menu_choice(provider_id), str(executable), "1", str(login), "",
                     "y") == 0
    windows = os.name == "nt"
    escaped = str(executable).replace("'", "''" if windows else "'\\''")
    marker = ("& " if windows else "") + "'" + escaped + "'"
    [command] = [line.strip() for line in capsys.readouterr().err.splitlines()
                 if line.strip().startswith(marker)]
    # Substitute only the executable. The operator's shell passes the printed arguments
    # to a harmless native process that records argv; no actual sign-in is possible.
    probe = tmp_path / "capture.py"
    probe.write_text("import json,sys; print(json.dumps(sys.argv[1:]))", encoding="utf-8")
    def quote(path):
        return "'" + str(path).replace("'", "''") + "'" if windows else shlex.quote(str(path))
    prefix = ("& " if windows else "") + quote(sys.executable) + " " + quote(probe)
    shell = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"] if windows else ["sh", "-c"]
    capture = subprocess.run([*shell, prefix + command[len(marker):]],
                             capture_output=True, timeout=15)
    assert capture.returncode == 0, capture.stderr
    assert json.loads(capture.stdout) == expected


def test_the_printed_command_is_for_the_shell_the_operator_is_in(monkeypatch):
    """This command runs on the operator's own machine, so the platform IS the
    answer. Printing PowerShell on a POSIX shell would repeat the defect this
    fixed, in the other direction -- and the DEFAULT is the half that decides
    that, so it is driven here on both platforms rather than assumed."""
    import conductor.provider_setup as setup

    hint = ("CLAUDE_CONFIG_DIR", ("auth", "login", "--claudeai"))
    monkeypatch.setattr(setup.os, "name", "posix")
    assert _login_lines("/var/auth", "/opt/claude", hint)[0].startswith("export ")
    monkeypatch.setattr(setup.os, "name", "nt")
    assert _login_lines("C:\\auth", "C:\\claude.exe", hint)[0].startswith("$env:")
    windows = _login_lines("C:\\Log In", "C:\\bin\\claude.exe", hint, True)
    posix = _login_lines("/var/log in", "/opt/bin/claude", hint, False)

    assert windows == ["$env:CLAUDE_CONFIG_DIR = 'C:\\Log In'",
                       "& 'C:\\bin\\claude.exe' auth login --claudeai"]
    assert posix == ["export CLAUDE_CONFIG_DIR='/var/log in'",
                     "'/opt/bin/claude' auth login --claudeai"]
    assert _login_lines("/o'brien", "/bin/x", hint, False)[0] == (
        "export CLAUDE_CONFIG_DIR='/o'\\''brien'")


def test_a_subscription_row_refuses_an_api_billing_name_while_it_is_typed(
        project, tmp_path, capsys):
    """Refused at the question, not at the finished row: a dialogue that took
    every answer and then refused would cost a person the whole conversation."""
    executable, _ = pinned_files(tmp_path, "claude-code")
    home = product_login(tmp_path, "claude-code")

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "1", str(home), "ANTHROPIC_API_KEY", "MY_TOOL_SETTING",
                     "y") == 0

    said = capsys.readouterr().err
    assert "pays for model access through an API account" in said, said
    assert written(project)["providers"][0]["env_allow"] == ["MY_TOOL_SETTING"]
