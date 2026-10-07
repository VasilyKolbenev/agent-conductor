"""The browser gate answers the same whatever order its files are named in.

Two modules each entered their own ``sync_playwright``. Nested in one loop that
raises "Playwright Sync API inside the asyncio loop", so the suite passed when
one file led and errored when the other did — a gate whose verdict depends on
argument order is not a gate. This module keeps the browser launch singular
per process and in stated places, from the fast suite, which runs whether
Playwright is installed or not.

Revised deliberately for the release-gate slice: browser_tests/gate.py (the
runner, not a test module — pytest never collects it) carries the second
launch in the tree. It cannot nest with the fixture's: the runner probes the
engine version in ITS OWN process and closes that browser before any module
process starts, so the ordering hazard this module guards is untouched. The
conftest, likewise, now holds the evidence hook beside the fixture — hook
functions, not fixtures, and still no browser launch but the one.
"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BROWSER_TESTS = ROOT / "browser_tests"
CONFTEST = BROWSER_TESTS / "conftest.py"
GATE = BROWSER_TESTS / "gate.py"


def test_exactly_one_browser_launch_serves_every_browser_test_module():
    modules = sorted(BROWSER_TESTS.glob("*.py"))
    assert CONFTEST in modules and GATE in modules
    launches = {
        path.name: path.read_text(encoding="utf-8").count("sync_playwright(")
        for path in modules
    }
    # The one call the TEST processes see lives in the conftest. Prose about
    # it is not a launch, so the call parenthesis is what this counts.
    assert launches.pop("conftest.py") == 1
    # The runner's own probe launch: a different process, opened and closed
    # before any module process exists, collected by pytest never.
    assert launches.pop("gate.py") == 1
    assert launches and set(launches.values()) == {0}


def test_the_one_browser_fixture_is_session_scoped_beside_the_evidence_hook():
    source = CONFTEST.read_text(encoding="utf-8")
    # ONE browser fixture, still, and it is the session-scoped one. The second
    # fixture is autouse and holds no browser: it closes the contexts a fixture
    # that died before its `try` could not, which is the shape the reverse
    # gate's failure really took. Counting launches above is what pins the
    # first claim; this counts the fixtures and names both.
    assert source.count("@pytest.fixture") == 2
    assert '@pytest.fixture(scope="session")' in source
    assert "@pytest.fixture(autouse=True)" in source
    assert "def test_" not in source
    # The conftest's whole surface, by name: the one browser fixture, the
    # per-test reaper, the page-evidence channels, the machinery the release
    # gate arms, and the protocol wrapper that says which test a page belongs
    # to -- without it every failure record carried every earlier test's words.
    # Nothing else may grow here.
    assert re.findall(r"^def (\w+)", source, re.MULTILINE) == [
        "_reap_contexts", "_remember", "_instrumented", "chromium",
        "_close_what_a_failed_setup_left", "_evidence_stem", "_live_pages",
        "_write_failure_evidence", "pytest_runtest_makereport",
        "pytest_runtest_protocol"]
    for path in sorted(BROWSER_TESTS.glob("*.py")):
        if path != CONFTEST:
            assert "def chromium(" not in path.read_text(encoding="utf-8")
