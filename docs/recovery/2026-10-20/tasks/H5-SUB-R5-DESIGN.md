# H5-SUB-R5: дизайн подписочного relay для Claude Code и Codex (v2)

**Решение Codex 23.10 — раздел 8:** access-only разрешён с обязательными уточнениями;
автоматический режим возврата из §0/§6/§7 не утверждён. Исходный v2 ниже сохранён для ревью.

Opus 5.5, 23.10.2026. Задание: [H5-SUB-R5-TASK.md](H5-SUB-R5-TASK.md); основа — вариант B
[R2-H5-ANALYSIS.md](R2-H5-ANALYSIS.md). v1 прошёл ревью трёх скептиков Opus (credentials;
двери/исполнение/квитанции; Windows runner/ACL), 46 находок, из них 2 blocker и 29 major; v2 их
учитывает, номера находок — в скобках (`1.4` = линза 1, находка 4). «Измерено» — проверено на этой
машине; «по бинарнику» — из байтов установленного CLI; остальное — решение дизайна.

## 0. Суть и главное решение

Подписочная задача Claude Code 2.1.239 и Codex 0.112.0 исполняется в execution boundary на
**временном relay-home вне проекта**. Под login lease продукт кладёт туда **только access token**
(без refresh token) и для Claude минимальный bootstrap; CLI работает с `CLAUDE_CONFIG_DIR`/`CODEX_HOME`
= relay-home. **Обратно ничего не копируется**: refresh выполняет сам CLI вне boundary, на настоящем
login-home, под той же lease, штатными вызовами, которые продукт уже делает (preflight и чтение
квот). На настоящий login-home у AppContainer прав нет; `LOGIN_LOAN_OPEN` остаётся `False`.

Почему access-only, а не возврат credential (как в v1 и в п. 4 задания). Ревью показало, что обратная
запись — источник почти всех тяжёлых рисков: враждебный процесс в boundary может подложить чужой
refresh token с подделанными полями аккаунта, и copy-out запишет его в личный вход (1.4, 2.9; офлайн
аккаунт Claude-credential не доказуем, у Codex `id_token` без проверки подписи тоже); CAS-конфликты,
temp-файлы в личном home, «устаревший вход» после потерянной ротации (1.5, 1.8, 2.5, 2.14). Без
refresh token в relay ребёнку нечего ротировать и нечего возвращать; утечка ограничена access token
на его срок (тот же класс риска, что API-ключ, R1). Отклонение от п. 4 задания — на утверждение Codex.
**Условие:** M2 должен показать, что каждый CLI выполняет задачу без refresh token. Если нет — для
этого CLI включается режим возврата (§7) со всеми защитами ревью.

## 1. Факты

| # | Факт | Источник |
| --- | --- | --- |
| F1 | Один предикат `_login_road_covered()` через `_road_covers` отвечает дверям plan/preview/authorize, отказу до claim, `_hold_boundary` и checker | `harness_attempt.py:142-228`, `independent_transport.py:20-23` |
| F2 | `_home_value` не знает mode; на подписке любой spawn получает настоящий login-home | `headless_login.py:62-70`, `headless_spec.py:39` |
| F3 | Любое исключение в теле `_owned_attempt` → lease uncertain → `login_recovery_required` до перезапуска ОС; так же — отказ runner на **входе** в контейнер | `ownership_login.py:143-145, 217-259`, `harness_attempt.py:366-391` |
| F4 | claim ставится до `_attempt`, снять маркер нельзя; повтор после claim — `unknown` | `headless_cli.py:382-394, 430`, `artifact_transport.py:376`, `independent_transport.py:54` |
| F5 | Runner принимает home только маршрутом под проектом; аренда `home` (`modify`) применима к любой абсолютной папке; журнал хранит абсолютный путь и identity | `process.py:497-503`, `process_loans.py:254-270, 506-513` |
| F6 | Claude: `.credentials.json` = `{claudeAiOauth:{accessToken, refreshToken, expiresAt, refreshTokenExpiresAt, scopes, subscriptionType, rateLimitTier, clientId}}`, но тот же файл может нести `mcpOAuth`, `pluginSecrets`, `enterpriseGateway`, `gatewayTrust`…; аккаунт — в `.claude.json` → `oauthAccount{accountUuid, organizationUuid, …}` | по бинарнику (1.2) |
| F7 | Claude включает Windows Credential Manager, если `CLAUDE_CODE_FORCE_WINDOWS_CREDMAN=1` или `cachedGrowthBookFeatures.tengu_windows_credman=true` в `.config.json` (приоритет) или `.claude.json`; refresh тогда пишет в credman и удаляет `.credentials.json` | по бинарнику (1.10) |
| F8 | Codex `cli_auth_credentials_store` ∈ {`file`, `keyring`, `auto`, `ephemeral`}, иное — отказ загрузки конфига; `auth.json` = `{OPENAI_API_KEY, tokens{id_token, access_token, refresh_token, account_id}, last_refresh}` | измерено 23.10; по бинарнику (1.14) |
| F9 | Codex пишет `tmp/arg0` в `CODEX_HOME` на любой запуск; отказывается ставить helper, если `CODEX_HOME` внутри TEMP | измерено |
| F10 | Переменные, подменяющие вход или маршрут: Claude `CLAUDE_CODE_OAUTH_TOKEN*`, `…_OAUTH_REFRESH_TOKEN`, `…_OAUTH_SCOPES`, `…_OAUTH_CLIENT_ID`, `…_HOST_CREDS_FILE`, `CLAUDE_SECURESTORAGE_CONFIG_DIR`, `…_FORCE_WINDOWS_CREDMAN`, `…_CUSTOM_OAUTH_URL`, `…_ACCOUNT_UUID`, `…_USER_EMAIL`, `…_ORGANIZATION_UUID`; Codex `CODEX_REFRESH_TOKEN_URL_OVERRIDE`; общие `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`, `NODE_EXTRA_CA_CERTS`, `NODE_TLS_REJECT_UNAUTHORIZED`, `SSL_CERT_FILE`, `SSL_CERT_DIR`, `HTTP(S)_PROXY`, `ALL_PROXY` | по бинарнику (1.11) |
| F11 | Процессы из приложений Claude/Codex пишут `%LOCALAPPDATA%` в LocalCache пакета | измерено 21.10 |
| F12 | Нативные тесты аренды зелёные на этом профиле после N1 (`test_process_loans_native` 8, `test_process_login_native` 15) | N1-REPORT (3.4) |

## 2. Размещение

- **Login-home продукта** обязан иметь форму `…\DecemberCommand\logins\<name>` (как
  `process_boundary.py:32-35`); для владельца — `%USERPROFILE%\DecemberCommand\logins\claude-code` и
  `…\codex`. Не `%LOCALAPPDATA%` (F11), не личные `~/.claude`, `~/.codex`. Иная форма — отказ
  готовности с фразой (2.4, 3.2, 3.12).
- **Relay-корень выводится из login-home**, подтверждённого lease: `…\DecemberCommand\relay` (сосед
  `logins`). Один источник для транспорта, runner и fake, без зависимости от `CONDUCT_HOME` и
  окружения процесса; тесты на tmp login-home никогда не трогают настоящие папки владельца (2.4, 3.2,
  3.5, 3.12).
- Relay-корень создаётся под `_winlaunch.acl_exclusive` по `NativeHold(DecemberCommand)`: `mkdir`,
  затем `acl_set("O:<owner>D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;<owner>)", protected=True)` и проверка;
  при каждом использовании DACL обязан совпасть ровно (protected, только SY и owner) (2.17, 3.2).
- **Relay-home попытки:** `relay\<key>\<k>-<16 hex>`, `key` = первые 16 hex
  `sha256(f"{vol}:{fileid}")` корня проекта, `k` = `c` (Claude) или `x` (Codex); короткие имена
  из-за длины пути (3.11). Создаётся `exist_ok=False`; файлы — с унаследованным DACL (3.CONFIRMED).
- Runtime ребёнка (`LOCALAPPDATA/TEMP/TMP`) остаётся в проекте; relay-home не внутри TEMP (F9).

## 3. Компоненты

### 3.1 Общая функция формы relay-home (слой runner, `process_loans.py`)

`relay_home_shape(auth_homes, root, path, work, install) -> str | None` — чистая функция, **одна** для
`ready()`, транспорта, `FolderLoans.targets` и `_fakeboundary` (2.4, 3.7): путь — ровно
`<relay>\<key>\<name>` одного из настроенных login-home проекта; `key` — этого проекта; имя — по
regex; сравнение через `normcase(realpath)`; lstat-обход `[DecemberCommand, relay, key, name]`
через `_required_lstat` + `portal_violation` (не `first_directory_violation`, 3.8); нет пересечений с
проектом, work, install, login-home. Нативная часть (`relay_acl_refusal`): DACL relay-корня ровно как
в §2; на `key` и relay-home только унаследованные ACE; ни на одном из них, ни на настоящем login-home
и его родителе `logins` нет ACE с trustee `AC`, `S-1-15-2-*`, `S-1-15-3-*` (типы A, OA; условные ACE —
отказ), разбор через `process_loans._split/_fields` (1.13, 2.17, 3.3). Recording-fake DACL не
проверяет — это держат юнит-тесты `FolderLoans` с fake native и нативный свидетель.

### 3.2 Runner

- Транспорт передаёт relay-home в `AttemptFolders.home` абсолютным путём (`str`), проектный home —
  как сейчас; `harness_attempt.py:385` не вызывает `relative_to` для relay (3.6).
- `ProcessRunner._loaned`: абсолютный home → `Path(home)` без `_resolve_cwd`; относительный — как
  сейчас. `FolderLoans.targets` для абсолютного home вызывает `_refuse_relay_home` (§3.1) до
  `create_profile`. Ключ аренды прежний `home`, права `modify`, журнал и recovery без изменений.
- Runner объявляет статическую способность `RELAY_HOME_LOANS = True`; `_launch_covers` на relay-дороге
  требует её, иначе ответ — общий `boundary_detail` (2.4).
- `process_boundary.AttemptFolders._route` — правка только для паритета тестового класса.

### 3.3 `adapters/login_relay.py` (новый)

- `RelaySpec`: `credential` (имя листа), `secret_fields` (только их значения — в leak scan; 1.16),
  `admit(doc) -> str | None` (строгая схема настоящего листа), `strip(doc) -> dict` (access-only
  копия), `bootstrap(real_home) -> dict[str, bytes]`, `fresh_enough(doc, now, horizon) -> bool`,
  `forbidden_env`.
- `read_leaf(path)`: обычный файл, не symlink, `st_reparse_tag == 0`, native identity без
  delete-pending, `nlink == 1`, размер ≤ `CREDENTIAL_LIMIT`, строгий UTF-8 JSON-объект.
- `ready(auth_home, spec, now, horizon) -> Ready(digest) | Refusal(code)`.
- `copy_in(auth_home, relay_home, spec, leased, digest) -> Ticket | Refusal`: под lease; lease
  называет этот home (`Owner.leased_login()`, identity); дайджест настоящего листа = `digest` из
  `ready()` (иначе отказ до claim); запись `strip(doc)` и bootstrap в пустой relay-home (create-new).
- `discard(relay_home)`: сначала явно удаляет лист и bootstrap, затем дерево; длинные пути через
  `\\?\`; отказ → `_retained += 1` (те же факты `DOER_HOME_RETAINED`/`CHECKER_HOMES_REFUSED`; 2.10, 3.11).
- `sweep(relay, key, kind)`: удаляет остатки; в access-only остаток содержит только access token и
  файлы ребёнка, возвращать нечего (1.9, 3.10).

### 3.4 Спецификации

- **Claude** (`claude_relay.py`; `claude_code.py` уже 677 строк): лист `.credentials.json`;
  `admit`: верхний уровень **ровно** `{"claudeAiOauth"}` (иначе отказ: «в папке входа есть другие
  credentials»), ключи `claudeAiOauth` ⊆ F6, типы строки/int/list[str], `subscriptionType` не console;
  `strip`: `claudeAiOauth` без `refreshToken` (ключ отсутствует, не пустой — `""` значит мёртвый, 1.4)
  и без `refreshTokenExpiresAt`; `bootstrap`: `.claude.json` только с `oauthAccount` из настоящего
  (allowlist; без `cachedGrowthBookFeatures`, `mcpServers`, `projects`, `primaryApiKey`; ключи по
  итогам M2); `fresh_enough`: `expiresAt − now ≥ horizon`; `secret_fields`: `accessToken`,
  `refreshToken`.
- **Codex** (`codex_relay.py`): лист `auth.json`; `admit`: верхний уровень ⊆ {`OPENAI_API_KEY`,
  `tokens`, `last_refresh`}, `OPENAI_API_KEY` отсутствует или null, `tokens` ⊆ четырёх ключей,
  `account_id` — непустая строка (1.14); `strip`: `tokens` без `refresh_token`; bootstrap пуст
  (`config.toml` не копируется; модель — из роли, иначе по умолчанию Codex, фиксируется в
  доказательствах, 1.15); `fresh_enough`: `exp` из payload `access_token` (без проверки подписи;
  только время) `− now ≥ horizon`; `secret_fields`: `id_token`, `access_token`, `refresh_token`,
  `OPENAI_API_KEY`. `$CODEX_HOME/.credentials.json` (MCP OAuth) не копируется и входит в leak scan.
- **Codex `-c cli_auth_credentials_store=file`** — в `LOGIN_ARGV` (одно место для мастера и квитанции,
  2.15) и во всех spawn: version, status, task, review, checker, quota.
- `HarnessProfile.login_relay: RelaySpec | None = None`; заполнено только у Claude и Codex.
- `horizon` = таймаут шага + 10 мин.

### 3.5 Refresh вне boundary

Если `fresh_enough` ложно, `_preflight` до claim один раз запускает штатный вызов вендора на
настоящем home вне boundary под lease: Codex — quota RPC `account/read` с `refreshToken: true`;
Claude — quota control RPC (`initialize`, M3 подтверждает, что он обновляет просроченный токен).
Затем `ready()` повторяется; если срок всё ещё мал — отказ до claim: «срок входа меньше шага;
войдите заново: <команда без пути>». Это и есть «обновление session» задания; refresh token никогда
не покидает настоящий home.

### 3.6 Предикат, готовность, claim

- `_login_road_covered()` = `not self._signed_in_road() or self._profile.login_relay is not None`;
  `_relayed(mode)` = `_confine` и mode ≠ None и подписка и `login_relay` (2.7). Неconfined дорога
  фейков не меняется (HOME = настоящий login-home); это записать в docstring.
- `ready()` вызывается **последним** шагом `_preflight` — после `_login_preflight`, то есть после
  последнего spawn на настоящем home (2.3, 1.7); ранняя дешёвая проверка допустима. Возвращает
  `digest` для `copy_in`.
- **claim переносится внутрь lease** для relay-попытки: `_owned_attempt` получает callback claim и
  вызывает его после успешного `copy_in`, непосредственно перед spawn (2.2). Отказы входа в lease,
  sweep и `copy_in` — типизированный `RelayRefused(code)` до claim: dispatch и review — квитанция
  failed «no task was spawned», checker — закрытый ключ `login_not_ready` (2.6). Дороги без relay —
  прежний порядок.

### 3.7 Исключения под lease (blocker 2.1, 3.1)

- `_run_confined` различает отказ **до** yield блока `container_profile` (ребёнка не было) и сбой
  **после** тела. Для relay-попытки отказ на входе → значение `NotStarted`, сбой на выходе →
  значение `LaunchLost`; ни то ни другое не бросается внутри lease, `discard` выполняется, lease
  закрывается чисто. Недоказанное завершение дерева ставит uncertain только через существующий
  `retire(False)` process-loan.
- `_attempt` **вне** декоратора превращает `NotStarted` в квитанцию «не запускалось» (до claim), а
  `LaunchLost` — в прежний `self.error` (runtime пишет unknown). Квитанции и runtime-слова — новые
  строки REASONS после «exceeded its timeout» и «exit non-zero» (2.6).

### 3.8 Leak scan (1.1, 2.8)

`sensitive_extra` = `secret_fields` настоящего листа (снятые в `ready`) ∪ значения relay-листа. После
spawn и до discard `_read_attempt_result` перечитывает relay-лист: его значения идут в `_login_echo`
и `_login_seen`; нечитаемый или не проходящий схему relay-лист → `_login_echo = True` (fail-closed).
`_take_back_login` для relay-попытки не вызывается: ребёнок не имел прав на настоящий home (2.14).

### 3.9 Окружение

Имена F10 отказываются (а) на двери конфига для подписки (`provider.py`, `provider_setup`) и (б) во
время выполнения по фактическим значениям в выбранном окружении — в `_login_home_refusal` до claim
и в quota (`not_supported`), по образцу Grok `grok_build.py:340-345, 515-516` (1.11). Claude
`auth status`: отказ при `tokenSource` (как `claude_quota.py:85-87`). `ready()` Claude отказывает,
если в настоящем `.config.json`/`.claude.json` `tengu_windows_credman == true` (1.10, F7).

### 3.10 UI и тексты (2.12, 2.13)

- Строка провайдера получает закрытый факт `task_road` = `registry.execution_boundary(id, "dispatch")`
  (`boundary`|`refused`); тексты Agents/Desk выбираются по паре (`auth`, `task_road`), не по списку
  вендоров. Мастер `conduct providers` — по `profile.login_relay is not None`.
- Удалить формулировки H5-V1 из: `harness_attempt.py` (145-146, 170-179, 208), `harness_profile.py`
  (77-87), `failure_reasons.py` (29-30), `process_boundary.py` (36-44, 48-56, 90-97),
  `process_loans.py` (29-33), `headless_login.py` (10-25, 62-70), `codex_cli.py` (590-600),
  `provider_setup.py` (357-361), `desk-wizard-copy.js` (420-428), `desk-wizard-prepare-view.js`
  (16-18), `studio-agents-copy.js` (196-199), `studio-people.js` (82-88), `isolation_facts.py`
  (143-148, строка про relay), docstring тестов; документы владельца: `first-run-v1*.md`,
  `README*.md`, `owner-acceptance*.md`, `release-smoke.md`, `R5-REHEARSAL-RUNBOOK.md`. Для Grok и
  Kimi: «вход по подписке для этого harness внутри изоляции пока не поддержан».

## 4. Тесты

- **Отрицательные свидетели** дверей, review, checker, `_attempt` — на Claude и Codex с
  `replace(profile, login_relay=None)` (у Grok и Kimi нет review и checker) плюс Grok и Kimi для
  дверей и dispatch; `[SUBSCRIPTION]` в `test_execution_boundary_refusal` — Claude без relay,
  проверка через `receipt.detail`. Стражи «один вызов `AttemptFolders(...)`», «gate читают только
  прежние модули», `mode=None` по умолчанию у `_home_value` сохраняются (2.11).
- **Положительные** — на активированном проекте с живым `ProjectOwner` и настоящей `LoginLease` на
  tmp login-home `…/DecemberCommand/logins/x` (без подмены `login_write_guard`); мутант «copy_in без
  lease/owner» краснеет (2.11).
- Relay: в relay-home ровно объявленное, без `refreshToken`/`refresh_token`; лишний ключ верхнего
  уровня, API-ключ, обрезанный JSON, > 64 KiB, symlink/junction/hardlink — отказ до claim;
  status-spawn удаляет или обнуляет лист → отказ до claim, маркера нет (1.7, 2.3); срок токена мал →
  refresh-вызов → повтор → допуск или отказ; `enter_error` → «не запускалось», `active.json`
  закрыт как `closed-*`, следующая lease берётся; `exit_error` → unknown, lease чистая;
  `retire(False)` → uncertain сохраняется (2.1, 3.1); review печатает relay-токен → не опубликован;
  sweep и отказ discard (`_retained`, публикация отказана); `stopped`/`timed_out` → discard выполнен;
  quota во время relay → deferred; два проекта с одним login → `login_owner_busy` до claim (1.17);
  Codex `-o` → `_answer == ANSWER_WRITTEN` (2.16); запрещённые env по значению.
- Runner/`FolderLoans` с fake native: relay-home чужого key, в проекте, с `..`, junction в маршруте,
  незащищённый DACL, ACE `AC`/`S-1-15-3-1`/`OA`, пересечение с login-home — отказ.
- Изоляция тестов: autouse-фикстура `CONDUCT_HOME` в tmp и страж «под `Path.home()` ничего не
  создано» (3.5).
- **Нативный свидетель** `tests/test_relay_home_native.py` (образец `test_process_loans_native` +
  refresh-шаблоны `test_process_login_native`, без `login_loan_open_module`, с `internet_client=True`,
  `_ps1` helper): ребёнок может на месте, rename, delete+move обновить лист в relay-home и создать
  файл; не может удалить relay-home, писать в `key`, relay-корень, relay-home другого key, читать или
  писать `.credentials.json` настоящего login-home, писать в box; после выхода `entries_naming == []`,
  DACL login-home и relay-корня прежние; `LOGIN_LOAN_OPEN is False`. Обязателен зелёный прогон
  локально на кириллическом basetemp и в CI (3.4).

## 5. Измерения (по заданию — не больше одного минимального запуска каждого CLI)

- **M1** (без вызова модели): после входа владельца — наличие листов; ключи схемы без значений;
  `oauthAccount` в `.claude.json`; `tengu_windows_credman`; сроки: Claude `expiresAt`,
  `refreshTokenExpiresAt`; Codex `last_refresh`, `exp` access token. Повторить после первого чтения
  квот (1.10).
- **M2** (один минимальный запуск каждого CLI, вне продукта, при остановленном сервере, чистый
  allowlist-окружение + NONESSENTIAL, папка с DACL как у relay): access-only копия (без refresh token)
  и bootstrap; ответ «OK»; список созданных файлов; появился ли refresh-ключ. Refresh token настоящего
  home не покидает, поэтому проба не может испортить вход (1.12, 3.9).
- **M3**: обновляет ли Claude quota control RPC просроченный access token (§3.5) — по первому случаю
  в цикле или по `expiresAt` до/после чтения квот.

## 6. Риски

- R1. Ребёнок в boundary видит access token и имеет сеть — класс риска API-ключа, на срок токена.
- R2. Claude credman (F7) после quota-spawn: `ready()` отказывает с действием; профилактику решаем по
  M1-повтору.
- R3. Остатки relay удалённых проектов: содержат только access token, истекающий в пределах срока;
  sweep по своему key; отдельная уборка — после V1.
- R4. Если M2 покажет, что CLI требует refresh token, — режим возврата (§7) для этого CLI.

## 7. Режим возврата (только если M2 требует)

Включается per-CLI флагом `RelaySpec.returns`. Тогда дополнительно: копируется и refresh token;
`copy_out` никогда не бросает; верхний уровень ровно как `admit`; Claude — сверка только
`accountUuid`/`organizationUuid` при обязательном relay `.claude.json` (1.3); Codex — `account_id`,
claims `id_token`/`access_token`, `last_refresh` растёт; CAS по дайджесту из `ready()`; temp в
настоящем home с `O_EXCL` и исключением шаблона из учёта; `NotReturned` — durable факт вне квитанции,
`ready()` отказывает до смены листа; после `Returned` — обязательная сверка аккаунта ответом вендора
(quota `account`) до следующего claim (1.4, 1.5, 1.8, 2.5). Подмена входа через copy-out — отдельный
риск на решение владельца.

## 8. Ревью Codex, 23.10.2026: решение для продолжения

**Продолжать access-only без copy-out.** Полное основание и доказательства —
[H5-SUB-R5-V2-REVIEW-REPORT.md](H5-SUB-R5-V2-REVIEW-REPORT.md).
Этот раздел и уточнённый TASK имеют приоритет над противоречащими им пунктами исходного v2.

- **C1, §3.4:** Codex 0.112.0 отказывает в чтении `auth.json` без поля `refresh_token`.
  Пустая строка проходит только локальный status; это кандидат для M2, не доказательство работы.
  Access-only означает отсутствие настоящего refresh-секрета. Не переносить формат на Claude
  без проверки; не менять метаданные времени ради допуска и не применять отсутствующий в
  pinned help `--with-access-token`.
- **C2, §3.6–3.7:** порядок для dispatch/review/checker — lease → copy-in → успешный enter
  boundary → claim → runner.run. Отказ enter не оставляет marker. После claim сохраняется
  честный unknown для неизвестного исхода, без автоматического повтора.
- **C3, §3.6–3.7:** ожидаемые отказы sweep/copy-in/enter возвращаются значением либо ловятся
  внутри lease, а публичная квитанция строится снаружи. Они не должны делать login uncertain.
  Непредвиденная потеря контроля и `retire(False)` по-прежнему требуют recovery.
- **C4, §0/§6/§7:** `RelaySpec.returns` и copy-out не реализовать как fallback этого задания.
  Неудачный M2 — конкретное препятствие для нового решения Codex, а не разрешение передать refresh.
- **§3.5/M3:** refresh Claude пока не доказан. Для первого прохода достаточно свежего токена
  с запасом timeout + 10 минут перед каждой попыткой, включая шаги после human gates и checker.
  Недостаточный или неизвестный срок — отказ до claim либо подтверждённый штатный refresh
  вне boundary под lease. Естественного истечения токена для первого цикла не ждать.

M2 обязателен для каждого pinned CLI; `login status` его не заменяет. Проба вне AppContainer
доказывает только auth-совместимость; boundary подтверждается native witness и продуктовым запуском.
Остальные ограничения TASK сохраняются. Это решение дизайна, не приёмка I1, CI или живого цикла.

### 8.1 Уточнение по фактическому M1, 23.10.2026

В §3.4 Codex добавить допустимый верхний ключ `auth_mode`. Если он есть, допустима только
строка `"chatgpt"`; отсутствие сохраняет прежнюю схему. Иные режимы, null и другие типы отказаны.
При copy-in сохранить поле без изменений. Запрет API-ключа и прочих неизвестных полей сохраняется.
Основание, узкая регрессия и порядок M2: [решение M1](H5-SUB-R5-M1-DECISION-REPORT.md).
Специально ждать истечения `id_token` для первого цикла не требуется; срок access token
не доказывает работоспособность CLI до этой даты. C1–C4 остаются в силе.

### 8.2 Модель checker после M2a, 23.10.2026

Default Codex 0.112.0 выбрал `gpt-5.3-codex` и получил отказ сервера для ChatGPT-аккаунта.
Для единственного дополнительного M2b явно выбрать `gpt-6.1-sol`. После успешной задачи
с этой моделью закрепить тот же ID в роли checker; до M2b совместимость pinned CLI неизвестна.
Условия и предел повтора: [решение M2](H5-SUB-R5-M2-MODEL-REPORT.md). C1–C4 не меняются.

### 8.3 После отказа M2b, 23.10.2026

M2b также отказал; §8.2 не дал рабочего model pin. Новых inference Codex пока не назначено.
Порядок продолжения — C (одна metadata-сессия), параллельно подготовка A (обновление CLI),
и B как промежуточный цикл с отдельным checker Claude после проверки продуктового пути.
Условия B и его бюджет — в TASK; он не заменяет обязательный Claude → Codex.
Задание C/A: [H5-CODEX-COMPAT-TASK.md](H5-CODEX-COMPAT-TASK.md). C1–C4 сохраняются.
