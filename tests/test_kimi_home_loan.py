"""The trusted staging identity restricts the real loan service, including at the final hold."""
import json

import pytest

from conductor.command.adapters.process_boundary import AttemptFolders
from conductor.command.adapters.process_loans import FolderLoans
from conductor.command.adapters.process_profile import ProfileRefused
from conductor.ownership_native import identity
from tests.test_process_loans import LoanHold, masks, OWNER, PRIOR, prior_acl, record_files, world


class StagingHold(LoanHold):
    def __init__(self, path, *, directory, grants):
        self.path, self.identity = path, identity(path)


def staged_world(tmp_path):
    w = world(tmp_path)
    home = w.root / ".kimi-home" / "attempt"
    (home / "credentials").mkdir(parents=True)
    w.folders["home"] = home
    config, leaf = home / "config.toml", home / "credentials/kimi-code.json"
    config.write_text("synthetic")
    leaf.write_text("synthetic")
    prior_acl(w)
    for path in (config, leaf.parent, leaf):
        w.state[str(path)] = (PRIOR, False, OWNER)
    # The fake native ACL store normally tracks only roots. Model Windows inheritance on
    # child reads. The separate native profile test checks this at the real process boundary.
    snapshot = w.store.native.acl_snapshot
    def observe(hold):
        text, protected, owner = snapshot(hold)
        inherited = hold.path in (config, leaf.parent, leaf) and not protected
        if inherited and w.sid in w.state[str(home)][0]:
            mask = 0x1200A9 if hold.path.is_dir() else 0x120089
            text += f"(A;ID;0x{mask:x};;;{w.sid})"
        return text, protected, owner
    w.store.native.acl_snapshot = observe
    return w


def bound_loan(w, ident, hold=StagingHold):
    return FolderLoans(w.store, w.store.native, hold_factory=hold, environ=w.environ,
                       readonly_home_identity=ident)


def test_bound_home_is_read_only_and_can_be_returned_from_its_record(tmp_path):
    w = staged_world(tmp_path)
    ident = identity(w.folders["home"])
    before = dict(w.state)
    loan = bound_loan(w, ident)
    record = loan.grant(w.profile_path, w.sid, "review", w.folders)
    home = json.loads(record.read_text())["loans"]["home"]
    assert home["identity"] == list(ident) and home["rights"] == "read"
    # Direct and inherited directories may be traversed. Files may never execute.
    assert masks(w.state[str(w.folders["home"])][0], w.sid) == [0x1200A9, 0x1200A9, 0x120089]
    loan.close()  # simulate a restarted recovery without the old live holds
    w.loans.restore(record)
    assert w.state == before


def test_substitution_on_actual_handle_refuses_before_grant_or_record(tmp_path):
    w = staged_world(tmp_path)
    home = w.folders["home"]
    ident = identity(home)
    before = dict(w.state)

    class SwappedHold(StagingHold):
        def __init__(self, path, **kw):
            if path == home:
                home.rename(home.with_name("original"))
                (home / "credentials").mkdir(parents=True)
                (home / "config.toml").write_text("synthetic replacement")
                (home / "credentials/kimi-code.json").write_text("synthetic replacement")
            super().__init__(path, **kw)

    loan = bound_loan(w, ident, SwappedHold)
    with pytest.raises(ProfileRefused, match="staged home"):
        loan.grant(w.profile_path, w.sid, "review", w.folders)
    assert identity(home) != ident and not record_files(w) and w.state == before


def test_stale_handoff_refuses_before_creating_a_new_profile(tmp_path, monkeypatch):
    w = staged_world(tmp_path)
    stale = (1, 2)
    assert identity(w.folders["home"]) != stale
    monkeypatch.setattr(w.store, "create_profile", lambda: pytest.fail("a profile was allocated"))
    with pytest.raises(ProfileRefused, match="staged home"):
        with w.store.container(mode="review", folders=w.folders, readonly_home_identity=stale):
            pytest.fail("a stale staged home was granted")


@pytest.mark.parametrize("bad", [False, (0, 0), (1, True), [1, 2], (1, 2, 3)])
def test_typed_home_identity_rejects_malformed_values(tmp_path, bad):
    with pytest.raises(ValueError, match="identity"):
        AttemptFolders("work/t1", ".kimi-home/a", str(tmp_path), readonly_home_identity=bad)


@pytest.mark.parametrize("member", ["", "config.toml", "credentials", "credentials/kimi-code.json"])
@pytest.mark.parametrize(("trustee", "rights"), [("AC", "FR"), ("S-1-15-3-1", "GW"),
                                                 ("S-1-15-2-2", "0x10000")])
def test_ambient_package_access_refuses_before_first_loan(tmp_path, member, trustee, rights):
    w = staged_world(tmp_path)
    home = w.folders["home"]
    target = str(home / member)
    sddl, protected, owner = w.state[target]
    w.state[target] = (sddl + f"(A;;{rights};;;{trustee})", protected, owner)
    before = dict(w.state)
    loan = bound_loan(w, identity(home))
    with pytest.raises(ProfileRefused, match="staged home"):
        loan.grant(w.profile_path, w.sid, "review", w.folders)
    assert not record_files(w) and w.state == before


def test_unowned_addition_to_staged_tree_refuses_before_grant(tmp_path):
    w = staged_world(tmp_path)
    home = w.folders["home"]
    (home / "credentials" / "unreviewed").write_bytes(b"untouched")
    loan = bound_loan(w, identity(home))
    with pytest.raises(ProfileRefused, match="staged home"):
        loan.grant(w.profile_path, w.sid, "review", w.folders)
    assert not record_files(w)
    assert (home / "credentials" / "unreviewed").read_bytes() == b"untouched"


def test_child_with_inheritance_cut_refuses_before_grant(tmp_path):
    w = staged_world(tmp_path)
    home = w.folders["home"]
    leaf = str(home / "credentials/kimi-code.json")
    sddl, _, owner = w.state[leaf]
    w.state[leaf] = (sddl, True, owner)
    loan = bound_loan(w, identity(home))
    with pytest.raises(ProfileRefused, match="protected child"):
        loan.grant(w.profile_path, w.sid, "review", w.folders)
    assert not record_files(w)


def test_unexpected_native_file_write_ace_after_grant_refuses_and_restores(tmp_path):
    w = staged_world(tmp_path)
    home, snapshot = w.folders["home"], w.store.native.acl_snapshot
    leaf = home / "credentials/kimi-code.json"
    before = dict(w.state)
    loan = bound_loan(w, identity(home))
    def unexpected(hold):
        text, protected, owner = snapshot(hold)
        if hold.path == leaf and w.sid in text:
            text += f"(A;ID;GW;;;{w.sid})"
        return text, protected, owner
    w.store.native.acl_snapshot = unexpected
    with pytest.raises(ProfileRefused, match="package rights"):
        loan.grant(w.profile_path, w.sid, "review", w.folders)
    assert len(record_files(w)) == 1
    loan.restore()
    loan.close()
    assert w.state == before
