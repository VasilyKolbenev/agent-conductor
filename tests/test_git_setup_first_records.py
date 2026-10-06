"""The durable records of the first commit: the op record, the bytes to install, the receipt.

Everything lives under `<data_root>/git/setup/`. The op only says how far the product got; what is
true is read from the repository on every retry, so these tests judge the files and their order,
never a Git state.
"""
import json
import os
from dataclasses import replace
from types import SimpleNamespace

import pytest

from conductor.command import git_setup_first_records as records
from conductor.command.accept_manifest import sha256
from conductor.command.git_setup_first_records import AWAITING_SIGNATURE, Op
from conductor.command.git_setup_first_resume import LOCKED, PREPARED, REF_MOVED
from conductor.command.git_setup_records import SetupRefused
from conductor.ownership import data_root

NONCE, OTHER_NONCE = "0123456789abcdef", "fedcba9876543210"
TREE, COMMIT = "a" * 40, "b" * 40
DIGEST, MESSAGE_DIGEST = "sha256:" + "c" * 64, "sha256:" + "d" * 64
DATA = b"DIRC\x00\x00\x00\x02" + bytes(range(40))
OTHER_DATA = b"DIRC\x00\x00\x00\x02" + bytes(range(40, 80))
NOW = "2026-10-05T21:00:00Z"
AUTHOR = {"name": "First Author", "email": "first@example.invalid"}


def an_op(data=DATA, **changes):
    fields = dict(
        stage=PREPARED, nonce=NONCE, mode="snapshot", paths_digest=DIGEST, digest_version=2,
        target_ref="refs/heads/trunk", object_format="sha1", expected_tree=TREE, commit=COMMIT,
        install_sha256=sha256(data), message_sha256=MESSAGE_DIGEST, file_count=2,
        requested_by="Owner", author=dict(AUTHOR), signing=False, started_at=NOW)
    return Op(**{**fields, **changes})


def setup_dir(root):
    return data_root(root) / "git" / "setup"


def op_file(root):
    return setup_dir(root) / records.OP_NAME


def install_file(root, nonce=NONCE):
    return setup_dir(root) / f"{records.INSTALL}{nonce}"


def names(root):
    return sorted(path.name for path in setup_dir(root).iterdir())


def encode(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"


def plant(root, change, **changes):
    """Start an op, then rewrite its record by hand with `change` applied to the decoded body."""
    records.start(root, an_op(**changes), DATA)
    body = json.loads(op_file(root).read_bytes())
    change(body)
    op_file(root).write_bytes(encode(body))


def damaged(call, *args, **keywords):
    with pytest.raises(SetupRefused) as caught:
        call(*args, **keywords)
    assert caught.value.reason == "setup_damaged"


# Each case plants one damage in an otherwise valid record; every one must read as setup_damaged.
DAMAGE = {
    "unknown_field": lambda b: b.update(extra=1),
    "missing_field": lambda b: b.pop("signing"),
    "schema_one": lambda b: b.update(schema_version=1),
    "schema_a_bool": lambda b: b.update(schema_version=True),
    "nonce_of_fifteen_hex": lambda b: b.update(nonce=NONCE[:-1]),
    "nonce_in_capitals": lambda b: b.update(nonce="0123456789ABCDEF"),
    "commit_longer_than_the_tree": lambda b: b.update(commit="b" * 64),
    "tree_that_does_not_fit_the_format": lambda b: b.update(object_format="sha256"),
    "unknown_object_format": lambda b: b.update(object_format="md5"),
    "ref_outside_heads": lambda b: b.update(target_ref="refs/tags/trunk"),
    "ref_with_a_control_character": lambda b: b.update(target_ref="refs/heads/a\nb"),
    "actor_with_a_control_character": lambda b: b.update(requested_by="Own\x07er"),
    "ref_with_a_lone_surrogate": lambda b: b.update(target_ref="refs/heads/\ud800"),
    "actor_with_a_lone_surrogate": lambda b: b.update(requested_by="Own\ud800er"),
    "author_name_a_lone_surrogate": lambda b: b.update(author={**AUTHOR, "name": "\ud800"}),
    "author_email_a_lone_surrogate": lambda b: b.update(
        author={**AUTHOR, "email": "a\udc80@example.invalid"}),
    "digest_version_one": lambda b: b.update(digest_version=1),
    "digest_version_a_float": lambda b: b.update(digest_version=2.0),
    "signing_as_a_word": lambda b: b.update(signing="false"),
    "author_without_a_name": lambda b: b.update(author={"email": "a@example.invalid"}),
    "author_with_an_extra_key": lambda b: b.update(author={**AUTHOR, "extra": "x"}),
    "author_with_an_empty_name": lambda b: b.update(author={**AUTHOR, "name": ""}),
    "message_digest_malformed": lambda b: b.update(message_sha256="sha256:xyz"),
    "commit_missing_at_locked": lambda b: b.update(stage=LOCKED, commit=None),
    "commit_missing_at_ref_moved": lambda b: b.update(stage=REF_MOVED, commit=None),
    "commit_set_at_awaiting_signature": lambda b: b.update(stage=AWAITING_SIGNATURE),
    "digest_missing_for_a_snapshot": lambda b: b.update(paths_digest=None),
    "digest_present_for_an_empty_commit": lambda b: b.update(mode="empty"),
    "unknown_mode": lambda b: b.update(mode="everything"),
    "too_many_files": lambda b: b.update(file_count=5001),
    "negative_file_count": lambda b: b.update(file_count=-1),
    "start_time_in_words": lambda b: b.update(started_at="yesterday"),
}


@pytest.mark.parametrize("case", DAMAGE)
def test_first_commit_op_record_with_any_damaged_field_is_setup_damaged(tmp_path, case):
    plant(tmp_path, DAMAGE[case])
    damaged(records.read_op, tmp_path)


def test_first_commit_op_record_round_trips_and_is_closed(tmp_path):
    op = an_op()
    assert records.read_op(tmp_path) is None
    assert records.start(tmp_path, op, DATA) == op
    assert records.read_op(tmp_path) == op
    raw = op_file(tmp_path).read_bytes()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1 and raw.isascii()
    assert set(json.loads(raw)) == {
        "schema_version", "stage", "nonce", "mode", "paths_digest", "digest_version", "target_ref",
        "object_format", "expected_tree", "commit", "install_sha256", "message_sha256",
        "file_count", "requested_by", "author", "signing", "started_at"}
    assert json.loads(raw)["schema_version"] == 2 and json.loads(raw)["digest_version"] == 2
    assert install_file(tmp_path).read_bytes() == DATA
    empty = an_op(nonce=OTHER_NONCE, mode="empty", paths_digest=None, file_count=0)
    records.retire(tmp_path, op)
    assert records.start(tmp_path, empty, DATA) == empty and records.read_op(tmp_path) == empty


def test_first_commit_op_record_that_is_not_one_json_object_is_setup_damaged(tmp_path):
    records.start(tmp_path, an_op(), DATA)
    good = op_file(tmp_path).read_bytes()
    stage = b'"stage":"prepared"'
    broken = {
        "a duplicate key": good.replace(stage, stage + b"," + stage),
        "a stage outside the four": good.replace(stage, b'"stage":"finished"'),
        "a stage with a trailing space": good.replace(stage, b'"stage":"prepared "'),
        "a list": b"[]\n",
        "text that is not JSON": b"not json\n",
        "bytes that are not UTF-8": b"\xff\xfe\n",
        "a record over its limit": good + b" " * records.OP_LIMIT,
    }
    for what, raw in broken.items():
        op_file(tmp_path).write_bytes(raw)
        with pytest.raises(SetupRefused, match="setup_damaged"):
            records.read_op(tmp_path)
        assert op_file(tmp_path).read_bytes() == raw, what      # a refusal rewrites nothing


def test_first_commit_records_nested_far_deeper_than_any_record_are_setup_damaged(tmp_path):
    """16000 bytes of brackets fit the size limit and are deeper than a JSON decoder allows on
    the older Pythons: that is a damaged record, not an exception of the decoder's own."""
    records.start(tmp_path, an_op(), DATA)
    nested = b"[" * 8000 + b"]" * 8000
    receipt = setup_dir(tmp_path) / records.RECEIPT_NAME
    for path, read in ((op_file(tmp_path), records.read_op), (receipt, records.read_receipt)):
        path.write_bytes(nested)
        damaged(read, tmp_path)


def test_first_commit_op_stage_advances_only_forward(tmp_path):
    op = records.start(tmp_path, an_op(), DATA)
    before = op_file(tmp_path).read_bytes()
    locked = records.advance(tmp_path, op, LOCKED)
    assert locked == replace(op, stage=LOCKED) and records.read_op(tmp_path) == locked
    after = op_file(tmp_path).read_bytes()
    assert after.replace(b'"stage":"locked"', b'"stage":"prepared"') == before
    for stage in (PREPARED, LOCKED):
        damaged(records.advance, tmp_path, locked, stage)
    moved = records.advance(tmp_path, locked, REF_MOVED)
    for stage in (PREPARED, LOCKED, REF_MOVED):
        damaged(records.advance, tmp_path, moved, stage)
    assert records.read_op(tmp_path) == moved
    assert names(tmp_path) == sorted([records.OP_NAME, install_file(tmp_path).name])


def test_first_commit_op_stage_replace_is_all_or_nothing(tmp_path, monkeypatch):
    op = records.start(tmp_path, an_op(), DATA)
    stored = op_file(tmp_path).read_bytes()

    def refuse(*_args):
        raise OSError("simulated fault at the replace")
    with monkeypatch.context() as patch:
        patch.setattr(records.os, "replace", refuse)
        with pytest.raises(OSError):
            records.advance(tmp_path, op, LOCKED)
    assert op_file(tmp_path).read_bytes() == stored and records.read_op(tmp_path) == op
    assert names(tmp_path) == sorted([records.OP_NAME, install_file(tmp_path).name])
    assert records.advance(tmp_path, op, LOCKED).stage == LOCKED


def test_first_commit_op_stage_skips_locked_only_to_ref_moved(tmp_path):
    op = records.start(tmp_path, an_op(), DATA)
    before = op_file(tmp_path).read_bytes()
    moved = records.advance(tmp_path, op, REF_MOVED)
    assert moved == replace(op, stage=REF_MOVED)
    assert op_file(tmp_path).read_bytes().replace(b"ref_moved", b"prepared") == before
    refused = [(PREPARED, PREPARED), (LOCKED, LOCKED), (LOCKED, PREPARED),
               (REF_MOVED, PREPARED), (REF_MOVED, LOCKED), (REF_MOVED, REF_MOVED)]
    for start, target in refused:
        folder = tmp_path / f"{start}-{target}"
        held = records.start(folder, an_op(), DATA)
        if start != PREPARED:
            held = records.advance(folder, held, start)
        damaged(records.advance, folder, held, target)
        assert records.read_op(folder) == held


def test_first_commit_op_waits_for_a_signature_and_takes_its_commit_only_when_the_ref_moved(
        tmp_path):
    waiting = records.start(tmp_path, an_op(stage=AWAITING_SIGNATURE, commit=None, signing=True),
                            DATA)
    assert records.read_op(tmp_path) == waiting and waiting.commit is None
    before = op_file(tmp_path).read_bytes()
    for stage, commit in ((REF_MOVED, None), (REF_MOVED, "b" * 64), (PREPARED, COMMIT),
                          (LOCKED, COMMIT), (AWAITING_SIGNATURE, COMMIT), (PREPARED, None),
                          (LOCKED, None)):
        damaged(records.advance, tmp_path, waiting, stage, commit=commit)
        assert op_file(tmp_path).read_bytes() == before
    moved = records.advance(tmp_path, waiting, REF_MOVED, commit=COMMIT)
    assert moved == replace(waiting, stage=REF_MOVED, commit=COMMIT)
    assert records.read_op(tmp_path) == moved
    was, now = json.loads(before), json.loads(op_file(tmp_path).read_bytes())
    assert {key for key in was if was[key] != now[key]} == {"stage", "commit"}
    prepared = records.start(tmp_path / "other", an_op(), DATA)
    damaged(records.advance, tmp_path / "other", prepared, LOCKED, commit=COMMIT)
    damaged(records.advance, tmp_path / "other", prepared, REF_MOVED, commit=COMMIT)


def test_first_commit_op_stage_never_moves_a_record_the_caller_does_not_hold(tmp_path):
    op = records.start(tmp_path, an_op(), DATA)
    moved = records.advance(tmp_path, op, REF_MOVED)
    stored = op_file(tmp_path).read_bytes()
    damaged(records.advance, tmp_path, op, LOCKED)          # a stale copy cannot step backwards
    damaged(records.advance, tmp_path, replace(moved, nonce=OTHER_NONCE), REF_MOVED)
    assert op_file(tmp_path).read_bytes() == stored


def test_first_commit_op_is_read_back_and_checked_against_its_install_bytes(tmp_path, monkeypatch):
    op = an_op()
    real = records._put

    def publish_other_bytes(root, path, payload):
        real(root, path, OTHER_DATA if path.name.startswith(records.INSTALL) else payload)
    monkeypatch.setattr(records, "_put", publish_other_bytes)
    damaged(records.start, tmp_path, op, DATA)
    assert records.read_op(tmp_path) is None and not op_file(tmp_path).exists()
    assert names(tmp_path) == [install_file(tmp_path).name]      # an orphan nothing names
    monkeypatch.setattr(records, "_put", real)
    assert records.start(tmp_path, op, DATA) == op              # the next start sweeps and lays
    assert install_file(tmp_path).read_bytes() == DATA
    install_file(tmp_path).unlink()
    damaged(records.read_op, tmp_path)
    assert op_file(tmp_path).exists()                           # what cannot be proven stays
    damaged(records.start, tmp_path, op, DATA)
    assert op_file(tmp_path).exists() and not install_file(tmp_path).exists()


def test_first_commit_op_start_publishes_nothing_for_an_invalid_op_or_oversized_bytes(
        tmp_path, monkeypatch):
    for bad in (an_op(requested_by="Own\ner"), an_op(commit=None), an_op(digest_version=1),
                an_op(install_sha256=sha256(OTHER_DATA))):
        damaged(records.start, tmp_path, bad, DATA)
    monkeypatch.setattr(records, "INDEX_LIMIT", len(DATA) - 1)
    damaged(records.start, tmp_path, an_op(), DATA)
    assert not setup_dir(tmp_path).exists()


def test_first_commit_op_start_leaves_a_standing_op_alone_and_repeats_idempotently(tmp_path):
    op = records.start(tmp_path, an_op(), DATA)
    assert records.start(tmp_path, op, DATA) == op
    before = {name: (setup_dir(tmp_path) / name).read_bytes() for name in names(tmp_path)}
    other = an_op(data=OTHER_DATA, nonce=OTHER_NONCE)
    damaged(records.start, tmp_path, other, OTHER_DATA)
    assert {name: (setup_dir(tmp_path) / name).read_bytes() for name in names(tmp_path)} == before


def test_first_commit_install_bytes_are_verified_against_the_recorded_digest(tmp_path):
    op = records.start(tmp_path, an_op(), DATA)
    assert records.read_install(tmp_path, op) == DATA
    flipped = bytearray(DATA)
    flipped[10] ^= 1
    install_file(tmp_path).write_bytes(bytes(flipped))
    damaged(records.read_install, tmp_path, op)
    damaged(records.read_op, tmp_path)
    install_file(tmp_path).unlink()
    damaged(records.read_install, tmp_path, op)


def receipt_row(**changes):
    return {**records.receipt_of(an_op(stage=REF_MOVED), NOW), **changes}


def test_first_commit_receipt_is_written_once_and_read_closed(tmp_path):
    assert records.read_receipt(tmp_path) is None
    row = receipt_row()
    assert records.write_receipt(tmp_path, row) == row
    assert records.write_receipt(tmp_path, dict(row)) == row
    assert records.read_receipt(tmp_path) == row
    damaged(records.write_receipt, tmp_path, receipt_row(requested_by="Someone"))
    assert records.read_receipt(tmp_path) == row
    elsewhere = tmp_path / "elsewhere"
    damaged(records.write_receipt, elsewhere, receipt_row(mode="x"))
    damaged(records.write_receipt, elsewhere, receipt_row(commit="b" * 64))
    assert not setup_dir(elsewhere).exists()                    # a bad row is never published
    path = setup_dir(tmp_path) / records.RECEIPT_NAME
    bad = [{**row, "extra": 1}, {**row, "mode": "x"}, {**row, "signature": "yes"},
           {**row, "digest_version": 1}, {**row, "schema_version": 2},
           {key: value for key, value in row.items() if key != "tree"},
           {**row, "target_ref": "refs/heads/\ud800"}]
    for body in bad:
        path.write_bytes(encode(body))
        damaged(records.read_receipt, tmp_path)


def test_first_commit_receipt_says_whether_a_signature_was_required(tmp_path):
    plain = records.receipt_of(an_op(stage=REF_MOVED), NOW)
    signed = records.receipt_of(an_op(stage=REF_MOVED, signing=True), NOW)
    assert plain["signature"] == "not_required" and signed["signature"] == "present"
    assert plain == {
        "schema_version": 1, "step": "first_commit", "mode": "snapshot", "paths_digest": DIGEST,
        "digest_version": 2, "target_ref": "refs/heads/trunk", "commit": COMMIT, "tree": TREE,
        "object_format": "sha1", "file_count": 2, "signature": "not_required",
        "requested_by": "Owner", "recorded_at": NOW}
    damaged(records.receipt_of, an_op(stage=AWAITING_SIGNATURE, commit=None), NOW)


def the_second_removal_fails(monkeypatch):
    """A crash between the two removals of a retirement: the first `unlink` works, the second
    raises. Returns the names it was asked to remove, in order."""
    real, asked = records._unlink_plain, []

    def stop_between_the_two_removals(root, path):
        asked.append(path.name)
        if len(asked) == 2:
            raise OSError("simulated crash between the two removals")
        real(root, path)
    monkeypatch.setattr(records, "_unlink_plain", stop_between_the_two_removals)
    return asked


def test_retiring_a_first_commit_removes_the_op_before_its_install_bytes(tmp_path, monkeypatch):
    op = records.start(tmp_path, an_op(), DATA)
    for name in ("init.json", "exclude.json", "unrelated.txt"):
        (setup_dir(tmp_path) / name).write_bytes(b"{}")
    with monkeypatch.context() as patch:
        asked = the_second_removal_fails(patch)
        with pytest.raises(OSError):
            records.retire(tmp_path, op)
    assert asked == [records.OP_NAME, install_file(tmp_path).name]
    assert names(tmp_path) == sorted([install_file(tmp_path).name, "init.json", "exclude.json",
                                      "unrelated.txt"])
    assert records.read_op(tmp_path) is None                    # no op, one orphan: nothing live
    fresh = an_op(data=OTHER_DATA, nonce=OTHER_NONCE)
    assert records.start(tmp_path, fresh, OTHER_DATA) == fresh
    assert names(tmp_path) == sorted([records.OP_NAME, install_file(tmp_path, OTHER_NONCE).name,
                                      "init.json", "exclude.json", "unrelated.txt"])
    assert records.read_op(tmp_path) == fresh


def test_calibration_removing_the_install_bytes_first_leaves_a_live_op_without_them(
        tmp_path, monkeypatch):
    """The old order of the forget, with the very fault of the test above: the op stands without
    the bytes it is restored from. The ruled order cannot reach this state."""
    op = records.start(tmp_path, an_op(), DATA)
    with monkeypatch.context() as patch:
        asked = the_second_removal_fails(patch)
        with pytest.raises(OSError):
            records._unlink_plain(tmp_path, install_file(tmp_path, op.nonce))
            records._unlink_plain(tmp_path, op_file(tmp_path))
    assert asked == [install_file(tmp_path).name, records.OP_NAME]
    assert op_file(tmp_path).exists() and not install_file(tmp_path).exists()
    damaged(records.read_op, tmp_path)                           # a live op, no bytes: refused


def test_first_commit_retire_removes_nothing_for_an_op_that_is_not_the_stored_one(tmp_path):
    op = records.start(tmp_path, an_op(), DATA)
    before = names(tmp_path)
    damaged(records.retire, tmp_path, replace(op, nonce=OTHER_NONCE))
    damaged(records.retire, tmp_path, replace(op, stage=REF_MOVED))
    assert names(tmp_path) == before and records.read_op(tmp_path) == op
    records.retire(tmp_path, op)
    assert names(tmp_path) == [] and records.read_op(tmp_path) is None


def test_first_commit_sweep_removes_only_unnamed_install_files_and_only_without_an_op(tmp_path):
    folder = setup_dir(tmp_path)
    folder.mkdir(parents=True)
    strangers = ["first_commit.index-short", f"first_commit.index-{OTHER_NONCE}.bak",
                 "init.json", "first_commit.json"]
    orphan = folder / f"{records.INSTALL}{OTHER_NONCE}"
    for name in (*strangers, orphan.name):
        (folder / name).write_bytes(b"x")
    op = an_op()
    kept = records.start(tmp_path / "second", op, DATA)          # a separate root, an op stands
    held = setup_dir(tmp_path / "second")
    (held / orphan.name).write_bytes(b"x")
    records.sweep_orphans(tmp_path / "second")
    assert (held / orphan.name).exists() and records.read_op(tmp_path / "second") == kept
    records.sweep_orphans(tmp_path)
    assert names(tmp_path) == sorted(strangers) and not orphan.exists()


def test_first_commit_sweep_refuses_what_is_not_a_plain_file_and_removes_nothing(tmp_path):
    folder = setup_dir(tmp_path)
    folder.mkdir(parents=True)
    stray = folder / f"{records.INSTALL}{'2' * 16}"
    stray.mkdir()                                                # a name of ours, not a file
    damaged(records.sweep_orphans, tmp_path)
    damaged(records.start, tmp_path, an_op(), DATA)
    assert stray.is_dir() and not op_file(tmp_path).exists()
    stray.rmdir()
    plain = folder / f"{records.INSTALL}{'1' * 16}"
    plain.write_bytes(b"x")
    linked = folder / "linked-name"
    try:
        os.link(plain, linked)
    except OSError as error:
        pytest.skip(f"no hard links here: {error}")
    damaged(records.sweep_orphans, tmp_path)                     # two names for one file
    assert plain.exists() and linked.exists()


def test_first_commit_new_op_freezes_what_the_preview_showed(tmp_path):
    shown = dict(target_ref="refs/heads/trunk", object_format="sha1", digest_version=2,
                 author=dict(AUTHOR), signing=False, files=[{"path": "a"}, {"path": "b"}])
    made = SimpleNamespace(nonce=NONCE, tree=TREE, commit=COMMIT, install=DATA)
    message = b"first commit\n"
    op = records.new_op("snapshot", DIGEST, "Owner", shown, made, NOW, message)
    assert op == an_op(message_sha256=sha256(message))
    assert records.start(tmp_path, op, DATA) == op
    asking = records.new_op("snapshot", DIGEST, "Owner", {**shown, "signing": True},
                            SimpleNamespace(**{**vars(made), "commit": None}), NOW, message)
    assert asking == an_op(stage=AWAITING_SIGNATURE, commit=None, signing=True,
                           message_sha256=sha256(message))
    empty = records.new_op("empty", None, "Owner", {**shown, "files": []}, made, NOW, message)
    assert (empty.mode, empty.paths_digest, empty.file_count) == ("empty", None, 0)
    assert records.start(tmp_path / "empty", empty, DATA) == empty
