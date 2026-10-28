"""Scope the Windows fake-process launch seam to each pytest test."""
import os
import subprocess

import pytest

from tests import _fakeprocess


@pytest.fixture(autouse=True)
def registered_fake_processes(monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", _fakeprocess.popen_for(
        subprocess.Popen, windows=os.name == "nt"))
    try:
        yield
    finally:
        _fakeprocess.clear()
