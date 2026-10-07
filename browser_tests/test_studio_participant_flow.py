"""Compact visual flow: documents exist independently of the verdict on work."""
from browser_tests.test_studio_participants import _detail, _inspector, _mount, _tab
from browser_tests.test_studio_rendered import studio, studio_url  # noqa: F401


def _artifact(ident, ref, action=None, content="literal document"):
    return {"record_type": "artifact", "record": {"artifact_id": ident,
        "artifact_ref": ref, "source_action_id": action, "content": content}}


def _review_detail():
    detail = _detail()
    node = detail["graph"]["definition"]["nodes"][0]
    node["capability"] = "review"
    node["arguments"] = {"target_artifact_refs": ["source"], "result_artifact_ref": "report"}
    return detail


def test_flow_has_three_short_stages_without_duplicate_navigation(studio):
    page, problems = studio
    _mount(page, _review_detail())
    panel = _inspector(page)
    assert panel.locator("[data-flow] h5").all_text_contents() == ["Input", "Action", "Result"]
    assert panel.get_by_text("Sources: 1", exact=True).is_visible()
    assert panel.get_by_text("No document recorded", exact=True).is_visible()
    assert panel.get_by_text("Parameters", exact=True).is_visible()
    assert panel.get_by_text("History", exact=True).is_visible()
    assert "Technical details" not in panel.inner_text()
    assert "Task assignment" not in panel.inner_text()
    assert "assigned steps" not in page.locator("#deckTest .studio-deck__fleet").inner_text()
    _tab(page, "Parameters")
    assert "Assigned steps: 2" in panel.inner_text()
    assert "Expected document: report" in panel.inner_text()
    assert problems == []


def test_expected_or_foreign_document_is_not_this_steps_result(studio):
    page, _ = studio
    detail = _review_detail()
    detail["records"] = [_artifact("manual", "report"),
        {"record_type": "action_request", "record": {"action_id": "foreign", "node_id": "repair"}},
        _artifact("foreign-doc", "report", "foreign")]
    _mount(page, detail)
    # The foreign attempt makes "repair" the plan's position, and the inspector opens on it;
    # this test is about the review step's own result, so it chooses that step.
    _inspector(page).get_by_role("combobox").select_option("analyse")
    result = _inspector(page).locator('[data-flow="result"]')
    assert result.get_by_text("No document recorded", exact=True).is_visible()
    assert result.locator("summary").count() == 0
    detail["records"].append({"record_type": "action_request", "record": {
        "action_id": "own", "node_id": "analyse"}})
    detail["records"].append(_artifact("own-doc", "report", "own"))
    _mount(page, detail)
    result.get_by_text("Documents: 1", exact=True).click()
    result.get_by_text("report", exact=True).click()
    assert "Source outcome: not recorded" in result.inner_text()
    assert "Document: own-doc" in result.inner_text()
    assert "manual" not in result.inner_text() and "foreign-doc" not in result.inner_text()


def test_result_document_keeps_its_own_failed_outcome(studio):
    page, _ = studio
    detail = _review_detail()
    detail["graph"]["runtime"]["nodes"][0]["outcome"] = "succeeded"
    detail["records"] = [
        {"record_type": "action_request", "record": {"action_id": "own", "node_id": "analyse"}},
        _artifact("report-1", "report", "own"),
        {"record_type": "action_result", "record": {"action_id": "own", "outcome": "verification_failed"}},
        {"record_type": "action_result", "record": {"action_id": "other", "outcome": "succeeded"}}]
    _mount(page, detail)
    result = _inspector(page).locator('[data-flow="result"]')
    result.get_by_text("Documents: 1", exact=True).click()
    result.get_by_text("report", exact=True).click()
    assert "Source outcome: verification_failed" in result.inner_text()
    assert "succeeded" not in result.inner_text()
    assert "not proof of success" in result.inner_text()
    assert "Process exit 0 proves" in result.inner_text()


def test_input_opens_literal_document_and_new_identity_closes_the_old_read(studio):
    page, problems = studio
    detail = _review_detail()
    literal = '<script>window.UNSAFE = true</script>\r\n# words, not markup'
    detail["records"] = [_artifact("source-1", "source", content=literal)]
    _mount(page, detail)
    panel = _inspector(page)
    panel.get_by_text("Sources: 1", exact=True).click()
    panel.get_by_text("source", exact=True).press("Enter")
    assert panel.locator("pre").text_content() == literal
    assert panel.locator("pre script").count() == 0
    assert "not proof of use" in panel.inner_text()
    _mount(page, detail)
    assert panel.locator("pre").is_visible()
    detail["records"].append(_artifact("source-2", "source", content="newer"))
    _mount(page, detail)
    assert not panel.locator("pre").is_visible()
    panel.get_by_text("source", exact=True).press("Enter")
    assert panel.locator("pre").text_content() == "newer"
    assert "Document: source-2" in panel.inner_text()
    detail["run"]["run_id"] = "different-run"
    _mount(page, detail)
    assert panel.locator("details[open]").count() == 0
    assert problems == []


def test_instruction_reference_is_not_omitted_or_claimed_as_a_missing_file(studio):
    page, _ = studio
    detail = _detail()
    node = detail["graph"]["definition"]["nodes"][0]
    node.update(capability="dispatch", arguments={"instruction_ref": "instructions",
        "artifact_refs": ["brief"]})
    _mount(page, detail)
    panel = _inspector(page)
    panel.get_by_text("Sources: 2", exact=True).click()
    assert "instructions: No recorded document; may resolve to a file" in panel.inner_text()
    assert "brief: No recorded document" in panel.inner_text()


def test_long_document_uses_one_scroll_position_and_keeps_it_on_live_read(studio):
    page, _ = studio
    detail = _review_detail()
    detail["records"] = [_artifact("long-1", "source", content="line\n" * 90)]
    _mount(page, detail)
    panel = _inspector(page)
    panel.get_by_text("Sources: 1", exact=True).click()
    panel.get_by_text("source", exact=True).press("Enter")
    pre = panel.locator("pre")
    assert pre.evaluate("el => el.scrollHeight <= el.clientHeight")
    panel.evaluate("el => {el.scrollTop = 460}")
    _mount(page, detail)
    assert panel.evaluate("el => el.scrollTop") == 460
    assert pre.is_visible()


def test_in_flight_attempt_does_not_inherit_a_previous_result_on_the_planet(studio):
    page, _ = studio
    detail = _review_detail()
    detail["graph"]["runtime"]["nodes"][0]["outcome"] = "succeeded"
    detail["records"] = [
        {"record_type": "action_request", "record": {"action_id": "current", "node_id": "analyse"}},
        {"record_type": "action_result", "record": {"action_id": "older", "outcome": "succeeded"}}]
    _mount(page, detail)
    planet = page.locator('#deckTest [data-instance="alpha"]')
    assert "1 awaiting result" in planet.inner_text()
    action = _inspector(page).locator('[data-flow="action"]')
    assert "Awaiting result" in action.inner_text()
    assert "not proof that the vendor process is still running" in action.inner_text()
    assert "succeeded" not in action.inner_text()
