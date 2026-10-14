"""The thirteen words lane H wrote for the page stand in `hub-copy.js` exactly as H wrote them.

`H-to-D2-hub-handlers-live.md` section 5 is H's table: the sentence a failed recovery is told in
(`hub.reason.<recover|recover_login>.<reason>`), the hint beside a failed profile copy
(`hub.reason.recovery_required`), the hint beside a tool that is not pinned
(`hub.tool.restart_to_find`) and the three sentences of a pin FILE that cannot be used
(`hub.tool.pin_problem.<reason>`). The wording is H's and the page only carries it: this table is a
typed copy of H's, and the catalogue is held equal to it in both languages, so a rewording of either
side reds here. The hub never prepares: the command a person types for a preparation is a word in
four of these sentences (and in the clone banner), and no message besides carries
`--prepare-restart`.
"""
from __future__ import annotations

import pytest

from tests.desk_wizard_node import run_js

MODULES = {"copy": "hub-copy.js"}

H_WORDS = {
    "hub.reason.recovery_required": (
        "This project was not closed properly. Recover it first (Recover, on its row: the "
        "answer says whether a restart or a preparation is needed), then apply the profile.",
        "Проект закрыт не до конца. Сначала восстановите его (кнопка «Восстановить» в его "
        "строке: ответ скажет, нужна ли перезагрузка или подготовка), затем примените "
        "профиль.",
    ),
    "hub.reason.recover.restart_needed": (
        "The OS has not restarted since this project was left open. Do a full Restart, then "
        "press Recover again.",
        "ОС не перезагружалась с тех пор, как проект остался открытым. Сделайте полную "
        "перезагрузку и нажмите «Восстановить» ещё раз.",
    ),
    "hub.reason.recover.prepare_needed": (
        "This project's record is from before the boot counter, so it cannot prove a "
        "restart yet. In a terminal run conduct ownership recover --prepare-restart --dir "
        "<the project folder>, do a full Restart, then press Recover again. The hub does "
        "not run the preparation.",
        "Запись проекта сделана до появления счётчика загрузки и пока не может доказать "
        "перезагрузку. В терминале выполните conduct ownership recover --prepare-restart "
        "--dir <папка проекта>, сделайте полную перезагрузку и нажмите «Восстановить» ещё "
        "раз. Подготовку hub не выполняет.",
    ),
    "hub.reason.recover.other_environment": (
        "The boot environment is no longer the one this record was made in, so another "
        "Restart will not help. In a terminal run conduct ownership recover "
        "--prepare-restart --dir <the project folder> to prepare in the current "
        "environment, do a full Restart, then press Recover again. The hub does not run the "
        "preparation.",
        "Среда загрузки уже не та, в которой сделана запись, поэтому ещё одна перезагрузка "
        "не поможет. В терминале выполните conduct ownership recover --prepare-restart "
        "--dir <папка проекта>, чтобы подготовить запись в текущей среде, сделайте полную "
        "перезагрузку и нажмите «Восстановить» ещё раз. Подготовку hub не выполняет.",
    ),
    "hub.reason.recover.not_proven": (
        "No restart is proven yet. In a terminal run conduct ownership recover --dir <the "
        "project folder> to read the exact reason.",
        "Перезагрузка пока не доказана. В терминале выполните conduct ownership recover "
        "--dir <папка проекта>, чтобы прочитать точную причину.",
    ),
    "hub.reason.recover_login.restart_needed": (
        "The OS has not restarted since this login was left open. Do a full Restart, then "
        "press Recover the login again.",
        "ОС не перезагружалась с тех пор, как вход остался открытым. Сделайте полную "
        "перезагрузку и нажмите «Восстановить вход» ещё раз.",
    ),
    "hub.reason.recover_login.prepare_needed": (
        "This login's record is from before the boot counter, so it cannot prove a restart "
        "yet. In a terminal run conduct ownership recover-login --prepare-restart "
        "--auth-home <the login folder>, do a full Restart, then press Recover the login "
        "again. The hub does not run the preparation.",
        "Запись входа сделана до появления счётчика загрузки и пока не может доказать "
        "перезагрузку. В терминале выполните conduct ownership recover-login "
        "--prepare-restart --auth-home <папка входа>, сделайте полную перезагрузку и "
        "нажмите «Восстановить вход» ещё раз. Подготовку hub не выполняет.",
    ),
    "hub.reason.recover_login.other_environment": (
        "The boot environment is no longer the one this record was made in, so another "
        "Restart will not help. In a terminal run conduct ownership recover-login "
        "--prepare-restart --auth-home <the login folder> to prepare in the current "
        "environment, do a full Restart, then press Recover the login again. The hub does "
        "not run the preparation.",
        "Среда загрузки уже не та, в которой сделана запись, поэтому ещё одна перезагрузка "
        "не поможет. В терминале выполните conduct ownership recover-login "
        "--prepare-restart --auth-home <папка входа>, чтобы подготовить запись в текущей "
        "среде, сделайте полную перезагрузку и нажмите «Восстановить вход» ещё раз. "
        "Подготовку hub не выполняет.",
    ),
    "hub.reason.recover_login.not_proven": (
        "No restart is proven yet. In a terminal run conduct ownership recover-login "
        "--auth-home <the login folder> to read the exact reason.",
        "Перезагрузка пока не доказана. В терминале выполните conduct ownership "
        "recover-login --auth-home <папка входа>, чтобы прочитать точную причину.",
    ),
    "hub.tool.restart_to_find": (
        "Installed a tool just now? Restart the hub: it looks for tools once, when it "
        "starts.",
        "Только что установили инструмент? Перезапустите hub: он ищет инструменты один раз, "
        "при запуске.",
    ),
    "hub.tool.pin_problem.corrupt": (
        "The pin file tools.json is damaged, so no tool can be pinned. Restore it from a "
        "copy or move it aside, then pin again.",
        "Файл закреплений tools.json повреждён, поэтому инструмент закрепить нельзя. "
        "Верните его из копии или уберите в сторону и закрепите снова.",
    ),
    "hub.tool.pin_problem.unreadable": (
        "The pin file tools.json cannot be read (check its permissions and whether another "
        "program holds it). Fix access, then pin again.",
        "Файл закреплений tools.json не читается (проверьте права доступа и не занят ли он "
        "другой программой). Исправьте доступ и закрепите снова.",
    ),
    "hub.tool.pin_problem.unwritable": (
        "The hub cannot write the pin file tools.json (permissions, a full disk or a lock). "
        "Fix that, then pin again.",
        "hub не может записать файл закреплений tools.json (права, место на диске или "
        "блокировка). Исправьте это и закрепите снова.",
    ),
}


def _catalogue() -> dict[str, list[str]]:
    return run_js("console.log(JSON.stringify(copy.HUB_COPY));", None, modules=MODULES)


@pytest.mark.parametrize("key", sorted(H_WORDS))
def test_a_word_lane_h_wrote_stands_in_the_catalogue_verbatim_in_both_languages(key):
    assert tuple(_catalogue()[key]) == H_WORDS[key]


def test_the_prepare_command_is_a_word_in_four_sentences_of_h_and_in_the_clone_banner_only():
    rows = _catalogue()
    assert len(H_WORDS) == 13 and set(H_WORDS) <= set(rows)
    sayers = {key for key, pair in rows.items()
              if any("--prepare-restart" in text for text in pair)}
    assert sayers == {key for key in H_WORDS
                      if ".prepare_needed" in key or ".other_environment" in key
                      } | {"hub.banner.clone_recovery_how"}
    assert len(sayers) == 5, "the hub never prepares: the command is told, and no button runs it"
