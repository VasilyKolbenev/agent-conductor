"""A git read can carry input, a larger answer and its own clock (spec 9.1.2, 9.3).

The seed reads the bytes of a tree through `cat-file --batch`, which takes its object names on
stdin, answers with as many bytes as the batch holds and is allowed longer than a one-line probe.
So a reader takes three keywords after `separate_stderr`: `stdin`, `output_limit` and `timeout`,
and hands each to the runner as the spec's own field. A call with none of them is the call it
always was. The wiring is judged against a runner that records the spec it was given; the two
effects that only a real git can show (the object named on stdin is read, a cut answer says so)
are judged against a real repository.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conductor.command import project_git
from conductor.command.adapters.process import STDIN_LIMIT
from tests.git_repo_helpers import (
    Script, blob_oid, commit, needs_git, real_reader, repository, said)


class Recording:
    """A runner that answers one fixed outcome and keeps every spec it was handed."""

    def __init__(self):
        self.specs = []

    def run(self, spec):
        self.specs.append(spec)
        return SimpleNamespace(exit_code=0, output=b"ok", output_truncated=False,
                               status="finished")


def reader_over(runner):
    return project_git.process_git_read(runner, "git", "/cwd", env={"LC_ALL": "C"})


def test_a_call_with_no_keyword_keeps_the_defaults_it_always_had():
    runner = Recording()
    reader_over(runner)(["status"])
    spec, = runner.specs
    assert spec.stdin_bytes is None
    assert spec.output_limit == project_git.READ_OUTPUT_LIMIT
    assert spec.timeout_seconds == project_git.READ_TIMEOUT_SECONDS


def test_the_three_keywords_arrive_in_the_spec_as_given():
    runner = Recording()
    reader_over(runner)(["cat-file", "--batch"], True, stdin=b"abc\n", output_limit=4096,
                        timeout=30)
    spec, = runner.specs
    assert (spec.stdin_bytes, spec.output_limit, spec.timeout_seconds) == (b"abc\n", 4096, 30)
    assert spec.separate_stderr is True
    assert spec.argv[-2:] == ("cat-file", "--batch")


def test_a_keyword_is_only_a_keyword_and_the_second_place_is_still_separate_stderr():
    runner = Recording()
    with pytest.raises(TypeError):
        reader_over(runner)(["status"], False, b"input")
    assert runner.specs == []


def test_the_ceiling_the_seed_sizes_its_batches_against_is_the_runners_own():
    assert STDIN_LIMIT == 256 * 1024


def test_a_script_reader_takes_the_keywords_and_keeps_them_apart_from_the_call_record():
    script = Script(said(b"one"), said(b"two"))
    assert script(["a"]).output == b"one"
    assert script(["b"], True, stdin=b"x", output_limit=9, timeout=3).output == b"two"
    assert script.calls == [(("a",), False), (("b",), True)]
    assert script.keywords == [{}, {"stdin": b"x", "output_limit": 9, "timeout": 3}]


@needs_git
def test_a_real_git_reads_the_object_named_on_stdin(tmp_path):
    folder = repository(tmp_path)
    commit(folder, {"a.txt": "alpha\n"})
    oid = blob_oid(folder, "a.txt")
    answer = real_reader(tmp_path)(
        ["-C", str(folder), "cat-file", "--batch"], True, stdin=f"{oid}\n".encode())
    assert answer.exit_code == 0 and not answer.truncated
    assert answer.output == f"{oid} blob 6\nalpha\n\n".encode()


@needs_git
def test_a_real_answer_longer_than_its_limit_is_cut_and_says_so(tmp_path):
    folder = repository(tmp_path)
    commit(folder, {"big.txt": "x" * 5000})
    oid = blob_oid(folder, "big.txt")
    reader = real_reader(tmp_path)
    cut = reader(["-C", str(folder), "cat-file", "-p", oid], True, output_limit=1000)
    whole = reader(["-C", str(folder), "cat-file", "-p", oid], True, output_limit=8000)
    assert cut.truncated and len(cut.output) <= 1000
    assert not whole.truncated and len(whole.output) == 5000
