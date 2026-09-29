"""The one environment git and gh run in (spec 8.9, 8.10 item 4).

`tool_env(source, pins, conduct_home)` is a builder over an explicit mapping: it names
what may pass and copies nothing else, so a token, a `GIT_*` variable of the owner or a
`PATH` entry the owner happens to have cannot arrive by accident. Most claims are read
off the dict it returns, with the platform stated (`win32`, `darwin`, `linux`) so all
three PATH rules and the case rule of Windows are judged on any OS. Two are judged
where they can be: `GCM_INTERACTIVE` is spelled one way and `core.hooksPath` is written
in one module of the whole product, and a REAL git proves that the hooks the built
environment silences are hooks that do run without it.
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor import tool_env

SRC = Path(__file__).resolve().parents[1] / "src" / "conductor"
HOME = "/home/owner/.december-command"
WIN_HOME = r"C:\Users\owner\.december-command"
TOKENS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_HOST")


def _pins(git: str | None = None, gh: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(git=None if git is None else SimpleNamespace(path=git),
                           gh=None if gh is None else SimpleNamespace(path=gh))


def _git_variables(env: dict[str, str]) -> dict[str, str]:
    return {name: value for name, value in env.items() if name.upper().startswith("GIT_")}


def test_gh_receives_no_token_env_and_only_pinned_dirs_on_path():
    owner = {name: f"secret-{name}" for name in TOKENS}
    owner["PATH"] = "/opt/owner/bin:/somewhere/else"
    env = tool_env.tool_env(owner, _pins("/usr/local/bin/git", "/opt/gh/bin/gh"), HOME,
                            platform="linux")
    assert not [name for name in env if name.upper() in TOKENS]
    assert not any("secret" in value for value in env.values())
    assert env["PATH"] == "/usr/local/bin:/opt/gh/bin:/usr/bin:/bin"


def test_no_git_variable_of_the_owner_passes_and_the_git_config_count_is_the_literal_two():
    owner = {"GIT_DIR": "/elsewhere/.git", "GIT_WORK_TREE": "/elsewhere", "GIT_EXEC_PATH": "/x",
             "GIT_CONFIG_GLOBAL": "/x/gitconfig", "GIT_CONFIG_COUNT": "99",
             "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/owner/hooks",
             "GIT_SSH_COMMAND": "ssh -i /x", "GIT_ASKPASS": "/x/ask", "SSH_ASKPASS": "/x/ask"}
    env = tool_env.tool_env(owner, _pins("/usr/bin/git"), HOME, platform="linux")
    assert _git_variables(env) == {
        "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": f"{HOME}/git/hooks-empty",
        "GIT_CONFIG_KEY_1": "core.fsmonitor", "GIT_CONFIG_VALUE_1": "false"}
    assert "SSH_ASKPASS" not in env and "GCM_INTERACTIVE" in env


def test_the_owner_names_that_pass_are_exactly_the_allowlist():
    unrelated = {"OPENAI_API_KEY": "k", "AWS_SECRET_ACCESS_KEY": "s", "PYTHONPATH": "/py",
                 "FOO": "bar", "PATHEXT": ".EXE"}
    owner = {name: f"value-{name}" for name in tool_env.TRANSFERRED} | unrelated
    env = tool_env.tool_env(owner, _pins(), HOME, platform="linux")
    for name in tool_env.TRANSFERRED:
        assert env[name] == f"value-{name}", name
    assert not set(unrelated) & set(env)


def test_lowercase_proxy_names_pass_and_are_not_upcased():
    owner = {"https_proxy": "http://p:1", "http_proxy": "http://p:2", "no_proxy": "localhost"}
    env = tool_env.tool_env(owner, _pins(), HOME, platform="linux")
    assert env["https_proxy"] == "http://p:1" and env["no_proxy"] == "localhost"
    assert "HTTPS_PROXY" not in env


def test_the_literals_are_the_values_of_section_8_9():
    env = tool_env.tool_env({}, _pins("/usr/bin/git"), HOME, platform="linux")
    assert env == {
        "PATH": "/usr/bin:/bin",
        "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1",
        "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never",
        "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C",
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": f"{HOME}/git/hooks-empty",
        "GIT_CONFIG_KEY_1": "core.fsmonitor", "GIT_CONFIG_VALUE_1": "false"}


def test_an_owner_value_can_never_replace_a_literal():
    owner = {"LC_ALL": "de_DE", "NO_COLOR": "", "GCM_INTERACTIVE": "always", "PATH": "/evil"}
    env = tool_env.tool_env(owner, _pins("/usr/bin/git"), HOME, platform="linux")
    assert (env["LC_ALL"], env["NO_COLOR"], env["GCM_INTERACTIVE"]) == ("C", "1", "never")
    assert env["PATH"] == "/usr/bin:/bin"


def test_windows_matches_names_case_insensitively_and_posix_does_not():
    windows = tool_env.tool_env({"systemroot": r"C:\Windows", "userprofile": r"C:\Users\o"},
                                _pins(), WIN_HOME, platform="win32")
    assert windows["SystemRoot"] == r"C:\Windows" and windows["USERPROFILE"] == r"C:\Users\o"
    posix = tool_env.tool_env({"home": "/lower", "HOME": "/upper"}, _pins(), HOME,
                              platform="linux")
    assert posix["HOME"] == "/upper" and "home" not in posix
    only_lower = tool_env.tool_env({"home": "/lower"}, _pins(), HOME, platform="linux")
    assert "HOME" not in only_lower and "home" not in only_lower


def test_windows_does_not_emit_one_proxy_name_in_two_spellings():
    owner = {"HTTPS_PROXY": "http://p:1"}
    env = tool_env.tool_env(owner, _pins(), WIN_HOME, platform="win32")
    assert [name for name in env if name.upper() == "HTTPS_PROXY"] == ["HTTPS_PROXY"]


@pytest.mark.parametrize("platform, git, gh, expected", [
    ("win32", r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files\GitHub CLI\gh.exe",
     r"C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;C:\Windows\System32;C:\Windows;"
     r"C:\Windows\System32\Wbem"),
    ("darwin", "/opt/homebrew/bin/git", "/usr/local/bin/gh",
     "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"),
    ("linux", "/usr/local/bin/git", "/opt/gh/bin/gh", "/usr/local/bin:/opt/gh/bin:/usr/bin:/bin"),
])
def test_path_is_pinned_git_then_pinned_gh_then_the_system_directories_per_platform(
        platform, git, gh, expected):
    home = WIN_HOME if platform == "win32" else HOME
    env = tool_env.tool_env({"SystemRoot": r"C:\Windows", "PATH": "/owner"},
                            _pins(git, gh), home, platform=platform)
    assert env["PATH"] == expected


def test_a_tool_that_is_not_pinned_adds_no_directory():
    only_gh = tool_env.tool_env({}, _pins(gh="/opt/gh/bin/gh"), HOME, platform="linux")
    only_git = tool_env.tool_env({}, _pins(git="/opt/git/bin/git"), HOME, platform="linux")
    neither = tool_env.tool_env({}, _pins(), HOME, platform="linux")
    assert only_gh["PATH"] == "/opt/gh/bin:/usr/bin:/bin"
    assert only_git["PATH"] == "/opt/git/bin:/usr/bin:/bin"
    assert neither["PATH"] == "/usr/bin:/bin"


def test_a_directory_named_twice_is_listed_once_in_the_order_it_first_appeared():
    env = tool_env.tool_env({}, _pins("/opt/x/git", "/opt/x/gh"), HOME, platform="linux")
    assert env["PATH"] == "/opt/x:/usr/bin:/bin"
    windows = tool_env.tool_env({"SystemRoot": r"C:\Windows"},
                                _pins(r"C:\WINDOWS\System32\git.exe"), WIN_HOME, platform="win32")
    assert windows["PATH"] == r"C:\WINDOWS\System32;C:\Windows;C:\Windows\System32\Wbem"


def test_windows_without_systemroot_lists_only_the_pinned_directories():
    env = tool_env.tool_env({}, _pins(r"C:\Git\cmd\git.exe"), WIN_HOME, platform="win32")
    assert env["PATH"] == r"C:\Git\cmd"


def test_the_builder_does_not_read_the_process_environment(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "process-secret")
    monkeypatch.setenv("HOME", "/process/home")
    monkeypatch.setenv("PATH", "/process/bin")
    env = tool_env.tool_env({}, _pins(), HOME, platform="linux")
    assert "GH_TOKEN" not in env and "HOME" not in env and env["PATH"] == "/usr/bin:/bin"


def test_the_hooks_folder_is_conduct_home_git_hooks_empty_with_forward_slashes():
    assert tool_env.hooks_folder(HOME, platform="linux") == f"{HOME}/git/hooks-empty"
    assert tool_env.hooks_folder(WIN_HOME, platform="win32") == (
        "C:/Users/owner/.december-command/git/hooks-empty")


def test_every_value_is_a_string_without_nul_and_a_value_with_nul_is_dropped():
    owner = {"HOME": "/ok", "TMP": "/bad\x00tmp", "LANG": 5}
    env = tool_env.tool_env(owner, _pins(), HOME, platform="linux")
    assert env["HOME"] == "/ok" and "TMP" not in env and "LANG" not in env
    assert all(type(k) is str and type(v) is str and "\0" not in v for k, v in env.items())


# -- guards over the module's own lists and over the product ----------------------


def test_no_allowlisted_name_is_a_token_or_a_git_variable():
    upper = {name.upper() for name in tool_env.TRANSFERRED}
    assert not upper & {name.upper() for name in tool_env.NEVER_TRANSFERRED}
    assert not [name for name in upper if name.startswith("GIT_")]
    assert set(TOKENS) <= set(tool_env.NEVER_TRANSFERRED), "the spec's five token names are named"


def _product_sources() -> list[Path]:
    return sorted(path for path in SRC.rglob("*") if path.suffix in (".py", ".js"))


def test_gcm_interactive_is_spelled_one_way_across_the_product():
    seen: list[str] = []
    for path in _product_sources():
        text = path.read_text(encoding="utf-8")
        for found in re.finditer(r"(?i)gcm_interactive", text):
            assert found.group(0) == "GCM_INTERACTIVE", (path.name, found.group(0))
            seen.append(path.name)
        for value in re.findall(r"GCM_INTERACTIVE[\"']?\s*[=:]\s*[\"']?(\w+)", text):
            assert value == "never", (path.name, value)
    assert "tool_env.py" in seen


def test_core_hookspath_is_written_by_this_module_and_no_other():
    writers: set[str] = set()
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.strip().lower().startswith("core.hookspath")):
                writers.add(path.name)
    assert writers == {"tool_env.py"}, "hooks are silenced by the environment, never by -c"


# -- a real git: the silence is real, and the control shows the hook does run -----


def _git_version(git: str) -> tuple[int, int]:
    said = subprocess.run([git, "--version"], capture_output=True, text=True).stdout
    found = re.match(r"git version (\d+)\.(\d+)", said)
    return (int(found.group(1)), int(found.group(2))) if found else (0, 0)


GIT = shutil.which("git")


@pytest.mark.skipif(GIT is None or _git_version(GIT) < (2, 31),
                    reason="needs git 2.31 or newer (GIT_CONFIG_COUNT)")
def test_git_runs_no_hook_under_the_built_environment_and_runs_it_without(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    plain = {name: os.environ[name] for name in ("PATH", "SystemRoot", "HOME", "USERPROFILE")
             if name in os.environ}

    def git(env: dict[str, str], *args: str) -> None:
        subprocess.run([GIT, *args], cwd=repo, env=env, check=True, capture_output=True)

    git(plain, "init", "-q")
    marker = tmp_path / "the-hook-ran"
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\necho ran > '{marker.as_posix()}'\n", newline="\n")
    hook.chmod(0o755)
    commit = ("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
              "commit", "--allow-empty", "-q", "-m", "one")
    git(plain, *commit)
    assert marker.exists(), "control: the hook runs when nothing silences it"
    marker.unlink()
    home = tmp_path / "home"
    (home / "git" / "hooks-empty").mkdir(parents=True)
    git(tool_env.tool_env(os.environ, _pins(GIT), home), *commit)
    assert not marker.exists(), "the built environment did not silence the hook"
