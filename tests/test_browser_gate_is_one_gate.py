"""The browser gate answers the same whatever order its files are named in.

Two modules each entered their own ``sync_playwright``. Nested in one loop that
raises "Playwright Sync API inside the asyncio loop", so the suite passed when
one file led and errored when the other did — a gate whose verdict depends on
argument order is not a gate. This module keeps the browser launch singular and
in one place, from the fast suite, which runs whether Playwright is installed
or not.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BROWSER_TESTS = ROOT / "browser_tests"
CONFTEST = BROWSER_TESTS / "conftest.py"


def test_exactly_one_browser_launch_serves_every_browser_test_module():
    modules = sorted(BROWSER_TESTS.glob("*.py"))
    assert CONFTEST in modules
    launches = {
        path.name: path.read_text(encoding="utf-8").count("sync_playwright(")
        for path in modules
    }
    # The one call lives in the conftest. Prose about it is not a launch, so
    # the call parenthesis is what this counts.
    assert launches.pop("conftest.py") == 1
    assert launches and set(launches.values()) == {0}


def test_the_one_browser_fixture_is_session_scoped_and_alone_in_its_conftest():
    source = CONFTEST.read_text(encoding="utf-8")
    assert source.count("@pytest.fixture") == 1
    assert '@pytest.fixture(scope="session")' in source
    assert source.count("\ndef ") == 1
    assert "\ndef chromium(" in source
    assert "def test_" not in source
    for path in sorted(BROWSER_TESTS.glob("*.py")):
        if path != CONFTEST:
            assert "def chromium(" not in path.read_text(encoding="utf-8")
