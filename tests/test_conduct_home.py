"""The path half of `conduct_home()` (spec 4.1.2): where the hub's folder is.

Only the rule that `conduct up --status-file` needs today lives here: the folder
is `~/.december-command` unless `CONDUCT_HOME` names an absolute path, and a
relative or empty override is refused rather than resolved against whatever the
working folder happens to be. The placement rules (not inside an activated
project, not overlapping a login folder) and the creating half arrive with the
registry on day 9 and grow this file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.hub import home


def test_conduct_home_defaults_to_the_dot_folder_in_the_user_profile(monkeypatch):
    monkeypatch.delenv("CONDUCT_HOME", raising=False)
    assert home.conduct_home_path() == Path.home() / ".december-command"


def test_an_absolute_conduct_home_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("CONDUCT_HOME", str(tmp_path / "elsewhere"))
    assert home.conduct_home_path() == tmp_path / "elsewhere"


@pytest.mark.parametrize("value", ["relative/folder", ".", "", "~/home"])
def test_a_relative_or_empty_conduct_home_is_refused_with_its_code(monkeypatch, value):
    monkeypatch.setenv("CONDUCT_HOME", value)
    with pytest.raises(home.ConductHomeInvalid) as caught:
        home.conduct_home_path()
    assert caught.value.code == "conduct_home_invalid"
    assert "absolute" in str(caught.value)


def test_computing_the_path_creates_nothing(monkeypatch, tmp_path):
    target = tmp_path / "not-yet"
    monkeypatch.setenv("CONDUCT_HOME", str(target))
    home.conduct_home_path()
    assert not target.exists()
