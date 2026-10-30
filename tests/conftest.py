"""Scope the Windows fake-process launch seam to each pytest test."""
import os
import subprocess

import pytest

from tests import _fakeprocess


@pytest.fixture(autouse=True)
def registered_fake_processes():
    """The seam has its own patch scope, not the test's `monkeypatch`: a test that calls
    `monkeypatch.undo()` reverts its own patches and must not revert the seam with them."""
    with pytest.MonkeyPatch.context() as seam:
        seam.setattr(subprocess, "Popen", _fakeprocess.popen_for(
            subprocess.Popen, windows=os.name == "nt"))
        try:
            yield
        finally:
            _fakeprocess.clear()
