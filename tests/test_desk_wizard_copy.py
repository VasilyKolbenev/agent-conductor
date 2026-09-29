"""The wizard's catalogue: complete in both languages, the spec's own words, no orphan word.

`studio-i18n.js` spreads `desk-wizard-copy.js` into the one table, so the parity guards of
`tests/test_studio_i18n.py` already cover it as a whole; these read the `wizard.` keys alone and
add what only the wizard can claim: the spec's strings stand as the spec gives them, and every
closed word the model can say (a reason, a refusal, a git state, a note, a control that waits)
has its message in both languages, so no screen ever falls back to a bare code.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.desk_wizard_node import PANEL, run_js

MODULES = {"wiz": "desk-wizard-model.js", "i18n": "studio-i18n.js"}
#: The codes of spec 7.4 the server may put in a diagnostics row (`FLOW_CODES` is lane L's and is
#: not delivered yet): each has its text here, and one it has none for falls back to a sentence.
DIAGNOSTIC_CODES = (
    "flow_invalid", "id_invalid", "id_repeated", "step_id_reserved", "text_invalid",
    "ref_unknown", "when_invalid", "link_makes_cycle", "ext_invalid", "dispatch_without_checker",
    "checker_is_doer", "dead_join", "final_gate_missing", "dispatch_not_accepted",
    "loop_body_empty", "gate_before_dispatch", "instruction_from_invalid", "reads_invalid",
    "bound_range", "timeout_range", "clean_over_actions", "clean_over_time", "template_refused",
    "contract_refused", "worst_over_actions", "worst_over_time", "timeout_clamped",
    "review_after_dispatch", "role_kind_mismatch", "link_outside_desk", "fork_failure_stops",
    "loop_order", "rework_after_correction", "return_after_correction", "role_unassigned",
    "role_capability_unsupported", "checker_cannot_verify")
#: The words the spec gives, in Russian, that the catalogue must carry exactly as given.
SPEC_WORDS = {
    "wizard.task.title": "Название задачи", "wizard.task.brief": "Что нужно сделать",
    "wizard.task.hint": "Подсказка агентам: как понять, что готово",
    "wizard.task.idea": "Идея проекта", "wizard.add.project_doc": "＋ Документ проекта",
    "wizard.add.plan": "＋ План", "wizard.add.ideas": "＋ Идеи", "wizard.add.note": "＋ Заметка",
    "wizard.add.scheme": "＋ Схема", "wizard.add.starter_docs": "Из стартовых документов",
    "wizard.instr.switch": "Передавать агентам инструкции этого проекта",
    "wizard.close.keep": "Оставить черновик", "wizard.cycle.build": "＋ Собрать свой",
    "wizard.cycle.make_project": "Сделать циклом проекта", "wizard.cycle.pinned": "цикл проекта",
    "wizard.cycle.unpin": "Открепить",
    "wizard.step.task": "Задача", "wizard.step.materials": "Материалы",
    "wizard.step.cycle": "Цикл", "wizard.step.roles": "Роли и указания",
    "wizard.step.prepare": "Подготовка", "wizard.step.run": "Запуск",
    "wizard.exit.connect_git": "Подключить git", "wizard.exit.first_commit": "Первый коммит",
    "wizard.exit.run_without_git": "Запустить без git", "wizard.role.unassigned": "назначьте",
    "wizard.git.unborn": "В репозитории нет ни одного коммита",
    "wizard.git.unsafe_directory": "git не доверяет этой папке (другой владелец)",
    "wizard.git.unavailable": "git не закреплён",
    "wizard.prepare": "Подготовить запуск", "wizard.prepare.continue": "Продолжить подготовку",
    "wizard.resume.retype": "Текст этих полей не был записан до перезагрузки — введите его заново",
    "wizard.chain.adopt": "Продолжить с записанной расстановкой",
    "wizard.chain.status.done": "сделано", "wizard.chain.status.needed": "нужно",
    "wizard.chain.status.todo": "ещё не начато",
    "wizard.launch.start": "Запустить", "wizard.launch.enqueue": "Поставить в очередь",
    "wizard.launch.skip": "Пропустить вперёд",
    "wizard.launch.refresh": "Обновить условия",
    "wizard.launch.continue_after": "Продолжить после…",
    "wizard.launch.window_queued": "окно начнётся, когда запуск стартует",
    "wizard.launch.time_info": "Проверяемый шаг резервирует время дважды — исполнителю и "
                               "проверяющему.",
    "wizard.launch.why.project_not_active": "Запуск — только у активного проекта",
    "wizard.launch.why.owner_required": "Нет владельца проекта",
    "wizard.launch.why.server_stopping": "Проект останавливается",
    "wizard.launch.seed_request": "копия HEAD на момент старта; засев сделает активный проект",
    "wizard.launch.result_queued_view": "В очереди · начнётся после активации проекта",
    "wizard.launch.caption_queue": "Запуск начнётся сам, когда освободится слот, если условия "
                                   "не изменятся. Если изменятся — спросим вас снова",
    "wizard.launch.caption_queue_view": (
        "Запуск начнётся после активации проекта — сам, только если у проекта стоит «продолжить "
        "после» с очередью задач; иначе после активации спросим вас снова"),
}
#: Messages with parameters whose Russian text, once filled in, is the spec's sentence.
SPEC_SENTENCES = {
    ("wizard.launch.actions", (("max", "4"), ("of", "8"))):
        "Действия: до 4 из 8 на весь запуск",
    ("wizard.launch.actions_spent", (("max", "4"), ("of", "8"), ("spent", "2"))):
        "Действия: до 4 из 8 на весь запуск · уже потрачено 2",
    ("wizard.launch.warn.clean_over_actions", (("actions", "9"), ("limit", "8"))):
        "Даже без исправлений запуску нужно 9 действий, разрешено 8 — он остановится, не "
        "дойдя до конца",
    ("wizard.launch.exhausted", (("spent", "8"), ("of", "8"))):
        "Лимит запуска исчерпан: потрачено 8 из 8 действий. Продолжить этот запуск нельзя — "
        "«Доработать» откроет новый запуск",
    ("wizard.launch.time", (("time", "3 ч 30 мин"),)): "Время работы: до 3 ч 30 мин",
    ("wizard.launch.window", (("time", "4 ч 30 мин"),)):
        "Разрешение действует 4 ч 30 мин с момента старта",
    ("wizard.launch.note.slot_busy", (("holder", "Add a search box"),)):
        "слот только что занял Add a search box",
    ("wizard.launch.result_queued", (("position", "3"),)): "В очереди · 3-я",
    ("wizard.launch.skip_dialog",
     (("task", "Add a search box"), ("until", "2026-09-29 13:00 UTC"))):
        "Add a search box встанет на паузу и продолжит после очереди. Его разрешение действует "
        "до 2026-09-29 13:00 UTC и за это время не продлевается.",
}
FAMILIES = {
    "reasons": "wizard.reason.{}", "git": "wizard.git.{}", "refusals": "wizard.refusal.{}",
    "notes": "wizard.note.{}", "quota": "wizard.quota.{}", "exits": "wizard.exit.{}",
    "later": "wizard.later.{}", "steps": "wizard.step.{}", "kinds": "wizard.role.{}",
    "adds": "wizard.add.{}", "cards": "wizard.card.kind.{}",
    "links": "wizard.chain.link.{}", "statuses": "wizard.chain.status.{}",
    "stages": "wizard.resume.exit_{}", "launch_why": "wizard.launch.why.{}",
    "launch_notes": "wizard.launch.note.{}", "launch_refusals": "wizard.launch.refused.{}",
    "launch_lines": "wizard.launch.line.{}", "skip_steps": "wizard.launch.skip_step.{}",
    "skip_stops": "wizard.launch.skip_stop.{}", "skip_status": "wizard.launch.skip_status.{}",
    "launch_stages": "wizard.launch.check.stage.{}",
}


def test_every_wizard_message_exists_in_russian_and_english_with_the_same_parameters():
    out = run_js("""
      const keys = Object.keys(i18n.MESSAGES).filter((key) => key.startsWith("wizard."));
      const rows = Object.fromEntries(keys.map((key) => [key, i18n.MESSAGES[key]]));
      const broken = {...rows, "wizard.x": {en: "{a}", ru: "{b}"}};
      const letters = /[A-Za-zА-Яа-я]/;
      const same = keys.filter((key) => rows[key].en === rows[key].ru
        && letters.test(rows[key].en));
      console.log(JSON.stringify({count: keys.length, whole: i18n.validateMessages(rows),
        catches: i18n.validateMessages(broken), same}));
    """, modules=MODULES)
    assert out["count"] >= 220
    assert out["whole"] is True and out["catches"] is False
    assert out["same"] == [], "a message that reads the same in both languages is untranslated"


def test_the_specs_own_words_are_used_verbatim_in_russian():
    out = run_js("""
      console.log(JSON.stringify(Object.fromEntries(
        Object.keys(d).map((key) => [key, i18n.MESSAGES[key]?.ru ?? null]))));
    """, SPEC_WORDS, modules=MODULES)
    assert out == SPEC_WORDS
    warning = run_js("""console.log(JSON.stringify(i18n.MESSAGES["wizard.close.warning"].ru));""",
                     modules=MODULES)
    assert "материалы не сохранены" in warning


def test_every_closed_word_the_model_can_say_has_a_message_in_both_languages():
    out = run_js("""
      const words = {reasons: wiz.REASONS, git: wiz.GIT_SENTENCES, refusals: wiz.REFUSALS,
        notes: wiz.NOTES, quota: wiz.QUOTA_REASONS, exits: wiz.GIT_EXITS,
        later: wiz.LATER, steps: wiz.STEPS, adds: wiz.MATERIAL_KINDS, cards: wiz.MATERIAL_KINDS,
        kinds: [...wiz.ROLE_KINDS, "custom"], links: wiz.CHAIN_LINKS,
        statuses: wiz.LINK_STATUSES, stages: wiz.RESUME_EXITS, launch_why: wiz.LAUNCH_WHY,
        launch_notes: wiz.LAUNCH_NOTES, launch_refusals: wiz.LAUNCH_REFUSALS,
        launch_lines: wiz.CARD_LINES, skip_steps: wiz.SKIP_STEPS, skip_stops: wiz.SKIP_STOPS,
        skip_status: wiz.SKIP_STATUS, launch_stages: wiz.LAUNCH_STAGES};
      const missing = [];
      for (const [family, list] of Object.entries(words)) {
        for (const word of list) {
          const key = d[family].replace("{}", word);
          const row = i18n.MESSAGES[key];
          if (!row || !row.en || !row.ru) missing.push(key);
        }
      }
      console.log(JSON.stringify({missing, sizes: Object.fromEntries(
        Object.entries(words).map(([family, list]) => [family, list.length]))}));
    """, FAMILIES, modules=MODULES)
    assert out["missing"] == []
    assert all(size > 0 for size in out["sizes"].values()), out["sizes"]
    assert out["sizes"]["reasons"] >= 23


def test_the_specs_sentences_of_the_card_come_out_as_given_once_their_numbers_are_filled_in():
    out = run_js("""
      console.log(JSON.stringify(d.map(([key, params]) => i18n.message("ru", key,
        Object.fromEntries(params)))));
    """, [[key, list(map(list, params))] for key, params in SPEC_SENTENCES], modules=MODULES)
    assert out == list(SPEC_SENTENCES.values())


def test_every_reason_note_and_refusal_the_card_returns_is_in_its_closed_list():
    text = (Path(PANEL) / "desk-wizard-launch.js").read_text(encoding="utf-8")
    held = re.search(r"function heldBy\(launch\) \{\n(.*?)\n\}\n", text, re.S).group(1)
    controls = re.search(r"export function controlsOf\(launch\) \{\n(.*?)\n\}\n", text,
                         re.S).group(1)
    reasons = set(re.findall(r'(?:return|:) "([a-z_]+)";', held)) | set(re.findall(
        r'"(slot_reading|slot_unread)"', controls))
    notes = set(re.findall(r'note: \{kind: "([a-z_]+)"', text))
    out = run_js("""
      console.log(JSON.stringify({why: wiz.LAUNCH_WHY, notes: wiz.LAUNCH_NOTES,
        refusals: wiz.LAUNCH_REFUSALS}));
    """, modules=MODULES)
    assert reasons and notes
    assert reasons <= set(out["why"]), reasons - set(out["why"])
    assert notes <= set(out["notes"]), notes - set(out["notes"])
    assert {"project_not_active", "owner_required", "server_stopping"} <= set(out["why"])


def test_every_state_of_the_preparation_read_the_card_can_draw_has_a_sentence_in_both_languages():
    out = run_js("""
      const plain = ["reading", "unlisted", "stage.documents_missing", "stage.ready_to_preview"];
      const said = (lang) => ({
        plain: plain.map((key) => i18n.message(lang, `wizard.launch.check.${key}`)),
        failed: i18n.message(lang, "wizard.launch.check.failed", {code: "made_up"}),
        other: i18n.message(lang, "wizard.launch.check.stage_other", {stage: "made_up"})});
      console.log(JSON.stringify({en: said("en"), ru: said("ru")}));
    """, modules=MODULES)
    for lang in ("en", "ru"):
        assert all(out[lang]["plain"]), lang
        assert "made_up" in out[lang]["failed"] and "made_up" in out[lang]["other"], lang


def test_every_stop_code_a_skip_ahead_press_returns_is_in_its_closed_list():
    text = (Path(PANEL) / "desk-wizard-skip.js").read_text(encoding="utf-8")
    coded = set(re.findall(r'code: "([a-z_]+)"', text))
    out = run_js("""
      const other = i18n.message("en", "wizard.launch.skip_stop.other", {code: "made_up"});
      console.log(JSON.stringify({stops: wiz.SKIP_STOPS, other}));
    """, modules=MODULES)
    assert coded == {"not_written", "read_failed"}, coded
    assert coded <= set(out["stops"])
    assert "made_up" in out["other"], "a refusal the desk has no words for is said by its code"


def test_every_diagnostic_code_of_spec_7_4_has_a_message_and_an_unknown_one_has_a_sentence():
    out = run_js("""
      const missing = d.filter((code) => !i18n.MESSAGES[`wizard.diag.${code}`]);
      const sentence = i18n.message("en", "wizard.diag.unknown", {code: "made_up"});
      console.log(JSON.stringify({missing, sentence}));
    """, list(DIAGNOSTIC_CODES), modules=MODULES)
    assert out["missing"] == []
    assert "made_up" in out["sentence"]


def test_every_code_a_gate_refusal_or_note_returns_is_in_its_closed_list():
    panel = Path(PANEL)
    text = {name: (panel / name).read_text(encoding="utf-8") for name in (
        "desk-wizard-model.js", "desk-wizard-team.js", "desk-wizard-materials.js",
        "desk-wizard-roles.js")}
    gates = []
    for name in ("desk-wizard-model.js", "desk-wizard-team.js"):
        for body in re.findall(r"function \w*Gate\(state\) \{\n(.*?)\n\}\n", text[name], re.S):
            for returned in re.findall(r"return ([^;]*);", body):
                gates += re.findall(r'"([a-z]+_[a-z_]+)"', returned)
    stops = re.findall(r'"(git_[a-z]+|starter_needs_git)"', text["desk-wizard-materials.js"])
    refusals = re.findall(r'refuse\(state, "([a-z_]+)"\)', text["desk-wizard-model.js"])
    blocked = re.findall(r'"(document_not_text|read_failed)"', text["desk-wizard-model.js"])
    notes = re.findall(r'notes(?:\.push\(|, )"([a-z_]+)"', text["desk-wizard-roles.js"])
    out = run_js("""
      console.log(JSON.stringify({reasons: wiz.REASONS, refusals: wiz.REFUSALS,
        notes: wiz.NOTES}));
    """, modules=MODULES)
    assert gates and stops and refusals and notes
    assert set(gates) | set(stops) <= set(out["reasons"]), set(gates) - set(out["reasons"])
    assert set(refusals) | set(blocked) <= set(out["refusals"])
    assert set(notes) <= set(out["notes"]), set(notes) - set(out["notes"])
    assert {"flow_conflict", "flow_changed_elsewhere", "flow_refused", "flow_unknown"} \
        <= set(out["reasons"]), "the flow_<status> family is spelled out, not built"
