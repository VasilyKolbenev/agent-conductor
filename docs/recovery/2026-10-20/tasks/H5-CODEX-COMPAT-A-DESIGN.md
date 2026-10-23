Итог: принято ревью с поправками | 69c2a7d | без запусков | решение Codex ниже | П0.

# H5-CODEX-COMPAT A: обновление Codex CLI 0.112.0 → 0.164.0 (v2)

**Решение Codex 23.10:** Р1–Р6 разобраны, переход к установке кандидата и проверкам разрешён.
[A-REVIEW-REPORT](H5-CODEX-COMPAT-A-REVIEW-REPORT.md) имеет приоритет над историческим текстом
v2 ниже: область refresh-override, preflight env, запас срока, критерий П11, порядок и один M2.
Нового общего раунда дизайна не требуется. Новый product pin пока не принят.

Opus 5.5, 23.10.2026. Задание: раздел A [H5-CODEX-COMPAT-TASK.md](H5-CODEX-COMPAT-TASK.md)
(`61a629f`), факты [C-REPORT](H5-CODEX-COMPAT-C-REPORT.md) (`b1de428`), стандарт; HEAD `6d5ad7c`.
Основа v1 — три исследования только чтением 23.10.2026 12:31–12:42 UTC: npm registry (`modified`
2026-10-23T04:58:05Z), GitHub releases и теги `rust-v*`, unpkg `?meta`. v1 прошёл две линзы
скептиков Opus (цепочка поставки и установка; контракты и матрица), 19 находок: 2 blocker, 7 major,
10 minor; v2 учитывает все, номера — в скобках (`1.4` = линза 1, находка 4). Скептики тоже только
читали (реестр, GitHub API, исходник на тегах, файлы репозитория, `icacls`); Codex не скачивался и
не запускался. **S112/S164** — `codex-rs/…` на `rust-v0.112.0`/`rust-v0.164.0` (по исходнику, не
измерение); **RN x** — release notes `rust-v0.x.0`; `файл:строка` — рабочая копия.
Зачем: по C 0.112.0 не декодирует живой каталог (`max`) и не знает `prolite`; H1 до M2 не доказана.
Ведущий перепроверил оба blocker: ACL — `icacls` 23.10 (§3); поля `TokenData` — S164
`login/src/token_data.rs` (§2 п. 13).

## 0. Решения Codex до П0

| Р | Вопрос | Рекомендация Opus | Находки |
| --- | --- | --- | --- |
| Р1 | Корень установки CLI. `Documents\Codex` даёт Modify группе `CodexSandboxUsers` и SID `S-1-5-21-2665565195-3440043910-1236113653-2211309706`; это наследуют все три установленных CLI (Claude 2.1.239, Codex 0.112.0, Grok 1.0.5) | Новый корень `$R` = `%USERPROFILE%\DecemberCommand\harnesses` с защищённым DACL (§3). 0.164.0 — сразу туда. Claude 2.1.239 перенести копированием со сверкой sha256 против записи установки **до цикла B**, Codex 0.112.0 и Grok — так же, до их первого цикла | 1.1 |
| Р2 | Кандидат и скачивание | 0.164.0; два tarball реестра: `codex-0.164.0-win32-x64.tgz` 172 854 349 Б и `codex-0.164.0.tgz` 4 902 Б с `registry.npmjs.org`. Разрешение на скачивание даёт владелец в чате | 1.4, 1.7 |
| Р3 | Неудавшийся refresh на access-only копии уходит в `auth.openai.com` (§2 п. 3) | Code-owned `CODEX_REFRESH_TOKEN_URL_OVERRIDE=http://127.0.0.1:9/oauth/token` в forced env: любая попытка кончается локально. Меняет `CODEX_FORCED_ENV` (`codex_cli.py:283`), digest гранта и запрет имени в `relay_env.py:38` | 2.3 |
| Р4 | Нотификации app-server в quota read | После П6а: если в stdout есть строки без id — `initialize.params.capabilities.optOutNotificationMethods` в `QUOTA_RPC` (меняет payload и digest) вместо расширения декодера | 2.8 |
| Р5 | Preflight-отказы адаптера | Отдельная задача после A: `_refuse_install` (`process_loans.py:229-246`) отказывает, если у кого-то, кроме SYSTEM, Administrators и владельца, есть ACE записи на install; отказ при наличии входов ProgramData/HKLM (§2 п. 10), аналог `LOGIN_FORBIDDEN` | 1.1, 1.3 |
| Р6 | П11 — вход владельца через 0.164.0 в отдельный home (human gate) | Да: только так проверяется схема `auth.json` нового входа до pin | 2.1 |

## 1. Кандидат: 0.164.0; запасной 0.163.0; нижняя граница 0.159.1

| Что | Значение | Источник |
| --- | --- | --- |
| Версия | `0.164.0`: npm `latest` и `win32-x64`; GitHub Latest → `rust-v0.164.0`, 2026-10-23T04:48:10Z, `prerelease=false` | NPM dist-tags; redirect `releases/latest` |
| Основной пакет | `@openai/codex@0.164.0`, 04:52:29Z, `sha512-TWj7UGyPRe3Pj/A3ddNAxs1te3a/W/xAd+J0LHrrFTmsSfahGMOLF/vn88D3QCIgAT3B1rm1y/Z3NYE0rx6cZQ==`, shasum `82693f5ef4b08b724dc1370f1622bc752e5d1bf4`; 3 файла, `files: ["bin/codex.js"]` | `registry.npmjs.org/@openai/codex` |
| Платформенный | `@openai/codex@0.164.0-win32-x64` (alias `@openai/codex-win32-x64` в `optionalDependencies`; отдельного пакета нет, 404), 04:55:52Z, `sha512-urWPhwh9YavuoAPIkmVYKBTtd5OtGVL4Ki0Fb28dhK/Mz6Pt4LSy+gbRrZFz5+RXrw9ubvXuXDCcd8beYcWhDg==`, shasum `02badb2d14813501bf1b94de44151670de3232cb`, 47 файлов, 483 692 160 Б | то же; unpkg `?meta` |
| Скрипты | нет ни в одном пакете: `scripts` пусто, `hasInstallScript` нет | реестр, `package.json` на unpkg (1.5) |
| GitHub-tgz | `codex-npm-win32-x64-0.164.0.tgz` 172 854 349 Б sha256 `4fbd23473a2fc223396cdd8490d3f658d368438134c12a3f1dac9d1e2041a65b`; `codex-npm-0.164.0.tgz` 4 902 Б sha256 `afb117ec0d382744583dd13154ba0ca6b0f1980f8ed6a23bffb3aaadb6226e30`. Workflow публикует в npm именно эти файлы, поэтому sha256 скачанного tgz сверяется с ассетом | GitHub API; `.github/workflows/rust-release.yml:1905-1918,1935-1947,2014` на теге (1.4); для 0.112.0 так же совпало (`r5-setup\codex-*.tgz`) |
| `bin\codex.exe` | 354 558 768 Б, sha256 `6f267830b029ee25d9339864aa867cd45de9f8fd4c5ea007d2e63c13a0c66d36` = ассет `codex-x86_64-pc-windows-msvc.exe`; ассеты code-mode-host, command-runner, sandbox-setup тоже совпадают с файлами пакета | unpkg `?meta`; ассеты релиза |
| Подпись | PE OpenAI подписаны Azure Trusted Signing, CI требует `Valid` | `.github/workflows/rust-release-windows.yml:7,440-452,481-519` (1.4) |
| Провенанс | SLSA v1 и npm publish attestation у обоих пакетов: subject sha512 = integrity; workflow `rust-release.yml@refs/tags/rust-v0.164.0`; commit `6aaac694803004a63c6f393d153c96d22521a6b9` = разыменованный тег (объект `fe3b2945…`, не подписан); run 39894017941, attempt 3; Rekor 04:50:53–04:56:05Z. По метаданным реестра, криптографически не проверено. Релиз `immutable=false` | `dist.attestations`; GitHub (1.4) |
| Запасной | `0.163.0` (2026-10-15): основной `sha512-HNd7vR9oTK6M2ikxFnvNDCdYUgAsyo9VVnd5KnEd2ON0GYI++7MiX9XNPUkhtdgGKFPsWS+CEppQ1UU63uVhUw==`; `-win32-x64` `sha512-QQGQ/q9dCJ5C5jqhgFrwycpWG3szIyFNThMiKl6hYtu6N/eM3Qd7StesgnCFAfzVED8IkE3N3oH71szzcludqw==`; `codex-npm-win32-x64-0.163.0.tgz` 167 618 721 Б sha256 `81377fd73b502a9e7208e32a4da2d468cdb3fc978e0b818c4707d846ad94eb1e`; `codex.exe` sha256 `2692c8c7bb2cf8b0aefe638741fc90236f4b824c59578ce84994f9de58200993`; главный GitHub-tgz не снят; старая фраза ключа; `0.163.1` нет (404) | NPM; GitHub (1.7) |
| Нижняя граница | 0.159.1: впервые все три свойства — план `prolite` (с 0.121.0, #17419), effort `max` (с 0.138.0 как `Custom`, `Max` с 0.143.0; #26444, #30467), `gpt-6.1-sol` во встроенном каталоге; у 0.138–0.158 его нет; ниже 0.138 `max` не разбирается | S120/S121/S137/S138 `PlanType.ts`, `openai_models.rs`; S159.0/S159.1 `models.json` |
| Почему 0.164.0 | исправления каталога #55958 (сохранение при неудачном обновлении), #54169 (перечитывание после смены аккаунта), #54946; новее клиент — меньше незнакомых значений живого каталога; цена замены та же, что у 0.159.1 | RN 160–164 |
| Риск | релизу меньше суток; линия ещё меняется: хотфикс-ветки `release-0.163.0-alpha.11.2` (22.10) и `0.164.0-alpha.11.1` (23.10 02:08Z) | NPM `time`, dist-tags (1.7) |
| Правило версии | Перед скачиванием перечитать dist-tags. `latest` ≠ 0.164.0 или 0.164.0 не прошла §4 — стоп, новые §1/§2 и решение Codex; автоматической подмены версии нет | TASK `:44-46`; стандарт §2 п. 5 (1.7) |

## 2. Что реально изменилось в наших контрактах

| # | Контракт | 0.112.0 | 0.164.0 | Влияние у нас | Источник |
| --- | --- | --- | --- | --- | --- |
| 1 | Раскладка пакета | `vendor\x86_64-pc-windows-msvc\codex\{codex,codex-command-runner,codex-windows-sandbox-setup}.exe`, `path\rg.exe` | `…\bin\codex.exe`; новые `bin\codex-code-mode-host.exe`, `codex-voice-host.exe` + 26 DLL (GStreamer/GLib, vcruntime140), `codex-package.json` (с 0.133.0); вспомогательные exe перенесены в `codex-resources\`, `rg.exe` — в `codex-path\`. Всего 6 exe + 26 DLL | путь pin, `_fakeboundary.py:44-47`, runbook; ресурсы ищутся по `codex-package.json` в родителе `bin\` — одиночный GitHub-exe не годится. `codex.exe` со статическим CRT, DLL грузит только voice-host | UNPKG 0.132/0.133/0.164; S164 `install-context/src/lib.rs:233-288`, `.cargo/config.toml`; #23637, #23596 (1.8) |
| 2 | `login status` | «Logged in using an API key - …» | решает поле `auth_mode`, ключ — только после него; фразы — П4 | `API_KEY_MARKER` (`codex_cli.py:380`) не сработает; допуск закрыт (`:379`, `:591`), но причина отказа станет неверной; docstring `:366-372, 584-586` («the key wins») неверен | S164 `cli/src/login.rs:49,464-513,593-613`, `login/src/auth/manager.rs:1835-1851`; RN 164, #55407 (2.6) |
| 3 | Обновление токена | только `last_refresh` > 8 дней | (а) любой `auth()` при `exp` ≤ now+5 мин: старт exec/app-server, фоновый воркер каталога, `account/rateLimits/read` даже при `refreshToken:false`, каждый запрос модели; (б) любой 401 → UnauthorizedRecovery → refresh независимо от `exp`. Пустой `refresh_token` не проверяется. 401/`invalid_grant`/известный код кэшируются в памяти процесса, иной ответ — Transient и повторяется при каждом `auth()`. `auth.json` пишется только после успеха; тело ответа не логируется (0.112.0 логировал) | ответ IdP на пустой токен неизвестен; критерий «sha256 копии прежний» попытку не ловит — только stderr (П6, M2); horizon — §5; Р3 | S164 `login/src/auth/manager.rs:1648-1691,1729-1740,1926-2112,2480-2499,2776-2793,3191-3196,3300-3318,3396-3419`; `app-server/src/models_refresh_worker.rs`; S112 `core/src/auth.rs:650-651,1272-1280` (2.3) |
| 4 | `account/read` | `prolite` → `unknown` | `PlanType` знает `prolite`; `email` может быть null; вариант `amazonBedrock` | продукт `planType` не читает (`subscription_quota.py:51-55`); факт для H2 | S121/S164 `PlanType.ts`, `v2/Account.ts` |
| 5 | `model/list` | effort none…xhigh, закрытый | `Max`, `Ultra`, `Persistent`, `Custom(String)`; `ModelVisibility` закрыт (List/Hide/None). Если сервер не дал ни одной модели `list`, клиент сливает ответ со встроенным каталогом, где есть `gpt-6.1-sol`; `models_cache.json` пишется после любого успешного fetch | каталог должен декодироваться; живость — только по `models_cache.json` (П6б) | S164 `protocol/src/openai_models.rs:62-74,290-299`; `models-manager/src/manager.rs:344-356,649-661,694-721` (2.4) |
| 6 | `--ignore-user-config` | нет (exit 2, `codex_cli.py:16-25`) | есть (#18646), также `--ignore-rules`, `--strict-config`; системный слой (п. 10) не покрывает | не добавляем: в свежем home нет `config.toml`; флаг меняет argv и digest гранта | S164 `exec/src/cli.rs:20-50`; RN 122 |
| 7 | Устройство exec | своя реализация | in-process app-server (с его фоновыми воркерами, п. 3); stdin при наличии промпта → блок `<stdin>`; SQLite-лог exec отключён (`log_db: None`) | наш `-` не затронут; раздельные stdout/stderr (`codex_cli.py:539`) и verdict — M2 | S164 `exec/src/lib.rs:740,1022,2377-2382`; RN 113/117/118 |
| 8 | Флаги и `-c` | в `exec/cli.rs` | `--sandbox`/`--model` в общих опциях, значения те же; `-c` на всех уровнях; `--full-auto` удалён | argv совместим по исходнику | S164 `utils/cli/src/shared_options.rs`; RN 123/147/164 |
| 9 | Файлы `CODEX_HOME` | `tmp\arg0`, `state_5.sqlite`, `.personality_migration`, `skills\.system` | arg0-диспетчер **до разбора argv** (и для `--version`): создаёт `CODEX_HOME`, `tmp\arg0-windows\codex-arg0*\{apply_patch.bat,applypatch.bat,.lock}`, читает `<CODEX_HOME>\.env`; без `CODEX_HOME` — `%USERPROFILE%\.codex` владельца; home под TEMP — WARNING. Плюс `logs_2`, `goals_1`, `memories_1`, `memories_v2_1`, `queue_1`, `thread_history_1`, `.sandbox\` (ежедневный лог), `log\codex-login.log` после входа, `models_cache.json` после quota read | каждый запуск 0.164.0 — в окружении §4; `LOGIN_SCRATCH`/`LOGIN_EXPECTED` (`codex_cli.py:355,362`) — по П7/П11; relay удаляется целиком | S164 `cli/src/main.rs:1043-1063`, `arg0/src/lib.rs:132-147,276-282,311-344`, `utils/home-dir/src/lib.rs:6-17`, `windows-sandbox-rs/src/logging.rs:143-146`; RN 145/163 (1.2, 1.6, 2.1) |
| 10 | Внешний вход конфигурации | `%ProgramData%\OpenAI\Codex\{config,requirements}.toml` | то же + `HKLM\SOFTWARE\Policies\OpenAI\Codex` `RequirementsPath` (любой абсолютный путь) + облачный бандл (только business/edu/enterprise, не `prolite`). Системный `config.toml` — полный слой (`notify`, `mcp_servers`, `model_provider`, `windows.sandbox`, `projects.<путь>.trust_level`); существующий, но нечитаемый файл — отказ загрузки | вход вне `CODEX_HOME`; адаптер его не изолирует (`codex_cli.py:105-136,390-391`); `C:\ProgramData` разрешает Users создавать подпапки; trusted-проект включает project config, hooks, exec policies (ломает основу П8). Измерено 23.10: `C:\ProgramData\OpenAI` и ключа HKLM нет. Стоп-предусловие П9, Р5 | S112 `core/src/config_loader/mod.rs:86-96,165-170,421`; S164 `config/src/loader/mod.rs:123-134,212-230,272-290,716-724,818-838,1126-1140`, `cloud-config/src/service.rs:52-61`, `core/src/config/windows_sandbox_config.rs:86-126` (1.3, 2.9) |
| 11 | Ответы app-server | базовые | `initialize` + `codexHome`, `platformFamily`, `platformOs`; rateLimits + `ordinaryUsageAllowed` и др.; при создании — воркеры каталога (сетевой fetch сразу) и стоимости ходов, рассылка нотификаций с метками времени; `optOutNotificationMethods` в `InitializeCapabilities` | лишние поля терпимы (`quota_contracts.py:119-153`); строки без id вероятны (`subscription_quota.py:35-43` — `unexpected native message`); quota read теперь вызывает `auth()` (п. 3) и пишет `models_cache.json`; Р4 | S164 `app-server/src/message_processor.rs:393-402`, `account_notifications.rs`, `schema/typescript/InitializeCapabilities.ts` (2.8) |
| 12 | Запуск через `codex.js` | — | ставит `CODEX_MANAGED_PACKAGE_ROOT`, `CODEX_MANAGED_BY_NPM=1` | pin на exe их не даёт (`CODEX_FORCED_ENV=()`, `codex_cli.py:283`); по коду `InstallMethod = Other` влияет только на doctor и подсказку обновления TUI, на exec/login/app-server — нет; живьём не проверено | S164 `codex.js`; `cli/src/doctor/updates.rs:392-413`, `tui/src/update_action.rs:33-42` |
| 13 | Схема `auth.json` входа | `tokens{id_token,access_token,refresh_token,account_id}` | `tokens` + `oauth_provenance{issuer,client_id}` (объект) + `login_owner_id` (str), оба `serde(default, skip_serializing_if)`; вход их пишет. Наверху возможны `agent_identity`, `personal_access_token`, `bedrock_*` (при None не пишутся). `login` сначала отзывает refresh прежнего входа этого home | `codex_relay.py:59,77-80` ответит `unknown_shape` → `ready()` отказ (`login_relay.py:457-459`): первый же повторный вход владельца после pin закрыл бы relay для всех Codex-ролей; П11, §5 | S164 `login/src/token_data.rs:22-33` (перепроверено ведущим), `login/src/server.rs:833-866`, `cli/src/login.rs:60-158`, `login/src/auth/revoke.rs:68-77` (2.1) |
| 14 | `-o` | при TurnComplete файл пишется всегда; нет сообщения — пустой | файл только при `TurnStatus::Completed`; Failed/Interrupted — файла нет; пустой — только Completed без сообщения агента | семантика `ANSWER_DETAIL[empty/absent]` (`codex_cli.py:180-191,436`) неверна; П8 теряет различающую силу: чистый запуск и отравленный `.codex/` оба дают absent | S112/S164 `exec/src/event_processor_with_human_output.rs` (S112 `:313-321`; S164 `:311-342,393-398`) (2.2) |
| 15 | env входа и маршрута | `OPENAI_API_KEY`, `CODEX_API_KEY` | + `CODEX_ACCESS_TOKEN` (перекрывает `auth.json`), `OPENAI_FEDERATION_RULE_ID`, `OPENAI_IDENTITY_TOKEN_FILE`, `OPENAI_WORKLOAD_IDENTITY_CONTEXT` (workload identity — раньше `auth.json`), `CODEX_REFRESH_TOKEN_URL_OVERRIDE`, `CODEX_REVOKE_TOKEN_URL_OVERRIDE`, `CODEX_APP_SERVER_LOGIN_CLIENT_ID`, `CODEX_AUTHAPI_BASE_URL`, `CODEX_SQLITE_HOME` | §5: `provider.py:92`, `relay_env.CODEX_ROUTE_ENV`; M2 проверяет весь список; П5 — подтверждение по байтам | S164 `login/src/auth/manager.rs:225-227,987-1004,1574-1592`, `protocol/src/shell_environment.rs`, `login/src/auth/workload_identity.rs:125-129`, `personal_access_token.rs:12`, `state/src/lib.rs:141` (2.7) |
| 16 | Выбор песочницы Windows | `WindowsSandboxLevel` | связка `windows.sandbox` + requirements + `prefer_mxc`; без `windows.sandbox` → `SandboxType::None`, `WindowsSandboxLevel` по умолчанию `Disabled`; `code_mode` и `prefer_mxc` выключены; voice и code-mode в exec не запускаются (по коду) | requirements из п. 10 могут принудить `windows.sandbox` (elevated `codex-windows-sandbox-setup.exe`) — ещё довод за стоп-предусловие П9 | S164 `features/src/lib.rs:1197-1202,1413-1436`, `core/src/config/mod.rs:3656-3668`, `config/windows_sandbox_config.rs:95-120`, `protocol/src/config_types.rs:297-301` (1.8) |
| — | Без изменений | — | печать `codex-cli X.Y.Z` (`_VERSION_FORM`, `codex_cli.py:469`); `exec`, `--skip-git-repo-check` (тот же отказ, exit 1), `--ephemeral`, `--color never`, значения `--sandbox`, `--model`, `-` = stdin; ключи телеметрии (`analytics.enabled`, `otel.*`, `otel.log_user_prompt`) и `"none"`; хранилище `file`; `CODEX_HOME` обязан существовать; `models_cache.json` TTL 300 с; имена методов app-server; транспорт app-server `stdio://`, `capabilities: null` допустим | менять нечего; живьём — §4 | S164 `exec/src/cli.rs:20-84,163-164,331-338`, `lib.rs:1013-1018`, `config/src/types.rs:248-251,600-666`, `config_toml.rs:293,539,554`, `cli/src/main.rs:595-606` |

`login status` на 0.164.0 refresh не делает и в сеть не ходит для ChatGPT-входа: `load_auth`
вместо `AuthManager::auth()`, ChatgptAuth строится без запросов (S164 `cli/src/login.rs:464-468`,
`manager.rs:420-440`); исключение — заданные env workload identity (`login.rs:451-462`) (2.6).

## 3. Где лежит новый бинарник

- **Корень (Р1, 1.1).** Измерено 23.10, только чтение: `icacls %USERPROFILE%\Documents\Codex` —
  явные `CodexSandboxUsers:(OI)(CI)(M)` и `S-1-5-21-…-2211309706:(OI)(CI)(M)`; унаследованы на
  `work\r5\harnesses\{codex\0.112.0, claude-code\2.1.239, grok-build}` и `work\h5-m`.
  `Get-LocalGroupMember CodexSandboxUsers` → `CodexSandboxOffline`, `CodexSandboxOnline`; SID не
  переводится (гипотеза: capability SID песочницы Codex desktop). Команда в этой песочнице может
  подменить `bin\codex.exe` или положить DLL в `bin\`. Продукт сверяет только форму пути и печать
  версии (`process_loans.py:229-246,308-321`, `codex_cli.py:754-763`), поэтому подмена пройдёт и на
  подписочной дороге с полным токеном, и в границе. `%USERPROFILE%\DecemberCommand` (там
  login-homes) — только SYSTEM, Administrators и владелец (унаследовано), измерено 23.10.
- **Установка.** `$R\codex\0.164.0\node_modules\@openai\{codex,codex-win32-x64}\`, `$R` =
  `%USERPROFILE%\DecemberCommand\harnesses`; pin —
  `…\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe` (≈188 символов). `$R` создаётся с
  защищённым DACL: `icacls $R /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F
  *S-1-5-32-544:(OI)(CI)F *<SID владельца>:(OI)(CI)F`; RX-аренда продукта добавляется поверх.
  Без `npm install -g`, PATH и `%LOCALAPPDATA%` (MSIX, стандарт §5). `…\r5\harnesses\codex\0.112.0\`
  и `codex-installed.json` не трогать: откатная сборка цела (sha256 `af6e92e7…474b` = ассет
  GitHub = запись установки).
- **Распаковка (1.5).** Параметризованная копия `unpack` из `r5-setup\install_harnesses.py:15-41`:
  версия и путь exe — аргументы; отказ на записи не file/dir, на `..` и на существующую цель
  (открытие `xb`). Не `tar.exe`: bsdtar примет symlink/hardlink и перезапишет файлы. После
  распаковки — опись 47 файлов (путь, размер, sha256) против unpkg `?meta`; запись
  `codex-0164-installed.json` с описью. Главный пакет — только ради паритета с npm-раскладкой:
  ресурсы `codex.exe` находит от своего пути.
- **Сверка перед работой.** sha256 всех 47 файлов против описи — в начале каждого захода П, перед
  M2 и перед каждым сеансом R5 (запись). Дизайн: внутри одного захода защищённый DACL держит.
- **Граница по коду.** RX получает ближайшая `harnesses\<name>\<version>`
  (`harness_attempt.py:75-93`, `process_loans.py:87-89`): весь `0.164.0\` с `codex-resources` и `codex-path` (OICI); форма
  `harnesses/<name>/<version>` в новом корне проходит `_refuse_install`.
- **Записи и home.** Записи без секретов — `Documents\Codex\work\h5-a\`. Каждый home запуска
  0.164.0, особенно с копией токена (П4, П6, П11, M2), — новая пустая папка
  `%USERPROFILE%\DecemberCommand\h5-a\<П>` под защищённым DACL `$R`-формы, вне TEMP и проекта
  (то же правило, что relay-home, `process_loans.py:39-42`).
- **Откат (1.6).** Откат = revert A-I1 + wheel/CI + мастер providers с путём 0.112.0 + новый грант;
  не настройка. До первого запуска 0.164.0 на постоянном login-home записать имена и sha256 его
  файлов, без содержимого. Совместимость home в обе стороны — П11.
- **Runbook (1.10).** `R5-REHEARSAL-RUNBOOK.md:69` берёт `$H` из `%LOCALAPPDATA%` — противоречит
  `:10-14` и стандарту §5; правка — §5.

## 4. Матрица проверок до нового pin (без inference)

**Окружение каждого запуска 0.164.0 (1.2).** `CODEX_HOME` = новая пустая существующая папка по §3;
окружение — только `SYSTEMROOT`, `WINDIR`, `PATH` = `%SystemRoot%\system32;%SystemRoot%`,
`TEMP`/`TMP`, `CODEX_HOME`; `os.environ` не наследовать (прежний установщик наследовал,
`install_harnesses.py:72-74`); после запуска — список имён в home. Один прогон на пункт, оба исхода
сохраняются. Настоящий login-home новой версией не открывать до решения о pin.

| П | Требование A | Как | Критерий | Пункты |
| --- | --- | --- | --- | --- |
| П0 | целостность | до скачивания: dist-tags (§1 «Правило версии»); после: sha512 и sha256 двух tgz, опись, `Get-AuthenticodeSignature` для 5 exe OpenAI и 26 DLL, `icacls` | sha512 = §1; sha256 и размер tgz = GitHub-ассеты §1; опись 47 файлов = unpkg; подпись `Valid`, издатель записан; `rg.exe` — записать как есть; любой иной PE не `Valid` — стоп; поля провенанса записаны с пометкой «по метаданным реестра»; у папки версии и `bin\` нет W/M/F ни у кого, кроме SYSTEM, Administrators и владельца (1.1, 1.4) | — |
| П1 | версия | `codex.exe --version` | объединённый вывод ровно `codex-cli 0.164.0` + CRLF; нет `WARNING:`; в home только `tmp\arg0-windows\…` (1.2) | 1 |
| П2 | exec/checker argv, stdin | `exec --help`, `login --help`, `app-server --help` | есть все флаги `codex_cli.py:632-637,668-673`; `-` = stdin; `-o`; `--model` | 6–9, 11–12 |
| П3 | телеметрия | S164 `config_toml.rs`/`types.rs` + поиск ключей в байтах exe | 5 ключей и `"none"` существуют | 10 |
| П4 | подписочный вход, access-only | синтетические `auth.json` (`exp` далеко), `login status` | таблица ниже; sha256 файла не изменился (2.6) | 17, 20–22 |
| П5 | env маршрута и ключа | поиск `CODEX_*`/`OPENAI_*` в байтах exe | список §2 п. 15 подтверждён; новые сверх него — в §5 | 24 |
| П6 | живой каталог, нет refresh | Предусловия: П9-предусловие; `exp − now` > Σ таймаутов спавнов этой копии + 6 мин. 2 сессии на access-only копии настоящего login-home, как C: (а) ровно `QUOTA_RPC`, EOF после id 3; (б) `model/list {limit:100}` | (а) exit 0 ≤ 15 с, окна разбираются, записаны методы всех строк без id; допуск — только объявленные в `SubscriptionRpc.notifications`, иначе Р4 (2.8). (б) из `models_cache.json` до удаления relay читаются только `fetched_at`, `client_version`, `models[].slug`, `models[].visibility`: есть хотя бы одна модель `list` и `gpt-6.1-sol` с `visibility: "list"`; число моделей сервера записано; `model/list` — сверка; `gpt-6.1-sol` только в `model/list` — «не доказан», стоп по §6 (2.4). Обе: stderr без учёта регистра не содержит `failed to refresh token`, `could not be refreshed`, `auth recovery`, `failed to decode`; sha256 копии и настоящего `auth.json` прежние (2.3) | 26–31 |
| П7 | очистка relay | список имён (без содержимого) home после П1, П4, П6, П11 и M2 | ожидаемы `models_cache.json` после П6а, `log\codex-login.log` после П11, возможно `.sandbox\`; решение по `LOGIN_SCRATCH`/`LOGIN_EXPECTED`; relay удалён после конца дерева процессов | 25, 32 |
| П8 | изоляция дерева | `test_command_codex_real_smoke.py:283` и контроль `:321`, без кредов, pin 0.164.0 | вывод попытки снимается обёрткой `_attempt` (как `_collecting_final_messages` для `-o`); отравленный недоверенный запуск: в выводе нет `PROBE_NO_SUCH_PROVIDER`, последняя строка ошибки = у чистого запуска; равенство `_answer` — вторично; контроль `:321` — только по `PROBE_NO_SUCH_PROVIDER` (2.2) | 33–34 |
| П9 | boundary Windows | **Предусловие (только существование, без содержимого):** нет `C:\ProgramData\OpenAI\Codex\config.toml`, `requirements.toml` и значения `HKLM\SOFTWARE\Policies\OpenAI\Codex\RequirementsPath`; есть хоть одно — стоп, содержимое показывает владелец, решение Codex; то же чтение — перед M2 и строкой runbook перед R5 (1.3, 2.9). Затем нативные `test_adapter_boundary_launch.py` (файл на процесс), pin в `0.164.0\…\bin`: `--version`, `login status`; тем же входом границы `codex.exe doctor` в пустом home | exe стартует в AppContainer, нет записи вне home; `--version` — как П1, имена в `CODEX_HOME` записаны; `doctor`: строка `search command:` указывает на `…\codex-path\rg.exe` (сетевые проверки doctor не изучены — гипотеза; при обращении к сети только запись); опись PE в install — ровно 6 exe + 26 DLL (1.8, 1.9). Не выполнено — в §7 «exec 0.164.0 в границе не проверен; граница для Codex 0.164.0 объявляется по форме пути» | 4, 9 |
| П10 | фейки и тесты | полный pytest после §5, с `PYTHONUTF8` и cp1251 | 0 failed; лимит 800 строк; `_fakecodex.py` по умолчанию на неудачном ходе `-o` не пишет (2.2) | 2–3, 35–39 |
| П11 | вход 0.164.0 и откат | **Human gate владельца (Р6).** `codex.exe login` (окружение выше) в пустой `…\DecemberCommand\h5-a\login-0164`. Записать только имена ключей `auth.json` (верх и `tokens`), типы значений, имена в home. Затем `CodexRelay` admit/strip на этом файле; `login status` 0.164.0 и 0.112.0 на том же home; 0.112.0 `login status` на настоящем login-home до и после; в конце `codex.exe logout` (0.164.0 отзывает refresh этого входа) и удаление home | имена = §2 п. 13 (иначе — новые §2/§5); на HEAD admit — `unknown_shape`, после A-I1 — принят, копия без `oauth_provenance`; обе версии — «Logged in using ChatGPT»/0 (откат, 1.6); настоящий вход до и после — ChatGPT/0 (второй вход первый не выбивает — гипотеза, проверяется здесь); logout exit записан (2.1) | 17, 20–22 |
| M2 | stdin/output/verdict, нет refresh в работе | §6 | §6 | 12, 14–15, 22 |

Ожидаемые исходы П4 (S164 `cli/src/login.rs:451-513,593-613`, `token_data.rs:22`):

| Случай | Фраза | exit |
| --- | --- | --- |
| ChatGPT (`auth_mode:"chatgpt"`, `tokens`) | «Logged in using ChatGPT» | 0 |
| ChatGPT + поля §2 п. 13 | «Logged in using ChatGPT» | 0 |
| `refresh_token: ""` | «Logged in using ChatGPT» | 0 |
| без `refresh_token` | «Error checking login status: …refresh_token…» | 1 |
| только ключ | «API key configured - …» + «Authentication is checked when you send a request.» | 0 |
| ключ + `auth_mode:"chatgpt"` | «Logged in using ChatGPT» (relay отказывает по ключу, `codex_relay.py:69-70` — записать оба) | 0 |
| ключ без `auth_mode` | «API key configured - …» | 0 |
| пусто | «Not logged in» | 1 |
| неверный литерал `cli_auth_credentials_store` | «Error loading configuration» | 1 |

## 5. Файлы адаптера и тестов

A-I1 — после коммита I2b его исполнителем, в отдельном `git worktree add` от этого коммита:
`codex_cli.py`, `codex_relay.py`, `relay_env.py`, `codex_quota.py` и их тесты сейчас у I2.

| Файл | Изменение | Условие |
| --- | --- | --- |
| `codex_cli.py` (784/800 строк) | `:257` → `"0.164.0"`; `API_KEY_MARKER` `:380` → `"API key configured"`; `:355,362` по П7/П11; `ANSWER_DETAIL[empty/absent]` `:436` и docstring `:180-191` по §2 п. 14; docstring `:366-372,584-586` по §2 п. 2; `:8-10,27-34`; при Р3 — `CODEX_FORCED_ENV` `:283`; правки на месте, новое — в соседний модуль | П1, П4, П7, П11, Р3 |
| `codex_relay.py` | `_TOKENS` `:59` + `login_owner_id` (str, копируется); `oauth_provenance` — допуск только dict ровно из `issuer`, `client_id` (str), в relay не копируется (нужен лишь для выбора refresh-endpoint, S164 `manager.rs:1790-1797`); `_TOP` `:58` — по именам П11; `CODEX_FORM` `:55` — только по M2 | П11 |
| `provider.py:92` | + `CODEX_ACCESS_TOKEN`, `OPENAI_FEDERATION_RULE_ID`, `OPENAI_IDENTITY_TOKEN_FILE`, `OPENAI_WORKLOAD_IDENTITY_CONTEXT` | §2 п. 15, П5 |
| `relay_env.py:38` `CODEX_ROUTE_ENV` | + `CODEX_REVOKE_TOKEN_URL_OVERRIDE`, `CODEX_AUTHAPI_BASE_URL`, `CODEX_APP_SERVER_LOGIN_CLIENT_ID`, `CODEX_SQLITE_HOME`; при Р3 `CODEX_REFRESH_TOKEN_URL_OVERRIDE` становится code-owned, запрет на пользовательское значение остаётся | §2 п. 15, Р3 |
| `subscription_quota.py:24` / `codex_quota.py:30-35` | объявленные нотификации или `optOutNotificationMethods` | П6а, Р4 |
| вызов `login_relay` (I2b) | для каждого Codex-спавна на копии (version, login status, quota app-server, doer, checker): `exp − now` > Σ таймаутов спавнов этой копии + 5 мин + 1 мин — передать исполнителю I2b | §2 п. 3 |
| без правок | `headless_routing.py`, `deep_contracts.py:48` (`codex-headless-v1`), `process_acl.py`; `process_loans.py` — только по Р5, отдельной задачей | П9, Р5 |
| тесты | `_fakeboundary.py:44-47` (`0.164.0`, сегмент `bin`); `_fakecodex.py:22-28,112-125,207-216` (неудачный ход без `-o`); версия — `test_command_codex_version.py:46,89,200,213,217`, `test_subscription_quota.py:36`; фраза — `test_harness_login_method.py:84,103`; `test_harness_login_leaks.py:692`; real smoke — путь и критерий П8; relay — поля §2 п. 13 | П10 |
| грант | профиль меняет digest (`policy_providers.py:31-34`): старые гранты отказываются, нужен новый | by design |
| документы, EN/RU | runbook `:10-16,69-71,81-91` (`$H` из `$env:USERPROFILE`/`$R`; `codex_cli.py:466` → `:469`), строка предусловия П9 перед R5; повторный вход через 0.164.0 отзывает refresh прежнего входа этого home; `first-run-v1(.en).md:133/135`, `release-notes-v1-alpha(.ru).md:30`, `H5-SUB-R5-TASK.md:56`, `2026-09-21-quota-observations.md:19`; `v1-v2-scope.md:31` — решение владельца | после приёмки (1.10) |

## 6. Кандидат model ID и один M2 новой связки

`gpt-6.1-sol` — **не доказан**. learn.chatgpt.com/docs/models рекомендует его платным планам при
ChatGPT sign-in (`H5-SUB-R5-M2-MODEL-REPORT.md:28-31`); changelog 29.09.2026: «when available to
your plan and client»; S164 `models-manager/models.json`: priority 1, `minimal_client_version
0.153.0`. Против: M2b на 0.112.0 отклонён сервером; встроенный каталог и `prolite` в JWT доступ не
доказывают; `model/list` может показать его из встроенного каталога (§2 п. 5). Брать, только если
П6б нашёл его с `visibility: "list"` в `models_cache.json`; иначе — стоп и решение ведущего.

M2: ровно один запуск. argv — `_review_argv` (`codex_cli.py:668-673`) с `--model gpt-6.1-sol`,
бинарник 0.164.0, вне AppContainer, relay с access-only копией настоящего login-home, окружение
§4; stdin — фиксированный минимальный материал, ожидающий `VERDICT: accept`, текст записан до
запуска. В отчёте назвать отличия от M2b: бинарник, позиция и кавычки `-c`, `--model` (2.5).
Предусловия: П0–П11 пройдены; сверка описи (§3); П9-предусловие перечитано; до запуска `exp − now`
≥ таймаут + 6 мин (часы записаны). Бюджет — решение ведущего. Успех — всё сразу:
1. exit 0; до запуска «Logged in using ChatGPT»; в stderr баннер `model: gpt-6.1-sol`, нет
   `model rerouted:`, `Model metadata for`, `ERROR:` и строк refresh из П6; в env нет ни одного
   имени §2 п. 15, `OPENAI_API_KEY`, `CODEX_API_KEY` (2.3, 2.5, 2.7).
2. Выполнены все условия `verdict()` (`independent_check.py:204-217`): exit 0, без усечения, stdin
   доставлен, нет эха env, первая непустая строка stdout после `lstrip` — ровно `VERDICT: accept`.
   stdout ≤ 16 KiB (`OUTPUT_LIMIT_BYTES["normal"]`, `deep_commands.py:50`: в Claude → Codex Codex
   проверяет dispatch, `independent_transport.py:55-60`; 48 KiB — только review,
   `codex_cli.py:395`); записать, укладывается ли в 4 KiB; `-o` — `written` (2.5).
3. После — sha256 копии и настоящего `auth.json` прежние, `refresh_token` пуст, обратной записи нет.
4. Digest рабочего дерева прежний; relay удалён после конца дерева процессов; имена записаны.
Отказ: точная причина рядом с M2a/M2b, возврат Codex; без повтора, другой модели, effort и ключа.
Успех доказывает только связку CLI/модель/аккаунт: boundary, цикл и R5 — отдельно.

## 7. Что не делать; что не проверено

- Не скачивать без явного разрешения владельца; не запускать `codex.js`, `npx`, `npm install -g`,
  `tar.exe` для распаковки.
- Не менять 0.112.0 и его записи; pin — не одной сменой номера; файлы I2 — не параллельно с ним.
- Не брать одиночный GitHub-exe и alpha-версии; не подменять версию без решения (§1); не запускать
  0.164.0 на настоящем login-home до решения о pin и без `CODEX_HOME`.
- Не ставить в `Documents\Codex` и `%LOCALAPPDATA%`; не класть копии токена вне защищённого DACL.
- Не добавлять `--ignore-user-config` и `CODEX_MANAGED_*` без решения (argv, env, digest гранта).
- Не перебирать модели и efforts, не подменять подписку ключом, не запускать платный smoke
  `test_command_codex_real_smoke.py:385`; H1 не объявлять доказанной до успешного M2.
- Закрыто v2 по исходнику и метаданным: refresh при `login status` (нет); GitHub-tgz = tarball
  реестра (сверка sha256 в П0); эффект без `CODEX_MANAGED_*` (по коду нет на exec/login/app-server).
- Не проверено: `--version` и exec живьём; ответ IdP на пустой `refresh_token`; сетевые обращения
  `doctor`; SQLite, `version.json`, `installation_id` при `--ephemeral`; фильтр `/models` по
  `client_version`; незнакомые значения живого каталога; не выбивает ли второй вход первый (П11).
- Уже на 0.112.0 app-server оставляет `.personality_migration` и `state_5.sqlite*` вне
  `LOGIN_EXPECTED`: остаток на постоянном login-home (гипотеза, `subscription_quota.py:103-107`).
- Мутанты: не применимо (документ). Ревью Codex: ожидает.

## Открытые вопросы (вне A)

- Р1 касается уже установленных Claude 2.1.239 и Grok 1.0.5: перенос Claude — до цикла B.
- Р5: preflight-отказ адаптера на чужие ACE записи в install и на входы ProgramData/HKLM.
- `Documents\Codex\work\h5-m` (записи M1/M2) тоже доступен песочнице на запись; секретов там нет,
  копии токена M2 удалены (список файлов 23.10: один `M1-M2-claude-codex.txt`).

## Передача

Последний доказанный шаг | первый несделанный: DESIGN A v2 с находками скептиков записан |
решения Codex Р1–Р6 и разрешение владельца на скачивание не получены. Не повторять: исследования A
и две линзы скептиков | только чтение 23.10 | этот файл. Следующий шаг: Codex решает Р1–Р6;
владелец разрешает скачать два tgz; затем П0.
