"""The decision table of the first commit (spec 9.8, S4): pure, so every combination is judged."""
import itertools

import pytest

from conductor.command.git_setup_first_resume import (
    Act, Index, LOCKED, Lock, PREPARED, REF_MOVED, Ref, Refuse, STAGES, next_action)

EVERY = list(itertools.product(STAGES, Ref, Lock, Index))   # 3 * 3 * 3 * 3 = 81


def test_first_commit_resume_never_installs_an_index_without_an_own_lock_and_an_absent_index():
    chosen = [row for row in EVERY if next_action(*row) is Act.INSTALL_INDEX]
    assert chosen, "the witness must be able to say yes"
    for stage, ref, lock, index in chosen:
        assert (stage, ref, lock, index) == (REF_MOVED, Ref.AT_COMMIT, Lock.OWN, Index.ABSENT)


def test_first_commit_resume_never_moves_the_ref_without_an_own_lock_and_a_free_ref():
    chosen = [row for row in EVERY if next_action(*row) is Act.MOVE_REF]
    assert chosen
    for stage, ref, lock, index in chosen:
        assert (stage, ref, lock, index) == (LOCKED, Ref.ABSENT, Lock.OWN, Index.ABSENT)


def test_first_commit_resume_never_acts_on_a_foreign_lock_except_to_refuse_it():
    for row in EVERY:
        if row[2] is Lock.FOREIGN:
            step = next_action(*row)
            assert isinstance(step, Refuse), row
            assert step.reason in {"head_exists", "index_locked"} and not step.release_own_lock
    for row in EVERY:
        step = next_action(*row)
        if isinstance(step, Refuse) and step.release_own_lock:
            assert row[2] is Lock.OWN
        if step is Act.TAKE_LOCK:
            assert row[2] is Lock.NONE
        if step is Act.FINISH:
            assert row[0] == REF_MOVED and row[1] is Ref.AT_COMMIT and row[3] is Index.MATCHES


A, N, O, F = Index.ABSENT, Lock.NONE, Lock.OWN, Lock.FOREIGN
NO_LOCK = Refuse("index_locked", drop_copy=True)
SPEC_ROWS = [   # (stage, ref, lock, index) -> what 9.8 and S4 say happens
    ((PREPARED, Ref.ABSENT, N, A), Act.TAKE_LOCK),
    ((PREPARED, Ref.ABSENT, O, A), Act.MARK_LOCKED),
    ((PREPARED, Ref.ABSENT, F, A), NO_LOCK),
    ((PREPARED, Ref.ABSENT, O, Index.OTHER), Refuse("index_exists", release_own_lock=True)),
    ((LOCKED, Ref.ABSENT, O, A), Act.MOVE_REF),
    ((LOCKED, Ref.ABSENT, N, A), Act.TAKE_LOCK),
    ((PREPARED, Ref.AT_COMMIT, O, A), Act.MARK_REF_MOVED),
    ((LOCKED, Ref.AT_COMMIT, N, A), Act.MARK_REF_MOVED),
    ((REF_MOVED, Ref.ABSENT, O, A), Refuse("head_exists", release_own_lock=True)),
    ((REF_MOVED, Ref.OTHER, N, A), Refuse("head_exists")),
    ((REF_MOVED, Ref.AT_COMMIT, O, A), Act.INSTALL_INDEX),
    ((REF_MOVED, Ref.AT_COMMIT, N, A), Act.TAKE_LOCK),                  # retake, then recheck
    ((REF_MOVED, Ref.AT_COMMIT, N, Index.MATCHES), Act.FINISH),         # already installed
    ((REF_MOVED, Ref.AT_COMMIT, O, Index.MATCHES), Act.RELEASE_LOCK),   # two names, one inode
    ((REF_MOVED, Ref.AT_COMMIT, N, Index.OTHER), Refuse("index_exists")),
    ((REF_MOVED, Ref.AT_COMMIT, F, A), NO_LOCK),
]


@pytest.mark.parametrize("row, expected", SPEC_ROWS)
def test_first_commit_resume_follows_the_rows_the_spec_quotes(row, expected):
    assert next_action(*row) == expected


def _apply(step, state):
    stage, ref, lock, index = state
    return {
        Act.TAKE_LOCK: (stage, ref, Lock.OWN, index),
        Act.MARK_LOCKED: (LOCKED, ref, lock, index),
        Act.MOVE_REF: (stage, Ref.AT_COMMIT, lock, index),
        Act.MARK_REF_MOVED: (REF_MOVED, ref, lock, index),
        Act.INSTALL_INDEX: (stage, ref, Lock.NONE, Index.MATCHES),
        Act.RELEASE_LOCK: (stage, ref, Lock.NONE, index),
    }[step]


def test_first_commit_resume_terminates_from_every_combination_of_facts():
    for start in EVERY:
        state = start
        for _ in range(8):
            step = next_action(*state)
            if isinstance(step, Refuse) or step is Act.FINISH:
                break
            state = _apply(step, state)
        else:
            pytest.fail(f"no end from {start}")
