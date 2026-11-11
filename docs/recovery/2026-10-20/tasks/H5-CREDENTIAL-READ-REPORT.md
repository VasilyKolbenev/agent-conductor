Итог: локально проверено и принято ревью | 919fed1 | 195 target + 312 guards passed
на кодировку, 0 failed | сужение до доказанного surrogate-сбоя | дальше Q6/Q8/Q10 и RS1.

# H5-CREDENTIAL-READ

Исполнитель native_test_runner_v2, ведущий Codex; независимый security/spec reviewer
do_rejected_inspector. База a3e06ef; TASK b1a7e5c/3819b36, DESIGN v2 7ec99aa.
Чужих правок нет; параллельно root обновлял только именованный alpha plan и CAPPED.

## Причина и исправление

JSON допускает escaped lone surrogate. Двенадцать таких codepoints доходили до
credential_values и бросали UnicodeEncodeError на строгом UTF-8 encode.
Заменена одна строка: errors=surrogatepass по существующему login_relay precedent.
Корректный сосед, Unicode, порядок, порог 12 символов и дедупликация сохранены;
нет catch-return-empty, skip файла, ignore scalar или расширения declared names.
Path/size/JSON guards, рекурсивный walker и admission не менялись.

## Проверки

Kit: Documents/Codex/work/credential-read-1111, вне Git.

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| RED на прежнем коде | 2 failed, 0 errors/skipped | red.xml: публичное чтение бросает UnicodeEncodeError, fake quota не достигает spawn |
| credential_read/harness_login_leaks/service_metadata/codex_quota_echo | 195 passed UTF-8 | green-utf8.xml |
| Те же targets, native utf8_mode=0, stdout cp1251 | 195 passed | green-native.xml |
| file endings/CAPPED | 312 passed/codec | guards-utf8.xml, guards-native.xml |
| M0 в полной копии | 1 passed | M0.xml |
| M1 строгий encode | 1 failed | UnicodeEncodeError |
| M2 ignore/drop surrogate | 1 failed | Несовпадение literal tuple bytes |
| M3 no-op scan | 1 failed | Несовпадение literal tuple bytes |

Мутанты: ошибки подготовки/пропуски 0, copied imports проверены,
после каждого SHA восстановлен, полная копия удалена; mutants.json.
Новый tests/test_credential_read.py (53 строки) внесён в CAPPED кодом 919fed1.
Исходный login leaks file уже 793 строки; его не ужимали и cap не поднимали.
crapper/dryer/mutator не ставились. Дополнительные vendor/model calls: 0.

## Что именно доказано

Публичный credential_values сохраняет точные bytes surrogate и валидного соседа,
дедуп, Unicode, threshold и содержимое исходного fake JSON; не читает unselected file.
Fake quota caller делает оба ожидаемых fake spawn и блокирует эхо соседа.
Account ID отсутствует в обоих собственных полях ответа: отказ не объясняется
побочным metadata account-id guard. Service/login samples и retained counter очищены,
fake login files побайтно прежние. OS lease recovery/ACL/profile retirement этим
свидетелем не измерены; новые реальные homes и аккаунты не открывались.

## Отклонения и открытые вопросы

Root probe: surrogate воспроизведён; deep600 на текущем Python 3.12.14 сохранил
валидное значение без исключения. Первое ожидание RecursionError не подтвердилось;
гипотеза на этой глубине опровергнута, walker по DESIGN v2 оставлен прежним.
Предмет полного RS1 ещё требует адресной сверки supported runtimes/depth.
Нечитаемый credential -> пустой scan является прежним отдельным Q10; эта политика
не изменена. Q6/Q8/Q10 и весь H5-QUOTA-IDS-RS1 не объявляются закрытыми.
Полные core/CI, новый wheel/защищённая установка и живые providers не проверялись.

## Ревью Codex и передача

Принято после двух независимых design lenses и финального чтения security/spec diff;
blocker/major нет. Ведущий проверил target/guard logs и mutant receipts.
Код/CAPPED 919fed1. Рабочая Studio остаётся на 19956c8, server 99419 на 7830.
Принятый counter-src-19956c8-r1 не повторялся. Alpha plan: ALPHA-NEXT-2-DAYS.md.
Последний доказанный шаг — устранение одного воспроизведённого Unicode crash;
первый несделанный — остальные pre-alpha security gates, затем candidate/CI/onboarding.
Не повторять завершённые targets и M0/M1/M2/M3. Новый предел 15%, остаток при проверке 19%.
