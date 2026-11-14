Итог: локально проверено и принято ревью | f9df475 | 79 passed/codec,0failed |
только устаревшие fixture inputs | следующий шаг — общий release candidate/CI.

# ALPHA-AUTH-FIXTURE

TASK fb50aa4/a3421b6, ведущий Codex, независимое чтение alpha_readiness_now.
Найден прежний Q8 positive fixture с unknown nested/list и billingType=None:
native RED1failed, Refused(account_unknown) вместо Ready. Перенесён тот же fake
вложенный секрет в измеренное ccOnboardingFlags=dict, billingType=str; Ticket,
UUID/plain values и запрет любых вложенных fake bytes в relay проверяются прежними asserts.
Полный модуль дал ещё1failed/78passed: refresh-leak witness использовал unknown note.
Изменён только ключ на измеренный displayName; fake refresh и ожидаемый refresh_leak
с пустым relay не менялись. Production guards/schema не менялись.

tests/test_login_relay_flow.py: финально79passed в UTF8 и79passed CP1251,0skips/errors.
Артефакты в work/credential-depth-1111/fixture-final-*.xml; первый RED в
work/rs1-depth-fixture-1111. Изменённые assertions сохраняют прежнюю защиту,
новые guard semantics не вводились; отдельные security mutants Q8 уже в 7742eaa.
Дополнительные mutants здесь не применимы: приведены в соответствие только inputs
и expected measured plain type, проверяемые leak/omission guards не менялись.
Чужих правок нет, temp очищены собственными bounded checks; моделей/CLI нет.
Код test-only f9df475, CAPPED без новых source/tests. Ревью: ослабления asserts нет.
