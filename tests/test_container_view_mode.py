"""A runner for a project opened for viewing refuses the container entry before anything exists.

`ProcessRunner(spawns_allowed=False)` already refuses every `run` and `start` before it does
anything else. The container entry is where a profile, a journal record and a grant of rights come
from, so it must refuse first too: a viewing runner that were handed an entry anyway would create
an OS profile and change ACLs for a project that may never start a child. The refusal is the same
`CommandSpecError` every unusable command gets, on every platform, before the host's native helper
is even imported.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from conductor import ownership
from conductor.command.adapters.process import CommandSpecError, ProcessRunner
from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.process_profile import ProfileJournal
from tests._drain_harness import DrainProject

ABSOLUTE_INSTALL = str(Path("/abs").resolve())


def folders() -> AttemptFolders:
    return AttemptFolders(work="work/t1", home=None, install=ABSOLUTE_INSTALL)


@pytest.fixture
def journal_opened(monkeypatch):
    """Every way into the profile journal, recorded: a refused entry must not reach any."""
    opened = []

    def spy(cls, *args, **kwargs):
        opened.append(args)
        raise AssertionError("a journal was opened for a runner that may not spawn")

    monkeypatch.setattr(ProfileJournal, "for_project", classmethod(spy))
    return opened


@pytest.mark.parametrize("call", [
    {"mode": "dispatch", "folders": "given"}, {"mode": "review", "folders": "given"},
    {"mode": "dispatch", "folders": None}, {"mode": None, "folders": None}])
def test_a_viewing_runner_refuses_the_container_entry_before_a_journal_is_opened(
        tmp_path, journal_opened, call):
    (tmp_path / "work" / "t1").mkdir(parents=True)  # the folders are fine: only the mode refuses
    runner = ProcessRunner(tmp_path, spawns_allowed=False)
    arguments = {"mode": call["mode"], "folders": folders() if call["folders"] else None}
    with pytest.raises(CommandSpecError, match="may not spawn"):
        with runner.container_profile(**arguments):
            pytest.fail("the block must not be entered")
    assert journal_opened == []


def test_the_viewing_refusal_comes_with_a_live_owner_and_leaves_no_profile_journal_behind(
        tmp_path, journal_opened):
    root = DrainProject.build(tmp_path).root
    (root / "work" / "t1").mkdir(parents=True)
    owner = ownership.acquire_owner(root)
    try:
        runner = ProcessRunner(root, spawns_allowed=False)
        with pytest.raises(CommandSpecError, match="may not spawn"):
            with runner.container_profile(mode="dispatch", folders=folders()):
                pytest.fail("the block must not be entered")
        owner.check()
    finally:
        owner.release()
    assert journal_opened == []
    assert not (root / "conductor.v3" / "process-profiles").exists()


@pytest.mark.skipif(os.name != "nt", reason="only the Windows helper reaches the journal")
def test_a_runner_that_may_spawn_reaches_the_journal_through_the_same_spy(
        tmp_path, journal_opened):
    with pytest.raises(AssertionError, match="a journal was opened"):
        ProcessRunner(tmp_path).container_profile(mode="dispatch")
    assert len(journal_opened) == 1, "the spy sees a runner that may spawn: the control is sound"
