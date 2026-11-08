"""Scope verified Windows launcher doubles to each test which uses this fixture."""
import os
import subprocess

import pytest

from tests import _fakeprocess


@pytest.fixture(autouse=True)
def registered_fake_processes():
    """A test may undo its own monkeypatch without uninstalling the fixture guard."""
    with pytest.MonkeyPatch.context() as seam:
        seam.setattr(subprocess, "Popen", _fakeprocess.popen_for(
            subprocess.Popen, windows=os.name == "nt"))
        try:
            yield
        finally:
            _fakeprocess.clear()
