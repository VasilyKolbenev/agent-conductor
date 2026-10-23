# Отчёт по задаче: H5-SUB-R5 / I2a. Relay-спецификации Claude и Codex

Итог: локально проверено | код и тесты `13be63a` (ведущий; база `b1de428`) |
UTF-8: 2228 passed, 6 skipped, 0 failed; cp1251: 2228 passed, 6 skipped, 0 failed (наборы в
«Проверки») | 12 отклонений ждут утверждения (раздел «Отклонения») | следующий шаг: I2b
(подключение к транспорту); M2a/M2b Codex неуспешны, C — `b1de428`.

- Исполнитель: Claude Code / Sonnet 5.5 (`claude-sonnet-5-5`). Итерация 1 — реализация; итерация 2
  — разбор двух ревью Opus (16 находок, раздел «Ревью Opus»). Не коммитил, `CAPPED` не трогал,
  ничего не пушил.
- Ветка `recovery/2026-10-20`. HEAD при написании — `b1de428`. Работа начата над `92a470f`
  (I1: `74e4b30`); ведущий закоммитил только документы (`674a42d`, `e2e7bce`, `01d4d85`, `f4b31c8`,
  `019cfdc`, `8bc2d64`, `61a629f`, `b1de428`): `git diff --stat f4b31c8 HEAD -- src tests
  pyproject.toml` пуст, то есть код и тесты, на которых я работал, те же.
- Прочитанные TASK и DESIGN. `H5-SUB-R5-DESIGN.md` (v2, §8, §8.1) и
  `H5-SUB-R5-M1-DECISION-REPORT.md` — на `f4b31c8`, итерация 2. `H5-SUB-R5-TASK.md`,
  `H5-SUB-R5-V2-REVIEW-REPORT.md`, I1-REPORT — итерация 1, рабочие копии до коммита `01d4d85`.
  После `f4b31c8` в DESIGN добавлены §8.2–8.3,
  в TASK — строки об M2b и промежуточном B, в решение M1 — дополнение о Grok (прочитаны как diff
  `f4b31c8..b1de428`): к I2a они не относятся.
- Состояние рабочей копии: 13 `M` и 16 `??` (с этим отчётом) — все мои; чужих изменений нет.
- Цель и наблюдаемое ожидаемое поведение. Новый модуль relay (`login_relay.py`) читает настоящий
  файл входа строго, говорит значением (не исключением), готов ли вход к попытке заданной длины,
  кладёт в пустой relay-home access-only копию и умеет убрать relay-home. Спецификации Claude и
  Codex объявлены в профилях; Codex везде получает файловое хранилище входа; имена окружения,
  подменяющие вход или маршрут, отказываются на двери и в мастере; статус Claude с `tokenSource`
  отказывается. К транспорту ничего не подключено, предикат `_login_road_covered` не менялся:
  подписочный запуск по-прежнему закрыт (H5-V1), тесты H5-V1 зелёные.

## Чужие правки

В начале итерации 2 `git status` показал только файлы I2a: чужих изменений нет. Ведущий
закоммитил свои документы (`01d4d85`, `f4b31c8`) до этого. Документы, кроме этого отчёта, не
менялись.

## Изменения

Пути `adapters/` — `src/conductor/command/adapters/`.

| Файл | Что |
| --- | --- |
| `adapters/login_relay.py` (новый, 701 строка) | `RelaySpec` (ABC, frozen), `Refused`/`Leaf`/`Ready`/`Ticket` (секреты вне `repr`), 20 кодов `REFUSALS`, `read_leaf`, `ready`, `copy_in`, `discard`, `sweep`, `_seal`, `secret_values`, `jwt_expiry`, `from_epoch_ms/seconds` |
| `adapters/claude_relay.py` (новый, 146) | `CLAUDE_RELAY`: admit, форма копии `CLAUDE_FORM`, bootstrap `.claude.json` (плоские значения `oauthAccount`), account из байтов копии, expires_at, credman |
| `adapters/codex_relay.py` (новый, 103) | `CODEX_RELAY`: admit (с `auth_mode`), форма копии `CODEX_FORM`, `AUTH_STORE_ARGV` (значение в кавычках), `CODEX_MCP_CREDENTIALS` |
| `adapters/codex_quota.py` (новый, 35) | политика квот Codex, `_native_quota`, `QUOTA_RPC`: вынесены из `codex_cli.py` без изменения содержимого (payload — те же 245 байт, сверено с `HEAD`) |
| `adapters/relay_env.py` (новый, 57) | имена, подменяющие вход или маршрут (перечень F10); `route_env_named` |
| `adapters/harness_profile.py` (+22) | `HarnessProfile.login_relay` и проверка при построении |
| `adapters/claude_code.py` | `login_relay=CLAUDE_RELAY`; `tokenSource` в `_login_method_admitted`, docstring о том, что это не измеренный отказ |
| `adapters/codex_cli.py` (784 строки; было 800) | `LOGIN_ARGV`, `LOGIN_STATUS_ARGV`, argv задачи и review/checker, `LOGIN_CREDENTIALS`, `login_relay=CODEX_RELAY`; quota импортируется из `codex_quota` |
| `adapters/provider.py` (+7), `provider_setup.py` (+6) | отказ имён маршрута на двери подписочной строки и в мастере |
| `tests/test_command_adapters.py` | `login_relay.py` в `SDK_WORKSPACE_DOOR` (как `relay_home.py` в I1) |
| тесты (новые, 10 файлов) | см. «Новые файлы»; `test_login_relay_discard.py` — `discard` и `sweep`, вынесены из `test_login_relay_flow.py` (файл перешёл 800 строк) |
| тесты (изменены) | `_fakeclaude.py` (свидетели `env_token`, `env_token_plan`, `token_source` помечен как синтетический), `test_harness_login_method.py`, три witness-а argv Codex, два теста строк подписки, один текст квитанции |

Как это устроено и чем отличается от текста задания (подробности — «Отклонения»):

1. **`RelaySpec` — данные в полях, поведение в методах.** `ProviderAuthority` замораживает профиль
   в digest плана как `asdict(profile)` → канонический JSON (`policy_providers.py:34`); спецификация
   с полями-функциями или `frozenset` сломала бы digest каждого запуска Claude и Codex. Поэтому
   поля — строки и кортежи, а `admit/bootstrap/account/expires_at/credman_refusal` — методы
   подклассов `ClaudeRelay` и `CodexRelay`. Следствие: смена формы копии меняет digest, старый
   грант отказывается. Тест через настоящий `ProviderAuthority` держит это (`test_relay_profiles`).
2. **Форма копии — одна константа на спецификацию** (`CLAUDE_FORM`, `CODEX_FORM`): пары
   `(ключ, None | текст)`, `None` убирает ключ. Конструктор разрешает менять только
   `refresh_fields`, поэтому правка после M2 не может обнулить access token.
3. **`read_leaf`**: `lstat` → открытие → `fstat` того же дескриптора; обычный файл, не symlink,
   `st_reparse_tag == 0`, `st_nlink == 1`, identity (`st_ino`, `st_dev`) до и после открытия
   совпадает; не больше `CREDENTIAL_LIMIT` (64 KiB; `.claude.json` — свой предел 4 MiB); строгий
   UTF-8 JSON-объект: без BOM, без повторных ключей, без `NaN` и `Infinity`, `RecursionError`
   перехвачен. Результат — `Leaf(doc, sha256 байтов)`; документ с настоящими токенами не в `repr`.
4. **`ready`** возвращает `Ready(digest, secrets, account, expires_at)` или `Refused(code)`:
   порядок — файл, `admit`, credman, bootstrap, срок. `expires_at − now >= horizon`; неизвестный
   срок — `expiry_unknown`, не допуск. `secrets` — значения `secret_fields` настоящего листа
   (включая refresh), для leak scan, не в `repr`. **`digest` — это digest того, из чего собрана
   копия** (`_seal`): у спецификации без других файлов (Codex) он равен SHA-256 байтов листа, у
   Claude — SHA-256 от digest листа и пар «имя файла, SHA-256 байтов» из `bootstrap`.
   `account` читается из того же документа и тех же байтов, без второго чтения диска.
5. **`copy_in`** перечитывает настоящий лист, снова применяет `admit`, берёт bootstrap и сверяет
   `_seal` с `digest` (смена оформления, смена записанного аккаунта — `changed`), **ищет значения
   настоящих refresh-полей в каждом байте, который будет записан** (сырыми и в JSON-экранировании)
   и отказывает `refresh_leak`, проверяет, что relay-home — существующая пустая папка без link и
   reparse (`relay_unusable`, `not_empty`), и пишет файлы `O_EXCL` в порядке «лист, затем
   bootstrap». Сбой записи убирает записанное (`write_failed`). `Ticket.account` — аккаунт того,
   что записано. DACL файлов — унаследованный, проверено `icacls`.
6. **`discard(relay_home, names=())`** сначала удаляет названные файлы (лист и bootstrap), затем
   дерево итеративно (без рекурсии), без перехода по link, junction и reparse (удаляются как
   записи), через `\\?\` на Windows, читает read-only флаг один раз; никогда не бросает, возвращает
   «ничего не осталось». **`sweep(relay_root, key, kind, names=())`** убирает остатки
   `<kind>-<16 hex>` в `<relay_root>/<key>` и возвращает отсортированные имена, которые остались;
   неверные `key` и `kind` — `ValueError`.
7. **Claude**: верх `.credentials.json` ровно `{"claudeAiOauth"}`, восемь ключей и их типы,
   `accessToken` непустой, `console` отказывается, неназванный план — `plan_unknown`. Копия — без
   `refreshToken` и `refreshTokenExpiresAt`. Bootstrap — `.claude.json` ровно `{"oauthAccount": …}`
   из настоящего (обязательны строки `accountUuid` и `organizationUuid`); **из объекта копируются
   только ключи с плоскими значениями** (текст, число, флаг, null), вложенные объекты и списки
   отбрасываются. Срок — `expiresAt` в миллисекундах. credman: `tengu_windows_credman is True` в
   `.config.json` **или** `.claude.json`, нечитаемый файл — `credman_unknown`.
8. **Codex**: верх ⊆ `{OPENAI_API_KEY, tokens, last_refresh, auth_mode}`, ключ API — отказ
   `api_key`; **`auth_mode` допустим только строкой `"chatgpt"`** (иная строка —
   `foreign_credentials`, не строка — `unknown_shape`; отсутствие допустимо), поле сохраняется в
   копии; `tokens` ⊆ четырёх ключей-строк, `access_token` и `account_id` непустые. Копия:
   `tokens.refresh_token = ""`, остальное не изменено (в том числе `last_refresh`, `auth_mode`).
   Bootstrap пуст. Срок — `exp` из JWT `access_token` (подпись не проверяется).
   `.credentials.json` в `login_credentials` профиля (leak scan), не копируется.
9. **Хранилище Codex.** `AUTH_STORE_ARGV = ("-c", 'cli_auth_credentials_store="file"')` — одна
   константа в `codex_relay.py`; значение — строка TOML в кавычках, как `TELEMETRY_ARGV` и как
   измерено ревью Codex. Она в `LOGIN_ARGV`, `LOGIN_STATUS_ARGV` (мастер и квитанция берут их же),
   argv задачи, review и checker (перед `TELEMETRY_ARGV`) и `QUOTA_RPC.argv`. `VERSION_ARGV` не
   тронут.
10. **Окружение.** `relay_env.py`: 12 имён Claude, 1 имя Codex, 9 общих (перечень F10 дизайна, не
    полная перепись того, что читают бинарники); совпадение без учёта регистра на всех
    платформах. Дверь `ProviderConfig` и мастер `conduct providers` отказывают их при
    `subscription`; `RelaySpec.forbids(name)` и `forbidden_env` — для пинов, собранных мимо
    `ProviderConfig` (проверку применит транспорт в I2b).
11. **Claude `auth status`**: `"tokenSource" not in said` в `_login_method_admitted` — защита в
    глубину, не измеренный отказ: бинарник 2.1.239 такого ключа в этом ответе не печатает
    (см. 1.2).

## Проверки

Каждая команда — после `. ...\December-Command-Environment.ps1 -Quiet`, Windows 11, Python 3.12.14,
`--basetemp C:\Users\Пользователь\<4 символа>` (26 символов), свой на прогон, удалён после (до
прогона `Test-Path` = False); для cp1251 — `Remove-Item Env:PYTHONUTF8, Env:PYTHONIOENCODING`
(в логе `PYTHONUTF8=[]`, `utf8_mode 0`, `preferred cp1251`; для UTF-8 — `utf8_mode 1`). Скрипты и
логи: `Documents\Codex\work\i2a-iter2\`. Живые CLI не запускались.

| Что | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| красная фаза: тесты итерации 2 против кода итерации 1 (копия `work\i2a-iter2-red` вне репозитория, `conductor.__file__` из копии; 11 файлов и тестов) | UTF-8 | **60 failed, 280 passed**: 42 на сравнениях (`Refused(...)` не то, `foreign_credentials` вместо `None`/`api_key`/`unknown_shape`, argv без кавычек, вложенные ключи, `Refused('changed')`, секрет в `repr`), 16 `TypeError` (новая сигнатура `account(doc, material)`), 2 `AttributeError` (`Ticket.account`) | новые поведения красные на старом коде; 280 прошедших — тесты поведения, которое не менялось |
| S1 (25 файлов): relay-файлы (leaf, flow, discard, claude, codex, env, profiles), стражи адаптеров, дверей, графа, hygiene, identity gate, каталога и контракта провайдеров, provider/provider_setup, `CAPPED`, file endings, unit-файлы relay_home | UTF-8 / cp1251 | **1155 passed / 1155 passed** | новые тесты и стражи зелёные (S1 повторялся на финальном дереве: первый прогон 1153, затем в `tests/test_login_relay_flow.py` добавлены два теста) |
| S2: Codex (auth_store, transport, review, version, leak surfaces, real_smoke), `test_harness_subscription_login`, `test_harness_login_method/leaks/lifetime`, `test_subscription_quota`, `test_subscription_road_boundary`, `test_production_door_boundary` | UTF-8 / cp1251 | **274 passed, 5 skipped / 274 passed, 5 skipped** | argv Codex, H5-V1 закрыт; 5 skipped — `test_command_codex_real_smoke` (нет `CONDUCT_CODEX_EXECUTABLE`, opt-in) |
| S3: Claude (transport, review, quota, leak), checker, `ProviderAuthority` (`test_check_road_limits`, `test_studio_*`), profile, vendor sandbox, model routing, grok/dsh/kimi leak surfaces (18 файлов, без нативного) | UTF-8 / cp1251 | **305 passed / 305 passed** | профиль с `login_relay` не ломает digest и соседние harness |
| S4: стражи H5-V1 (`test_execution_boundary_refusal`, `test_adapter_boundary_launch`, `test_adapter_boundary_roads`, `test_login_lease_refusal_words`, `test_process_login_closed`, `test_execution_boundary`) и потребители квот Codex после переноса (`test_command_quota`, `test_quota_connection`, `test_studio_quota_session_rows`, `test_dsh_quota_connection`) | UTF-8 / cp1251 | **488 passed, 1 skipped / 488 passed, 1 skipped** | подписочная дорога закрыта; перенос `codex_quota` не сломал потребителей; skipped — `test_execution_boundary.py:114`, был в `HEAD` |
| нативный `test_login_relay_native.py` (один файл на процесс, `icacls`) | UTF-8 / cp1251 | **2 passed / 2 passed** | файлы копии несут ровно записи папки (две: SYSTEM и пользователь), обе унаследованные |
| нативный AppContainer `test_process_login_config_native.py` (один файл на процесс) | UTF-8 / cp1251 | **4 passed / 4 passed** | прежний нативный свидетель login-home зелёный |
| `test_login_relay_native.py` в `cmd` при `chcp 866` и `chcp 65001`, обе кодировки Python (8 прогонов: старый тест из итерации 1 на старом коде и новый) | — | старый: `chcp 866` + `PYTHONUTF8=1` **2 failed**, три других сочетания 2 passed; новый: **2 passed во всех четырёх** | зависимость от кодовой страницы консоли воспроизведена и снята (находка 2.1) |
| мутанты (57) на копии вне репозитория | UTF-8 | M0 444 passed; **57 из 57 красные**, SHA-256 восстановлен 57 из 57 | таблица в «Мутанты» |
| сквозные поломки X1–X3 (ready / copy_in / read_leaf всегда отказывают) | UTF-8 | 74 / 54 / 109 failed; все — `AssertionError` (в X2 из 54: 48 `AssertionError`, 3 `DID NOT RAISE`, 3 переписанных `assert`) | ни один тест не падает исключением вместо сравнения (находка 2.4) |
| лимиты (`limits.py`): новые файлы целиком, изменённые — добавленные строки | — | LIMITS OK | строки ≤ 100, без хвостовых пробелов, CR, BOM, один `\n` в конце, файлы ≤ 800 (`login_relay.py` 701, `codex_cli.py` 784, `claude_code.py` 689) |
| неиспользуемые импорты (AST, ruff не установлен) | — | 4 замечания, все не из этой работы | `claude_code.py:177 QUOTA_POLICY` (реэкспорт, есть в `HEAD`), `test_harness_subscription_login.py:38,43` (`CODEX_HOME_ENV`, `WORK_DIR`, есть в `HEAD`), `test_codex_auth_store.py:29` (фикстура `boundary_assumed`, `noqa: F401`) |

Итого зелёных: 2228 passed, 6 skipped, 0 failed в каждой кодировке (S1 1155 + S2 274 + S3 305 + S4
488 + нативные 2 + 4). Наборы S2–S4 прогнаны на дереве, которое от финального отличается двумя
тестовыми файлами набора S1 (`test_login_relay_flow.py` — добавленные тесты,
`test_claude_relay.py` — проверяющий помощник); эти файлы S2–S4 не импортируют (`grep` по
`tests/`). Полный core, кириллический полный прогон (R5-PLAN п. 9) и CI не запускались.

Новых тестов 452 (collect-only, по файлам): `test_login_relay_leaf.py` 27,
`test_login_relay_flow.py` 79, `test_login_relay_discard.py` 27, `test_claude_relay.py` 90,
`test_codex_relay.py` 76, `test_relay_env.py` 112, `test_relay_profiles.py` 31,
`test_codex_auth_store.py` 8, `test_login_relay_native.py` 2. В итерации 1 их было 393 (27 тестов
`discard`/`sweep` из них перенесены в отдельный файл, число не меняется); итерацией 2 добавлено 59.

Условия среды, названные проверками, а не допущенные молча: junction на месте листа и жёсткая
ссылка создаются настоящие (`assert st_nlink == 2`; `st_reparse_tag == 0` у обычного файла);
**настоящий symlink-файл здесь создать нельзя** (WinError 1314, измерено), поэтому случаи
symlink, reparse-тега и подмены identity подаются в `read_leaf` ответом границы ФС (`os.lstat`) —
это подмена границы, не свойства среды; пути длиннее 260 и дерево глубже предела рекурсии
строятся тестом. Тест длинного пути `test_a_path_longer_than_the_classic_limit_is_discarded`
доказывает удаление там, где обычное длинное имя не работает (`LongPathsEnabled` = 0 здесь,
прочитано из реестра); форму `\\?\` ловит независимый от реестра тест, который наблюдает границу ФС.
Консоль: нативный тест больше не зависит от кодовой страницы консоли (проверено при `chcp 866` и
`chcp 65001`, обе кодировки Python).

Что шло параллельно: наборы S1–S4 каждой кодировки шли последовательно одним фоновым процессом;
параллельно шли только мои чтения (байтовый скан `codex.exe`, реестр) и копирование дерева красной
фазы (во время cp1251 S1–S2). На машине работали чужие процессы (Codex и Claude desktop, один
`python` с 11:35); их нагрузка не измерялась.

### Read-only измерения этой итерации (не запуск вендорских CLI)

- Байты `claude.exe` 2.1.239 (mmap, без запуска): единственный построитель ответа `auth status
  --json` собирает `{loggedIn, authMethod, apiProvider}` и добавляет `forcedLoginMethod`,
  `apiKeySource`, при `claude.ai` — `email`, `orgId`, `orgName`, `subscriptionType`; `tokenSource`
  в его окне нет (14 вхождений слова — в других местах). Метод при токене из окружения —
  `oauth_token`. Все 12 имён, названных находкой 1.7, найдены в байтах.
- Байты `codex.exe` 0.112.0: найдены `CODEX_CONNECTORS_TOKEN`, `CODEX_OSS_BASE_URL`,
  `CODEX_INTERNAL_ORIGINATOR_OVERRIDE`, `CODEX_REFRESH_TOKEN_URL_OVERRIDE`.
- Windows PowerShell 5.1 (5.1.26100.9711) передаёт программе `-c cli_auth_credentials_store="file"`
  и `-c cli_auth_credentials_store=file` одинаково: `['-c', 'cli_auth_credentials_store=file',
  'login']` (проверено `sys.argv` у `python`, без Codex).
- `HKLM\...\FileSystem\LongPathsEnabled` = 0 (чтение).

## Мутанты

Копия `src`, `tests`, `pyproject.toml` — `Documents\Codex\work\i2a-iter2-mut` (удалена после
прогона); `PYTHONPATH` на её `src`, проверено: `conductor.__file__` из копии. M0 без изменений:
444 passed (relay-тесты, env, нативный). После каждого мутанта файл возвращён и сверён по SHA-256
(57 из 57 совпали). Все 57 мутантов прогнаны одним запуском на финальном дереве; первый запуск на
предфинальном дереве оставил выжившим S2 (имя файла не входило в проверку) — добавлен тест, S2
красный; остальные 56 красные и там. Набор по умолчанию — relay-тесты (6 файлов: leaf, flow,
discard, claude, codex, profiles); свои выборки: E1–E3 — `test_relay_env`; A1–A6 и Q1 — argv-тесты
(`test_codex_auth_store` и пять тестов transport, review, subscription_login); T1, T2 —
`test_harness_login_method -k "token_source or env_token"`; M12s — один тест
`-k extended_length`; N1 — relay-тесты и нативный.

| Мутант | Что делает | Результат | Что красное |
| --- | --- | --- | --- |
| M1 | strip leaves the refresh token | 31 failed | claude_relay, codex_relay, login_relay_flow |
| M2a | Claude admit passes an extra top-level key | 8 failed | claude_relay, login_relay_flow |
| M2b | Codex admit passes an extra top-level key | 5 failed | codex_relay, login_relay_flow |
| M2c | Claude admit passes an extra credential key | 2 failed | claude_relay |
| M3 | bootstrap copies .claude.json whole | 6 failed | claude_relay, login_relay_flow |
| M4 | copy_in without the digest comparison | 7 failed | login_relay_flow |
| M5a | ready ignores the deadline against the horizon | 4 failed | login_relay_flow |
| M5b | Claude expires_at ignores the token's own expiry | 14 failed | claude_relay, login_relay_flow |
| M6 | read_leaf ignores the link count | 1 failed | login_relay_leaf |
| M7 | read_leaf ignores the reparse tag | 1 failed | login_relay_leaf |
| M8 | read_leaf does not compare the opened file with the one looked at | 1 failed | login_relay_leaf |
| M9 | read_leaf accepts two values for one key | 1 failed | login_relay_leaf |
| M10 | read_leaf reads one byte less than the limit allows to see | 2 failed | login_relay_leaf |
| M11 | discard follows a link | 3 failed | login_relay_discard |
| M12 | discard has no extended-length form | 3 failed | login_relay_discard |
| M12s | то же, выборка только теста, наблюдающего границу ФС | 1 failed | login_relay_discard |
| M13 | discard does not take the credentials first | 2 failed | login_relay_discard |
| M14 | sweep removes the homes of every kind | 1 failed | login_relay_discard |
| M15 | copy_in copies into a relay home that is not empty | 2 failed | login_relay_flow |
| M16 | copy_in has no refresh guard | 6 failed | login_relay_flow |
| M17 | Codex admit lets an API key through | 7 failed | codex_relay, login_relay_flow |
| M18 | Codex form leaves the refresh token as it is | 17 failed | codex_relay, login_relay_flow, relay_profiles |
| M19 | Claude credman is never refused | 4 failed | claude_relay |
| M20 | Claude admit lets the API-billing plan through | 4 failed | claude_relay |
| M21 | jwt expiry accepts a flag as a number | 1 failed | codex_relay |
| M22 | copy_in writes a file its spec did not declare | 3 failed | login_relay_flow |
| N1 | the copy is written elsewhere and moved in | 3 failed | login_relay_flow, login_relay_native |
| E1 | route names are matched case-sensitively | 24 failed | relay_env |
| E2 | the config door does not refuse the route names | 49 failed | relay_env |
| E3 | the wizard does not refuse the route names | 7 failed | relay_env |
| P1 | a profile accepts a relay credential the leak scan does not read | 1 failed | relay_profiles |
| P2 | the Codex leak scan does not read the tool-server credentials | 1 failed | relay_profiles |
| A1 | the dispatch argv has no auth store | 2 failed | codex_auth_store, command_codex_transport |
| A2 | the review and checker argv has no auth store | 3 failed | codex_auth_store, command_codex_review |
| A3 | the status read has no auth store | 4 failed | codex_auth_store, harness_subscription_login |
| A4 | the quota app-server has no auth store (теперь `codex_quota.py`) | 2 failed | codex_auth_store |
| A5 | the sign-in command has no auth store | 4 failed | codex_auth_store, harness_subscription_login |
| A6 | the version print carries the auth store | 10 failed | codex_auth_store, command_codex_review, command_codex_transport, harness_subscription_login |
| T1 | Claude status admits a token source | 1 failed | harness_login_method (только синтетический `token_source`) |
| T2 | Claude status admits the method `oauth_token` | 1 failed | harness_login_method (`env_token_plan`) |
| RP1 | Leaf.doc is in the repr | 2 failed | login_relay_flow |
| RP2 | Ready.secrets is in the repr | 2 failed | login_relay_flow |
| RP3 | Ticket.secrets is in the repr | 2 failed | login_relay_flow |
| S1 | the digest ignores the files beside the credential | 3 failed | login_relay_flow |
| S2 | the digest does not cover the names of the files | 1 failed | login_relay_flow |
| S3 | the Ticket names no account | 2 failed | login_relay_flow |
| S4 | the Ready names no account | 4 failed | login_relay_flow |
| S5 | Claude names an account that is not the one written | 3 failed | claude_relay, login_relay_flow |
| N2 | the account object is copied with what is nested in it | 3 failed | claude_relay, login_relay_flow |
| AM1 | Codex admit takes any text as the login mode | 10 failed | codex_relay, login_relay_flow |
| AM2 | Codex admit takes any type as the login mode | 12 failed | codex_relay, login_relay_flow |
| AM3 | Codex admit does not know the login mode (код итерации 1) | 21 failed | codex_relay, login_relay_flow |
| AM4 | the copy drops the login mode | 2 failed | codex_relay, login_relay_flow |
| Q1 | the auth store literal is the bare word | 12 failed | codex_auth_store, command_codex_review, command_codex_transport, harness_subscription_login |
| R1 | sweep removes any name that begins like a home | 1 failed | login_relay_discard |
| R2 | the refresh guard looks for the raw spelling only | 4 failed | login_relay_flow |
| PA1 | the grant digest leaves the relay out of the facts (`policy_providers`) | 4 failed | relay_profiles |

Мутанты на `_force` (повтор после снятия read-only) и на фразы `REFUSALS` не гонялись: первое держит
один тест (`test_discard_removes_a_file_the_child_made_read_only`), вторые — только проверка «фраза
есть и не называет путь». Refresh-значение, спрятанное в `oauthAccount`, ловит `refresh_leak`
(отдельный тест добавлен итерацией 2; его держит мутант M16).

## Отклонения

| Что | Почему | Кто утвердил |
| --- | --- | --- |
| `RelaySpec` — ABC-датакласс с данными в полях и методами в подклассах; `forbidden_env` — отсортированный кортеж, не `frozenset`; поля `kind`, `files`, `refresh_fields`, `section`, `form` сверх списка задания | профиль замораживается как JSON в digest плана (`policy_providers.py:34`); поля-функции и `frozenset` сломали бы его; `kind` нужен транспорту для имени `c-`/`x-`, `files` — для явного удаления, `form` — единая константа M2 | ожидает ведущего |
| `copy_in` дополнительно ищет значения настоящих refresh-полей в записываемых байтах (`refresh_leak`) | access-only не должен держаться на правильности одной константы `form`; граница C4 из ревью v2 | ожидает ведущего |
| имена окружения: общий запрет для **всех** подписочных строк (объединение Claude, Codex, общих), без учёта регистра на всех платформах (не только Windows) | дверь не ветвится по имени провайдера; строчные `https_proxy` читаются инструментами на POSIX. `API_BILLING_ENV` остался с точным регистром (не менял) | ожидает ведущего |
| `relay_acl_refusal` не вызывается из `login_relay` и не передаётся параметром | ему нужен `native` из `_winlaunch`, а `import _winlaunch` разрешён только `process.py`; вызов без `native` молча пропускал бы проверку. Остаётся I2b (см. «Передача») | ожидает ведущего |
| credman: отказывает, если «да» в любом из двух файлов; нечитаемый — `credman_unknown`; вердикт credman в digest `ready` не входит | какой файл читается первым, не измерено; ошибка в сторону допуска была бы небезопасной (дизайн F7, «приоритет `.config.json`» не принят буквально). Под lease между `ready` и `copy_in` ничего не запускается | ожидает ведущего |
| изменены ожидания существующих тестов, которые описывали прежнее поведение: HTTPS_PROXY допустим в подписочной строке (`test_provider_auth_mode.py`, `test_provider_setup_login.py`), текст команды входа в квитанции (`test_harness_subscription_login.py`: `run login` → `run -c cli_auth_credentials_store="file" login`), argv-witness-ы (по заданию) | прямое следствие пунктов 3–4 задания, а не ослабление проверки | ожидает ведущего |
| `tests/test_login_relay_native.py` помечен `skipif(os.name != "nt")` и использует `icacls`; SID берёт из `tests.os_boundary_windows` (импорт внутри функции: модуль бросает `ImportError` вне Windows) | DACL — факт Windows (образец `test_relay_home_native.py`) | ожидает ведущего |
| `Ready.digest` покрывает то, из чего собрана копия (`_seal`: лист и байты `bootstrap`), а не только лист; `RelaySpec.account(doc, material)` вместо `account(real_home)`; `Ticket` несёт `account` | находка 1.5: аккаунт доказательств и bootstrap не были привязаны к digest, `.claude.json` читался тремя разными чтениями. DESIGN §3.3 пишет `Ready(digest)` без пояснения, что он покрывает | ожидает ведущего |
| `AUTH_STORE_ARGV` — `cli_auth_credentials_store="file"` (строка TOML в кавычках); DESIGN §3.4/§3.9 пишут без кавычек | находка 1.3: измерена форма с кавычками (`results.json` ревью Codex: exit 0/1/0), голая держится на фолбэке из `--help`, который на этом ключе не пробовали. Напечатанная владельцу команда значит то же (PowerShell снимает кавычки, измерено). Правка DESIGN — ведущему | ожидает ведущего |
| блок quota Codex (политика, `_native_quota`, `QUOTA_RPC`) перенесён из `codex_cli.py` в новый `codex_quota.py`, `codex_cli.py` реэкспортирует `QUOTA_POLICY` и `QUOTA_RPC` | находка 2.8: файл стоял ровно на 800 строках за счёт убранных пустых строк, а I2b правит его; теперь 784 строки. Код не менялся (payload сверен с `HEAD`) | ожидает ведущего |
| `copy_in` без параметра `leased` (DESIGN §3.3, мутант §4 «copy_in без lease/owner краснеет») | находка 1.6: `login_relay` не знает lease (это слой транспорта); параметр без объекта аренды проверял бы равенство двух переменных вызывающего. Проверка и мутант §4 переносятся в I2b (см. «Передача») | ожидает ведущего |
| bootstrap Claude копирует из `oauthAccount` только плоские значения; закрытого набора ключей (DESIGN §3.4 «allowlist») пока нет | находка 1.4: набор ключей определит M2 Claude; вложенное содержимое чужого файла в relay не идёт | ожидает ведущего |
| `auth_mode` Codex допустим строкой `"chatgpt"` и сохраняется в копии | решение Codex M1 (DESIGN §8.1, `f4b31c8`): измеренное поле реального `auth.json` | утверждено Codex (`f4b31c8`) |

## Не проверено

- Живые CLI: ни один не запускался (ни M1, ни M2, ни платный вызов). Работает ли Claude на
  access-only копии без `refreshToken` и с `{oauthAccount}`, работает ли Codex на пустом
  `refresh_token` и с `auth_mode`, — по записи исполнителя M1/M2 (не мои измерения) совместимость
  вне AppContainer подтверждена для Claude (OK, 5,4 с) и дошла до сервера для Codex (M2a/M2b
  отказали на модели); продуктовая граница, цикл и сама команда продукта с `="file"` — M2 Codex.
- Подключение к транспорту (I2b): claim, lease, enter boundary, квитанции, leak scan попытки,
  `_login_road_covered`, двери, панель, тексты и документы владельца не тронуты.
- `relay_acl_refusal` и native-свидетель relay-home с настоящим копированием в AppContainer;
  `test_relay_home_native.py` (I1) в этой итерации не гонялся.
- Linux и macOS: тесты нейтральны, кроме junction (на POSIX — symlink на каталог), `icacls`
  (Windows) и `os.link`; не прогонялись, CI не запускался. Windows не закрывает Linux и macOS.
- Полный core и кириллический полный прогон (R5-PLAN п. 9); CI на SHA; ревью Codex.
- Привилегия на symlink-файл: настоящий не создавался (1314), случай подаётся ответом `lstat`.
- Чтение через link выше `auth_home` (сам настоящий login-home как junction): `read_leaf` видит
  только имя листа; identity login-home проверяет lease транспорта, не этот модуль.
- Гонка двух процессов над одним relay-home и убийство процесса посреди `copy_in`: не
  воспроизводились; `copy_in` пишет только в пустую папку `O_EXCL`, остаток убирает `discard` или
  `sweep` следующей попытки.
- Побочный факт: `~/DecemberCommand\logins\claude-code`, `\codex` и `\grok-build` существуют с
  23.10 (настоящие входы владельца; не созданы моими тестами: их пути — `tmp_path`; папки `relay`
  и `~/.december-command` нет). Содержимого не читал и не менял.

## Открытые вопросы

1. **Литерал хранилища Codex** — теперь `-c cli_auth_credentials_store="file"` (измеренная форма).
   Подтвердить в M2 Codex командой, которая пойдёт в продукт. DESIGN §3.4/§3.9 пишет литерал без
   кавычек: правка за ведущим.
2. **Закрытый набор ключей `oauthAccount`.** Сейчас копируются плоские значения целиком. Какие
   ключи нужны CLI и можно ли сузить до двух uuid — решает M2 Claude. Рекомендация: сузить после
   M2.
3. **credman: «любой из двух» против «приоритет `.config.json`»**; вердикт читается в `ready`, не
   входит в digest. Рекомендация: оставить, пока приоритет не измерен.
4. **`API_BILLING_ENV` сравнивается с точным регистром** (`provider.py`): `anthropic_api_key`
   проходит дверь. Не менял (вне задания). Живого обхода нет (ключ окружения снимается с верхним
   регистром, `select_environment` ищет точное имя). Рекомендация: отдельной малой правкой
   `casefold`.
5. **Union-запрет для Grok и Kimi.** Их подписочные строки отказывают `CLAUDE_CODE_*` и `CODEX_*`;
   им они не нужны. Рекомендация: оставить, пока у них нет своей спецификации.
6. **`Ready.account` и `Ticket.account`** — сырой `accountUuid` или `account_id` (идентификатор, не
   секрет; в `repr` остаётся). Если доказательства уходят за пределы машины владельца — хранить
   хеш. Решает ведущий.
7. **Перечень F10 неполный (находка 1.7).** В байтах `claude.exe` 2.1.239 есть имена, которые
   подменяют вход или маршрут и в перечень не входят: `CLAUDE_CODE_HOST_AUTH_ENV_VAR`,
   `CLAUDE_CODE_HFI_BEARER_TOKEN`, `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST`,
   `CLAUDE_CODE_HOST_HTTP_PROXY_PORT`, `CLAUDE_CODE_HOST_SOCKS_PROXY_PORT`,
   `ANTHROPIC_UNIX_SOCKET`, `ANTHROPIC_CUSTOM_HEADERS`, `ANTHROPIC_IDENTITY_TOKEN`,
   `ANTHROPIC_IDENTITY_TOKEN_FILE`, `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_AUTH_TOKEN`,
   `ANTHROPIC_AWS_API_KEY`; в `codex.exe` 0.112.0 — `CODEX_CONNECTORS_TOKEN`, `CODEX_OSS_BASE_URL`,
   `CODEX_INTERNAL_ORIGINATOR_OVERRIDE`. Семантику каждого не измерял. Окружение ребёнка строится
   из allowlist, поэтому риск — ошибка оператора в `env_allow`. Решение за дизайном: расширить F10
   или ввести префиксные правила (`CLAUDE_CODE_HOST_*`, `CLAUDE_CODE_OAUTH_*`, `ANTHROPIC_*` кроме
   имён моделей).
8. **Проверка lease в `copy_in` (находка 1.6)** — в I2b, вместе с мутантом §4.
9. **Нативные свидетели `FolderLoans` и relay-home** не дублируют `icacls`-тест; полный нативный
   witness копирования внутри boundary — I2b.
10. **Красная фаза итерации 1 сохранена не полностью**: `red2.log` (289 failed) снят с `--tb=no`,
    вид падений не записан и сейчас не восстанавливается; девять тестов, добавленных после него, на
    заглушках не показаны красными (покрыты мутантами, например M2c).

## Ревью Opus

Два ревью (линзы «CREDENTIALS» и «Доказательность и стандарт»), 16 находок. Каждая перепроверена
мною; нумерация — линза.находка. Статус: подтверждена / частично / нет.

| № | Серьёзность | Находка | Статус | Итог |
| --- | --- | --- | --- | --- |
| 1.1 | major | `repr` датаклассов выносит секреты | подтверждена | исправлено, страж, мутанты RP1–RP3 |
| 1.2 | minor | `tokenSource` не бывает в `auth status`; докстринг утверждает измерение | подтверждена | докстринг, реалистичные свидетели, T1/T2 |
| 1.3 | minor | литерал хранилища без кавычек | частично | кавычки, 5 свидетелей, Q1 |
| 1.4 | minor | `oauthAccount` копируется целиком | подтверждена | плоские значения; закрытый набор — после M2 |
| 1.5 | minor | аккаунт и bootstrap не привязаны к digest | подтверждена | `_seal`, `account(doc, material)`, `Ticket.account` |
| 1.6 | minor | `copy_in` без `leased`, отклонение не заявлено | подтверждена | заявлено, проверка и мутант §4 — в I2b |
| 1.7 | minor | перечень F10 назван «прочитанным из бинарников» | подтверждена | докстринги; расширение — решение дизайна |
| 2.1 | major | нативный тест зависит от кодовой страницы консоли | подтверждена, воспроизведена | исправлено, 8 прогонов |
| 2.2 | major | `admit` Codex отвергает реальный `auth.json` (`auth_mode`) | подтверждена | исправлено по §8.1, AM1–AM4 |
| 2.3 | minor | выжили мутанты R1 (`sweep`) и R2 (JSON-экранирование) | подтверждена | тесты, R1/R2 красные |
| 2.4 | minor | красная фаза падала не только на сравнениях | подтверждена | проверки типа, X1–X3, формулировка исправлена |
| 2.5 | minor | нативный AppContainer-тест не в отдельном процессе | подтверждена | отдельные процессы, обе кодировки |
| 2.6 | minor | M12 убит только из-за `LongPathsEnabled=0` | подтверждена | независимый от реестра тест, M12s |
| 2.7 | minor | `test_relay_profiles` повторяет логику `_facts` | подтверждена | через `ProviderAuthority`, PA1 |
| 2.8 | minor | `codex_cli.py` ровно 800 строк | подтверждена | quota в `codex_quota.py`, 784 строки |
| 2.9 | minor | таблица мутантов не называет дерево, число «36» | подтверждена | 57 мутантов на финальном дереве |

**1.1. `repr` выносит секреты (major) — подтверждена.** Красная фаза: тест-страж на коде итерации
1 падает на `assert secret not in text` для `Leaf` (2 failed, claude и codex): настоящий лист с
refresh-токеном был в `repr`. Исправлено: `field(repr=False)` у `Leaf.doc`, `Ready.secrets`,
`Ticket.secrets`; docstring модуля и классов. Страж `test_no_repr_of_what_the_relay_returns_
carries_a_secret` (оба вендора): `repr`, `str` и f-string трёх объектов не содержат ни одного fake-
секрета (access, refresh, id_token), и объекты не пусты. Мутанты RP1, RP2, RP3: по 2 failed.

**1.2. `tokenSource` (minor) — подтверждена по байтам.** Мой read-only скан `claude.exe` 2.1.239:
единственный построитель ответа `auth status --json` не печатает `tokenSource`; токен из
окружения даёт `authMethod: "oauth_token"`, который уже отказывает `ADMITTED_LOGIN_METHODS`. Условие
оставлено как защита в глубину. Исправлено: docstring `_login_method_admitted` (убрано «grounded in
measurement», назван источник вывода и то, что свидетель синтетический); в `_fakeclaude` добавлены
реалистичные `env_token` (форма бинарника, без плана) и `env_token_plan` (метод отдельно от
плана), `token_source` помечен SYNTHETIC; все три в параметризации
`test_a_login_that_is_not_a_subscription_refuses_the_run`. T1 (снять `tokenSource`): красный
только синтетический `token_source` (1 failed); T2 (допустить метод `oauth_token`): красный
`env_token_plan` (1 failed) — то есть метод и защита в глубину держатся независимо.

**1.3. Литерал хранилища (minor) — частично.** Верно: измерена форма с кавычками
(`probe.py:20`, `results.json` ревью Codex: exit 0, 1, 0 для полного, отсутствующего и пустого
refresh), голая форма держится на фолбэке из `--help` («если не разбирается как TOML, берётся
строка» — прочитан в `login --help`, на этом ключе не пробовался); `TELEMETRY_ARGV` сам объясняет
кавычки. Неверно, что есть риск для напечатанной владельцу команды: Windows PowerShell 5.1 снимает
кавычки у обеих форм и отдаёт `cli_auth_credentials_store=file` (измерено `sys.argv`); спавны
продукта получают список argv, и кавычки доходят буквально. Исправлено на форму с кавычками (одна
константа); обновлены пять свидетелей (`test_codex_auth_store`, argv задачи и review, статус и
текст квитанции в `test_harness_subscription_login`) и docstring. Q1 (голое слово): 12 failed.
DESIGN §3.4 и §3.9 пишут без кавычек — правка за ведущим (вопрос 1).

**1.4. `oauthAccount` целиком (minor) — подтверждена.** Код итерации 1 копировал объект как есть
(красная фаза: `assert ('nested' not in {...})`). Исправлено: копируются только ключи с плоскими
значениями (текст, число, флаг, null); вложенные объекты и списки отбрасываются, не отказывают
(реальный объект может нести флаги и null, ложный отказ закрыл бы сценарий). Тесты: плоское
идёт, вложенное — нет, на любой глубине (200 уровней); в relay-файле нет вложенных маркеров;
ключи с булевыми значениями сохранены. N2 (копировать всё): 3 failed. Закрытый набор ключей —
после M2 (вопрос 2).

**1.5. Аккаунт и bootstrap не привязаны к digest (minor) — подтверждена.** В коде итерации 1
`account()` Codex читал `auth.json` заново, а `.claude.json` у Claude читался в `ready` трижды
(credman, bootstrap, account) и ещё раз в `copy_in`, вне digest. Исправлено: `account(doc,
material)` не читает диск; `Ready.digest` покрывает лист и байты `bootstrap`
(`_seal`; без других файлов он равен прежнему SHA-256 листа); `copy_in` сверяет `_seal` после
admit и bootstrap и отказывает `changed`; `Ticket.account` читается из тех же байтов. Теперь
`.claude.json` читается в `ready` дважды (credman и bootstrap), в `copy_in` — раз. Тесты:
digest Codex равен SHA-256 листа (литерал); digest Claude меняется от `displayName` аккаунта и не
меняется от некопируемой части профиля; подмена `accountUuid` после `ready` → `changed` и пустой
relay; тикет называет аккаунт, записанный в файл. Мутанты S1–S5, N2: красные (S2 — имя файла в
digest — выжил в первом прогоне, добавлен тест «те же байты под другим именем», затем 1 failed).

**1.6. `copy_in` без `leased` (minor) — подтверждена как незаявленное отклонение.** DESIGN §3.3 и
§4 требуют, чтобы lease называла этот home, и мутанта «copy_in без lease/owner». Модуль
содержательного слоя не знает lease (`ownership_login`/`Owner.leased_login()` — транспорт);
параметр, который вызывающий заполнил бы тем же значением, проверял бы равенство двух его
переменных. Код не менялся; отклонение внесено в таблицу и в «Передачу», проверка и мутант §4 —
в план I2b.

**1.7. Перечень F10 (minor) — подтверждена.** Скан байтов: все 12 имён `claude.exe` и 3 имени
`codex.exe` из находки найдены (список — вопрос 7); семантику не измерял. Исправлено: докстринг
`relay_env.py` и тестового модуля («перечень F10 дизайна, не полная перепись»), тест переименован
(`..._is_the_one_f10_of_the_design_lists`). Перечень не расширял: это решение дизайна.

**2.1. Нативный тест зависит от консоли (major) — подтверждена, воспроизведена.** Старый тест (из
итерации 1) в `cmd` при `chcp 866` и `PYTHONUTF8=1`: 2 failed (`AttributeError: 'NoneType' object
has no attribute 'strip'` и `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xaf` в потоке
чтения); `chcp 866` + cp1251, `chcp 65001` в обеих кодировках — 2 passed. Исправлено: SID берёт
`tests.os_boundary_windows.current_user_sid()` (байты `whoami`, декодирование `oem` с `replace`;
импорт внутри функции). Новый тест: 2 passed во всех четырёх сочетаниях. Условие консоли названо
в «Проверки». В отчёте итерации 1 «UTF-8: 1098 passed» верно было только при консоли 65001.

**2.2. `auth_mode` (major) — подтверждена.** Код итерации 1 отказывал реальную форму M1 (красная
фаза: `assert 'foreign_credentials' is None`, 10 строк `Refused(code='foreign_credentials')`).
Исправлено по §8.1 и решению M1 (пп. 1–2): `auth_mode` допустим только строкой `"chatgpt"`, иная
строка — `foreign_credentials`, не строка — `unknown_shape`, отсутствие допустимо, ключ API
по-прежнему `api_key` (и при `auth_mode: "chatgpt"`, и при `"apikey"`), поле сохраняется в копии.
Регрессия через `ready` и `copy_in` на fake credentials: форма M1 принимается, копия равна
литералу с `auth_mode`, настоящего refresh в ней нет; девять чужих значений отказаны и
`ready`, и `copy_in` (relay пуст); старый случай без поля допустим. Личный `auth.json` не
использовался. Мутанты AM1–AM3 (любой текст / любой тип / поле неизвестно) и AM4 (копия
теряет поле): красные.

**2.3. Выжившие R1 и R2 (minor) — подтверждена.** Добавлены тесты: в key-папке рядом с настоящими
домами лежат семь папок, которые начинаются как дом, но домом не являются (`c-notes`, `c-0123`,
длинный и не-hex хвост, суффикс `.bak`, `c_…`, `c-`), и `sweep` обязан их оставить (заглавной
буквы нет: папка `C-…` в Windows — это `c-…`); и случаи refresh-токена с кавычкой, обратной
чертой, переводом строки и не-ASCII буквами с проверкой предусловия, что сырое написание в файле
отсутствует. R1: 1 failed; R2: 4 failed.

**2.4. Красная фаза падала не только на сравнениях (minor) — подтверждена.** `red1b.log` итерации
1 (96 failed): 68 `AssertionError`, 12 `Failed` (`DID NOT RAISE`), 16 исключений (13
`AttributeError`, 2 `FileNotFoundError`, 1 `RecursionError`); `red2.log` (289 failed) снят с
`--tb=no`, вид падений неизвестен. Формулировка «падают на сравнениях» заменена этим абзацем.
Исправлено: перед использованием `.digest`, `.doc`, перед чтением relay-листа и результата
`bootstrap` проверяется тип (`digest_of`, `leaf_of`, `bootstrapped`, `isinstance(..., Ticket)`).
Результат: при трёх сквозных поломках (X1–X3) все падения — `AssertionError` (X2 ещё 3 `DID NOT
RAISE` на тестах `pytest.raises`); до правки X3 давал 4 `TypeError`.

**2.5. Нативный AppContainer-тест в общем процессе (minor) — подтверждена.** В итерации 1 set3
начинался с `test_process_login_config_native.py`. Теперь нативные файлы идут отдельными
процессами: `test_login_relay_native.py` (2 passed) и `test_process_login_config_native.py`
(4 passed), в обеих кодировках (S3 без него). `test_relay_home_native.py` (I1) в этой итерации не
гонялся.

**2.6. M12 зависит от `LongPathsEnabled` (minor) — подтверждена.** `LongPathsEnabled` = 0 здесь
(прочитано). Исправлено: docstring длинного теста называет условие; добавлен тест, который
записывает пути, о которых `discard` спрашивает файловую систему (`lstat`, `scandir`, `unlink`,
`rmdir`), и требует, чтобы все были в форме `\\?\`, — он не зависит от настройки. M12 (без `\\?\`):
3 failed; M12s (выборка только нового теста): 1 failed. Тест пропускается вне Windows.

**2.7. `test_relay_profiles` повторял `_facts` (minor) — подтверждена.** Тесты digest гранта теперь
строят настоящий `ProviderAuthority` над настоящим registry (fake-бинарь Claude и Codex) и
сравнивают `authority.digest(...)` для профиля с relay, без relay и с изменённой формой; факты
содержат `login_relay` со своими полями. PA1 (убрать `login_relay` из фактов в
`policy_providers`): 4 failed.

**2.8. `codex_cli.py` ровно 800 строк (minor) — подтверждена.** Блок quota (около 15 строк в хвосте)
вынесен в `codex_quota.py`; строки перенесены по 100 символов, payload сверен с `HEAD` побайтно
(245 байт), `codex_cli.py` реэкспортирует `QUOTA_POLICY` и `QUOTA_RPC`, потребители (S2, S4)
зелёные. 784 строки: запас 16 для I2b. A4 перенесён на `codex_quota.py`: красный.

**2.9. Таблица мутантов не называла дерево (minor) — подтверждена.** Журналы итерации 1: M0 = 380
для мутантов M6–M21, E, P, A, T1 и 385 для пяти названных заданием; «36» в итоговой сводке против
38 в таблице. Исправлено: все мутанты (теперь 57) прогнаны одним запуском на финальном дереве
(M0 444 passed), таблица выше называет дерево и число.

## Ревью Codex: ожидает

Статус: ожидает. Заполняется после независимого чтения diff и необходимых проверок.

## Передача

- Итоговый commit кода и тестов: `13be63a` (ведущий Opus, 23.10.2026), не запушен; 15 новых файлов
  внесены в `CAPPED` тем же коммитом. Ведущий перед коммитом повторил 24 файла I2a и смежных дверей:
  1060 passed в UTF-8 и 1060 passed в cp1251; `test_login_relay_native.py` отдельным процессом —
  2 passed в обоих режимах. Отчёт — отдельный docs-коммит. Текст ниже — состояние до коммита.
- Статус по шкале: реализовано, локально проверено (обе кодировки). Не проверено CI, не принято
  ревью. Поправка `auth_mode` (решение M1) сделана и в этой итерации.
- Новые файлы для `CAPPED` (вносит ведущий, тем же коммитом), 15:

```
src/conductor/command/adapters/login_relay.py
src/conductor/command/adapters/claude_relay.py
src/conductor/command/adapters/codex_relay.py
src/conductor/command/adapters/codex_quota.py
src/conductor/command/adapters/relay_env.py
tests/relay_credentials.py
tests/test_login_relay_leaf.py
tests/test_login_relay_flow.py
tests/test_login_relay_discard.py
tests/test_claude_relay.py
tests/test_codex_relay.py
tests/test_relay_env.py
tests/test_relay_profiles.py
tests/test_codex_auth_store.py
tests/test_login_relay_native.py
```

- `git status --short` в конце: `M` у `claude_code.py`, `codex_cli.py`, `harness_profile.py`,
  `provider.py`, `provider_setup.py`, `tests/_fakeclaude.py`, `test_command_adapters.py`,
  `test_command_codex_review.py`, `test_command_codex_transport.py`, `test_harness_login_method.py`,
  `test_harness_subscription_login.py`, `test_provider_auth_mode.py`, `test_provider_setup_login.py`
  (все мои); `??` у 15 файлов выше и у этого отчёта (все мои). Чужих изменений нет.
- Временные файлы вне репозитория: `Documents\Codex\work\i2a-iter2\` (скрипты и логи прогонов,
  мутантов, красной фазы) и `Documents\Codex\work\i2a\` (итерация 1) оставлены; копии
  `i2a-iter2-red` и `i2a-iter2-mut` и все мои basetemp в `C:\Users\Пользователь` удалены.

### API для I2b

Модуль `adapters/login_relay.py` (в `SDK_WORKSPACE_DOOR`), спецификации — `profile.login_relay`
(`CLAUDE_RELAY`, `CODEX_RELAY`; у остальных профилей `None`).

| Вызов | Возвращает | Заметки |
| --- | --- | --- |
| `ready(auth_home, spec, now, horizon)` | `Ready(digest, secrets, account, expires_at)` или `Refused(code)` | `now` — aware `datetime`, иначе `ValueError`; `horizon` — `timedelta` (таймаут шага + 10 мин); не кешировать на цикл; зови **последним** шагом preflight. `digest` — digest того, из чего собрана копия (`_seal`), его держи до `copy_in` без изменений |
| `copy_in(auth_home, relay_home, spec, digest)` | `Ticket(leaf, names, secrets, account)` или `Refused(code)` | `digest` из `Ready`; relay-home — существующая пустая папка (`mkdir(exist_ok=False)` до вызова); повторно читает, допускает и сверяет digest. **Параметра lease нет**: зови только внутри `Owner.leased_login()` того же login-home (identity); проверка и мутант §4 — в I2b |
| `discard(relay_home, names=spec.files)` | `bool`: ничего не осталось | не бросает; `False` → `_retained += 1` |
| `sweep(relay_root, key, spec.kind, spec.files)` | `list[str]` оставшихся имён | пусто — можно; непусто — отказ до claim; `ValueError` только за неверные `key` (16 hex) и `kind` (одна буква) |
| `read_leaf(path, limit)` | `Leaf(doc, digest)` или `Refused` | общая читалка |
| `spec.forbids(name)`, `spec.forbidden_env` | `bool`, кортеж | применить к фактическим значениям выбранного окружения до claim |
| `spec.account(doc, material)` | `str` или `None` | читает только то, что ему дали; транспорт его не зовёт — аккаунт уже в `Ready` и `Ticket` |
| `Refused.code`, `Refused.phrase` | код и фраза без пути и значения | коды: `leaf_absent`, `leaf_unsafe`, `leaf_too_large`, `leaf_malformed`, `foreign_credentials`, `unknown_shape`, `no_access_token`, `api_key`, `plan_unknown`, `console_plan`, `account_unknown`, `credman`, `credman_unknown`, `expiry_unknown`, `expiry_short`, `changed`, `refresh_leak`, `relay_unusable`, `not_empty`, `write_failed` |
| `Ready.secrets`, `Ticket.secrets` | значения как `bytes` | только в `sensitive_extra`/leak scan; **не** в квитанцию, журнал, доказательства; в `repr` не попадают (`Leaf.doc` тоже) |
| `Ready.account`, `Ticket.account` | строка или `None` | идентификатор для доказательств, не секрет (вопрос 6); у `Ticket` — аккаунт записанного |
| `Ticket.leaf` | путь строкой | для `_read_attempt_result` и перечитывания; в доказательства не класть |
| `codex_relay.AUTH_STORE_ARGV` | `("-c", 'cli_auth_credentials_store="file"')` | кавычки внутри значения — часть argv, не оболочки |

Что делать транспорту (порядок по решению Codex C2–C3, §8 DESIGN):

1. До lease: `ProcessRunner.ensure_relay_root(auth_home)` (бросает `ProfileRefused`; внутри lease
   сделало бы lease uncertain), `relay_key(identity(root))`.
2. В lease, до claim, всё значением: `sweep(...)` → непусто — квитанция «не запускалось»;
   `ready(...)` → `Refused` — то же с `phrase`; `relay_acl_refusal(native, auth_home)` (I1;
   `login_relay` его не зовёт, см. отклонения) до и после создания relay-home;
   `copy_in(...)` → `Refused` — то же; затем enter boundary; затем claim; затем `runner.run`.
3. Утечки: `sensitive_extra` = `Ready.secrets` ∪ `Ticket.secrets`; после spawn перечитать
   `Ticket.leaf` как `read_leaf`, значения — в `_login_echo`/`_login_seen`; нечитаемый —
   fail-closed.
4. `finally`: `discard(relay_home, spec.files)`; `False` → `_retained`; при потере дерева
   `retire(False)` и uncertain остаются как есть.
5. Каждый spawn Codex, читающий вход, уже несёт `AUTH_STORE_ARGV` (кроме `--version`).
6. Тексты H5-V1 (`provider_setup.py:360-361` и остальные из §3.10 DESIGN) этой итерацией не
   менялись: их вычищает I2b.
7. Из этой итерации в I2b: проверка lease в `copy_in` и мутант §4; M2 Codex — одним запуском с
   argv продукта (`="file"`) и формой M1 (`auth_mode`).
