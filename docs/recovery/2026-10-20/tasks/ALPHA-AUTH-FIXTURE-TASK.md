# ALPHA-AUTH-FIXTURE

При RS1 аудите найден оставшийся Q8 positive fixture, несовместимый с принятым
контрактом 7742eaa. Код schema не менять. На test_login_relay_flow.py::
test_a_nested_value_in_the_account_object_is_never_written_to_the_relay доказан
RED: 1 failed native, Ready ожидался, Refused(account_unknown) получен.

Техническое решение Codex: только в tests/test_login_relay_flow.py заменить
старые unknown nested/list и billingType=None на измеренный ccOnboardingFlags=dict
с теми же fake вложенными значениями и billingType=str. Сохранить положительный
Ticket, UUID/прочие plain fields и запрет попадания вложенных значений в relay.
Unknown/type-change negatives уже проверены в test_claude_auth_contract.py.
Это отдельный test-only срез, не ослабление Q8 и не RS1 production change.
Прогнать весь модуль в двух кодировках, code/tests и отчёт отдельно; моделей нет.
