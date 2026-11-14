# H5-CREDENTIAL-READ: остаток RS1 перед альфой

Владелец разрешил 5 дополнительных п.п. на полезные остатки; предел 15%.
База a3e06ef, repo чистый. Стандарт WORKING-STANDARD.md обязателен.
Основание: OPEN-DECISIONS H5-QUOTA-IDS-RS1 и отчёт H5-QUOTA-IDS.

Локальный файл с фиктивной строкой из 12 одиночных surrogate подтверждает
UnicodeEncodeError в credential_values. Не читать настоящие login-home и не
вызывать vendor CLI, модели, рабочую Studio или новые циклы.

Исправить total credential byte collection, сохраняя валидные соседние secrets,
порядок, дедупликацию, прежний порог и declared-file/size/path guards.
Не превращать unreadable в «безопасно» новым catch-return-empty.
Глубина 600 на текущем Python 3.12 не бросила: прежнее утверждение о deep crash
не считать новым измерением; нужны отдельный различающий тест и точная граница вывода.

Разрешены login_home.py и новый tests/test_credential_read.py: существующий
test_harness_login_leaks.py уже 793 строки, его не ужимать ради cap.
Root добавляет новый файл в CAPPED (tests/test_command_line_cap.py) вместе с кодом.
Документы/решения/handoff правит root. Исполнитель не коммитит.
Red старого кода, позитивный valid-neighbor witness, два режима кодировки,
relevant caller tests, no-op/drop-bad-value/recursive mutants на полных копиях.
Не закрывать этой задачей Q6/Q8/Q10 и альфу целиком.
