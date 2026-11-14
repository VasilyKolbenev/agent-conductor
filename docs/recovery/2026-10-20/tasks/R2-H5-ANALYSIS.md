# R2 / H5: какие объекты login-home может записывать попытка внутри execution boundary

- Исполнитель: Claude Code / Opus 5.5. Тип работы: анализ и подготовка решения. Код продукта не менялся.
- База: ветка `feature/v1-desk-integration`. Продуктовый код соответствует `4d0e3af`. На момент
  анализа HEAD = `6a6d693`, но поверх `4d0e3af` легли только docs-коммиты `8117fe5` и `6a6d693`.
  В рабочей копии есть чужие незакоммиченные правки R1.1: `process.py` (проверка платформы в
  `container_profile`) и `tests/test_execution_boundary.py`. Номера строк `process.py` ниже
  указаны по рабочей копии, поэтому для него в первую очередь названа функция.
- Утрачено и **не восстанавливалось**: решение «Codex ruling» по H5, текст первого раунда ревью
  login loan и файл `OPUS-H5-TO-CODEX-2026-10-16.md`, на который ссылается merge `0e060fa`.
  Всё ниже опирается на код, тесты, сообщения коммитов и первичные документы вендоров.
- Как помечены источники: `файл:строка` — текущий код; «тест» — существующий тест;
  «коммит» — сообщение коммита; «vendor-doc» — текущая документация вендора на 20.10.2026,
  **не привязанная к проверенным в продукте версиям** (Claude Code 2.1.239, Codex 0.112.0,
  Grok Build 1.0.5, Kimi Code 0.38.0); «не подтверждено» — ни кодом, ни документацией.
- Реализация любого варианта начинается **только после решения Codex и владельца** (план R2).

## 0. Коротко

1. **Сейчас subscription road внутри boundary закрыт двумя независимыми заслонками.** Простое
   включение `LOGIN_LOAN_OPEN` его не откроет. Первая заслонка в транспорте:
   `_road_covers` отказывает всякой попытке, у которой есть `_signed_in_road()`. Её production-двери
   и проверяют до claim. Вторая заслонка в runner — сам флаг. Из production она недостижима:
   `harness_attempt.AttemptFolders` не имеет поля `login`, и транспорт никогда не просит login-home.
   Пользователь на Windows видит отказ шага `sandbox route 'execution-boundary'`. Ничего не
   запускается, аренда не берётся.
2. **Аренда каталога login-home целиком принципиально не разделяет «обновить credentials» и
   «изменить исполняемую конфигурацию».** У трёх harness из четырёх (Claude, Codex, Grok) файл
   credentials лежит в корне home рядом с исполняемой конфигурацией. Обновление через временный
   файл и rename требует права создавать объекты в корне. Права NTFS нельзя ограничить по именам
   новых объектов. Возврат прав восстанавливает DACL, но не содержимое. Это уже доказано
   нативной характеристикой `b9fc4c3`.
3. **Рекомендация Opus.**
   - Для V1 оставить отказ (вариант D) и сделать его согласованным и честным.
   - Целевая схема — вариант B, «credential relay». Confined-ребёнок работает в минтованном
     per-spawn home. Существующая аренда `home` уже умеет его выдавать и возвращать. Продукт
     копирует внутрь только credential и проверенную bootstrap-конфигурацию. Обратно он забирает
     только credential-лист: после проверки схемы и неизменности идентичности аккаунта, по
     compare-and-swap и под login lease.
   - На настоящий login-home confined-процесс прав не получает вообще. Аренду `login`
     (`LOGIN_LOAN_OPEN`) не открывать.
   - B включается по одному harness и только после измерения на pinned-версии с реальным входом.

## 1. Что сейчас происходит на subscription road

### 1.1 Две заслонки, и вторая недостижима

| Где | Что проверяет | Источник |
| --- | --- | --- |
| Транспорт, до claim | `boundary_provided(mode)` = confined, платформа и `_road_covers`. `_road_covers` требует `not self._signed_in_road()`, вход runner, принимающий вызов, и install-папку версии. | `harness_attempt.py:142-166` |
| Транспорт, у самого spawn | `_hold_boundary` повторяет тот же вопрос и бросает `BoundaryUnavailable` | `harness_attempt.py:191-201` |
| Двери плана, preview и authorize | спрашивают `AdapterRegistry.execution_boundary`, то есть ответ транспорта | тест `test_execution_boundary_refusal.py:96-128` (параметр `SUBSCRIPTION`) |
| Runner | `FolderLoans.targets` отказывает ключу `login`, пока `login_loan_provided()` ≠ `True`: до чтения lease, до profile и до журнала | `process_loans.py:376-378`, `process_boundary.py:36-52`, тест `test_process_login_closed.py:41-56` |
| Что транспорт передаёт runner | `AttemptFolders(work, home, install)` **без `login`**; `home` — минтованный per-spawn home | `harness_attempt.py:52-67`, `harness_attempt.py:357-360` |

Следствия:

- Docstring `login_loan_provided` называет флаг «фактом, который спрашивает дверь»
  (`process_boundary.py:45-52`). Но ни одна дверь его не спрашивает: grep находит
  `login_loan_provided` и `login_home_named` только в `process_loans.py`. Двери отвечают по
  `_signed_in_road()`.
- Включение флага **ничего не меняет в production**: транспорт по-прежнему отказывает до claim.
- Если кто-то протянет `login` из транспорта, не согласовав `_road_covers` с флагом, runner
  откажет внутри `container_profile`. Транспорт превратит отказ в `LAUNCH_REFUSALS`, затем в
  фиксированную ошибку. Это случится **после claim**, то есть дверь и launcher разойдутся
  (`harness_attempt.py:49`, `347-364`). Критерий плана «production-отказ и фактический launcher
  не расходятся» требует один общий предикат.

### 1.2 Confined-транспорт (production, Windows)

- Provider door ограничивает каждый адаптер для платформы хоста (`test_production_door_boundary.py:74-145`).
- Для шага dispatch/review, привязанного к harness с `auth = subscription`, дверь плана
  отвечает `service_refused` с деталью `{run_id, node_id, sandbox: "execution-boundary"}`.
  Текст: «step '<node>' demands sandbox route 'execution-boundary' that this build does not provide»
  (`api_refusals.py:379-381`, `714-722`). Preview и authorize отказывают так же.
- Если транспорт вызван в обход дверей, квитанция будет `failed` с текстом «the execution
  boundary is not provided for this <tool> attempt on this build, so no task was spawned»
  (`harness_profile.py:66-74`, `harness_attempt.py:181-189`, `headless_cli.py:406`).
- Причина «subscription» в отказе **не названа**: так задумано, предложение не несёт причины
  (`harness_profile.py:66-72`). Пользователь видит отказ границы, но не узнаёт, что дело в
  способе входа.
- Ничего не запускается: ни version preflight, ни `login status`, ни login lease, ни home
  (тест `test_adapter_boundary_launch.py:222-234`).
- Quota-чтения не являются task attempt и продолжают работать вне boundary с HOME = настоящий
  login-home (`subscription_quota.py:132-154`, `kimi_code.py:371-422`). Перед ними проверяются
  только `login_forbidden` и контент (`subscription_quota.py:137`).
- На Linux и macOS boundary не предоставлен вообще (`execution_boundary.py:28`), поэтому
  отказывает всякая попытка, не только subscription.

### 1.3 Не-confined транспорт (fakes, `confine_platform=None`)

- Запускается как до R5. Все spawn идут вне boundary с HOME = настоящий login-home:
  `_login_home_refusal`, затем version, затем `login status`, затем задача
  (`headless_cli.py:523-551`, `headless_login.py:57-70`).
- После spawn `_take_back_login` удаляет объявленные scratch-имена, которые **появились**, и
  считает остальное residue (`headless_login.py:306-335`, `login_home.py:425-476`).
- Production такой транспорт не строит (`test_production_door_boundary.py:127-143`). Registry
  отвечает «не предоставлен», поэтому двери отказывают любому шагу, привязанному к нему
  (`test_execution_boundary_refusal.py:131-147`).

### 1.4 Что именно закрыто флагом

Если флаг открыт, runner выдаёт AppContainer-профилю на login-home три ACE
(`process_loans.py:93-99`, маски `process_acl.py:34-35`, `process_loans.py:62-66`):

- На саму папку `0x1201BF`: чтение, создание файлов и подпапок, запись атрибутов, обход.
  Без DELETE и DELETE_CHILD.
- На вложенные папки `CIIO 0x1201BF`, то же самое на любой глубине.
- На вложенные файлы `OIIO 0x13019F` на любой глубине: чтение, запись, append, DELETE, без EXECUTE.

Отсюда **любое новое имя на любой глубине** можно создать, а **любой существующий файл**,
у которого не отрезано наследование, можно переписать на месте, заменить rename-ом поверх или
удалить и затем переместить. Не дают права только `WRITE_DAC`, удаление и перемещение самих
папок, а также объекты с защищённым DACL. Для Grok это `hooks` и `hooks-paths`: их обязаны
предварительно защитить (`process_loans.py:455-481`).

Нативная характеристика `b9fc4c3` (`tests/test_process_login_config_native.py:78-114`)
показывает:

- ребёнок создаёт **каждое** имя из `login_forbidden` четырёх профилей;
- переписывает `config.toml` и `.claude.json` и подкладывает объект в каталог `skills` оператора;
- **всё это остаётся после возврата прав**.

Защищённый объект не трогается. Коммит `214a58c` формулирует причину закрытия так: продукт
снова запускает вендора в этой папке вне boundary («a status read, a quota read, the person's
own sign-in»).

### 1.5 Существующая семантика login lease (важна для всех вариантов)

- Lease берётся на каждую `_owned_attempt` subscription road, включая preflight
  (`login_lifetime.py:43-50`, `process.py: ProcessRunner.login_write_guard`).
- Lease исключительна между процессами и проектами: anchor держится эксклюзивно, а box
  `.conduct-login-<id>` лежит рядом с home (`ownership_login.py:52-59`, `87-98`, `135-165`).
  Две попытки на одном login-home **никогда не пересекаются**. Вторая получает
  `login_owner_busy` или `login_recovery_required`.
- **Любое исключение внутри блока** помечает lease как uncertain. Тогда `close()` не переименует
  `active.json`, и дальше нужен `conduct ownership recover-login`, а он требует доказанного
  перезапуска ОС (`ownership_login.py:241-259`, `217-233`, `414-429`).
- Если проект не активирован (нет scope), lease не берётся вовсе
  (`process_ownership_values.py:64-79`). Аренда `login` в этом случае отказывает сама
  (`process_loans.py:333-351`). Любая будущая relay-схема тоже обязана требовать стоящую lease.

### 1.6 Тесты в этой сессии

Команда (окружение `December-Command-Environment.ps1`):

```text
python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-o2h ^
  tests/test_process_loans_scope.py tests/test_process_loans_native.py tests/test_process_loans_recovery.py ^
  tests/test_process_loans_overlap.py tests/test_process_loans_mutex.py tests/test_process_loans.py ^
  tests/test_process_login_closed.py tests/test_process_login_grant.py tests/test_process_login_hooks.py ^
  tests/test_process_login_overlap.py tests/test_process_login_refusals.py tests/test_process_login_return_order.py ^
  tests/test_process_login_native.py tests/test_process_login_native_overlap.py tests/test_process_login_config_native.py ^
  tests/test_login_leased_home.py tests/test_production_door_boundary.py tests/test_execution_boundary_refusal.py ^
  tests/test_adapter_boundary_roads.py tests/test_adapter_boundary_launch.py
```

Результат: **348 passed, 15 failed, 10 errors**, 69 с.

- Все падения находятся в четырёх **нативных** файлах: `test_process_loans_native` (3),
  `test_process_login_native` (8), `test_process_login_config_native` (4) и
  `test_process_login_native_overlap` (10 errors в setup).
- Повторный прогон этих четырёх файлов (`--basetemp ...\pt-o2i`, `--tb=line`) показал причины:
  - `UnicodeDecodeError` на байте `0x8F` в позиции 9 вывода ребёнка. Это `П` из `C:\Users\Пользователь`
    в кодировке cp866: PowerShell-ребёнок внутри AppContainer печатает ошибку с путём профиля;
  - `login_recovery_required: shared resource lease is uncertain` в setup overlap — следствие той же
    ошибки ребёнка, см. 1.5;
  - несовпадение `outcome` ребёнка.
- Тот же класс сбоев отчёт R1.1 зафиксировал на чистом HEAD (`tasks/R1.1-REPORT.md:72-73`).
  Значит, это окружение этой машины, а не продукт. Механизм не исследовался.
- **Вывод:** нативная характеристика `b9fc4c3` и нативные свидетели аренды в этой сессии
  **не переподтверждены**. Опираюсь на сообщения коммитов и тексты тестов. Все не-нативные тесты
  аренды, отказа и дверей прошли.

## 2. Матрица по harness V1

Каталог V1: Claude Code, Codex, Kimi Code, Grok Build через subscription и DSH через API key
(`docs/first-run-v1.en.md:122-128`, `provider.py:97-98`).

### 2.1 Объекты login-home

| Harness, HOME-переменная | Credentials: читать и обновлять во время задачи | Прочее, что вендор пишет в home за задачу | Исполняемая и меняющая поведение конфигурация в home | Защита продукта сейчас | Кто читает home позже вне boundary |
| --- | --- | --- | --- | --- | --- |
| **Claude Code**, `CLAUDE_CONFIG_DIR` | `.credentials.json`. Объявлен, но не измерен (`claude_code.py:318-323`). Vendor-doc: на Windows credentials лежат в `.credentials.json`, а `CLAUDE_CONFIG_DIR` переносит туда этот файл [A1]. Механизм записи при refresh (на месте или rename) **не подтверждён**. `.claude.json` хранит состояние и «sign-in session» [A2]; нужен ли он для работы — **не подтверждено**. | scratch `sessions`, `.last-cleanup`, `session-env`, `shell-snapshots`, `plans`, `projects`, `file-history` (`claude_code.py:312-313`, измерено); expected `.claude.json`, `backups` (`:317`) | `settings.json` (hooks, `apiKeyHelper`, `statusLine`, env), `CLAUDE.md`, `rules/`, `skills/`, `commands/`, `agents/`, `output-styles/`, `workflows/`, `plugins/` [A3]. **`.claude.json` содержит личные MCP-серверы** [A2][A3], то есть исполняемую конфигурацию в том же файле, что и состояние входа. Изменения hooks и `apiKeyHelper` применяются горячо [A2]. | `login_forbidden` = `settings.json`, `CLAUDE.md` (по имени, `claude_code.py:338-342`). Во всех spawn продукта на subscription стоит `--safe-mode`: подавление hooks, MCP и memory измерено (`claude_code.py:259-279`, `538-546`, `claude_quota.py:208-213`). Подавляет ли `--safe-mode` `apiKeyHelper` — **не подтверждено**. | `auth status --json` (preflight), quota `-p --input-format stream-json` (control RPC), собственные `claude auth login` и `claude` человека |
| **Codex CLI**, `CODEX_HOME` | `auth.json`. Объявлен; синтетические файлы измерены на 0.112.0 (`codex_cli.py:356-371`). Vendor-doc: при file-хранилище credentials лежат в `auth.json` под `CODEX_HOME`; Codex обновляет токены во время использования и пишет новые токены и `last_refresh` обратно в `auth.json`; токены может ротировать другой процесс [B1][B2]. Значение `cli_auth_credentials_store` по умолчанию в документации не указано [B1]. При keyring файла нет — **не подтверждено** для 0.112.0 на Windows. | scratch `tmp`; expected `skills` (кэш), `version.json` (`codex_cli.py:349-359`) | `config.toml`: `notify`, `mcp_servers.*.command`, `hooks`, `model_providers.*.auth.command`, `shell_environment_policy`, `profiles` (`$CODEX_HOME/<name>.config.toml`), `projects.*.trust_level` [B3]; `AGENTS.md` и `AGENTS.override.md` в `CODEX_HOME` [B4] | `config.toml` проверяется только по ключам `projects`, `model_provider` на любой глубине (`codex_cli.py:378-388`, `562-573`, `login_home.py:103-149`). **`notify`, `mcp_servers`, `hooks`, `AGENTS.md` сейчас не отклоняются.** Флага, аналогичного `--safe-mode`, нет. | `login status` (preflight), quota `app-server` (`codex_cli.py:797-800`, `refreshToken:false`), собственные `codex login` и `codex` человека. Исполняет ли `app-server` при `initialize` hooks или MCP — **не подтверждено**. |
| **Grok Build**, `GROK_HOME` | `auth.json` (`grok_build.py:279`). Схема `AuthStore` взята из исходников вендора (`grok_build.py:534-544`). В ней поля `key`, `refresh_token`, а также **`oidc_issuer`, `oidc_client_id`** — адрес, куда уходит refresh. Vendor-doc: credentials в `auth.json`, токены обновляются в фоне [C1]. Способ записи — **не подтверждено**. | scratch `logs`, `sessions`, `active_sessions.*`, `.config-init.lock`, `managed_config.lock`; expected `config.toml`, `.metadata_version`, `agent_id`, `docs`, `README.md` (`grok_build.py:280-282`) | `hooks/`, `hooks-paths` [C2][C3], `plugins/`, `skills/`, `mcp.json`, `lsp.json`, `mcp_credentials.json`; в `config.toml` есть `[mcp_servers] command` [C4]. `GROK_AUTH_PROVIDER_COMMAND` задаётся только окружением [C1]. | `login_forbidden` из 6 имён (`grok_build.py:283`). `config.toml` допускается только в трёх точных формах (`:507-511`, `:338-345`). Запрещены переопределения окружения (`:515-516`). В аренде есть проверка защищённых `hooks` и `hooks-paths` (`process_loans.py:67-70`). | ACP `agent stdio` (preflight статуса и quota), `grok login` и `grok` человека |
| **Kimi Code**, `KIMI_CODE_HOME` | `credentials/<key>.json` во вложенном каталоге (`kimi_code.py:237-243`, `326-368`). Vendor-doc: `credentials/` имеет права 0700, файлы 0600; **запись идёт атомарно: temp-файл, fsync, rename** [D2]; есть `credentials/mcp/` с OAuth-ключами MCP [D2]. | scratch `logs`, `sessions`, `server`, `cache`, `data`, `device_id`, `migrations-effort.json`, `workspaces.json`; expected `config.toml`, `credentials`, `server.token`, `region` (`kimi_code.py:159-160`) | `mcp.json`, `skills/`, `plugins/` (`installed.json`, `managed/<id>/`), `AGENTS.md` [D2]. **`bin/rg`, `bin/fd` — кэшированные исполняемые файлы (`.exe` на Windows)** [D2]. `tui.toml` (`[upgrade].auto_install`), `updates/` [D2]. Раскладка vendor-doc новее 0.38.0: имена `cache`, `data`, `server` из профиля в ней отсутствуют. | `login_forbidden` = `hooks`, `plugins`, `skills`, `mcp.json`, `agents` (`kimi_code.py:161`). `config.toml` допускается только как managed-профиль (`:227-235`, `:326-368`). **`AGENTS.md`, `bin/`, `tui.toml` не отклоняются.** | ACP `acp` (статус), quota `kimi web` на loopback (`kimi_code.py:415`), `kimi login` и `kimi` человека |
| **DSH** (DeepSeek Harness) | Login-home нет. Только API key через окружение. Минтованный home на каждый spawn (`dsh_harness.py:114-126`, `133-146`). | — | — | H5 не затрагивает | — |

Сноски vendor-doc (текущие страницы, не pinned):

- [A1] https://code.claude.com/docs/en/authentication, раздел «Credential management». Там же
  описан `CLAUDE_CODE_OAUTH_TOKEN`, который `--bare` не читает.
- [A2] https://code.claude.com/docs/en/settings: «~/.claude.json … holds your sign-in session,
  MCP server configurations…».
- [A3] https://code.claude.com/docs/en/claude-directory: таблица файлов, `.credentials.json`
  в списке «state files to keep».
- [B1] https://learn.chatgpt.com/docs/auth: перенаправление с developers.openai.com.
- [B2] https://learn.chatgpt.com/docs/auth/ci-cd-auth: перенаправление с
  developers.openai.com/codex/auth/ci-cd-auth.
- [B3] https://learn.chatgpt.com/docs/config-file/config-reference. Прочитаны первые 100 000
  символов из 156 747.
- [B4] https://developers.openai.com/codex/guides/agents-md. Факт взят из выдачи поиска по
  официальной странице, страница целиком не загружалась.
- [C1] https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/02-authentication.md.
  Ветка `main`, а не `PINNED_COMMIT`.
- [C2] https://docs.x.ai/build/features/hooks.
- [C3] https://docs.x.ai/build/features/skills-plugins-marketplaces. [C2] и [C3] взяты из
  выдачи поиска.
- [C4] https://docs.x.ai/build/settings.
- [D1] https://moonshotai.github.io/kimi-code/en/configuration/env-vars.html.
- [D2] https://moonshotai.github.io/kimi-code/zh/configuration/data-locations.html.

Общий вывод по матрице:

- Credential-лист лежит **в корне** home у Claude, Codex и Grok, а у Kimi — в отдельном каталоге
  `credentials/`.
- Рядом с ним всегда лежит исполняемая конфигурация. У Claude она находится даже **в том же
  классе файлов**: `.claude.json` хранит одновременно состояние и MCP-серверы.
- Значит, право «обновлять credentials» на каталоге неизбежно даёт право создавать и подменять
  исполняемую конфигурацию.
- Сами credentials тоже могут нести поле, которое меняет последующее исполнение: у Grok это
  `oidc_issuer`, адрес refresh. Поэтому обратная запись credentials тоже требует проверки схемы.

### 2.2 Сценарии

Строки — что будет с **механизмом H5, если открыть флаг (вариант C/«как построено»)**, и с
**рекомендуемым relay (вариант B)**.

| Сценарий | Аренда login-home как построено (флаг открыт) | Relay через минтованный home (B) |
| --- | --- | --- |
| Штатный конец | Свои ACE снимаются по DACL, каким он стал. Счётчик lease погашается как proven (`process_loans.py:596-646`, `437-453`). **Содержимое не восстанавливается:** подложенное остаётся (`b9fc4c3`). | Real home в confined-фазе не меняется: прав на него нет. Обратно копируется только проверенный credential-лист, по CAS и атомарно. Shadow home удаляется `_discard`. |
| Ошибка или прерывание внутри попытки | Возврат в `finally` блока `container`. При неудаче lease uncertain и `login_recovery_required` (`process_profile.py:292-309`, `ownership_login.py:250-255`). | Shadow не копируется обратно или копируется только после проверки. Lease uncertain, как сейчас. Refresh, сделанный ребёнком и ротировавший токен, может пропасть. Тогда нужен повторный вход; у Codex это задокументированный «reseed» [B2]. |
| Падение сервера или перезапуск ОС | Запись `loan-*.json` возвращает права при recovery **без** доказательства перезапуска (`process_profile.py:203-238`, тест `test_process_login_grant.py:200`). Lease требует перезапуска и `recover-login` (`ownership_login.py:414-429`). Подложенное содержимое остаётся. | Shadow остаётся под home root. Следующий dispatch вычищает его через `sweep_homes`, а если не может — отказывает. В real home нет ничего от ребёнка. Lease восстанавливается тем же `recover-login`. |
| Параллельная попытка на том же login-home | Исключено: lease эксклюзивна между процессами (`ownership_login.py:87-98`, `141-145`). | То же. Copy-in и copy-out сериализованы lease. Параллельная **личная** сессия человека lease не видит: документация просит этого не делать (`docs/first-run-v1.en.md:156`). Для B её ловит CAS при copy-out. |
| Параллельные попытки разных harness | Свидетели overlap: каждый возврат оставляет чужие ACE (`test_process_login_overlap.py`, `test_process_login_native_overlap.py`, коммит `45238b8`). Нативно здесь не переподтверждено, см. 1.6. | Не пересекаются: каждый shadow — свой минтованный home своего harness. |
| Подмена пути login-home | Идентичность папки сверяется с той, что записала lease, а затем ещё раз на удерживаемом handle. Junction или symlink самой папки отклоняются (`process_loans.py:173-192`, `342-360`, `483-500`, тест `test_process_login_refusals.py:171-206`). | Copy-in и copy-out читают и пишут только по объявленным именам. Каждое имя проверяется: обычный файл, не портал, `nlink==1`. Real home определяется той же идентичностью lease. Нужны новые тесты. |
| Junction, symlink или hardlink, созданные ребёнком **внутри** home | Ребёнок может создавать папки и файлы. Ограничивает ли Windows создание junction или hardlink из AppContainer — **не измерено в проекте**. `login_home.measure` останавливается на портале в scratch-каталогах и даёт residue (`login_home.py:272-310`). Портал на неизвестном имени верхнего уровня отмечается как unexpected, **но остаётся на диске** и затем может быть пройден вендором вне boundary. Hardlink в home `measure` не проверяет. | Портал и hardlink возможны только в shadow. Copy-out их отвергает. Home удаляет дверь workspace: home, где есть имя неустановленного вида, она оставляет на месте и не удаляет «насквозь», а следующий sweep тогда отказывает (`harness_attempt.py:228-237`, `271-284`). Как именно удаляются hardlink, не проверял. В real home ничего не попадает. |
| Подмена содержимого credential-файла | Ребёнок переписывает credentials как угодно, в том числе `oidc_issuer` у Grok. Позже, вне boundary, refresh может уйти на чужой адрес. | Copy-out проверяет схему: неизменяемые поля (аккаунт, issuer, client_id, тип входа) должны совпасть с copy-in, а API key не должен появиться (`provider.py:90-91`). Иначе файл не копируется, и попытка получает residue. |

## 3. Варианты решения

### A. Аренда только конкретных файлов credentials (ACE на файл, без прав на каталог)

- Плюсы: минимальная поверхность. Механизм ACL и журнал уже есть, нужен ключ уровня «файл».
- Минусы:
  - работает, только если вендор пишет **на месте**. Kimi по документации пишет temp-файлом
    и rename [D2]: для этого нужны `FILE_ADD_FILE` в каталоге и DELETE на целевом файле;
    способ записи у остальных не подтверждён;
  - вендор пишет scratch (`sessions`, `tmp`, `logs`) в тот же home. Если корень закрыт на
    запись, вендор, скорее всего, упадёт (не подтверждено). Значит, понадобится второй home
    для scratch, а это уже вариант B.
- Остаточный риск: подмена содержимого credentials (поле issuer у Grok).
- Объём: малый в коде, но нужны измерения записи у каждого вендора с реальным входом.
- Вывод: **сам по себе нежизнеспособен**.

### B. Credential relay через минтованный per-spawn home (рекомендуемая цель)

- Суть:
  - для confined task attempt на subscription road HOME = минтованный home, как на API-key
    road. Он уже арендуется как `home` с `modify` и возвращается
    (`harness_attempt.py:357-360`, `process_loans.py:505-512`);
  - до spawn, под lease, сервер копирует из real home **объявленный набор**: credential-листы
    и проверенную bootstrap-конфигурацию (Codex `config.toml` после `config_grants`, Grok —
    `plain_config`, Kimi — `_managed_profile`). Каждое имя проверяется: обычный файл, не
    портал, ограничение размера;
  - после spawn, до `_discard`, под той же lease, сервер забирает **только credential-листы**,
    сверяет схему и неизменные поля, проверяет CAS (real-файл не изменился после copy-in) и
    атомарно заменяет файл в real home;
  - всё остальное из shadow удаляется вместе с home.
- Плюсы:
  - запрещённая запись в real home **отклоняется ОС**: у AppContainer нет ACE на real home;
  - не нужен новый вид ACL и новый ключ журнала, аренду `login` можно не открывать;
  - для Codex сам вендор описывает такую схему «скопировать, затем записать обратно» [B2];
  - вендор ничего не оставляет в real home, поэтому residue по login-home для задачи исчезает.
- Минусы:
  - для каждого harness нужно измерить на pinned-версии с реальным входом: работает ли CLI в
    свежем home только с credential и bootstrap, какие поля меняются при refresh, нужен ли
    Claude `.claude.json`;
  - refresh, ротировавший токен, теряется при сбое между выходом ребёнка и copy-out;
  - копия credential на время попытки лежит в проекте (`<home root>/<minted>`). Если проект
    синхронизируется (OneDrive), это экспозиция; альтернатива — продуктовая relay-папка вне
    проекта, см. вопрос 3;
  - Codex с keyring-хранилищем не поддерживается: нужен file store (вопрос 4).
- Остаточный риск:
  - (1) ребёнок видит credential и имеет сеть (`entry_call` даёт `internet_client=True`,
    `boundary_entry.py:24`) — как и с API key в окружении. Это риск утечки, не устойчивости;
  - (2) валидация схемы должна быть строгой, иначе через credential можно перенаправить refresh;
  - (3) потеря ротированного токена ведёт к повторному входу.
- Объём:
  - общий механизм: около 3–5 дней Sonnet плюс ревью;
  - каждый harness: около 1 дня кода плюс измерение у владельца;
  - нативный свидетель нужен на хосте, где нативные тесты зелёные (CI Windows; здесь они
    падают, см. 1.6).
- Совместимость:
  - схема `loan-*.json` не меняется; recovery старых `login`-записей сохраняется
    (`test_process_login_closed.py:65-75`);
  - тесты с параметром `SUBSCRIPTION` в `test_execution_boundary_refusal.py` и тест
    `test_adapter_boundary_launch.py:222-234` нужно разделить на «harness без relay-спецификации»
    (по-прежнему отказ) и «с relay-спецификацией»;
  - тесты H5 (`test_process_login_*`) остаются: они проверяют закрытый механизм через `login_gate`.

### C. Открыть аренду login-home, сузив её «защитой по именам» и проверкой после попытки

- Суть: заранее создать защищённые заглушки для опасных имён (как сейчас для `hooks` у Grok),
  после попытки помещать в карантин новые и изменённые объекты, сверять контент
  `.claude.json` и `config.toml` по ключам.
- Плюсы: механизм уже построен и закоммичен (`45238b8`, `93911b8`, `214a58c`).
- Минусы:
  - критерий «запрещённая запись **реально отклоняется**» не выполняется: запись происходит и
    потом откатывается;
  - список опасных имён открыт и растёт с версиями (у Kimi `bin/`, у Codex `AGENTS.md`,
    `profiles/*.config.toml`, `hooks`);
  - у Claude MCP-серверы лежат в `.claude.json`, который вендор переписывает сам. Нужен
    дифф по ключам с пониманием формата вендора;
  - после сбоя нужно восстанавливать **содержимое**, а значит, держать долговременный снимок
    home, что фактически вариант B наоборот;
  - во время попытки личная сессия человека на том же home может исполнить подложенное.
- Остаточный риск высокий, объём 5–10 дней, решение хрупкое. **Не рекомендую.**

### D. В V1 оставить отказ subscription road внутри boundary, с честным и согласованным сообщением

- Суть: поведение сохраняется. Кроме этого:
  - (1) один предикат «subscription road покрыт boundary» использовать и в `_road_covers`, и в
    runner. Docstring флага исправить: двери его не спрашивают. Либо убрать двусмысленность
    одним фактом;
  - (2) обновить `docs/first-run-v1*.md`: в V1 confined-исполнение идёт только через API-key
    road, а subscription нужен только для quota-чтений;
  - (3) по решению — уточнить текст отказа, см. вопрос 6.
- Плюсы:
  - малый объём, полдня–день;
  - нулевой новый риск;
  - текущие тесты почти не меняются.
- Минусы:
  - критерий «разрешённое обновление работает» не выполняется, обновления просто нет;
  - V1-задачи Claude, Codex, Grok и Kimi в production возможны только через API key.
    Это продуктовое решение владельца, вопрос 1.
- Остаточный риск: прежний. Узкие `login_forbidden` по-прежнему касаются личных сессий человека
  и quota-чтений, см. 2.1 и вопрос 8.

### E (только Claude). Токен в окружении `CLAUDE_CODE_OAUTH_TOKEN`

- Суть: `claude setup-token` выпускает токен на год; он работает только для запросов к модели;
  `--bare` его не читает [A1]. Confined-ребёнок получает минтованный home и токен через
  allowlist окружения. Login-home в задаче не участвует, refresh нет.
- Плюсы: не нужны ни relay, ни запись. Работает уже существующая API-key-подобная дорога.
- Минусы:
  - это новый режим входа в двери конфигурации;
  - метод нужно измерить в `auth status` и проверить, читает ли токен `--safe-mode`
    (не подтверждено);
  - годовой токен в окружении.
- Объём: 1–2 дня плюс измерение. Для Codex документированного аналога для ChatGPT-входа не
  найдено. `CODEX_API_KEY` означает API-биллинг и запрещён (`provider.py:90-91`).

## 4. Рекомендация Opus

1. **Не открывать `LOGIN_LOAN_OPEN` и не строить решение на аренде всего login-home.** Причины:
   - 2.1: credential лежит рядом с исполняемой конфигурацией, а у Claude — в том же файле;
   - 1.4: права NTFS на каталог не ограничиваются по именам, возврат не откатывает содержимое;
   - 2.2: подложенное переживает возврат прав и recovery.
   Предлагаемая формулировка решения для Codex: «попытка не получает прав на запись ни на
   один объект настоящего login-home».
2. **V1 — вариант D сейчас.** Нужны три вещи: один предикат для двери и launcher, честная
   документация и, по решению, уточнённый текст отказа. Это безопасно, мало по объёму и не
   блокирует R3–R5.
3. **Целевая схема — вариант B (credential relay)**, по одному harness. Порядок предлагаю такой:
   - Codex: у вендора есть документированная схема записи обратно в `auth.json` [B2];
   - Grok: схема `AuthStore` уже есть в коде;
   - Kimi: credential в отдельном каталоге, запись атомарная;
   - Claude: больше всего неизвестного; возможно, проще вариант E.
   Harness без измеренной relay-спецификации остаётся в режиме D. Если владелец решит, что
   V1 без subscription неприемлем, B для одного–двух harness входит в V1, а D остаётся для
   остальных.

Как B выполняет критерии плана:

| Критерий | Как выполняется в B |
| --- | --- |
| Запрещённая запись действительно отклоняется | В confined-фазе у AppContainer **нет ACE** на real login-home (выдаются только `work`, `home`, `install`). ОС отклоняет любую запись туда. Copy-out не принимает ничего, кроме объявленного credential-листа с проверенной схемой. |
| Разрешённое обновление работает | Refresh вендора пишет в shadow. Сервер переносит новый credential в real home атомарно, по CAS, под lease. Свидетель: ребёнок-фейк «обновляет» токен, после попытки real home содержит новое значение, и больше ничего не изменилось. |
| Отказ до побочных эффектов | Статический факт «у harness есть relay-спецификация» участвует в `boundary_provided`, то есть его видят двери до claim. Динамическая готовность (credential присутствует и обычный, конфигурация проходит проверку, file store) проверяется в `_preflight` сразу после `_login_home_refusal` и **до** version spawn (`headless_cli.py:532`). |
| Выдача и возврат прав корректны после ошибок и прерываний | Новых видов ACL нет: используется проверенная аренда `home` с журналом и recovery. Copy-out — отдельный шаг под lease; при ошибке lease уходит в uncertain по существующей семантике (1.5). Real home при сбое не меняется. |
| Production-отказ и launcher не расходятся | Один предикат («road покрыт», включая relay-спецификацию) используется в `_road_covers` и в `_hold_boundary`. Runner по-прежнему отказывает ключу `login`, а транспорт его никогда не передаёт; это закрепляет структурный тест. |

## 5. Набросок задания для Sonnet

> **ВНИМАНИЕ: реализация начинается только после решения Codex и владельца по вопросам раздела 6.**
> Ниже две независимые задачи; S-H5-D можно выдать сразу после решения, S-H5-B — после
> измерений.

### S-H5-D: согласованный отказ subscription road в V1

- Файлы:
  - `src/conductor/command/adapters/harness_attempt.py` (`_road_covers`, docstring
    `boundary_provided`);
  - `src/conductor/command/adapters/process_boundary.py` (только docstring и комментарий
    `LOGIN_LOAN_OPEN` и `login_loan_provided`, значение не трогать);
  - `docs/first-run-v1.md` и `docs/first-run-v1.en.md`;
  - тесты.
- Шаги:
  1. Вынести предикат `subscription_road_covered(transport) -> bool` (в V1 всегда `False`) и
     вызывать его из `_road_covers` вместо прямого `not self._signed_in_road()`.
  2. Исправить docstring `login_loan_provided`: это факт runner для ключа `login`, транспорт
     этот ключ не передаёт.
  3. Добавить структурный тест: `harness_attempt.AttemptFolders` не имеет поля `login`, а
     `_run_confined` его не передаёт.
  4. Добавить тест, что при `monkeypatch LOGIN_LOAN_OPEN=True` ответ `boundary_provided` для
     subscription-транспорта остаётся `False` и `runner.entries == []`.
  5. В документации описать, что видит пользователь и какой road нужен для confined-исполнения.
  6. Если решён вопрос 6 — изменить текст отказа.
- Проверки: `test_adapter_boundary_launch.py`, `test_execution_boundary_refusal.py`,
  `test_production_door_boundary.py`, `test_process_login_closed.py`, `test_adapter_boundary_roads.py`.

### S-H5-B: credential relay, общий механизм и первый harness за спецификацией

- Предусловие: измерения владельца на pinned-версии, вопрос 4.
- Файлы:
  - новый `src/conductor/command/adapters/login_relay.py`: `RelaySpec`, `copy_in`, `copy_out`,
    валидаторы; лимит 800 строк;
  - `harness_profile.py`: поле `login_relay: RelaySpec | None = None`;
  - `harness_attempt.py`: `_road_covers`, `_owned_attempt`, `_home_value` для confined
    task attempt;
  - `headless_login.py`: `_login_secrets` читает и shadow, и real home;
  - `headless_cli.py`: проверка готовности relay в `_preflight` до version spawn;
  - модуль первого harness, например `codex_cli.py`: спецификация и валидатор `auth.json`;
  - тесты.
- Шаги:
  1. `RelaySpec`:
     - `copy_in` — имена или пути из одной вложенности (для Kimi `credentials/<key>.json`)
       плюс функции проверки конфигурации; переиспользовать `config_grants`, `plain_config`,
       `_managed_profile`;
     - `copy_out` — только credential-листы;
     - `validate(before, after)` — неизменяемые поля, допустимые изменения, отсутствие API key,
       ограничение размера (`login_home.CREDENTIAL_LIMIT`).
  2. `copy_in(real, shadow, spec)` выполняется под стоящей lease; без lease — отказ, как в
     `process_loans.py:333-351`. Проверяет каждый лист: обычный файл, `nlink==1`, не портал
     (`login_home._is_portal`). Возвращает дайджесты.
  3. `copy_out(shadow, real, spec, digests)` выполняется в `finally` попытки **до** `_discard`.
     Проверяет обычность и не-портальность листа в shadow, затем валидирует. CAS: дайджест
     real-файла равен снятому при copy-in. Затем temp-файл в real home и `os.replace`. Любой
     отказ — `_login_residue += 1` без исключения, чтобы не терять исход попытки; подробности
     идут в лог, не в квитанцию.
  4. `_road_covers`: для subscription road нужна `profile.login_relay is not None`; тот же
     ответ в `_hold_boundary`.
  5. Для confined task attempt на subscription road HOME = минтованный home. Preflight и
     quota остаются вне boundary на real home, как сейчас.
  6. Ключ `login` в runner не трогать; `LOGIN_LOAN_OPEN` остаётся `False`.
- Тесты на фейках:
  - copy-in берёт ровно объявленный набор;
  - подложенные ребёнком имена (`settings.json`, `hooks/`, `AGENTS.md`, `bin/rg.exe`, изменённый
    `config.toml`) не появляются в real home;
  - credential с изменённым аккаунтом, issuer или с API key не копируется обратно;
  - при конфликте CAS real home не меняется;
  - портал или hardlink в shadow отклоняется;
  - исключение между spawn и copy-out оставляет real home нетронутым, а lease — uncertain;
  - `boundary_provided` равен `True` тогда и только тогда, когда есть спецификация;
  - runner никогда не получает `login`;
  - параметр `SUBSCRIPTION` в `test_execution_boundary_refusal.py` и тест
    `test_adapter_boundary_launch.py:222-234` разделить на варианты с relay и без.
- Нативный свидетель на Windows-хосте, где нативные тесты зелёные: AppContainer-ребёнок с
  арендой shadow не может открыть на запись ни один объект real login-home; ACL real home
  совпадает до и после, `icacls` не называет профиль.
- Не делать:
  - не включать флаг;
  - не расширять `AttemptFolders` транспорта полем `login`;
  - не копировать в shadow ничего из списка «исполняемой конфигурации» матрицы 2.1;
  - не печатать значения credentials.

## 6. Открытые вопросы для Codex и владельца

1. **Владельцу.** Нужен ли subscription road для confined-исполнения в V1 (owner acceptance и
   полезный результат)? Или V1 принимается с API-key road и вариантом D, а B переносится в V1.x?
   Это определяет, войдёт ли B в V1.
2. **Codex.** Утвердить как решение по H5, что попытка не получает прав на запись ни на один
   объект настоящего login-home. Тогда `LOGIN_LOAN_OPEN` остаётся `False` навсегда. Удалять ли
   построенную аренду `login` позже, отдельной задачей, или держать её закрытой?
3. **Codex.** Где лежит shadow: в минтованном home проекта (просто, но экспозиция при
   синхронизации проекта) или в продуктовой relay-папке вне проекта (безопаснее, нужна новая
   свежая папка в духе `process_acl`)?
4. **Владельцу.** Разрешение и объём измерений на реальных аккаунтах для pinned-версий
   (по каждому harness):
   - (а) работает ли CLI в свежем home только с credential и bootstrap-конфигурацией;
   - (б) как пишется refresh: на месте или temp-файлом и rename, какие поля меняются;
   - (в) Claude: нужен ли `.claude.json`;
   - (г) Codex: значение `cli_auth_credentials_store` по умолчанию на Windows в 0.112.0 —
     если keyring, требовать `file`?
5. **Codex.** Политика при конфликте CAS и при сбое до copy-out: отбрасывать токен попытки
   (риск повторного входа) или перезаписывать? Нужно ли в V1 спасение ротированного токена
   после падения сервера, или достаточно честного «войдите заново»?
6. **Codex.** Текст отказа. Нынешнее предложение границы утверждено и не несёт причины
   (`harness_profile.py:50-53`, `66-74`). Нужно ли отдельное предложение для subscription road
   и упоминание в Studio рядом с отказом `sandbox route`? Деталь двери закрыта:
   `{run_id, node_id, sandbox}`.
7. **Codex и владельцу.** Для Claude рассматривать ли вариант E (`CLAUDE_CODE_OAUTH_TOKEN`,
   новый режим входа) вместо relay?
8. **Codex.** Побочная находка, отдельная от H5: списки `login_forbidden` уже, чем
   документированная исполняемая конфигурация.
   - Codex: `notify`, `mcp_servers`, `hooks`, `AGENTS.md`.
   - Claude: `agents/`, `skills/`, `commands/`, `plugins/`, MCP в `.claude.json`.
   - Kimi: `AGENTS.md`, `bin/`, `tui.toml`.

   Это касается quota-чтений вне boundary (у Codex нет аналога `--safe-mode`) и личных сессий.
   Делать ли отдельную задачу, сверив списки с pinned-версиями?
9. **Codex.** Существующая семантика: любое исключение под login lease требует перезапуска ОС
   и `recover-login`. Допустима ли она для ошибок relay или нужен более мягкий путь?
10. **Codex.** Принимаем ли явно, что confined-ребёнок subscription road видит refresh token и
    имеет сеть? Это тот же класс риска, что API key в окружении, но масштаб — целый аккаунт
    подписки.
11. Если найдутся `OPUS-H5-TO-CODEX-2026-10-16.md` или текст ревью первого раунда, сверить с
    этим анализом. Новое решение записать как новое.

## 7. Что проверено и что нет

- Прочитано:
  - `process_boundary.py`, `process_loans.py`, `process_acl.py`, `process_profile.py`;
  - `harness_attempt.py`, `login_home.py`, `login_lifetime.py`, `headless_login.py`;
  - `headless_cli.py` (dispatch и preflight), `subscription_quota.py`, `claude_quota.py`;
  - адаптеры пяти harness, `provider.py`, `ownership_login.py`, `process_ownership_values.py`;
  - `execution_boundary.py`, `boundary_entry.py`, `api_refusals.py` (отказ sandbox);
  - тесты из задания и тесты `test_process_login_*`, `login_gate.py`;
  - коммиты `9892747`, `2098c8d`, `1e7f481`, `45238b8`, `93911b8`, `d1f4ce6`, `aca8f40`,
    `214a58c`, `b9fc4c3`, `0e060fa` (`git log` 9–18.10 по этим файлам).
- `docs/architecture.ru.md` раздела про execution boundary **не содержит** (grep по
  boundary, AppContainer, sandbox пуст). «H contract» (`H-to-L-execution-boundary`) есть
  только в ссылках из кода и тестов; сам документ в репозитории отсутствует.
- Тесты: см. 1.6. Не-нативные прошли. Нативные в этом окружении не проходят, как и на чистом
  HEAD по отчёту R1.1.
- Не проверено и не запускалось:
  - реальные провайдеры, вход и refresh;
  - поведение pinned-версий вендоров;
  - ограничения Windows на создание junction и hardlink из AppContainer;
  - исполняет ли `codex app-server` hooks или MCP при `initialize`;
  - подавляет ли `--safe-mode` `apiKeyHelper`;
  - нативная характеристика `b9fc4c3` на этой машине.
