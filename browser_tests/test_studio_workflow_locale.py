"""The actual workflow detail changes language while domain bytes stay put."""
from playwright.sync_api import expect

from browser_tests.test_studio_artifacts import WORKFLOW_ID, bench, project  # noqa: F401
from browser_tests.test_studio_preferences import _switch
from conductor.command.template_store import TemplateStore
from tests.studio_source_messages import message_english, message_russian


def test_workflow_artifact_transition_and_canvas_copy_switches_without_a_write(bench, project):
    page = bench.page
    bench.select_step("build")
    arguments = project.stored_arguments("build")
    refs = bench.refs()
    titles = page.locator(".studio-node__title").all_text_contents()
    requests = list(bench.recorder.rows)
    _switch(page, "ru", "light")
    expect(page.locator('[data-section="artifacts"]')).to_contain_text("Ссылка задаёт имя")
    expect(page.locator('[data-section="transitions"] h4').first).to_have_text("Исходящие связи")
    expect(page.locator('[data-focus="ref-add"]')).to_have_text("Добавить требование")
    expect(page.locator('[data-focus="canvas-help"]')).to_have_text("Управление схемой и клавиши")
    expect(page.locator('[data-port="build"]')).to_have_attribute(
        "aria-label", "Соединить из Carry it out. Перетащите на другой шаг или используйте раздел переходов в панели свойств.")
    assert bench.refs() == refs and page.locator(".studio-node__title").all_text_contents() == titles
    assert project.stored_arguments("build") == arguments
    _switch(page, "en", "dark")
    expect(page.locator('[data-focus="ref-add"]')).to_have_text("Require it")
    expect(page.locator('[data-focus="canvas-help"]')).to_have_text("Canvas controls and keyboard")
    expect(page.locator('[data-section="transitions"] h4').first).to_have_text("Outgoing connections")
    assert bench.refs() == refs and page.locator(".studio-node__title").all_text_contents() == titles
    assert project.stored_arguments("build") == arguments
    assert [row for row in bench.recorder.rows if row[0] == "POST"] == [
        row for row in requests if row[0] == "POST"]
    assert bench.problems == []


def _stored(project, node_id, field="title"):
    draft = TemplateStore(project.root).load_draft(WORKFLOW_ID)
    return next(row[field] for row in draft.document["nodes"] if row["node_id"] == node_id)


def test_a_refused_word_and_an_unsaved_edit_survive_both_switches_and_speak_each_language(bench, project):
    """Moving to the language control blurs the field, and the field refuses what was typed.

    The words must still be there after the switch, with the field's own error said in the new
    language; the step edit committed but saved nowhere must survive as well, unwritten.
    """
    page = bench.page
    bench.select_step("build")
    title = page.locator('[data-focus="edit-title"]')
    title.fill("Carry it out in person")
    title.press("Tab")
    card = page.locator('[data-node-id="build"] .studio-node__title')
    expect(card).to_have_text("Carry it out in person")
    role, error = page.locator('[data-focus="edit-role_id"]'), page.locator("#studio-invalid-role_id")
    role.fill("not an id!")
    expect(error).to_have_text(message_english("workflow.copy_4"))
    posts = [row for row in bench.recorder.rows if row[0] == "POST"]
    # The person reaches for the language control: the field loses focus and refuses its word.
    page.locator('[data-focus="preference-language"]').focus()
    expect(role).to_have_attribute("aria-invalid", "true")
    for language, theme, say in (("ru", "light", message_russian), ("en", "dark", message_english)):
        _switch(page, language, theme)
        expect(role).to_have_value("not an id!")
        expect(error).to_be_visible()
        expect(error).to_have_text(say("workflow.copy_4"))
        expect(role).to_have_attribute("aria-invalid", "true")
        expect(title).to_have_value("Carry it out in person")
        expect(card).to_have_text("Carry it out in person")
    assert [row for row in bench.recorder.rows if row[0] == "POST"] == posts
    assert _stored(project, "build") == "Carry it out"
    assert bench.problems == []


def test_a_refused_word_typed_into_one_step_never_lands_in_the_same_field_of_another(bench, project):
    """Every step draws its role under one key, so the key alone cannot say whose words these are.

    A person types a role the field refuses into one step and clicks another on the canvas. The
    other step shows its own role, unjudged; coming back shows the first step's stored role. The
    refused word belongs to the form it was typed into and is banked for neither step.
    """
    page = bench.page
    bench.select_step("build")
    title, role = page.locator('[data-focus="edit-title"]'), page.locator('[data-focus="edit-role_id"]')
    error = page.locator("#studio-invalid-role_id")
    role.fill("not an id!")
    expect(error).to_have_text(message_english("workflow.copy_4"))
    posts = [row for row in bench.recorder.rows if row[0] == "POST"]
    bench.select_step("identify")
    expect(title).to_have_value("Identify problems")
    expect(role).to_have_value("thinker")
    expect(error).to_be_hidden()
    expect(role).not_to_have_attribute("aria-invalid", "true")
    # Nor is the other step's field handed the caret: focus stays where the person put it.
    assert page.evaluate("document.activeElement?.getAttribute('data-focus')") != "edit-role_id"
    bench.select_step("build")
    expect(title).to_have_value("Carry it out")
    expect(role).to_have_value("builder")
    expect(error).to_be_hidden()
    assert [row for row in bench.recorder.rows if row[0] == "POST"] == posts
    assert (_stored(project, "build", "role_id"), _stored(project, "identify", "role_id")) == ("builder", "thinker")
    assert bench.problems == []
