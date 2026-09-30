"""The short and the exact time of an instant (spec 5.6.7), from the real `desk-time.js`.

The module is values in, values out: a string the server wrote goes in, and the words a person
reads (`28.09 16:50`) and the string itself, untouched, for a hint come out. It reads no clock
-- the desk's modules do not (`studio-runs.js`) -- so each case here fixes the zone of the run
and hands over the instant, and the same instant answers the same in every run. The table is
spelled out here and not read back from the module, so a format that drifted reds in this file.
What may be reached is held by source guards below, each shown to bite on a planted line.
"""
from __future__ import annotations

import re

import pytest

from tests.desk_node import PANEL, run_js
from tests.test_graph_source import _code

MODULES = {"time": "desk-time.js"}
MOSCOW, NEW_YORK, UTC = "Europe/Moscow", "America/New_York", "UTC"
NOT_GIVEN = {"en": "time not given", "ru": "время не указано"}
#: (zone, locale, instant, the short text): the day and month in the locale's own order, the
#: clock on 24 hours, no seconds and no fraction, no year, in the zone of the run.
SHORT = (
    (MOSCOW, "ru", "2026-09-28T13:50:07Z", "28.09 16:50"),
    (MOSCOW, "en", "2026-09-28T13:50:07Z", "09/28 16:50"),
    (MOSCOW, "de", "2026-09-28T13:50:07Z", "09/28 16:50"),
    (NEW_YORK, "ru", "2026-09-28T13:50:07Z", "28.09 09:50"),
    (MOSCOW, "ru", "2026-09-28T21:00:00Z", "29.09 00:00"),
    (MOSCOW, "ru", "2026-01-05T07:05:59Z", "05.01 10:05"),
    (MOSCOW, "ru", "2026-09-28T13:50:07.123456Z", "28.09 16:50"),
    (UTC, "ru", "2026-09-28T16:50:00+03:00", "28.09 13:50"),
    (UTC, "en", "2026-12-31T23:59:59Z", "12/31 23:59"),
)
#: Everything that is not an instant: not a string, not a time, or a time the calendar refuses.
INVALID = (None, 0, 1785246600000, {}, [], "", "yesterday", "2026-09-28", "16:50",
           "2026-13-28T13:50:07Z", "2026-09-31T13:50:07Z", "2026-09-28T25:00:00Z",
           "2026-09-28 13:50:07Z", "2026-09-28T13:50:07")


def _run(zone: str, body: str, data: object) -> object:
    """`body` under `zone`; the zone is set on the process before the module is asked."""
    return run_js(f'process.env.TZ = {zone!r}; {body}', MODULES, data)


def test_an_instant_reads_as_day_month_and_clock_in_the_zone_of_the_run():
    for zone, locale, iso, short in SHORT:
        said = _run(zone, "console.log(JSON.stringify(time.instantText(d[0], d[1])));",
                    [locale, iso])
        assert said["short"] == short, (zone, locale, iso)
        assert said["known"] is True


def test_the_exact_text_is_the_string_that_came_in_and_nothing_made_of_it():
    for _zone, locale, iso, _short in SHORT:
        said = _run(MOSCOW, "console.log(JSON.stringify(time.instantText(d[0], d[1])));",
                    [locale, iso])
        assert said["exact"] == iso


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_a_value_that_is_not_an_instant_says_time_not_given_and_never_an_empty_text(locale):
    said = _run(MOSCOW, """console.log(JSON.stringify(d[1].map(
      (value) => time.instantText(d[0], value))));""", [locale, list(INVALID)])
    for value, one in zip(INVALID, said):
        assert one["short"] == NOT_GIVEN[locale], value
        assert one["known"] is False and one["exact"] == (value if isinstance(value, str) else "")


def test_the_answer_is_frozen_and_has_three_keys_and_no_more():
    out = _run(MOSCOW, """const one = time.instantText("en", "2026-09-28T13:50:07Z");
      const bad = time.instantText("en", null);
      console.log(JSON.stringify({keys: [Object.keys(one).sort(), Object.keys(bad).sort()],
        frozen: [Object.isFrozen(one), Object.isFrozen(bad)]}));""", None)
    assert out == {"keys": [["exact", "known", "short"]] * 2, "frozen": [True, True]}


def test_the_module_exports_instant_text_and_nothing_else():
    out = run_js("console.log(JSON.stringify(Object.keys(time).sort()));", MODULES)
    assert out == ["instantText"]


def test_one_instant_asked_in_two_zones_answers_in_each_zone_because_the_zone_is_read_per_call():
    out = run_js("""process.env.TZ = "Europe/Moscow";
      const first = time.instantText("ru", "2026-09-28T13:50:07Z").short;
      process.env.TZ = "America/New_York";
      console.log(JSON.stringify([first, time.instantText("ru", "2026-09-28T13:50:07Z").short]));
      """, MODULES)
    assert out == ["28.09 16:50", "28.09 09:50"]


# -- what the module may reach ------------------------------------------------------------
SOURCE = PANEL / "desk-time.js"
#: A read of the clock, in any spelling this codebase could write: the shared `Date` constructor
#: with no argument, the call without `new`, `Date.now`, the timers and the performance clock.
CLOCK = re.compile(r"\bDate\s*\.\s*now\b|\bnew\s+Date\s*\(\s*\)|(?<!new )\bDate\s*\(\s*\)"
                   r"|\bperformance\b|\bsetTimeout\b|\bsetInterval\b|\brequestAnimationFrame\b")
#: `Intl` is admitted for this module as the date formatter alone; its other doors read the
#: platform's own language and zone.
INTL_OTHER = re.compile(r"\bIntl\s*\.\s*(?!DateTimeFormat\b)\w+")
RESOLVED = re.compile(r"\.\s*resolvedOptions\b|\bnavigator\b|\blocalStorage\b|\bdocument\b")
IMPORT = re.compile(r"^import\b|\bimport\s*\(", re.M)


def clock_reads(code: str) -> list[str]:
    return CLOCK.findall(code)


def reaches(code: str) -> list[str]:
    """What the module may not touch: another module, the platform's own language or zone."""
    return (IMPORT.findall(code) + INTL_OTHER.findall(code) + RESOLVED.findall(code))


def test_the_module_reads_no_clock_and_imports_nothing_and_asks_the_platform_nothing():
    code = _code(SOURCE)
    assert "Intl.DateTimeFormat" in code and "new Date(iso)" in code
    assert clock_reads(code) == [] and reaches(code) == []


PLANTED_CLOCKS = (
    "const a = Date.now();", "const a = new Date();", "const a = new Date( );",
    "const a = Date();", "const a = performance.now();", "setTimeout(() => 0, 1);",
    "setInterval(() => 0, 1);", "requestAnimationFrame(() => 0);")
PLANTED_REACHES = (
    'import {x} from "./y.js";', 'const m = await import("./y.js");',
    "const a = Intl.NumberFormat();", "const a = Intl.DateTimeFormat().resolvedOptions();",
    "const a = navigator.language;", "const a = document.documentElement.lang;")


@pytest.mark.parametrize("planted", PLANTED_CLOCKS)
def test_the_clock_guard_bites_on_every_planted_read_of_the_clock(planted):
    assert clock_reads(_code(SOURCE) + "\n" + planted) != []


@pytest.mark.parametrize("planted", PLANTED_REACHES)
def test_the_reach_guard_bites_on_every_planted_import_or_platform_question(planted):
    assert reaches(_code(SOURCE) + "\n" + planted) != []


def test_a_sentence_about_the_clock_in_a_comment_is_not_a_read_of_it():
    assert clock_reads(_code(SOURCE)) == []
    assert "Date.now" in SOURCE.read_text(encoding="utf-8")
