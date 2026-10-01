"""The hub page's words: complete in both languages, the spec's own words, no bare code.

`hub-copy.js` is the one catalogue of the page (the hub imports neither `studio-i18n.js` nor
`command-view.js`). It also says the keys of `desk-status-copy.js`, the shared module whose words
the hub's column and the desk's rail both use, so a task is told in the same words in both places.
These tests read the catalogue under Node and hold it to what the spec writes down: every `state`
and every `working` value of 4.1.10 has its words; every code of the two closed lists of 4.6.5 and
every `state_code` of 4.1.5 has one clause in each language, one per name (a condition that is
checked before a route answers and inside a long step carries one name and one word); no message
shows a raw code; the parameters of a message are the ones its two languages share; and the strings
the spec gives stand as the spec gives them. The lists are typed here as the spec's tables. Once
`conductor.hub.refusals` exists (lane H), the route codes are held equal to its `HUB_ERROR_STATUS`
and no code of either of its lists may lie outside the table (the operation codes are held only
within it, not equal to it); until then that one test is skipped, and says why.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

import pytest

from tests.desk_wizard_node import run_js
from tests.test_panel_cascade import strip_comments

MODULES = {"copy": "hub-copy.js"}
#: `HUB_ERROR_STATUS` of spec 4.6.5, group by group.
ROUTE_CODES = (
    "same_origin_denied", "csrf_denied", "malformed_request", "route_not_found",
    "method_not_allowed", "contract_invalid", "windows_name_unsafe", "windows_path_too_long",
    "name_invalid", "folder_invalid", "repo_invalid",
    "project_not_found", "operation_not_found", "pick_not_found", "login_not_found",
    "candidate_not_found",
    "pick_invalid", "legacy_writers_unconfirmed", "folder_exists", "projects_home_invalid",
    "review_harness_missing", "operation_busy", "registry_busy", "registry_invalid",
    "dialog_busy", "dialog_unavailable", "profile_absent", "profile_invalid",
    "git_not_pinned", "gh_not_pinned", "git_changed", "gh_changed", "git_too_old",
    "tool_version_unreadable", "gh_not_logged_in", "gh_unreachable", "gh_failed",
    "project_busy", "project_running", "project_not_running", "project_unavailable",
    "already_active", "active_not_closed", "recovery_required", "recover_not_needed",
    "operation_not_cancellable", "project_queue_changed", "hub_in_kill_on_close_job")
#: `state_code` of spec 4.1.5: the table of the start refusals and the three codes the hub adds
#: (`status_unreadable` is the tech lead's rule of 30.09: a status file that is not the record).
STATE_CODES = (
    "hub_flags_incomplete", "project_id_invalid", "hub_origin_invalid", "status_file_invalid",
    "stdin_is_terminal", "mode_invalid", "project_identity_changed", "hub_in_kill_on_close_job",
    "owner_busy", "recovery_required", "ownership_lost", "transition_conflict",
    "ownership_unavailable", "store_error", "providers_invalid", "bind_failed", "start_failed",
    "start_timeout", "active_not_closed", "status_unreadable")
#: `OPERATION_ERROR_CODES` of spec 4.6.5 by step (the `start` row is the state codes above).
OPERATION_CODES = (
    "projects_home_invalid", "folder_exists", "gh_not_pinned", "gh_changed", "gh_not_logged_in",
    "gh_unreachable", "gh_failed", "clone_timeout", "clone_failed", "clone_cleanup_incomplete",
    "root_invalid", "root_too_broad", "root_nested", "root_in_login_home",
    "root_already_registered", "root_path_too_long", "windows_name_unsafe", "conduct_home_invalid",
    "name_invalid", "repo_invalid",
    "git_not_pinned", "git_changed", "git_too_old", "tool_version_unreadable",
    "project_not_repo_root", "tracks_product_dir",
    "legacy_writers_must_stop", "unsettled_action", "recovery_required", "transition_conflict",
    "activation_present", "inventory_bound", "git_exclude_failed",
    "ports_exhausted", "registry_busy", "registry_invalid",
    "profile_absent", "profile_invalid", "owner_busy", "stop_uncertain",
    "recovery_refused", "ownership_lost",
    "login_recovery_required", "login_owner_busy", "login_ownership_invalid",
    "login_context_required", "subprocess_failed")
ALL_CODES = sorted({*ROUTE_CODES, *STATE_CODES, *OPERATION_CODES})
#: The two values of `state` and `working` the spec names (4.1.10, 4.3.3).
STATES = ("stopped", "starting", "running", "stopping", "stop_overdue", "stop_uncertain", "failed",
          "busy_elsewhere", "recovery_required", "identity_mismatch", "missing")
WORKING = ("active", "queued", "stopped", "view")
#: The words the spec gives, in Russian, that the catalogue carries exactly as given.
SPEC_WORDS = {
    "hub.working.active": "В работе", "hub.working.view": "Просмотр",
    "hub.working.stopped": "Остановлен", "hub.working.stopped_since": "Остановлен · с {time}",
    "hub.working.queued": "В очереди · {position}-й",
    "hub.working.view_queued": "Просмотр · в очереди {position}-й",
    "hub.state.starting_active": "Запускается…", "hub.state.starting_view": "Открывается…",
    "hub.state.stopping": "Останавливается, до {time}",
    "hub.state.stop_overdue": "Остановка затянулась: шаг не закончился к {time}",
    "hub.state.stop_uncertain": "Остановка не подтверждена · нужна перезагрузка ОС",
    "hub.state.failed": "Не запустился: {reason}",
    "hub.state.busy_elsewhere": "Открыт другим conduct up",
    "hub.state.recovery_required": "Нужна перезагрузка ОС",
    "hub.state.identity_mismatch": "В папке теперь другой проект",
    "hub.state.missing": "Папка не найдена или заменена",
    "hub.line.becomes_active": "Станет активным после остановки {name}",
    "hub.line.not_active": "Не стал активным: {name} не закрыт · нужна перезагрузка ОС",
    "hub.act.stop": "Остановить на контрольной точке", "hub.act.activate": "Сделать активным",
    "hub.act.resume": "Продолжить", "hub.act.view_open": "Открыть на просмотр",
    "hub.act.view_close": "Закрыть просмотр", "hub.act.restart": "Запустить снова",
    "hub.act.recheck": "Проверить снова", "hub.act.recover": "Восстановить",
    "hub.act.forget": "Убрать из списка", "hub.act.raise": "Поднять", "hub.act.lower": "Опустить",
    "hub.act.clear_flag": "Снять флаг", "hub.act.recover_login": "Восстановить вход",
    "hub.confirm.switch": "Сейчас в работе {name}: он остановится на контрольной точке — "
                          "текущий шаг закончится сам.",
    "hub.confirm.stop": "Текущий шаг закончится сам, новые шаги не начнутся. Отменить остановку "
                        "нельзя.",
    "hub.confirm.stop_next": "Следом станет активным {name}.",
    "hub.rail.heading": "Проекты · {count}", "hub.rail.waiting": "◆ ждут вас: {count}",
    "hub.waiting.heading": "Ждут вас",
    "hub.banner.profile_absent": "Харнессы не настроены",
    "hub.banner.tools": "git / gh не закреплены или изменились",
    "hub.banner.login": "Вход {harness} не закрыт", "hub.banner.registry": "Реестр не читается",
    "hub.banner.job": "Проекты из этого hub не запускаются: он внутри задания Windows",
    "hub.banner.job_how": "Остановите hub (Ctrl+C) и запустите conduct hub из отдельного окна "
                          "терминала, а не из встроенного терминала другого приложения",
    "hub.view.with_active": "Просмотр · в работе {name}",
    "hub.view.no_active": "Просмотр · активного проекта нет",
    "hub.queue.now": "В работе: {name}", "hub.queue.none_active": "Активного проекта нет",
    "hub.queue.entry": "{position}. {name} · продолжит сам · флаг с {time}",
    "hub.limits.snapshot": "лимиты читает активный проект · снимок {time}",
    "hub.limits.none": "нет данных · лимиты читает активный проект",
    "hub.limits.unverified": "аккаунт не подтверждён",
}
#: The messages whose two texts are the same: the product's name, a glyph, and the
#: sentences made only of parameters.
KEEPS_ENGLISH = {"hub.page_title", "hub.act.menu", "hub.waiting.row_task",
                 "hub.waiting.row_project"}


def js(body: str) -> Any:
    return run_js("const show = (value) => console.log(JSON.stringify(value));\n" + body, None,
                  modules=MODULES)


def _rows() -> dict[str, list[str]]:
    return js("show(copy.HUB_COPY);")


def _parameters(text: str) -> list[str]:
    return sorted(set(re.findall(r"\{([a-z_]+)\}", text)))


def test_every_message_has_both_languages_and_the_same_parameters_in_each():
    rows = _rows()
    assert len(rows) > 150, "the whole page's words, and the codes of three closed lists"
    for key, pair in rows.items():
        assert isinstance(pair, list) and len(pair) == 2, key
        assert all(isinstance(text, str) and text.strip() == text and text for text in pair), key
        assert _parameters(pair[0]) == _parameters(pair[1]), key
        if key not in KEEPS_ENGLISH:
            assert re.search("[а-яёА-ЯЁ]", pair[1]), f"{key}: the Russian text is English"


def test_no_message_says_a_raw_code_or_a_machine_word():
    for key, pair in _rows().items():
        for text in pair:
            bare = re.sub(r"\{[a-z_]+\}", "", text)
            assert not re.search(r"\b[a-z]+_[a-z_]+\b", bare), f"{key}: {text!r}"


def test_every_state_and_working_value_of_the_spec_has_its_words():
    rows = _rows()
    need = [f"hub.working.{name}" for name in ("active", "queued", "stopped", "stopped_since",
                                                "view", "view_queued")]
    need += [f"hub.state.{name}" for name in (
        "starting_active", "starting_view", "stopping", "stopping_open", "stop_overdue",
        "stop_overdue_open", "stop_uncertain", "failed", "busy_elsewhere", "recovery_required",
        "identity_mismatch", "missing")]
    assert set(need) <= set(rows)
    assert set(STATES) - {"stopped", "running"} == {
        "starting", "stopping", "stop_overdue", "stop_uncertain", "failed", "busy_elsewhere",
        "recovery_required", "identity_mismatch", "missing"}, "the two states with no word"
    assert set(WORKING) == {"active", "queued", "stopped", "view"}


def test_the_code_words_are_exactly_the_union_of_the_three_closed_lists_of_the_spec():
    rows = _rows()
    held = sorted(key[len("hub.code."):] for key in rows if key.startswith("hub.code."))
    assert held == ALL_CODES, sorted(set(held) ^ set(ALL_CODES))
    assert len(ROUTE_CODES) == 48 and len(set(OPERATION_CODES)) == len(OPERATION_CODES)
    assert len(ALL_CODES) == 90 and "hub.code.unknown" not in rows


def _hub_refusals():
    """The hub's own module of closed lists, or None while lane H has not written it."""
    try:
        return importlib.import_module("conductor.hub.refusals")
    except ModuleNotFoundError as error:
        if error.name not in ("conductor.hub", "conductor.hub.refusals"):
            raise
        return None


def test_the_hub_route_codes_equal_the_spec_table_and_no_hub_code_lies_outside_the_table():
    refusals = _hub_refusals()
    if refusals is None:
        pytest.skip("conductor.hub.refusals not written yet (lane H)")
    named = set(refusals.HUB_ERROR_STATUS) | set(refusals.OPERATION_ERROR_CODES)
    assert named <= set(ALL_CODES), sorted(named - set(ALL_CODES))
    assert set(ROUTE_CODES) == set(refusals.HUB_ERROR_STATUS)


def test_the_state_codes_the_page_has_words_for_are_exactly_those_the_hub_can_put_on_a_project():
    lifecycle = importlib.import_module("conductor.hub.lifecycle")
    assert set(STATE_CODES) == set(lifecycle.STATE_CODES), (
        sorted(set(STATE_CODES) ^ set(lifecycle.STATE_CODES)))


@pytest.mark.parametrize("key,russian", sorted(SPEC_WORDS.items()))
def test_the_words_the_spec_gives_stand_as_the_spec_gives_them(key, russian):
    assert _rows()[key][1] == russian


def test_a_message_is_said_by_its_locale_and_a_wrong_call_fails_loudly():
    out = js("""
      const fails = (call) => { try { call(); return false; } catch (_error) { return true; } };
      show({
        ru: copy.hubText("ru", "hub.working.queued", {position: "2"}),
        en: copy.hubText("en", "hub.working.queued", {position: "2"}),
        shared: copy.hubText("ru", "desk_status.waiting_you"),
        sharedParam: copy.hubText("en", "desk_status.queued", {position: "3"}),
        locale: fails(() => copy.hubText("de", "hub.working.active")),
        key: fails(() => copy.hubText("en", "hub.working.nothing")),
        missing: fails(() => copy.hubText("en", "hub.working.queued")),
        extra: fails(() => copy.hubText("en", "hub.working.active", {surplus: "1"})),
        notText: fails(() => copy.hubText("en", "hub.working.queued", {position: 2})),
      });
    """)
    assert out == {"ru": "В очереди · 2-й", "en": "Queued · #2", "shared": "Ждёт вашего решения",
                   "sharedParam": "Queued · #3", "locale": True, "key": True, "missing": True,
                   "extra": True, "notText": True}


def test_a_code_is_said_by_its_clause_and_a_code_the_page_has_no_word_for_is_said_without_it():
    out = js("""
      show({known: copy.codeWords("en", "project_busy"),
        knownRu: copy.codeWords("ru", "project_busy"),
        unknown: copy.codeWords("en", "a_code_from_the_future"),
        notText: copy.codeWords("en", 7), none: copy.codeWords("ru", null)});
    """)
    assert out["known"] and out["knownRu"] and out["known"] != out["knownRu"]
    assert out["unknown"] == out["notText"] and "a_code_from_the_future" not in out["unknown"]
    assert out["none"] and "a_code" not in out["none"]


# -- every word of the catalogue is said by something ----------------------------------------------

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
#: The modules that say a message. The catalogue's own table is not one of them (it would name every
#: key); its functions, after the table, are.
SAYERS = ("hub.js", "hub-add.js", "hub-rail.js", "hub-stub.js")
LITERAL = re.compile(r'"((?:hub|desk_status)\.[a-z0-9_.]+)"')
FAMILY = re.compile(r"`((?:hub|desk_status)\.[a-z0-9_.]+\.)\$\{")


def test_every_hub_message_is_named_by_a_module_or_belongs_to_a_family_one_names():
    tail = (PANEL / "hub-copy.js").read_text(encoding="utf-8").split("export const HUB_LOCALES")[1]
    source = "\n".join([strip_comments((PANEL / name).read_text(encoding="utf-8"))
                        for name in SAYERS] + [strip_comments(tail)])
    page = (PANEL / "hub.html").read_text(encoding="utf-8")
    labels = set(re.findall(r'data-i18n-label="(hub\.[a-z.]+)"', page))
    literals, families = set(LITERAL.findall(source)) | labels, set(FAMILY.findall(source))
    keys = {key for key in _rows() if key.startswith("hub.")}
    orphans = sorted(key for key in keys if key not in literals
                     and not any(key.startswith(prefix) for prefix in families))
    assert orphans == [], "a message nothing says is a word the catalogue keeps for nobody"
    wanted = {key for key in literals if key.startswith("hub.")}
    assert sorted(wanted - keys) == [], "a module names a message the catalogue does not have"


def test_the_orphan_check_names_a_message_nothing_says_and_a_key_no_catalogue_has():
    said = 'const a = "hub.one"; const b = `hub.fam.${x}`;'
    literals, families = set(LITERAL.findall(said)), set(FAMILY.findall(said))
    assert literals == {"hub.one"} and families == {"hub.fam."}
    assert "hub.fam.other".startswith("hub.fam.") and "hub.two" not in literals
