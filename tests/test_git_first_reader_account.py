"""The reader the first-commit tests give the product does not show it the account's Git settings.

`GIT_CONFIG_GLOBAL` arrived in Git 2.32, so on the lower bound of the pin (2.31) the variable the
tests have always set hides nothing, and the account's own `~/.gitconfig` would reach every Git
call of the product (the preview, the preparation, the driver): a `commit.gpgsign=true` there turns
the preview into the signing road. The witness plants such a file and reads the preview's own facts
(`first_facts`) through `product_reader` on three readers: the current Git, the isolated 2.31 (gate
G-old; its id is skipped while `CONDUCT_OLD_GIT` is unset) and the current Git played as a Git that
ignores `GIT_CONFIG_GLOBAL`, which is the one that is red here when the empty home is taken away.
"""
import os

import pytest

from conductor.command import git_setup_facts
from conductor.command.adapters.process import ProcessRunner
from conductor.command.project_git import process_git_read
from tests import git_first_readers as readers
from tests.git_first_readers import product_reader, reader_binary
from tests.git_repo_helpers import ISOLATED, KEPT, git, needs_git

pytestmark = needs_git
OLD_GIT_CASES = [pytest.param("old", False, id="old_git"),
                 pytest.param("current", True, id="current_git_as_if_2_31")]
ALL_CASES = [pytest.param("current", False, id="current_git"), *OLD_GIT_CASES]


def account_home(tmp_path, monkeypatch):
    """An account whose Git configuration signs every commit; the home variables name it."""
    home = tmp_path / "account-home"
    home.mkdir()
    (home / ".gitconfig").write_text("[commit]\n\tgpgsign = true\n", encoding="utf-8")
    for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(name, str(home))


def without_the_global_variable(monkeypatch):
    """Play the current Git as one that never heard of `GIT_CONFIG_GLOBAL`; the environment the
    tests have always given a reader, less that variable, is returned."""
    kept = {name: value for name, value in ISOLATED.items() if name != "GIT_CONFIG_GLOBAL"}
    monkeypatch.setattr(readers, "ISOLATED", kept)
    return kept


def unborn_project(tmp_path, binary):
    """An empty repository of its own, and a folder for the runner, both outside the account."""
    project, runner = tmp_path / "project", tmp_path / "runner"
    project.mkdir()
    (runner / "cwd").mkdir(parents=True)
    git("init", "-q", cwd=project, binary=binary)
    git("config", "user.name", "First Author", cwd=project, binary=binary)
    git("config", "user.email", "first@example.invalid", cwd=project, binary=binary)
    return project, runner, runner / "cwd"


def reader_that_keeps_the_account_home(runner, binary, cwd, environment):
    """The reader as the first writing of the bench built it: the runner passes HOME on."""
    names = {name: os.environ[name] for name in KEPT if name in os.environ}
    return process_git_read(ProcessRunner(runner, environ=names), binary, str(cwd),
                            env_allow=KEPT, env=environment)


@pytest.mark.parametrize("which, as_if_2_31", ALL_CASES)
def test_the_preview_facts_of_the_tests_reader_ignore_the_accounts_signing_setting(
        tmp_path, monkeypatch, which, as_if_2_31):
    binary = reader_binary(which)
    account_home(tmp_path, monkeypatch)
    if as_if_2_31:
        without_the_global_variable(monkeypatch)
    project, runner, cwd = unborn_project(tmp_path, binary)
    facts = git_setup_facts.first_facts(project, product_reader(runner, binary, cwd))
    assert facts["signing"] is False


@pytest.mark.parametrize("which, as_if_2_31", OLD_GIT_CASES)
def test_a_reader_without_the_empty_home_shows_the_product_the_accounts_signing_setting(
        tmp_path, monkeypatch, which, as_if_2_31):
    """Calibration: on a Git that ignores the variable the account's file does reach the product's
    reads through the reader of the first bench, so the witness above can be red."""
    binary = reader_binary(which)
    account_home(tmp_path, monkeypatch)
    environment = without_the_global_variable(monkeypatch) if as_if_2_31 else dict(ISOLATED)
    project, runner, cwd = unborn_project(tmp_path, binary)
    leaky = reader_that_keeps_the_account_home(runner, binary, cwd, environment)
    assert git_setup_facts.first_facts(project, leaky)["signing"] is True
