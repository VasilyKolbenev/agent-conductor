"""Atlas keeps one Do attempt through questions on its handoff, patch, checker and tests."""
import base64
import hashlib
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from browser_tests.desk_hold import close_context
from browser_tests.test_studio_atlas import atlas_url  # noqa: F401
from conductor.command.run_store import RunStore
from conductor.command.studio_routes import recovered_payload
from conductor.command.task_store import TaskStore
from tests.test_arachnid_handoff_data import world


QUESTION = "Что Grok передал Codex?"
FOLLOWUP = "Что из этого проверили тестами?"
CHANGES = "А что именно Codex исправил?"
VERDICT = "А почему проверяющий принял эту правку?"
CASES = "А что именно проверили эти три теста?"
OLD_TESTS = "А какие из этих тестов поймали бы старую ошибку?"


def handoff_read(root, action="action-first-2"):
    """The served store supplies the graph and requests. Attach the recorded artifact chain."""
    detail = recovered_payload(RunStore(root).read("first"), TaskStore(root),
                               computed_at="2026-11-10T10:00:00Z")
    sample = world()
    detail["config"]["instances"].extend(sample["config"]["instances"][:2])
    rows = sample["records"]
    for row in rows:
        row["record"]["run_id"] = "first"
    request, result = rows[-2]["record"], rows[-1]["record"]
    original = next(r["record"] for r in detail["records"]
                    if r["record"].get("action_id") == action)
    request.update(node_id="repair-counter", action_id=action,
                   attempt_id="attempt-" + action, instance_id="maker")
    result.update(action_id=request["action_id"], attempt_id=request["attempt_id"],
                  instance_id=request["instance_id"])
    # Keep the store's complete request and the slot of its previous attempt.
    original.update(request)
    index = next(i for i, r in enumerate(detail["records"]) if r["record"] is original)
    detail["records"][index:index] = rows[:-2]
    detail["records"].append(rows[-1])
    return detail


def ask(page, text):
    field = page.locator("#command")
    field.fill(text)
    field.press("Enter")


def native_protocol(action="action-first-2"):
    fixture = Path(__file__).parents[1] / "tests/fixtures/atlas-accepted-native.json"
    row = json.loads(fixture.read_text(encoding="utf-8"))
    row.update(action_id=action, attempt_id="attempt-" + action)
    row["tests"]["protocol"]["binding"].update(action=action, attempt=row["attempt_id"])
    return row


@pytest.mark.parametrize("width", [1440, 375])
def test_six_questions_follow_one_handoff_to_the_tests_that_reveal_the_old_bug(
        chromium, atlas_url, tmp_path, width):
    context = chromium.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    writes, requests = [], []
    page.on("request", lambda r: writes.append(r.method) if r.method != "GET" else None)
    # The later Do is also Codex; only the older Do received this plan.
    journal = handoff_read(tmp_path / "root", "action-first-1")
    proof = native_protocol("action-first-1")
    for row, count, expected in zip(proof["tests"]["cases"], (0, 4, 9), (0, 2, 1), strict=True):
        row["old_length"] = {"expression": "len(rows)", "function": "count_succeeded",
                             "path": "runstats/counts.py", "line": 3,
                             "actual": count, "expected": expected}

    def attempt(route):
        requests.append(route.request.url.rsplit("/", 1)[-1])
        route.fulfill(json=proof)

    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    page.route("**/steps/repair-counter/actions/*", attempt)
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        panel = page.locator("#inspection")
        source = panel.locator('[data-handoff-node="source"]')
        source.press("Enter")
        expect(panel.locator('[data-handoff-proof="source"]')).to_contain_text("diagnosis-1")
        expect(panel).to_contain_text("Counts cancelled rows.")
        panel.locator('[data-handoff-node="target"]').press("Enter")
        expect(panel.locator('[data-handoff-proof="target"]')).to_contain_text("plan-1")
        expect(panel).to_contain_text("Count only succeeded.")
        expect(panel.locator('[data-handoff-revision="different_revision"]')).to_be_visible()
        panel.locator('[data-handoff-node="input"]').click()
        expect(panel.locator('[data-handoff-proof="input"]')).to_contain_text("revision-2")
        page.locator("#close").click()
        ask(page, FOLLOWUP)
        tests = panel.locator('[data-handoff-tests]')
        expect(tests).to_have_attribute("data-handoff-action", "action-first-1")
        expect(tests).to_have_attribute("data-handoff-attempt", "attempt-action-first-1")
        reply = page.locator("#messages .msg.atlas").last
        expect(reply).to_contain_text("test_empty_input_is_zero")
        expect(reply).to_contain_text("test_skips_non_dictionaries_and_inexact_outcomes")
        expect(reply).to_contain_text("Связи отдельных выводов с тестами не записаны")
        expect(tests).to_contain_text("Для отдельных выводов связь с тестами не записана.")
        tests.locator('[data-handoff-protocol] summary').press("Enter")
        expect(tests.locator('[data-handoff-protocol]')).to_contain_text("Ran 3 tests")
        if width == 375:
            page.locator("#close").click()
        ask(page, CHANGES)
        changes = panel.locator('[data-handoff-view="changes"]')
        diff = changes.locator('[data-atlas-diff="runstats/counts.py"]')
        expect(diff).to_be_visible()
        expect(diff).to_contain_text("-    return len(rows)")
        predicate = 'if isinstance(row, dict) and row.get("outcome") == "succeeded"'
        expect(diff).to_contain_text(predicate)
        expect(reply).to_contain_text("runstats/counts.py")
        expect(reply).to_contain_text("len(rows)")
        expect(reply).to_contain_text(predicate)
        related = changes.locator("[data-handoff-tests]")
        expect(related).to_have_attribute("data-handoff-action", "action-first-1")
        expect(related).to_have_attribute("data-handoff-attempt", "attempt-action-first-1")
        expect(related.locator("[data-handoff-case]")).to_have_count(3)
        expect(related.get_by_role("button", name="test_empty_input_is_zero",
                                   exact=False)).to_be_visible()
        changes.locator('[data-focus="atlas:file:tests/test_counts.py"]').click()
        expect(changes.locator('[data-atlas-diff="tests/test_counts.py"]')).to_contain_text(
            "+        self.assertEqual(count_succeeded(rows), 2)")
        expect(related).to_contain_text("test_skips_non_dictionaries_and_inexact_outcomes")
        if width == 375:
            page.locator("#close").click()
        ask(page, VERDICT)
        verdict = panel.locator('[data-handoff-view="verdict"] [data-handoff-verdict]')
        expect(verdict).to_have_attribute("data-handoff-action", "action-first-1")
        expect(verdict).to_have_attribute("data-handoff-attempt", "attempt-action-first-1")
        expect(verdict).to_contain_text("checker")
        expect(verdict).to_contain_text(proof["manifest_digest"])
        expect(verdict).to_contain_text("runstats/counts.py")
        expect(verdict).to_contain_text("tests/test_counts.py")
        expect(verdict).to_contain_text("всего 3, падений 0, ошибок 0, пропущено 0")
        for evidence in (reply, verdict):
            expect(evidence).to_contain_text("Отдельное обоснование проверяющего не записано.")
        expect(reply).to_contain_text("checker")
        if width == 375:
            page.locator("#close").click()
        ask(page, CASES)
        evidence = panel.locator('[data-handoff-view="cases"] [data-handoff-cases]')
        expect(evidence).to_have_attribute("data-handoff-action", "action-first-1")
        expect(evidence).to_have_attribute("data-handoff-attempt", "attempt-action-first-1")
        cards = evidence.locator("[data-case-source] [data-handoff-case]")
        expect(cards).to_have_count(3)
        named = evidence.locator("[data-case-run]")
        expect(named.locator("[data-case-observation]")).to_have_count(3)
        for method, line, assertion in (
                ("test_empty_input_is_zero", 7, "self.assertEqual(count_succeeded([]), 0)"),
                ("test_counts_only_succeeded_records", 16,
                 "self.assertEqual(count_succeeded(rows), 2)"),
                ("test_skips_non_dictionaries_and_inexact_outcomes", 30,
                 "self.assertEqual(count_succeeded(rows), 1)")):
            source = cards.filter(has_text=method)
            expect(source).to_contain_text("tests/test_counts.py:" + str(line))
            expect(source).to_contain_text(assertion)
            expect(reply).to_contain_text(method)
            expect(reply).to_contain_text(assertion)
            row = f"{method} (test_counts.CountSucceededTest.{method}) ... ok"
            expect(named.locator("[data-case-observation]").filter(has_text=row)).to_have_text(row)
        for method, examples, other in (
                ("test_counts_only_succeeded_records",
                 ('{"outcome": "failed"}', "{}"), '{"outcome": "Succeeded"}'),
                ("test_skips_non_dictionaries_and_inexact_outcomes",
                 ('{"outcome": "Succeeded"}', '{"outcome": "succeeded "}'),
                 '{"outcome": "failed"}')):
            excerpt = cards.filter(has_text=method).locator("[data-case-example]")
            excerpt.locator("summary").click()
            for example in examples:
                expect(excerpt.locator("pre")).to_contain_text(example)
            expect(excerpt.locator("pre")).not_to_contain_text(other)
        raw = evidence.locator("[data-handoff-protocol]")
        if raw.get_attribute("open") is None:
            raw.locator("summary").click()
        assert raw.locator("pre").last.text_content() == proof["tests"]["protocol"]["output"]
        if width == 375:
            page.locator("#close").click()
        ask(page, OLD_TESTS)
        comparison = panel.locator('[data-handoff-view="old-tests"] [data-handoff-old-tests]')
        expect(comparison).to_have_attribute("data-handoff-attempt", "attempt-action-first-1")
        expect(comparison).to_have_attribute("data-handoff-action", "action-first-1")
        expect(comparison).to_contain_text("len(rows)")
        expect(comparison).to_contain_text("runstats/counts.py:3")
        expect(comparison).to_contain_text("Расчёт без выполнения старого кода")
        expect(comparison.locator("[data-case-run]")).to_contain_text("Протокол Do после правки")
        widths = []
        for name, old, expected, effect in (
                ("test_empty_input_is_zero", "0", "0", "Не обнаружил бы"),
                ("test_counts_only_succeeded_records", "4", "2", "Обнаружил бы"),
                ("test_skips_non_dictionaries_and_inexact_outcomes", "9", "1", "Обнаружил бы")):
            row = comparison.locator("[data-old-row]").filter(has_text=name)
            expect(row.locator("[data-old-actual]")).to_have_text(old)
            expect(row.locator("[data-old-expected]")).to_have_text(expected)
            expect(row.locator("[data-old-effect]")).to_have_text(effect)
            for series, number in (("actual", old), ("expected", expected)):
                bar = row.locator(f'meter[data-old-bar="{series}"]')
                expect(bar).to_be_visible()
                assert bar.evaluate("m => [m.min, m.max, m.value]") == [0, 9, int(number)]
                widths.append(bar.bounding_box()["width"])
        assert min(widths) > 0 and max(widths) - min(widths) <= 1
        expect(comparison.locator("[data-case-run] meter")).to_have_count(0)
        actual = comparison.locator("[data-case-run] [data-case-observation]")
        assert actual.all_text_contents() == [
            s for s in proof["tests"]["protocol"]["output"].splitlines() if s.endswith(" ... ok")]
        expect(reply).to_contain_text("Обнаружили бы ошибку: 2 из 3")
        assert "test_" not in reply.inner_text()
        assert reply.inner_text().count("2 из 3") == 1
        expect(page.locator("#messages .msg.user")).to_have_count(6)
        assert requests and set(requests) == {"action-first-1"}
        assert writes == []
    finally:
        close_context(context)


def test_switching_sessions_during_read_never_paints_or_replies_with_foreign_tests(
        chromium, atlas_url, tmp_path):
    context = chromium.new_context(viewport={"width": 1440, "height": 850})
    page = context.new_page()
    journal = handoff_read(tmp_path / "root")
    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    page.add_init_script("""const fetchNormally = window.fetch.bind(window);
        window.fetch = (url, options) => String(url).endsWith('/actions/action-first-2')
        ? new Promise(done => { window.deliverFirst = row =>
          done(new Response(JSON.stringify(row), {headers: {'Content-Type':'application/json'}}));
        })
        : fetchNormally(url, options);""")
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        expect(page.locator('[data-handoff-view="handoff"]')).to_be_visible()
        page.locator("#close").click()
        ask(page, FOLLOWUP)
        page.wait_for_function("typeof window.deliverFirst === 'function'")
        ask(page, CHANGES)
        ask(page, VERDICT)
        ask(page, CASES)
        page.locator("#close").click()
        page.locator('[data-session="run/second"]').click()
        expect(page.locator("#messages")).not_to_contain_text(QUESTION)
        page.evaluate("row => window.deliverFirst(row)", native_protocol())
        page.evaluate("() => new Promise(requestAnimationFrame)")
        expect(page.locator('[data-handoff-tests]')).to_have_count(0)
        expect(page.locator('[data-atlas-diff]')).to_have_count(0)
        expect(page.locator('[data-handoff-verdict]')).to_have_count(0)
        expect(page.locator('[data-handoff-cases]')).to_have_count(0)
        ask(page, FOLLOWUP)
        expect(page.locator("#messages .msg.atlas").last).to_contain_text("Выберите запуск")
        expect(page.locator("#messages")).not_to_contain_text("Ran 3 tests")
        page.locator('[data-session="run/first"]').click()
        expect(page.locator("#messages")).to_contain_text(QUESTION)
        expect(page.locator("#messages")).not_to_contain_text("len(rows)")
        expect(page.locator("#messages")).not_to_contain_text("Снимок подтверждён")
        expect(page.locator('[data-handoff-tests]')).to_have_count(0)
    finally:
        close_context(context)


@pytest.mark.parametrize("invalid", ["attempt", "checker", "adapter"])
def test_followup_refuses_foreign_attempt_or_checker(chromium, atlas_url, tmp_path, invalid):
    context = chromium.new_context()
    page = context.new_page()
    journal = handoff_read(tmp_path / "root")
    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    old = native_protocol()
    if invalid == "attempt":
        old["tests"]["protocol"]["binding"]["attempt"] = "attempt-action-first-1"
    elif invalid == "checker":
        old["verdict"]["instance_id"] = "maker"
    else:
        old["verdict"]["adapter_id"] = "grok-build"
    page.route("**/steps/repair-counter/actions/action-first-2", lambda r: r.fulfill(json=old))
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        expect(page.locator('[data-handoff-view="handoff"]')).to_be_visible()
        page.locator("#close").click()
        ask(page, FOLLOWUP)
        expect(page.locator("#inspection")).to_contain_text("Сведения об этой попытке недоступны")
        expect(page.locator('[data-handoff-tests]')).to_have_count(0)
        expect(page.locator("#inspection")).not_to_contain_text("Ran 3 tests")
        ask(page, CHANGES)
        expect(page.locator("#messages .msg.atlas").last).to_contain_text(
            "Доказательства этой попытки не подтверждены")
        ask(page, OLD_TESTS)
        expect(page.locator('[data-handoff-view="old-tests"]')).to_contain_text(
            "Сведения об этой попытке недоступны")
        expect(page.locator("[data-handoff-old-tests]")).to_have_count(0)
        expect(page.locator("#inspection [data-atlas-diff]")).to_have_count(0)
        expect(page.locator("#inspection [data-handoff-case]")).to_have_count(0)
        ask(page, CASES)
        expect(page.locator('[data-handoff-view="cases"]')).to_contain_text(
            "Сведения об этой попытке недоступны")
        expect(page.locator("[data-handoff-cases]")).to_have_count(0)
        expect(page.locator("#messages .msg.atlas").last).not_to_contain_text("test_empty_input")
        expect(page.locator("#inspection [data-handoff-case]")).to_have_count(0)
        ask(page, VERDICT)
        expect(page.locator('[data-handoff-view="verdict"]')).to_contain_text(
            "Сведения об этой попытке недоступны")
        expect(page.locator("[data-handoff-verdict]")).to_have_count(0)
        expect(page.locator("#messages .msg.atlas").last).to_contain_text(
            "Доказательства этой попытки не подтверждены")
    finally:
        close_context(context)


@pytest.mark.parametrize("source", ["quiet", "external"])
def test_run_totals_do_not_turn_source_definitions_into_named_outcomes(
        chromium, atlas_url, tmp_path, source):
    context = chromium.new_context(viewport={"width": 1440, "height": 850})
    page = context.new_page()
    journal = handoff_read(tmp_path / "root")
    proof = native_protocol()
    tests = proof["tests"]
    if source == "quiet":
        raw = b"...\r\nRan 3 tests in 0.000s\r\n\r\nOK\r\n"
        tests["protocol"].update(output=raw.decode(), output_b64=base64.b64encode(raw).decode(),
                                 output_sha256="sha256:" + hashlib.sha256(raw).hexdigest())
    else:
        tests["source"] = "external"
        del tests["protocol"]
        # A saved assertion can still be displayed when this file has no available diff.
        test_file = next(f for f in proof["files"] if f["path"] == "tests/test_counts.py")
        test_file.update(diff_status="base_unavailable", lines=[])
        impl = next(f for f in proof["files"] if f["path"] == "runstats/counts.py")
        impl.update(diff_status="withheld", lines=[])
        tests["cases"][0]["old_length"] = {
            "expression": "len(rows)", "function": "count_succeeded", "path": "runstats/counts.py",
            "line": 3, "actual": 0, "expected": 0}
    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    page.route("**/steps/repair-counter/actions/action-first-2", lambda r: r.fulfill(json=proof))
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        expect(page.locator('[data-handoff-view="handoff"]')).to_be_visible()
        ask(page, VERDICT)
        expect(page.locator('[data-handoff-verdict]')).to_be_visible()
        ask(page, CASES)
        panel = page.locator('[data-handoff-view="cases"] [data-handoff-cases]')
        expect(panel.locator("[data-case-source] [data-handoff-case]")).to_have_count(3)
        run = panel.locator("[data-case-run]")
        expect(run).to_be_visible()
        expect(run.locator("[data-case-observation]")).to_have_count(0)
        expect(run).not_to_contain_text("test_empty_input_is_zero")
        if source == "quiet":
            expect(run).to_contain_text("Поимённых результатов в выводе нет")
            expect(page.locator("#messages .msg.atlas").last).to_contain_text(
                "Поимённых результатов в выводе нет")
        else:
            expect(run.locator("[data-handoff-protocol]")).to_have_count(0)
            expect(panel.locator("[data-case-example]")).to_have_count(0)
            expect(panel.locator("[data-case-source]")).to_contain_text(
                "self.assertEqual(count_succeeded(rows), 2)")
        ask(page, OLD_TESTS)
        old = page.locator("[data-handoff-old-tests]")
        expect(old.locator("[data-old-row]")).to_have_count(3)
        expect(old.locator("[data-old-actual]")).to_have_count(0)
        expect(old.locator("meter")).to_have_count(0)
        expect(old.locator("[data-old-effect]")).to_have_text(["Недостаточно данных"] * 3)
        expect(old.locator("[data-case-run]")).to_contain_text("всего 3", ignore_case=True)
        expect(old.locator("[data-case-observation]")).to_have_count(0)
    finally:
        close_context(context)


def test_old_test_chart_scales_zero_and_keeps_negative_or_unknown_values_textual(
        chromium, atlas_url, tmp_path):
    context = chromium.new_context()
    page = context.new_page()
    journal = handoff_read(tmp_path / "root")
    proof = native_protocol()
    for case, actual, expected in zip(proof["tests"]["cases"][:2], (0, 4), (0, -2), strict=True):
        case["old_length"] = {"expression": "len(rows)", "function": "count_succeeded",
                              "path": "runstats/counts.py", "line": 3,
                              "actual": actual, "expected": expected}
    page.route("**/command/runs/first", lambda r: r.fulfill(json=journal))
    page.route("**/steps/repair-counter/actions/action-first-2", lambda r: r.fulfill(json=proof))
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        expect(page.locator('[data-handoff-view="handoff"]')).to_be_visible()
        ask(page, OLD_TESTS)
        panel = page.locator("[data-handoff-old-tests]")
        empty = panel.locator('[data-old-row="test_empty_input_is_zero"]')
        bars = empty.locator("meter[data-old-bar]")
        expect(bars).to_have_count(2)
        assert bars.evaluate_all("ms => ms.map(m => [m.min, m.max, m.value])") == [[0, 1, 0]] * 2
        negative = panel.locator('[data-old-row="test_counts_only_succeeded_records"]')
        expect(negative.locator("[data-old-actual]")).to_have_text("4")
        expect(negative.locator("[data-old-expected]")).to_have_text("-2")
        expect(negative.locator("meter")).to_have_count(0)
        unknown = panel.locator('[data-old-row="test_skips_non_dictionaries_and_inexact_outcomes"]')
        expect(unknown.locator("[data-old-effect]")).to_have_text("Недостаточно данных")
        expect(unknown.locator("meter, [data-old-actual], [data-old-expected]")).to_have_count(0)
    finally:
        close_context(context)


def test_successful_tests_do_not_supply_a_missing_checker_verdict(chromium, atlas_url, tmp_path):
    context = chromium.new_context(viewport={"width": 1440, "height": 850})
    page = context.new_page()
    journal = handoff_read(tmp_path / "root")
    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    proof = native_protocol()
    proof["verdict"] = None
    page.route("**/steps/repair-counter/actions/action-first-2", lambda r: r.fulfill(json=proof))
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        expect(page.locator('[data-handoff-view="handoff"]')).to_be_visible()
        ask(page, VERDICT)
        panel = page.locator('[data-handoff-view="verdict"]')
        for evidence in (panel, page.locator("#messages .msg.atlas").last):
            expect(evidence).to_contain_text("независимый вердикт не подтверждён")
            expect(evidence).not_to_contain_text("Снимок подтверждён")
    finally:
        close_context(context)


def test_closing_retains_the_handoff_but_selecting_the_whole_cycle_releases_it(
        chromium, atlas_url, tmp_path):
    context = chromium.new_context()
    page = context.new_page()
    journal = handoff_read(tmp_path / "root")
    page.route("**/command/runs/first", lambda route: route.fulfill(json=journal))
    requests = []

    def attempt(route):
        requests.append(route.request.url)
        route.fulfill(json=native_protocol())

    page.route("**/steps/repair-counter/actions/action-first-2", attempt)
    try:
        page.goto(atlas_url + "/#session=first&lang=ru")
        expect(page.locator('#orbitHere [data-step="repair-counter"]')).to_be_attached()
        ask(page, QUESTION)
        expect(page.locator('[data-handoff-view="handoff"]')).to_be_visible()
        page.locator("#close").click()
        ask(page, FOLLOWUP)
        expect(page.locator("[data-handoff-tests]")).to_have_attribute(
            "data-handoff-attempt", "attempt-action-first-2")
        page.locator("[data-atlas-scope]").select_option("")
        ask(page, FOLLOWUP)
        expect(page.locator("#messages .msg.atlas").last).to_contain_text("Выберите запуск")
        expect(page.locator("[data-handoff-tests]")).to_have_count(0)
        assert len(requests) == 1
    finally:
        close_context(context)
