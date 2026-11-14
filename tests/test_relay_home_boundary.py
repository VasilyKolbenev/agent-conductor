"""The boundary double and the static fact of the runner take the relay home as the runner does.

The doors and the transports are tested over `tests/_fakeboundary.py` (no Windows host, no
AppContainer). An absolute home must therefore be judged there by the SAME function the runner's
loan uses (`relay_home_shape`), or a transport could pass every test and be refused by the real
runner. `RELAY_HOME_LOANS` is the runner's static answer to "does your entry lend one", read by a
door before any runner is built.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters.process import ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.command.adapters.relay_home import relay_key
from conductor.command.boundary_entry import entry_lends_relay_homes
from tests import _fakeboundary
from tests._fakeboundary import BoundaryRunner
from tests.relay_fixtures import HEX, layout, link, shape


def runner_of(found, tmp_path, **options) -> BoundaryRunner:
    options.setdefault("auth_homes", (found.login,))
    return BoundaryRunner(found.root, scratch=tmp_path / "scratch", **options)


def folders_of(found, home) -> AttemptFolders:
    return AttemptFolders(work="work/t1", home=home, install=str(found.install))


def test_the_double_lends_the_relay_home_of_the_project_as_the_attempts_home(tmp_path):
    found = layout(tmp_path)
    runner = runner_of(found, tmp_path)
    with runner.container_profile(
            mode="dispatch", internet_client=True, folders=folders_of(found, str(found.home))
    ) as (boundary, paths):
        assert paths["home"] == found.home
        assert paths["work"] == runner._root / "work" / "t1" and boundary.internet_client
    assert runner.events == ["enter", "exit"]


@pytest.mark.parametrize("where", [
    "another-key", "outside", "no-login-homes", "wrong-name", "inside-the-project",
    "a-project-home-written-absolute", "a-junction-outside-into-the-project",
    "relay-shaped-inside-the-project"])
def test_the_double_refuses_an_absolute_home_the_runners_loan_refuses(tmp_path, where):
    found = layout(tmp_path)
    options = {}
    home = found.home
    if where == "another-key":
        home = found.relay / relay_key((9, 9)) / f"c-{HEX}"
    elif where == "outside":
        home = tmp_path / "elsewhere" / "h"
    elif where == "no-login-homes":
        options["auth_homes"] = ()
    elif where == "wrong-name":
        home = found.key / "c-short"
    elif where == "inside-the-project":
        home = found.root / "work" / "t1" / "relay"
    elif where == "a-project-home-written-absolute":
        home = found.root / ".claude-home" / "a"
    elif where == "a-junction-outside-into-the-project":
        (found.root / ".claude-home" / "a").mkdir(parents=True)
        link(tmp_path / "outside-link", found.root / ".claude-home")
        home = tmp_path / "outside-link" / "a"
    else:
        home = found.root / "DecemberCommand" / "relay" / found.key.name / f"c-{HEX}"
    home.mkdir(parents=True, exist_ok=True)
    reason = shape(found, path=home, auth_homes=options.get("auth_homes", (found.login,)))
    assert reason is not None, "the case is meant to be one the shape refuses"
    runner = runner_of(found, tmp_path, **options)
    with pytest.raises(ProfileRefused, match="profile_acl_invalid: the relay home is refused: "):
        with runner.container_profile(mode="dispatch", folders=folders_of(found, str(home))):
            pytest.fail("the block must not be entered")
    assert runner.events == ["enter"] and runner.entries[0].paths is None
    with pytest.raises(ProfileRefused) as raised:
        runner.container_profile(mode="review", folders=folders_of(found, str(home))).__enter__()
    assert reason in str(raised.value)


@pytest.mark.parametrize("where", [
    "inside-the-project", "a-project-home-written-absolute", "a-junction-outside-into-the-project",
    "relay-shaped-inside-the-project"])
def test_the_runner_refuses_at_its_own_seam_every_absolute_home_in_the_project_the_double_does(
        tmp_path, where):
    # The double's judge is the shape; the runner's loan judges the shape of a home outside the
    # project (`test_relay_home_loans.py`) and refuses one inside it before any loan is asked.
    # Both must say no to the same homes, or a transport passes the tests and fails on the runner.
    found = layout(tmp_path)
    home = found.root / "work" / "t1" / "relay"
    if where == "a-project-home-written-absolute":
        home = found.root / ".claude-home" / "a"
    elif where == "a-junction-outside-into-the-project":
        (found.root / ".claude-home" / "a").mkdir(parents=True)
        link(tmp_path / "outside-link", found.root / ".claude-home")
        home = tmp_path / "outside-link" / "a"
    elif where == "relay-shaped-inside-the-project":
        home = found.root / "DecemberCommand" / "relay" / found.key.name / f"c-{HEX}"
    home.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ProfileRefused, match="the relay home is refused: "):
        ProcessRunner(found.root)._loaned(folders_of(found, str(home)))
    with pytest.raises(ProfileRefused, match="the relay home is refused: "):
        with runner_of(found, tmp_path).container_profile(
                mode="dispatch", folders=folders_of(found, str(home))):
            pytest.fail("the block must not be entered")


def test_the_double_asks_the_shared_function_and_nothing_of_its_own(tmp_path, monkeypatch):
    found = layout(tmp_path)
    asked = []

    def shared(*arguments):
        asked.append(arguments)
        return "asked"

    monkeypatch.setattr(_fakeboundary, "relay_home_shape", shared)
    runner = runner_of(found, tmp_path)
    with pytest.raises(ProfileRefused, match="relay home is refused: asked"):
        with runner.container_profile(mode="dispatch", folders=folders_of(found, str(found.home))):
            pytest.fail("the block must not be entered")
    [(auth_homes, root, identity, home, work, install)] = asked
    assert (auth_homes, root, tuple(identity), home) == (
        (found.login,), runner._root, found.ident, found.home)
    assert (work, install) == (runner._root / "work" / "t1", found.install)


def test_the_double_takes_a_route_home_as_it_always_did_and_asks_no_shape(tmp_path, monkeypatch):
    found = layout(tmp_path)
    monkeypatch.setattr(_fakeboundary, "relay_home_shape",
                        lambda *arguments: pytest.fail("a route is not a relay home"))
    runner = runner_of(found, tmp_path)
    with runner.container_profile(
            mode="dispatch", folders=folders_of(found, ".claude-home/a")) as (_, paths):
        assert paths["home"] == runner._root / ".claude-home" / "a"
    with runner.container_profile(mode="dispatch", folders=folders_of(found, None)) as (_, paths):
        assert paths["home"] is None


def test_the_runner_says_it_lends_relay_homes_as_a_fact_of_its_class(tmp_path):
    found = layout(tmp_path)
    assert ProcessRunner.RELAY_HOME_LOANS is True
    assert entry_lends_relay_homes(ProcessRunner(found.root))
    assert entry_lends_relay_homes(runner_of(found, tmp_path))


def test_only_the_boolean_true_on_the_class_of_a_runner_is_a_runner_that_lends_them():
    class Silent:
        pass

    def runner_with(value):
        return type("Runner", (), {"RELAY_HOME_LOANS": value})()

    assert not entry_lends_relay_homes(Silent()) and not entry_lends_relay_homes(None)
    for not_true in (1, "yes", None, object(), False):
        assert not entry_lends_relay_homes(runner_with(not_true)), repr(not_true)
    assert entry_lends_relay_homes(runner_with(True))
    later = Silent()
    later.RELAY_HOME_LOANS = True  # an instance may not claim what its class does not
    assert not entry_lends_relay_homes(later)
