"""`read_leaf`: the one reading of a credential file the relay copies from.

The file is the operator's own login, so it is read as strictly as a file that could have been
put there by something else: an ordinary single-link file, as large as a login file is and no
larger, and one JSON object in strict UTF-8. Every refusal is a closed code and a sentence with no
path and no value, and none of them is an exception: the caller turns them into a refusal before
anything is claimed.

A link standing where the file should be is the case this guards most. A real file symlink needs a
privilege this machine does not give the test process (error 1314 was measured), so the symlink and
the reparse-point cases are answered to `read_leaf` by the file-system boundary (`os.lstat`) as the
operating system words them; a junction and a hard link are real.
"""
from __future__ import annotations

import hashlib
import os
import stat
from types import SimpleNamespace

import pytest

from conductor.command.adapters import login_relay
from conductor.command.adapters.login_home import CREDENTIAL_LIMIT
from conductor.command.adapters.login_relay import Leaf, Refused, read_leaf
from tests.relay_fixtures import link

DOCUMENT = b'{"alpha": 1, "beta": ["fake-value-0123456789"]}'


def place(tmp_path, data=DOCUMENT, name="leaf.json"):
    target = tmp_path / name
    target.write_bytes(data)
    return target


def codes(found):
    assert isinstance(found, Refused), found
    return found.code


def leaf_of(found):
    assert isinstance(found, Leaf), found
    return found


def as_the_os_words_it(monkeypatch, target, **answer):
    """`os.lstat` answers for one path with the real answer changed as given; the rest is real."""
    real = os.lstat

    def lstat(path, *args, **kwargs):
        found = real(path, *args, **kwargs)
        if os.fspath(path) != os.fspath(target):
            return found
        fields = {name: getattr(found, name) for name in dir(found) if name.startswith("st_")}
        fields.update(answer)
        return SimpleNamespace(**fields)

    monkeypatch.setattr(login_relay.os, "lstat", lstat)


def test_a_plain_file_is_read_whole_with_the_digest_of_its_bytes(tmp_path):
    found = read_leaf(place(tmp_path))

    assert found == Leaf(
        {"alpha": 1, "beta": ["fake-value-0123456789"]},
        "d3d51543ad94ccf097963b405a4fcd02a6b802b486c0b1db971738c5c70e3b22")
    assert found.digest == hashlib.sha256(DOCUMENT).hexdigest()


def test_the_digest_is_of_the_bytes_and_not_of_the_document(tmp_path):
    """Two spellings of one document are two files: a change of spelling is a change."""
    one = leaf_of(read_leaf(place(tmp_path, b'{"a":1}', "one.json")))
    other = leaf_of(read_leaf(place(tmp_path, b'{"a": 1}', "other.json")))

    assert one.doc == other.doc == {"a": 1}
    assert one.digest != other.digest


def test_a_file_that_is_not_there_is_refused_by_its_own_code(tmp_path):
    assert codes(read_leaf(tmp_path / "nothing.json")) == "leaf_absent"


def test_a_folder_where_the_file_should_be_is_refused(tmp_path):
    (tmp_path / "leaf.json").mkdir()

    assert codes(read_leaf(tmp_path / "leaf.json")) == "leaf_unsafe"


def test_a_junction_standing_where_the_file_should_be_is_refused(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link(tmp_path / "leaf.json", elsewhere)

    assert codes(read_leaf(tmp_path / "leaf.json")) == "leaf_unsafe"


def test_a_symlink_standing_where_the_file_should_be_is_refused(tmp_path, monkeypatch):
    target = place(tmp_path)
    as_the_os_words_it(monkeypatch, target, st_mode=stat.S_IFLNK | 0o777)

    assert codes(read_leaf(target)) == "leaf_unsafe"


def test_a_file_behind_a_reparse_point_is_refused(tmp_path, monkeypatch):
    """A placeholder or a mounted-folder kind of reparse tag on a file that says it is regular."""
    target = place(tmp_path)
    as_the_os_words_it(monkeypatch, target, st_reparse_tag=0x9000001A)

    assert codes(read_leaf(target)) == "leaf_unsafe"


def test_a_real_plain_file_reports_no_reparse_tag_on_this_system(tmp_path):
    """The precondition of the case above: an ordinary file here is not reparse-tagged."""
    info = os.lstat(place(tmp_path))

    assert getattr(info, "st_reparse_tag", 0) == 0
    assert read_leaf(tmp_path / "leaf.json") != Refused("leaf_unsafe")


def test_a_second_hard_link_to_the_file_refuses_it(tmp_path):
    target = place(tmp_path)
    os.link(target, tmp_path / "second-name.json")

    assert os.lstat(target).st_nlink == 2, "this volume does not count hard links"
    assert codes(read_leaf(target)) == "leaf_unsafe"


def test_a_file_swapped_between_the_look_and_the_open_is_refused(tmp_path, monkeypatch):
    """What was looked at is not what was opened: the identity of the two differs."""
    target = place(tmp_path)
    real = os.lstat(target)
    as_the_os_words_it(monkeypatch, target, st_ino=real.st_ino + 1)

    assert codes(read_leaf(target)) == "leaf_unsafe"


def test_the_limit_is_the_credential_limit_of_the_login_home(tmp_path):
    padding = b" " * (CREDENTIAL_LIMIT - len(b"{}"))
    exact = place(tmp_path, b"{}" + padding, "exact.json")
    over = place(tmp_path, b"{}" + padding + b" ", "over.json")

    assert CREDENTIAL_LIMIT == 64 * 1024
    assert os.lstat(exact).st_size == CREDENTIAL_LIMIT
    assert leaf_of(read_leaf(exact)).doc == {}
    assert codes(read_leaf(over)) == "leaf_too_large"


def test_a_caller_may_name_its_own_larger_limit(tmp_path):
    big = place(tmp_path, b'{"a": "' + b"x" * (CREDENTIAL_LIMIT + 10) + b'"}')

    assert codes(read_leaf(big)) == "leaf_too_large"
    larger = leaf_of(read_leaf(big, limit=CREDENTIAL_LIMIT * 2))
    assert larger.doc["a"] == "x" * (CREDENTIAL_LIMIT + 10)


@pytest.mark.parametrize("data", [
    pytest.param(b"", id="empty"),
    pytest.param(b'{"a": 1', id="truncated"),
    pytest.param(b"[1, 2]", id="list"),
    pytest.param(b'"text"', id="string"),
    pytest.param(b"12", id="number"),
    pytest.param(b"null", id="null"),
    pytest.param(b"\xff\xfe{}", id="utf16-mark"),
    pytest.param(b"\xef\xbb\xbf{}", id="utf8-mark"),
    pytest.param(b'{"a": "\xc3("}', id="broken-utf8"),
    pytest.param(b'{"a": 1, "a": 2}', id="two-values-for-one-key"),
    pytest.param(b'{"a": NaN}', id="nan"),
    pytest.param(b'{"a": Infinity}', id="infinity"),
    pytest.param(b"[" * 60000, id="nested-past-the-recursion-limit"),
])
def test_anything_that_is_not_one_strict_json_object_is_refused(tmp_path, data):
    """Truncated, empty, not an object, not UTF-8, a byte order mark, two values for one key."""
    assert codes(read_leaf(place(tmp_path, data))) == "leaf_malformed"


def test_every_refusal_has_a_sentence_that_names_no_path_and_no_value(tmp_path):
    target = tmp_path / "secret-name-of-a-folder"
    found = read_leaf(target)

    assert found.phrase and str(tmp_path) not in found.phrase
    assert "secret-name-of-a-folder" not in found.phrase
    assert set(login_relay.REFUSALS) >= {
        "leaf_absent", "leaf_unsafe", "leaf_too_large", "leaf_malformed"}


def test_an_unknown_refusal_code_cannot_be_made():
    with pytest.raises(ValueError):
        Refused("not-in-the-vocabulary")
