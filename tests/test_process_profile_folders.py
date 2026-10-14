"""The profile journal's block with LOANED folders: order, refusals and what the recovery returns.

The natives are injected (no OS ACL changes); the holds are the real ones, so this runs on
Windows only. The OS behaviour of the same block is `test_process_loans_native.py`.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from conductor.command.adapters import process_profile
from conductor.command.adapters.process_profile import ProfileRefused
from tests._boot_world import counter, later_boot, measure
from tests.test_process_acl import SID
from tests.test_process_loans import OWNER, PRIOR, prior_acl, record_files, world

pytestmark = pytest.mark.skipif(os.name != "nt", reason="the holds are the Windows holds")
NOW = counter(42)


@pytest.fixture
def block(tmp_path, monkeypatch):
    measure(monkeypatch, NOW)
    monkeypatch.setattr(process_profile.ownership, "require_owner",
                        lambda root: SimpleNamespace(check=lambda: None))
    w = world(tmp_path)
    w.store.retire(w.profile_path)  # the shared fixture made a profile; the block makes its own
    w.profile_path.unlink()
    prior_acl(w)
    return w


def folders(w):
    return dict(w.folders)


def test_the_block_yields_loaned_and_fresh_folders_and_returns_every_one_at_exit(block):
    w = block
    with w.store.container(mode="dispatch", active_tokens=lambda: (), folders=folders(w)) as (
            container, paths):
        assert set(paths) == {"parent", "runtime", "work", "home", "install"}
        assert paths["work"] == w.folders["work"].resolve()
        assert paths["parent"].is_dir() and paths["runtime"].parent == paths["parent"]
        assert all(w.state[str(w.folders[key])][0] != PRIOR for key in w.folders)
        assert container.sid == SID
        assert container.install == str(paths["install"]), "the spawn is bound to this folder"
    assert not paths["parent"].exists()
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())
    assert all(path.is_dir() for path in w.folders.values())
    assert (w.folders["work"] / "seed.txt").read_text(encoding="utf-8") == "seed"
    assert w.store.inspect(SID) is None


def test_a_refused_folder_makes_no_profile_and_no_record(block):
    w = block
    bad = {**folders(w), "install": w.root}
    with pytest.raises(ProfileRefused, match="profile_acl_invalid"):
        with w.store.container(mode="dispatch", active_tokens=lambda: (), folders=bad):
            pytest.fail("the block must not be entered")
    assert w.store.inspect(SID) is None
    assert not w.store.directory.exists() or list(w.store.directory.glob("*.json")) == []


def test_folders_need_an_attempt_mode(block):
    w = block
    with pytest.raises(ProfileRefused, match="profile_acl_invalid"):
        with w.store.container(active_tokens=lambda: (), folders=folders(w)):
            pytest.fail("the block must not be entered")


def test_a_child_still_alive_at_exit_leaves_the_loan_in_place_for_the_recovery(block, monkeypatch):
    w = block
    with pytest.raises(ProfileRefused, match="profile_acl_unproven"):
        with w.store.container(mode="dispatch", active_tokens=lambda: ("t",),
                               folders=folders(w)):
            pass
    assert all(SID in w.state[str(path)][0] for path in w.folders.values())
    assert [p.name.startswith("loan-") for p in record_files(w)] == [True]
    measure(monkeypatch, later_boot(NOW))
    w.store.recover()
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())
    assert w.store.inspect(SID) is None


def test_the_profile_sweep_does_not_mistake_a_loan_record_for_a_stray_file(block, monkeypatch):
    w = block
    with pytest.raises(ProfileRefused, match="profile_acl_unproven"):
        with w.store.container(mode="review", active_tokens=lambda: ("t",), folders=folders(w)):
            pass
    measure(monkeypatch, later_boot(NOW))
    w.store.recover()  # raises profile_record_invalid if `loan-<attempt>.json` is not known
    w.store.recover()  # and a second time, with everything retired, changes nothing
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())


def test_a_loan_goes_back_at_a_recovery_that_the_fresh_folders_still_wait_on(block):
    w = block
    with pytest.raises(ProfileRefused, match="profile_acl_unproven"):
        with w.store.container(mode="dispatch", active_tokens=lambda: ("t",),
                               folders=folders(w)):
            pass
    with pytest.raises(ProfileRefused, match="profile_acl_unproven"):
        w.store.recover()  # no restart is proven: the fresh folders and the profile stay
    assert all(w.state[str(path)] == (PRIOR, False, OWNER) for path in w.folders.values())
    assert w.store.inspect(SID) is not None, "the profile waits for the proof as before"


def left_with_a_replaced_work_folder(w):
    """An attempt that ended with a child alive, whose work folder is another folder by now."""
    with pytest.raises(ProfileRefused, match="profile_acl_unproven"):
        with w.store.container(mode="dispatch", active_tokens=lambda: ("t",),
                               folders=folders(w)):
            pass
    work = w.folders["work"]
    work.rename(work.with_name("t1-moved"))
    work.mkdir()
    w.state[str(work)] = (OWNER + "x", True, OWNER)


def test_a_loan_that_cannot_go_back_does_not_keep_the_acl_and_profile_recoveries_from_running(
        block, monkeypatch):
    w = block
    left_with_a_replaced_work_folder(w)
    measure(monkeypatch, later_boot(NOW))
    with pytest.raises(ProfileRefused) as raised:
        w.store.recover()
    assert all(w.state[str(w.folders[key])] == (PRIOR, False, OWNER) for key in ("home", "install"))
    assert list((w.store.directory.parent / "container-attempts").glob("*")) == []
    assert w.store.inspect(SID) is None, "the profile was retired in the same recovery"
    assert "work folder is not the one the record names" in str(raised.value)


def test_the_owner_gives_the_astray_loan_up_and_the_whole_recovery_then_ends_clean(
        block, monkeypatch):
    w = block
    left_with_a_replaced_work_folder(w)
    measure(monkeypatch, later_boot(NOW))
    w.store.recover(abandon_loans=True)
    assert w.store.inspect(SID) is None
    w.store.recover()
