"""Native Windows reader conflicts and bounded fake-only atomic publication."""
import errno
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests import _fakeproc


@pytest.mark.skipif(os.name != "nt", reason="native Windows replacement semantics")
def test_reader_release_after_real_child_error_allows_atomic_publication(tmp_path):
    target, observed_error = tmp_path / "heartbeat", tmp_path / "error-seen"
    target.write_text("1", encoding="ascii")
    script = '''import importlib.util,json,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("fake_publisher",sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
replace=module.os.replace
errors=[]
def recording(source,destination):
    try:
        return replace(source,destination)
    except OSError as error:
        if not errors:
            errors.append({"exception":type(error).__name__,"errno":error.errno,
                           "winerror":getattr(error,"winerror",None)})
            Path(sys.argv[3]).write_text("1",encoding="ascii")
        raise
module.os.replace=recording
module._write_atomic(sys.argv[2],"2")
print(json.dumps({"first_error":errors[0],"published":True}))
'''
    child = None
    try:
        with target.open("r", encoding="ascii") as held:
            child = subprocess.Popen(
                [sys.executable, "-I", "-c", script, str(Path(_fakeproc.__file__)),
                 str(target), str(observed_error)], cwd=tmp_path,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            assert _fakeproc.wait_for_int(observed_error, timeout=5) == 1
            assert held.read() == "1"
            assert target.read_text(encoding="ascii") == "1"
        # Release happens only after the child reports a real failed replace.
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 0, stderr
        result = json.loads(stdout)
        print("SHARING_CALIBRATION " + json.dumps(result))
        assert result["first_error"]["exception"] == "PermissionError"
        assert result["first_error"]["winerror"] in (5, 32, 33)
        assert result["published"] is True
        assert target.read_text(encoding="ascii") == "2"
        assert list(tmp_path.glob("*.tmp")) == []
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="native Windows replacement semantics")
def test_reader_held_past_deadline_keeps_the_native_error_visible(tmp_path):
    target = tmp_path / "heartbeat"
    target.write_text("1", encoding="ascii")
    with target.open("r", encoding="ascii"):
        with pytest.raises(PermissionError) as caught:
            _fakeproc._write_atomic(str(target), "2")
    print("PUBLICATION_DEADLINE " + json.dumps({
        "exception": type(caught.value).__name__, "errno": caught.value.errno,
        "winerror": caught.value.winerror}))
    assert caught.value.winerror in (5, 32, 33)
    assert target.read_text(encoding="ascii") == "1"
    assert [path.read_text(encoding="ascii") for path in tmp_path.glob("*.tmp")] == ["2"]


def test_other_errors_propagate_immediately_without_a_retry(tmp_path, monkeypatch):
    errors = [OSError(errno.EIO, "synthetic I/O failure"),
              PermissionError(errno.EACCES, "no native sharing error code")]
    for error in errors:
        calls = []
        def failing_replace(*args):
            calls.append(args)
            raise error
        def no_sleep(_seconds):
            raise AssertionError("non-sharing failure was retried")
        with monkeypatch.context() as patch:
            patch.setattr(_fakeproc.os, "replace", failing_replace)
            patch.setattr(_fakeproc.time, "sleep", no_sleep)
            with pytest.raises(type(error)) as caught:
                _fakeproc._write_atomic(str(tmp_path / "heartbeat"), "2")
        assert caught.value is error
        assert len(calls) == 1
