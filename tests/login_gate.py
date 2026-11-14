"""Opens the gate of the leased login home for a test that exercises the loan itself.

The runner loans a leased login home only while `process_boundary.LOGIN_LOAN_OPEN` is True, and as
shipped it is not (`test_process_login_closed.py`). A test of what the loan grants, refuses,
journals and returns opens the gate for its own duration: a function-scoped fixture for the
fake-native tests, a module-scoped one for the native modules whose child runs in a module-scoped
fixture.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import process_boundary


@pytest.fixture
def login_loan_open():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(process_boundary, "LOGIN_LOAN_OPEN", True)
        yield


@pytest.fixture(scope="module")
def login_loan_open_module():
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(process_boundary, "LOGIN_LOAN_OPEN", True)
        yield
