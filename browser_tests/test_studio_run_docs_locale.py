"""Changing document-form language preserves the exact bytes later published."""
from playwright.sync_api import expect

from browser_tests.test_studio_artifacts import project  # noqa: F401
from browser_tests.test_studio_documents import (
    RUN_ID, LONE_AWAITED_REF, _choose_ref, _documents, _open, _publish,
    _publish_form, _read, _type_document)
from browser_tests.test_studio_preferences import _switch


def test_document_locale_preserves_draft_and_publishes_exact_original_content(chromium, project):
    page, window = _open(chromium, project)
    words = '# Personal <b>Текст</b>\n\nLiteral {ref} and $& remain unchanged.'
    try:
        _read(page, RUN_ID)
        _publish_form(page)
        _choose_ref(page, LONE_AWAITED_REF)
        _type_document(page, words)
        before = window.writes('/artifacts')
        _switch(page, 'ru', 'light')
        expect(page.locator('[data-focus-key="document:publish"]')).to_have_text('Опубликовать документ')
        expect(page.locator('[data-focus-key="field:content"]')).to_have_value(words)
        expect(page.locator('[data-focus-key="field:artifact_ref"]')).to_have_value(LONE_AWAITED_REF)
        _switch(page, 'en', 'light')
        expect(page.locator('[data-focus-key="document:publish"]')).to_have_text('Publish this document')
        expect(page.locator('[data-focus-key="field:content"]')).to_have_value(words)
        assert window.writes('/artifacts') == before
        _switch(page, 'ru', 'light')
        assert _publish(page) == 201
        held = [row for row in _documents(project.root, RUN_ID) if row.artifact_ref == LONE_AWAITED_REF]
        assert len(held) == 1 and held[0].content == words
        assert held[0].artifact_id == LONE_AWAITED_REF + '-0'
        assert window.writes('/artifacts') == before + 1
        assert window.page_errors == []
    finally:
        page.context.close()
