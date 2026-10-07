"""Owned attempt ACL journal with injected native callbacks; no OS ACL mutation."""
from types import SimpleNamespace
import os

import pytest

from conductor.command.adapters.process_acl import AttemptAclJournal, _grant
from conductor.command.adapters.process_profile import ProfileJournal, ProfileRefused
from conductor.ownership_native import identity


SID = "S-1-15-2-1-2-3-4-5-6-7"


def fixture(tmp_path):
    data = tmp_path / "conductor.v3"
    data.mkdir()
    acl_state, mappings = {}, {}

    class FakeHold:
        def __init__(self, path, *, directory, security):
            assert directory and security
            self.path, self.identity = path, identity(path)

        def check(self):
            assert identity(self.path) == self.identity

        def close(self):
            pass

        def delete(self):
            self.check()
            self.path.rmdir()

    def derive(name):
        return SID

    def create(name, display):
        mappings[SID] = (name, display)
        return SID

    def delete(name):
        del mappings[SID]

    def snapshot(hold):
        hold.check()
        return acl_state.setdefault(str(hold.path), ("O:S-1-5-21-1D:(A;;FA;;;SY)", False, "S-1-5-21-1"))

    def set_acl(hold, sddl, *, protected):
        hold.check()
        acl_state[str(hold.path)] = (sddl, protected, "S-1-5-21-1")

    native = SimpleNamespace(acl_snapshot=snapshot, acl_set=set_acl,
                             acl_equal=lambda a, b: a == b)
    store = ProfileJournal(data, owner_nonce="a" * 32, root_identity=[1, 2],
                           data_identity=[3, 4], derive=derive, create=create,
                           inspect=mappings.get, delete=delete)
    store.native = native
    profile_path, sid = store.create_profile()
    return store, AttemptAclJournal(store, native, hold_factory=FakeHold), profile_path, sid, acl_state


def test_acl_grant_is_durable_before_native_set_and_cleanup_requires_proof(tmp_path):
    store, acl, profile_path, sid, state = fixture(tmp_path)
    record, paths = acl.prepare(profile_path, sid, "dispatch")
    assert record.exists() and all(path.exists() for path in paths.values())
    assert all(state[str(path)][1] for path in paths.values())
    with pytest.raises(ProfileRefused, match="profile_acl_unproven"):
        acl.retire(record)
    assert paths["work"].exists()
    (paths["work"] / "result.txt").write_text("done", encoding="utf-8")
    acl.retire(record, proven=True)
    stale = record.with_name(f".{record.name}.{'f' * 16}.tmp")
    stale.write_text("interrupted replace", encoding="utf-8")
    acl.recover()
    assert not stale.exists()
    assert not paths["parent"].exists()
    store.retire(profile_path)


def test_acl_refuses_hardlinked_child_before_restore_or_deletion(tmp_path):
    store, acl, profile_path, sid, state = fixture(tmp_path)
    record, paths = acl.prepare(profile_path, sid, "dispatch")
    foreign = tmp_path / "foreign.txt"
    foreign.write_text("foreign", encoding="utf-8")
    os.link(foreign, paths["work"] / "alias.txt")
    before = state[str(paths["work"])]
    with pytest.raises(ProfileRefused, match="profile_acl_invalid"):
        acl.retire(record, proven=True)
    assert state[str(paths["work"])] == before
    assert foreign.read_text(encoding="utf-8") == "foreign"


def test_acl_refuses_unexpected_parent_entry_before_propagating_restore(tmp_path):
    store, acl, profile_path, sid, state = fixture(tmp_path)
    record, paths = acl.prepare(profile_path, sid, "dispatch")
    (paths["parent"] / "extra.txt").write_text("not a leaf", encoding="utf-8")
    before = state[str(paths["parent"])]
    with pytest.raises(ProfileRefused, match="profile_acl_invalid"):
        acl.retire(record, proven=True)
    assert state[str(paths["parent"])] == before


def test_review_grant_has_no_write_and_dispatch_delete_is_descendants_only():
    owner = "S-1-5-21-1"
    review = _grant(owner, SID, mode="review", leaf="work")
    review_runtime = _grant(owner, SID, mode="review", leaf="runtime")
    dispatch = _grant(owner, SID, mode="dispatch", leaf="work")
    parent = _grant(owner, SID, mode="dispatch", leaf="parent")
    assert "0x1200a9" in review and "0x1301bf" not in review
    assert "(A;OICIIO;0x1301bf" in review_runtime
    assert "(A;;0x1201bf" in dispatch and "(A;OICIIO;0x1301bf" in dispatch
    assert SID not in parent
