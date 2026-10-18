"""Two attempts of different harnesses overlap: each return leaves the other's entries.

The ACL natives are fakes here; the same overlap runs natively in
`test_process_login_native_overlap`.

Each harness keeps its own login home, its own pinned install folder and its own work item, and each
attempt holds the lease on its own login home only. The return of one attempt takes away that
attempt's profile entries and nothing else, so the attempt still running keeps every right it was
given, on all three of its folders, and is never given the other's login home.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from conductor.command.adapters.process_loans import FolderLoans
from conductor.command.adapters.process_profile import ProfileRefused
from tests.login_gate import login_loan_open  # noqa: F401 -- a fixture
from tests.test_process_loans import OWNER, PRIOR, masks, record_files, world
from tests.test_process_login_grant import AnyHold, leased_fact

pytestmark = pytest.mark.usefixtures("login_loan_open")

SID2 = "S-1-15-2-1-2-3-4-5-6-8"
FOLDER, FILES = 0x1201BF, 0x13019F


def two_harnesses(tmp_path):
    """Attempt `a` (claude-code) and attempt `b` (codex): every folder of theirs is their own."""
    w = world(tmp_path, extra_sids=(SID2,))
    logins = tmp_path / "DecemberCommand" / "logins"
    a = {"work": w.folders["work"], "install": w.folders["install"],
         "login": logins / "claude-code"}
    b = {"work": w.root / "work" / "t2", "install": tmp_path / "harnesses" / "other" / "2.0",
         "login": logins / "codex"}
    for path in (*a.values(), *b.values()):
        path.mkdir(parents=True, exist_ok=True)
        w.state[str(path)] = (PRIOR, False, OWNER)
    profile_b, sid_b = w.store.create_profile()
    both = [a["login"], b["login"]]

    def loans(login):
        return FolderLoans(w.store, w.store.native, hold_factory=AnyHold, environ=w.environ,
                           login_homes=lambda: tuple(both),
                           leased_login=lambda: leased_fact(login))

    first = SimpleNamespace(loans=loans(a["login"]), path=w.profile_path, sid=w.sid, folders=a)
    second = SimpleNamespace(loans=loans(b["login"]), path=profile_b, sid=sid_b, folders=b)
    return w, first, second


def grant(w, attempt):
    return attempt.loans.grant(attempt.path, attempt.sid, "dispatch", attempt.folders)


def sid_on(w, attempt):
    return {key: masks(w.state[str(path)][0], attempt.sid) for key, path in attempt.folders.items()}


def test_the_grant_of_one_attempt_gives_the_other_attempts_login_home_nothing(tmp_path):
    w, a, b = two_harnesses(tmp_path)
    grant(w, a)
    assert w.state[str(b.folders["login"])] == (PRIOR, False, OWNER)
    grant(w, b)
    assert a.sid not in w.state[str(b.folders["login"])][0]
    assert b.sid not in w.state[str(a.folders["login"])][0]
    assert sorted(sid_on(w, a)["login"]) == [FOLDER, FOLDER, FILES]
    assert sorted(sid_on(w, b)["login"]) == [FOLDER, FOLDER, FILES]


@pytest.mark.parametrize("order", ["a-leaves-first", "b-leaves-first"])
def test_of_two_overlapping_attempts_the_one_that_leaves_takes_back_only_its_own_entries(
        tmp_path, order):
    w, a, b = two_harnesses(tmp_path)
    records = {"a": grant(w, a), "b": grant(w, b)}
    together = {"a": sid_on(w, a), "b": sid_on(w, b)}
    leaving, staying = ("a", "b") if order == "a-leaves-first" else ("b", "a")
    attempts = {"a": a, "b": b}
    attempts[leaving].loans.restore(records[leaving])
    for key, path in attempts[leaving].folders.items():
        assert w.state[str(path)] == (PRIOR, False, OWNER), f"{leaving} left an entry on {key}"
    assert sid_on(w, attempts[staying]) == together[staying], "the attempt running lost rights"
    assert all(rights for rights in sid_on(w, attempts[staying]).values())
    attempts[staying].loans.restore(records[staying])
    assert all(w.state[str(path)] == (PRIOR, False, OWNER)
               for attempt in (a, b) for path in attempt.folders.values())
    phases = [json.loads(p.read_text(encoding="utf-8"))["phase"] for p in record_files(w)]
    assert phases == ["retired", "retired"]


def test_an_attempt_is_refused_the_login_home_of_the_other_while_the_others_loan_stands(tmp_path):
    w, a, b = two_harnesses(tmp_path)
    grant(w, a)
    with pytest.raises(ProfileRefused, match="profile_acl_invalid: .*lease does not name"):
        b.loans.grant(b.path, b.sid, "dispatch", {**b.folders, "login": a.folders["login"]})
    assert sorted(sid_on(w, a)["login"]) == [FOLDER, FOLDER, FILES]
    assert b.sid not in w.state[str(a.folders["login"])][0]


def test_an_entry_another_hand_adds_to_a_login_home_during_the_loan_is_there_after_it(tmp_path):
    w, a, b = two_harnesses(tmp_path)
    record = grant(w, a)
    login = str(a.folders["login"])
    foreign = "(A;OICI;0x1200a9;;;S-1-5-21-77)"
    sddl, protected, owner = w.state[login]
    w.state[login] = (sddl + foreign, protected, owner)
    a.loans.restore(record)
    assert w.state[login] == (PRIOR + foreign, False, OWNER)
