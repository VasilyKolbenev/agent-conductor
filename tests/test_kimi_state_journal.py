"""A bounded, nonsecret Kimi state tree is recovered by identity, independently of a login."""
import os

import pytest

from conductor.command.adapters.process_acl import AttemptAclJournal
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.ownership_native import identity
from tests._boot_world import counter, later_boot, measure
from tests._prepared_world import read
from tests.test_process_acl import SID, fixture
from tests.test_process_loans import masks
from tests.test_process_profile import journal


NOW = counter(42)


def applied(tmp_path, monkeypatch):
    measure(monkeypatch, NOW)
    store, acl, profile, sid, state = fixture(tmp_path)
    record, paths = acl.prepare(profile, sid, "review", folders=True, kimi_state=True)
    return store, acl, record, paths, state


def test_kimi_state_and_every_fixed_child_are_recorded_separately(tmp_path, monkeypatch):
    _, acl, rec, paths, acls = applied(tmp_path, monkeypatch)
    root = paths["parent"] / "kimi-state"
    assert paths == {"parent": paths["parent"], "runtime": paths["parent"] / "runtime",
                     "kimi_state": root, "kimi_sessions": root / "sessions",
                     "kimi_logs": root / "logs", "kimi_credentials": root / "credentials"}
    assert {k: v["identity"] for k, v in read(rec)["paths"].items()} == {
        k: list(identity(path)) for k, path in paths.items()}
    assert masks(acls[str(root)][0], SID) == [0x1200ab, 0x13019f]
    assert masks(acls[str(root / "credentials")][0], SID) == [0x1200a9]
    assert masks(acls[str(root / "sessions")][0], SID) == [0x1201bf, 0x1301bf, 0x13019f]
    acl.retire(rec, proven=True)
    assert not paths["parent"].exists() and read(rec)["phase"] == "retired"


@pytest.mark.parametrize("overrides", [
    {"internet_client": True}, {"mode": "dispatch"}, {"readonly_home_identity": None}])
def test_state_cannot_open_without_the_offline_staged_review(tmp_path, overrides):
    store, mappings, _ = journal(tmp_path)
    args = {"mode": "review", "internet_client": False, "folders": {},
            "readonly_home_identity": (12, 34), "kimi_state": True}
    with pytest.raises(ProfileRefused, match="offline staged home"):
        with store.container(**{**args, **overrides}):
            pytest.fail("unsafe state was granted")
    assert mappings == {} and not store.directory.exists()


def test_unrecorded_partial_tree_is_preserved_and_never_called_retired(tmp_path):
    store, mappings, deleted = journal(tmp_path)
    profile, sid = store.create_profile()
    attempt = store.directory.parent / "container-attempts" / read(profile)["attempt"]
    (attempt / "kimi-state").mkdir(parents=True)
    marker = attempt / "kimi-state" / "unproven"
    marker.write_text("preserve")
    with pytest.raises(ProfileRefused, match="not been retired"):
        store.recover()
    assert marker.read_text() == "preserve" and sid in mappings
    assert not deleted and read(profile)["phase"] == "created"


def test_retiring_a_profile_must_establish_that_its_attempt_is_absent(tmp_path, monkeypatch):
    store, mappings, deleted = journal(tmp_path)
    profile, sid = store.create_profile()
    attempt = store.directory.parent / "container-attempts" / read(profile)["attempt"]
    original = os.lstat
    def unreadable(path, *args, **kwargs):
        if path == attempt:
            raise PermissionError("injected access denial")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, "lstat", unreadable)
    with pytest.raises(ProfileRefused, match="cannot establish"):
        store.retire(profile)
    assert sid in mappings and not deleted and read(profile)["phase"] == "created"


def test_cleanup_resumes_after_deleting_one_confirmed_directory(tmp_path, monkeypatch):
    store, acl, record, paths, _ = applied(tmp_path, monkeypatch)
    target = acl.holds[1]["kimi_sessions"]
    delete = target.delete
    def interrupted():
        delete()
        raise OSError("crash after the first removal")
    monkeypatch.setattr(target, "delete", interrupted)
    with pytest.raises(OSError, match="first removal"):
        acl.retire(record, proven=True)
    acl.close()
    assert not paths["kimi_sessions"].exists()
    assert read(record)["phase"] == "retiring"
    measure(monkeypatch, later_boot(NOW))
    fresh = AttemptAclJournal(store, store.native, hold_factory=acl.hold_factory)
    fresh.recover()
    assert read(record)["phase"] == "retired" and not paths["parent"].exists()


def test_new_journal_restores_interrupted_state_after_proven_restart(tmp_path, monkeypatch):
    store, acl, rec, paths, _ = applied(tmp_path, monkeypatch)
    work = paths["kimi_sessions"] / "one"
    work.mkdir()
    (work / "events").write_bytes(b"fixture data")
    acl.close()
    fresh = AttemptAclJournal(store, store.native, hold_factory=acl.hold_factory)
    with pytest.raises(ProfileRefused, match="restart"):
        fresh.recover()
    assert (work / "events").read_bytes() == b"fixture data"
    measure(monkeypatch, later_boot(NOW))
    fresh.recover()
    fresh.recover()
    assert not paths["parent"].exists() and read(rec)["phase"] == "retired"


@pytest.mark.parametrize("fault", ["missing", "replacement", "outside-link", "unknown", "token"])
def test_bad_state_stays_unretired_and_preserves_external_file(tmp_path, monkeypatch, fault):
    store, acl, rec, paths, _ = applied(tmp_path, monkeypatch)
    acl.close()
    outside = tmp_path / "external"
    outside.write_bytes(b"untouched")
    leaf = paths["kimi_logs"]
    if fault == "outside-link":
        os.link(outside, leaf / "hardlink")
    elif fault == "unknown":
        (paths["kimi_state"] / "unexpected").write_text("preserve")
    elif fault == "token":
        (paths["kimi_credentials"] / "other-region").write_bytes(b"fixture")
    else:
        leaf.rename(tmp_path / "original-logs")
        if fault == "replacement":
            leaf.mkdir()
            (leaf / "different").write_bytes(b"replacement")
    measure(monkeypatch, later_boot(NOW))
    fresh = AttemptAclJournal(store, store.native, hold_factory=acl.hold_factory)
    with pytest.raises(ProfileRefused):
        fresh.recover()
    assert read(rec)["phase"] != "retired" and outside.read_bytes() == b"untouched"
    if fault == "replacement":
        assert (leaf / "different").read_bytes() == b"replacement"
    if fault == "unknown":
        assert (paths["kimi_state"] / "unexpected").read_text() == "preserve"
    if fault == "token":
        assert (paths["kimi_credentials"] / "other-region").read_bytes() == b"fixture"
