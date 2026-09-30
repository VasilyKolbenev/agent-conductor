"""The «Схема»'s catalogue: complete in both languages, the spec's own words, no bare code on screen.

`studio-i18n.js` spreads `desk-flow-copy.js` into the one table, so the parity guards of
`tests/test_studio_i18n.py` already cover it as a whole; these read the `schema.` keys alone and add
what only the panel can claim: every closed word its modules can say (an edit's refusal, a write's
notice, a model's notice, a field, a road word, a section) has its message in both languages, the
parameters of a message are the ones the code really passes, and the spec's strings stand as the spec
gives them. A diagnostic row's text is the wizard's (`wizard.diag.*`), held to the server's own list
of codes in `tests/test_desk_flow_guards.py`.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import fixture, run_js

MODULES = {"i18n": "studio-i18n.js", "shape": "desk-flow-shape.js",
           "write": "desk-flowwrite.js", "quick": "desk-quickcycle.js",
           "model": "desk-flow-model.js", "fields": "desk-flow-fields.js",
           "edits": "desk-flow-edits.js", "graph": "desk-flow-graph.js"}
DATA: dict[str, Any] = {"tester": fixture("flow", "desk-standard-tester.flow-state.json")["flow"],
                        "dalio": fixture("flow", "dalio-v5.flow-state.json")["flow"]}
#: The words the spec gives, in Russian, that the catalogue must carry exactly as given.
SPEC_WORDS = {
    "schema.new.from": "Начать с: {title}", "schema.starter.dalio_v5": "Цикл Далио",
    "schema.step.branch_first": "Сначала эта ветка",
    "schema.fix.rework_first": "Поставить доработку раньше",
    "schema.fix.when_success": "Заменить на «при успехе»",
    "schema.section.ext_count": "Расширенные поля · {count}",
    "schema.section.ext": "Расширенные поля", "schema.diag.heading": "Что мешает публикации",
    "schema.branch.waits": "ждёт очереди", "schema.publish": "Опубликовать",
    "schema.check": "Проверить", "schema.save": "Сохранить", "schema.ext.set": "Задать вручную",
    "schema.ext.reset": "Вернуть вычисленное", "schema.new.copy": "Править как копию",
    "schema.add.decision": "＋ Вы", "schema.kind.decision": "Вы",
}


def js(body: str) -> Any:
    return run_js("const show = (value) => console.log(JSON.stringify(value));\n" + body,
                  DATA, modules=MODULES)


def test_every_closed_word_the_flow_modules_can_say_has_a_message_in_both_languages():
    out = js("""
      const want = [
        ...shape.NOTICE_NAMES.map((name) => `schema.notice.${name}`),
        ...write.WRITE_NOTICES.map((name) => `schema.write.${name}`),
        ...quick.QUICK_NOTICES.map((name) => `schema.quick.${name}`),
        ...model.MODEL_NOTICES.map((name) => `schema.model.${name}`),
        ...fields.WRITTEN_FIELDS.map((name) => `schema.field.${name}`), "schema.field.when",
        ...shape.LINK_WHENS.map((word) => `schema.when.${word}`),
        ...["none", ...shape.REVIEW_PROFILES].map((name) => `schema.profile.${name}`),
        ...["review", "dispatch"].map((name) => `schema.capability.${name}`),
        ...Object.keys(shape.ROLE_KINDS).map((kind) => `schema.add.${kind}`),
        "schema.add.decision", "schema.add.loop",
        ...["decision", "route", "loop", "custom"].map((name) => `schema.kind.${name}`),
        ...Object.keys(shape.ROLE_KINDS).map((kind) => `wizard.role.${kind}`),
        ...["flow_title", "flow_contract", "step_removed", "step_added", "step_changed",
          "link_removed", "link_added", "link_changed", "order"]
          .map((name) => `schema.change.${name}`)];
      const sections = new Set();
      for (const flow of [d.tester, d.dalio]) {
        for (const step of flow.steps) fields.stepRows(flow, step).forEach((row) => sections.add(row.section));
        fields.flowRows(flow).forEach((row) => sections.add(row.section));
      }
      for (const name of sections) want.push(`schema.section.${name}`);
      const both = (key) => i18n.LOCALES.every((locale) => Object.hasOwn(i18n.MESSAGES, key)
        && typeof i18n.MESSAGES[key][locale] === "string");
      show({missing: want.filter((key) => !both(key)), count: want.length,
        sections: [...sections].sort()});
    """)
    assert out["missing"] == [], "a word the modules can say has no message in some language"
    assert out["count"] > 100
    assert out["sections"] == ["ext", "flow", "general", "inputs", "limits", "loop", "rework",
                               "role"]


def test_the_parameters_of_a_notice_are_the_ones_the_edits_really_pass_in_both_languages():
    out = js("""
      const say = (notice) => i18n.LOCALES.map((locale) => i18n.noticeText({locale}, notice));
      const flow = d.tester;
      const tried = (edit) => edits.applyEdit(flow, edit).notice;
      const notices = [
        tried({type: "set-field", nodeId: "do", field: "passes", value: 500}),
        tried({type: "set-field", nodeId: "result", field: "rework", value: 99}),
        tried({type: "set-field", nodeId: "do", field: "reads", value: Array(9).fill("a")}),
        edits.applyEdit(flow, {type: "add", kind: "agent", roleKind: "doer", afterId: "do"}).notice,
        edits.applyEdit(flow, {type: "duplicate", nodeId: "do"}).notice,
        edits.applyEdit(flow, {type: "delete-node", nodeId: "tester"}).notice,
        tried({type: "add", kind: "nonsense"})];
      show(notices.map((notice) => [notice.key, say(notice)]));
    """)
    assert [row[0] for row in out] == [
        "schema.notice.passes_range", "schema.notice.rework_range", "schema.notice.reads_limit",
        "schema.notice.added", "schema.notice.duplicated", "schema.notice.removed",
        "schema.notice.kind_unknown"]
    for _key, (english, russian) in out:
        assert english and russian and english != russian
    assert "1" in out[0][1][0] and "99" in out[0][1][0]


def test_a_publication_row_of_every_kind_says_itself_with_the_parameters_its_row_carries():
    out = js("""
      const before = structuredClone(d.tester), after = structuredClone(d.tester);
      after.title = "Other";
      after.ext = {execution_contract: null};
      after.steps.find((row) => row.step_id === "do").title = "Do it";
      after.steps = after.steps.filter((row) => row.step_id !== "tester-fix");
      after.steps.push({...structuredClone(d.tester.steps[0]), step_id: "extra"});
      after.steps.reverse();
      after.links = after.links.filter((link) => link.to !== "tester-fix");
      after.links.push({from: "analyst", to: "extra", when: "success"});
      after.links.find((link) => link.from === "analyst" && link.to === "do").when = "always";
      after.links = after.links.filter((link) => !(link.from === "do" && link.to === "tester"));
      const rows = graph.changeSummary(after, before);
      const needs = (text) => [...text.matchAll(/\\{([a-z_]+)\\}/g)].map((found) => found[1]);
      const text = (value) => (Array.isArray(value) ? value.join(", ") : String(value));
      const said = rows.map((row) => i18n.LOCALES.map((locale) => i18n.message(locale,
        `schema.change.${row.kind}`, Object.fromEntries(needs(
          i18n.MESSAGES[`schema.change.${row.kind}`][locale]).map((name) => [name,
          text(row[name])])))));
      show({kinds: [...new Set(rows.map((row) => row.kind))].sort(), count: said.length});
    """)
    assert out["kinds"] == ["flow_contract", "flow_title", "link_added", "link_changed",
                            "link_removed", "order", "step_added", "step_changed", "step_removed"]


def test_the_spec_s_russian_words_stand_exactly_as_the_spec_gives_them():
    out = js("show(Object.keys(%s).map((key) => [key, i18n.MESSAGES[key]?.ru]));"
             % __import__("json").dumps(SPEC_WORDS))
    assert {key: ru for key, ru in out} == SPEC_WORDS


def test_a_message_is_an_english_and_a_russian_text_and_a_raw_field_name_is_the_same_in_both():
    out = js("""
      const rows = Object.entries(i18n.MESSAGES).filter(([key]) => key.startsWith("schema."));
      show({count: rows.length,
        same: rows.filter(([, text]) => text.en === text.ru).map(([key]) => key).sort()});
    """)
    assert out["count"] > 150
    assert out["same"] == [
        "schema.field.arguments", "schema.field.attempt_bound", "schema.field.failure_policy",
        "schema.field.gate_id", "schema.field.missing_artifact_policy",
        "schema.field.required_evidence", "schema.field.resources", "schema.field.stage",
        "schema.field.success_requires"], "only the raw names of the extension fields are alike"
