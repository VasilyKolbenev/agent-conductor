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

import pytest

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
    else:
        assert "sign in?" not in said, said
        assert "drives no vendor login" in said, said
    assert written(project)["providers"][0].get("auth", "api_key") == "api_key"


def test_the_vendor_login_writes_a_directory_and_prints_the_command_to_run(
        project, tmp_path, capsys):
    """The dialogue asks WHERE the login is kept and never for the login itself.

    A relative answer is re-asked, as every other path is. What the person is
    given back is the exact command to run in their own shell: this build never
    performs a login, and a product that did would be holding an account.
    """
    executable, _ = pinned_files(tmp_path, "claude-code")
    home = tmp_path / "auth" / "claude-code"

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "1", "auth/claude-code", str(home), "", "y") == 0

    row = written(project)["providers"][0]
    assert row["auth"] == "subscription"
    assert row["auth_home"] == str(home)
    said = capsys.readouterr().err
    # The two lines a person really runs, in the shell this command runs in:
    # an assignment PowerShell performs, and a call to the binary they already
    # named. A `NAME=value` line and a literal `<executable>` were neither.
    assert f"$env:CLAUDE_CONFIG_DIR = '{home}'" in said, said
    assert f"& '{executable}' auth login --claudeai" in said, said
    assert "<executable>" not in said, said
    assert "this build never runs a login" in said, said
    assert "login       subscription" in said, said
    assert f"login dir   {home}" in said, said


@pytest.mark.parametrize("where", [
    r"C:\Program Files\Conduct Login\claude-code",
    r"C:\Users\O'Brien\conduct\login",
])
def test_the_printed_login_command_survives_a_real_machine_path(
        project, tmp_path, capsys, where):
    """A space splits an unquoted argument and an apostrophe ends the quoting a
    naive printer opened. Both are ordinary in a Windows path, and a command a
    person cannot paste is not a command."""
    executable, _ = pinned_files(tmp_path, "claude-code")

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "1", where, "", "y") == 0

    said = capsys.readouterr().err
    quoted = where.replace("'", "''")
    assert f"$env:CLAUDE_CONFIG_DIR = '{quoted}'" in said, said
    assert written(project)["providers"][0]["auth_home"] == where


def test_the_printed_command_is_for_the_shell_the_operator_is_in():
    """This command runs on the operator's own machine, so the platform IS the
    answer. Printing PowerShell on a POSIX shell would repeat the defect this
    fixed, in the other direction."""
    from conductor.provider_setup import _login_lines

    hint = ("CLAUDE_CONFIG_DIR", ("auth", "login", "--claudeai"))
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
    home = tmp_path / "auth" / "claude-code"

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "1", str(home), "ANTHROPIC_API_KEY", "HTTPS_PROXY",
                     "y") == 0

    said = capsys.readouterr().err
    assert "pays for model access through an API account" in said, said
    assert written(project)["providers"][0]["env_allow"] == ["HTTPS_PROXY"]
