"""What a child interpreter shows about `conductor.report`.

Everything here spawns a real Python. In-process assertions cannot measure any
of it: a module already imported by the test session hides what importing the
report costs, and a clock patched inside the test process is a patch on the
test process rather than on the render.

Two claims are measured, both of them stated in `conductor.report`'s module
docstring:

* the same document renders the same bytes whatever the interpreter's
  environment and whatever its clock says. The environment battery and the
  clock battery are separate on purpose — the three environments below run
  within the same second of each other, so a clock read at day granularity
  renders identically in all three and no environment can catch it. The clock
  battery moves the clock itself, a hundred days, and demands the bytes hold
  still;
* importing the report loads no module that can reach off the machine, taken
  against a baseline child that does not import it.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.test_report import (NETWORKING_ROOTS, SRC_ROOT, _root_of, a_finding,
                               a_lane, a_map, merged, role)

_RENDER_PROBE = """
import datetime, json, sys, time
from conductor import report
with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
with open(sys.argv[2], "wb") as out:
    out.write(report.render(state).encode("utf-8"))
with open(sys.argv[3], "w", encoding="utf-8") as clock:
    json.dump([datetime.datetime.now().isoformat(), datetime.date.today().isoformat(),
               time.strftime("%Y-%m-%d %H:%M:%S"), time.time()], clock)
"""

#: A `sitecustomize` module, which CPython imports at startup from anything on
#: `PYTHONPATH`, moving the child's clock to whatever instant the environment
#: names. It replaces the module attributes rather than the classes, so a
#: `datetime.date.today()` written anywhere — including inside a function, in a
#: module imported later — reads the fake instant.
_FAKE_CLOCK = """
import datetime, os, time

_at = float(os.environ["CONDUCT_FAKE_EPOCH"])


class _Date(datetime.date):
    @classmethod
    def today(cls):
        return cls.fromtimestamp(_at)


class _DateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(_at, tz)

    @classmethod
    def utcnow(cls):
        return cls.utcfromtimestamp(_at)

    @classmethod
    def today(cls):
        return cls.fromtimestamp(_at)


datetime.date, datetime.datetime = _Date, _DateTime
_localtime, _gmtime, _strftime = time.localtime, time.gmtime, time.strftime
time.time = lambda: _at
time.time_ns = lambda: int(_at * 1_000_000_000)
time.localtime = lambda secs=None: _localtime(_at if secs is None else secs)
time.gmtime = lambda secs=None: _gmtime(_at if secs is None else secs)
# strftime() with no second argument reads the real clock inside C, not
# time.localtime, so patching localtime alone would leave it telling the truth.
time.strftime = lambda fmt, t=None: _strftime(fmt, _localtime(_at) if t is None else t)
"""

#: Three environments that break a renderer reading anything but its argument.
#: A different hash seed reorders set iteration everywhere; TZ and LC_ALL move
#: a clock read and a formatted number only where the platform lets them —
#: measured on Windows, `time.tzset` does not exist and CPython never calls
#: `setlocale`, so there those two vary the child's environment and nothing
#: else. That is why the clock is moved directly below rather than through TZ.
_HOSTILE_ENVIRONMENTS = (
    {"PYTHONHASHSEED": "0", "TZ": "UTC", "LC_ALL": "C"},
    {"PYTHONHASHSEED": "271828", "TZ": "Asia/Tokyo", "LC_ALL": "de_DE.UTF-8"},
    {"PYTHONHASHSEED": "999983", "TZ": "America/Sao_Paulo", "LC_ALL": "tr_TR.UTF-8"},
)


def _a_rich_document():
    """A document with enough repetition for a reordering to have somewhere to show.

    Several roles share every listed property but their id, and several findings
    share a review state: any line built by walking a set instead of the document
    reorders under a different hash seed.
    """
    return merged(
        a_map([role("impl"), role("rev", ["impl"], stage="implement"), role("qa"),
               role("sec"), role("docs"), role("ops")]),
        [a_lane("claude", "impl",
                [a_finding(), a_finding("D-2"), a_finding("D-3"), a_finding("D-4")],
                waits=[{"id": "w-1", "kind": "decision", "title": "t",
                        "why": "w", "blocks": ["D-1"]}]),
         a_lane("codex", "rev",
                verdicts={"D-1": {"disposition": "confirmed", "note": "n"}})])


def _render_in_a_child(work, state, tag, environment):
    """Render `state` in a child interpreter; report its bytes and its clock.

    Args:
        work: A directory the child may write into.
        state: The document to render.
        tag: Names this child's files apart from the others'.
        environment: Environment variables layered over this process's own,
            `PYTHONPATH` included — a caller that prepends to it must pass the
            whole value.

    Returns:
        `(rendered bytes, what the child's clock said)`.
    """
    document = Path(work) / f"state-{tag}.json"
    document.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    script = Path(work) / "probe.py"
    script.write_text(_RENDER_PROBE, encoding="utf-8")
    out, clock = Path(work) / f"render-{tag}.md", Path(work) / f"clock-{tag}.json"
    done = subprocess.run(
        [sys.executable, str(script), str(document), str(out), str(clock)],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(SRC_ROOT), **environment})
    assert out.is_file(), done.stderr.decode("utf-8", "replace")
    return out.read_bytes(), json.loads(clock.read_text(encoding="utf-8"))


def test_the_render_ignores_the_hash_seed_and_the_rest_of_the_environment(tmp_path):
    state = _a_rich_document()
    renders = {_render_in_a_child(tmp_path, state, str(index), environment)[0]
               for index, environment in enumerate(_HOSTILE_ENVIRONMENTS)}
    assert len(renders) == 1 and renders != {b""}


def test_moving_the_clock_a_hundred_days_moves_nothing_in_the_render(tmp_path):
    state = _a_rich_document()
    clock_dir = tmp_path / "clock"
    clock_dir.mkdir()
    (clock_dir / "sitecustomize.py").write_text(_FAKE_CLOCK, encoding="utf-8")
    path = os.pathsep.join([str(clock_dir), str(SRC_ROOT)])
    epoch = 1780000000                                    # 2026-05-29, near enough
    early, early_clock = _render_in_a_child(
        tmp_path, state, "early",
        {"PYTHONPATH": path, "CONDUCT_FAKE_EPOCH": str(epoch)})
    late, late_clock = _render_in_a_child(
        tmp_path, state, "late",
        {"PYTHONPATH": path, "CONDUCT_FAKE_EPOCH": str(epoch + 100 * 86400)})
    # Without this the guard would be the emptiest kind: two children agreeing
    # because nothing about them differed. Every way of asking the time must
    # answer differently before the renders are compared.
    assert all(was != now for was, now in zip(early_clock, late_clock)), (
        f"the injected clock never moved: {early_clock} against {late_clock}")
    assert early == late and early


#: `sys.argv[2]` decides whether the child imports the module under measurement,
#: so the same script produces both the measurement and its baseline. The whole
#: of `sys.modules` is reported, not the growth: a networking module already
#: loaded when the probe started would vanish from a difference.
_MODULES_PROBE = """
import json, sys
if sys.argv[2] == "import":
    import conductor.report
with open(sys.argv[1], "w", encoding="utf-8") as out:
    json.dump({"loaded": sorted(sys.modules),
               "has_report": "conductor.report" in sys.modules}, out)
"""


def _modules_loaded(work, mode):
    """Every module name a child interpreter holds, with or without the import."""
    script, out = Path(work) / "probe.py", Path(work) / f"loaded-{mode}.json"
    script.write_text(_MODULES_PROBE, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(script), str(out), mode], cwd=work,
        stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(SRC_ROOT)})
    assert out.is_file(), done.stderr.decode("utf-8", "replace")
    return json.loads(out.read_text(encoding="utf-8"))


def test_importing_the_report_loads_no_module_that_can_reach_the_network():
    with tempfile.TemporaryDirectory() as work:
        measured = _modules_loaded(work, "import")
        baseline = _modules_loaded(work, "skip")
    assert measured["has_report"], "the child never imported the module measured"
    assert not baseline["has_report"], "the baseline is not a baseline"
    # Asserted on the whole module table, then attributed: the first assertion
    # is the claim, the difference only says who to blame if it fails.
    reached = {n for n in measured["loaded"] if _root_of(n) in NETWORKING_ROOTS}
    assert reached == set(), (
        f"a child holding conductor.report also holds {sorted(reached)}; "
        f"of those, {sorted(reached - set(baseline['loaded']))} arrived with it")
