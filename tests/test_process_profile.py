"""Profile journal proves an exact owned mapping before any deletion."""
import json
import os

import pytest

from conductor.command.adapters.process_profile import ProfileJournal, ProfileRefused


def journal(tmp_path):
    mappings = {}
    deleted = []
    data = tmp_path / "conductor.v3"
    data.mkdir()

    def derive(name):
        return "S-1-15-2-1-2-3-4-5-6-7" if name else ""

    def create(name, display):
        sid = derive(name)
        mappings[sid] = (name, display)
        return sid

    def delete(name):
        sid = derive(name)
        deleted.append(name)
        del mappings[sid]

    store = ProfileJournal(data, owner_nonce="a" * 32, root_identity=[1, 2],
                           data_identity=[3, 4], derive=derive, create=create,
                           inspect=mappings.get, delete=delete)
    return store, mappings, deleted


def test_plan_precedes_create_and_recovery_handles_crash_before_record_update(tmp_path):
    store, mappings, deleted = journal(tmp_path)
    path, plan = store.plan()
    assert json.loads(path.read_text(encoding="utf-8"))["phase"] == "planned"
    mappings[plan["sid"]] = (plan["moniker"], plan["display"])
    interrupted_update = path.with_name(f".{path.name}.{'f' * 16}.tmp")
    interrupted_update.write_text("partial state", encoding="utf-8")
    store.recover()
    assert deleted == [plan["moniker"]]
    assert not interrupted_update.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["phase"] == "retired"
    store.recover()
    assert len(deleted) == 1


def test_planned_profile_absent_from_os_never_calls_delete(tmp_path):
    store, mappings, deleted = journal(tmp_path)
    path, plan = store.plan()
    assert plan["sid"] not in mappings
    store.recover()
    assert deleted == []
    assert json.loads(path.read_text(encoding="utf-8"))["phase"] == "retired"


def test_foreign_mapping_never_deleted_even_with_matching_sid(tmp_path):
    store, mappings, deleted = journal(tmp_path)
    path, plan = store.plan()
    mappings[plan["sid"]] = (plan["moniker"], "foreign display")
    with pytest.raises(ProfileRefused, match="profile_ambiguous"):
        store.recover()
    assert not deleted and json.loads(path.read_text(encoding="utf-8"))["phase"] == "planned"
    with pytest.raises(ProfileRefused, match="profile_conflict"):
        store.create_profile()
    assert not deleted


def test_create_existing_race_leaves_planned_record_and_foreign_profile(tmp_path):
    store, mappings, deleted = journal(tmp_path)

    def raced_create(moniker, display):
        mappings[store.derive(moniker)] = (moniker, "another owner's display")
        raise FileExistsError("CreateAppContainerProfile found an existing name")

    store.create = raced_create
    with pytest.raises(FileExistsError):
        store.create_profile()
    with pytest.raises(ProfileRefused, match="profile_ambiguous"):
        store.recover()
    assert not deleted
    assert next(store.directory.glob("profile-*.json")).read_text(encoding="utf-8").find('"phase":"planned"') > 0


def test_created_profile_normal_cleanup_and_owner_record_binding(tmp_path):
    store, mappings, deleted = journal(tmp_path)
    path, sid = store.create_profile()
    assert sid in mappings
    store.retire(path)
    assert len(deleted) == 1 and sid not in mappings
    path.write_text(path.read_text(encoding="utf-8").replace('"owner_nonce":"' + "a" * 32,
                                                               '"owner_nonce":"' + "b" * 32),
                    encoding="utf-8")
    with pytest.raises(ProfileRefused, match="profile_record_invalid"):
        store.recover()


def test_native_profile_mapping_preserves_owned_display_marker(tmp_path):
    if os.name != "nt":
        pytest.skip("AppContainer profiles require Windows")
    from conductor.command.adapters import _winlaunch

    data = tmp_path / "conductor.v3"
    data.mkdir()
    store = ProfileJournal(data, owner_nonce="b" * 32, root_identity=[1, 2],
                           data_identity=[3, 4], derive=_winlaunch.derive_profile_sid,
                           create=_winlaunch.create_profile, inspect=_winlaunch.inspect_profile,
                           delete=_winlaunch.delete_profile)
    try:
        path, sid = store.create_profile()
        record = json.loads(path.read_text(encoding="utf-8"))
        assert _winlaunch.inspect_profile(sid) == (record["moniker"], record["display"])
    finally:
        store.recover()
    assert _winlaunch.inspect_profile(sid) is None
