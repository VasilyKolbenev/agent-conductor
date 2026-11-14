Итог: локально проверено (Р1, П0–П5) | 80f3370 | 23 прогона, 0 failed | 4 отклонения | Р7–Р10.

# Отчёт по задаче: H5-CODEX-COMPAT A — защищённый корень (Р1), П0–П5 для Codex 0.164.0

- Исполнитель: Opus 5.5 (ведущий), 23.10.2026 18:05–18:45 МСК; независимая проверка — три линзы
  Opus только чтением (workflow `wf_fda3bb29-2fe`).
- Исходный commit и ветка: `80f3370`, `recovery/2026-10-20`; решения Codex — `2a5bcdd`
  ([A-REVIEW-REPORT](H5-CODEX-COMPAT-A-REVIEW-REPORT.md)), дизайн — `69c2a7d`.
- Рабочая копия до изменений: незакоммиченная работа I2b (на 18:30 — 23 изменённых и 8 новых
  файлов) — не тронута; этот коммит её не включает. Прогонов CLI без входа и inference — 23:
  2 `--version` копий, П1 1, П2 3, П3 2, П4 9, П3x 4, П4x 2.
- Цель: по Р1 перенести CLI в защищённый корень; по Р2 скачать и проверить 0.164.0 (П0) и
  пройти П1–П5 без входа и inference. Ожидаемое: все критерии П0–П5 выполнены, следов вне
  отведённых мест нет, старые установки целы.

## Изменения

В репозитории: этот отчёт и [H5-CODEX-COMPAT-A-INVENTORY.json](H5-CODEX-COMPAT-A-INVENTORY.json) —
закреплённая в git опись 61 файла защищённого корня (размер, sha256). Код продукта не менялся.

Вне репозитория (измерено, все пути от `%USERPROFILE%`):

| Что | Где | Как |
| --- | --- | --- |
| Корни с защищённым DACL | `DecemberCommand\{harnesses,downloads,h5-a}` | `icacls /inheritance:r`, явные `(OI)(CI)F` только SYSTEM, Administrators, владелец `S-1-5-21-1587090867-1133322786-1120936243-1000` (из HKLM ProfileList = `whoami`) |
| Claude 2.1.239 | `harnesses\claude-code\2.1.239\claude.exe` | побайтная копия `r5-setup\claude-2.1.239.exe`; sha256 `0bc1304c…0a2b` = живой `manifest.json` |
| Codex 0.112.0 | `harnesses\codex\0.112.0\…` | распаковка архивов `r5-setup` после сверки sha512 с реестром; дерево = старому и unpkg |
| Codex 0.164.0 | `harnesses\codex\0.164.0\node_modules\@openai\{codex,codex-win32-x64}` | §П0 ниже; pin-путь `…\vendor\x86_64-pc-windows-msvc\bin\codex.exe` |
| Архивы | `downloads\codex-0.164.0\` | два tgz реестра |
| Эталон и инструменты | `h5-a\ref\harnesses-inventory.json` (sha256 `8a757acb…cd46`), `h5-a\tools\` | `preflight.ps1` (ручная сверка по Р5), скрипты метода |
| Дома проб | `h5-a\p0-*`, `p1-*`…`p4-*`, `p3x-*`, `p4x-*` | только поддельные `auth.json` и scratch CLI |
| Записи без секретов | `Documents\Codex\work\h5-a\*.json` | 11 файлов, перечень в «Проверках» |

Старые установки `Documents\Codex\work\r5\harnesses` не тронуты и остаются свидетельством; откат —
на защищённую копию 0.112.0 (см. «Открытые вопросы»).

## Проверки

| Шаг | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| meta (`p0.py meta`) | dev venv, сеть, чтение | dist-tags `latest`=0.164.0; integrity обоих пакетов = DESIGN §1; scripts/deprecated нет; GitHub-ассеты (размер, sha256) = DESIGN; unpkg 47 файлов; manifest Claude = запись; integrity 0.112.0 = запись. Первая попытка — HTTP 403 rate limit GitHub, повтор после сброса | версия и источники не сдвинулись; Р2 «изменение latest» не наступило |
| download | то же | `codex-0.164.0.tgz` 4 902 Б, `codex-0.164.0-win32-x64.tgz` 172 854 349 Б; sha512 = npm integrity, sha256 = ассеты GitHub | П0: размер, npm sha512, GitHub sha256 |
| install164 | то же | безопасная распаковка (только file/dir, без `..`, `xb`); 3 + 47 файлов, 483 692 160 Б; каждый файл = integrity unpkg; `codex.exe` = ассет GitHub `6f267830…6d36` | П0: опись, раскладка |
| claude, codex112 | то же | sha256 копий = манифест / записи; 0.112.0 `codex.exe` `af6e92e7…474b` | Р1 |
| подписи и ACL (`p0-sig-acl.ps1`) | PowerShell | 0.164.0: 31 PE Valid (30 «OpenAI OpCo, LLC», `vcruntime140.dll` — Microsoft через каталог), `rg.exe` NotSigned; claude.exe Valid «Anthropic, PBC»; 89 объектов `harnesses` без проблем | П0: подписи; Р1: дерево |
| versions | минимальный env, свежие home | `2.1.239 (Claude Code)`, `codex-cli 0.112.0`, exit 0, stderr пуст, установка не изменилась | копии исполняемы |
| П1 | 0.164.0, env DESIGN §4 | stdout `codex-cli 0.164.0\n` (18 Б, LF), stderr пуст, нет `WARNING`; в home только `tmp\arg0-windows\codex-arg0*\{.lock,apply_patch.bat,applypatch.bat}` | `version_token` + `_VERSION_FORM` продукта примут |
| П2 | то же | все флаги адаптера в справке с теми же написаниями; `-` = stdin; `login status` есть; app-server `stdio://` | argv совместим |
| П3 + П3x | то же | ключи и `"none"` приняты при загрузке конфигурации; отрицательный контроль на **каждый** из пяти ключей отвергнут с именем ключа | все пять ключей существуют и типизированы; отключение во время работы не измерено |
| П4 + П4x | поддельные `auth.json` | 9/9 строк таблицы DESIGN: фраза и exit; sha256 файла не изменился; `tokens.oauth_provenance="x"` → «invalid type … struct AccountOAuthProvenance»/1; тот же ключ наверху игнорируется → ChatGPT/0 | Р6: оба поля внутри `tokens`; схема входа 0.164.0 |
| `CodexRelay.admit` | базовый python, офлайн | `chatgpt_new_fields` → `unknown_shape`; ключ → `api_key`; `key_plus_chatgpt` → `api_key`; ChatGPT, `refresh_token:""`, без refresh → допуск | находка DESIGN 2.1 воспроизведена; правка — A-I1 |
| П5 | байты `codex.exe` | 11/11 имён DESIGN §2 п. 15 найдены; ещё 114 кандидатов, классифицированы по S164 (ниже) | перепись = исходник + байты |
| preflight-1 (`preflight.ps1 -Mode check`) | PowerShell, Get-FileHash | цепочка `C:\`→`Users`→профиль→`DecemberCommand`, три корня и деревья, владельцы, reparse, 61 хеш = эталону, издатели по классам, входы ProgramData/HKLM отсутствуют: **0 проблем** | Р1 целиком и П9-предусловие на 18:41 |
| независимая проверка | 3 линзы Opus, только чтение | все хеши, подписи, ACL, след, отсутствие секретов, сохранность старых установок подтверждены другими средствами (System32 PowerShell, свежие метаданные) | см. «Отклонения» |

Записи: `Documents\Codex\work\h5-a\{p0-meta, p0-download, codex-0164-installed,
claude-2.1.239-protected, codex-0.112.0-protected, p0-versions, p0-authenticode, p0-acl, p1-p5,
p3-p4-followup, preflight-1}.json`. Провенанс (по метаданным реестра, криптографически не
проверено): subject sha512 = integrity обоих пакетов; SAN
`https://github.com/openai/codex/.github/workflows/rust-release.yml@refs/tags/rust-v0.164.0`,
issuer `token.actions.githubusercontent.com`, commit `6aaac694803004a63c6f393d153c96d22521a6b9`,
run 39894017941/3, Rekor 04:50:53–04:56:05Z; тег → объект `fe3b2945…`, не подписан.

**П5, классификация по S164 (проверяющий 3, исходник прочитан в памяти).** Предлагается для A-I1:
в `relay_env.CODEX_ROUTE_ENV` — `CODEX_CA_CERTIFICATE` (свой CA HTTPS-клиентов),
`CODEX_EXEC_SERVER_URL` и
`CODEX_EXEC_SERVER_NOISE_{REGISTRY_URL,ENVIRONMENT_ID,AUTH_TOKEN,CHATGPT_ACCOUNT_ID}` (исполнение на удалённом exec-server, дайджест дерева его не увидит),
`CODEX_AGENT_IDENTITY_{AUTHAPI,JWKS}_BASE_URL`, `CODEX_APP_SERVER_LOGIN_ISSUER`,
`CODEX_CONNECTORS_TOKEN`, `CODEX_ROLLOUT_TRACE_ROOT` (сырые trace вне attempt home); дёшево и
низкий риск — `OPENAI_ORGANIZATION`, `OPENAI_PROJECT` (байтовый поиск его не видит: имя собрано
в immediate-операндах), `CODEX_INTERNAL_ORIGINATOR_OVERRIDE`, `CODEX_OSS_{BASE_URL,PORT}`; в
`provider.py:92` — `CODEX_GUARDIAN_DECISIONS_API_KEY`. Безвредны: TUI, аналитика, маркеры дочерних
процессов, denylist-имена (`AWS_*`, `AZURE_*`, …), установка/daemon, внутренности песочницы,
обрывки пула строк. Ребёнок продукта получает env по allowlist, поэтому список важен для строк,
которые оператор пропускает явно.

## Отклонения

| Что | Почему | Кто утвердил |
| --- | --- | --- |
| П0–П5 выполнены интерпретатором dev `.venv` и скриптами из `%LOCALAPPDATA%\Temp`; оба доступны песочнице на запись, `.pth` исполняется и при `-I` (проверяющие 1.1, 2.2) | не учтено при подготовке | ожидает Codex. Результат перепроверен независимо: System32 `Get-FileHash`, свежие метаданные, Authenticode. Дальше — базовый `python -I -S` (у песочницы только RX) и скрипты в `h5-a\tools` |
| Эталон описи лежал в `Documents\Codex\work\h5-a` (запись песочницы) (1.1, 2.6) | то же | ожидает Codex. Эталон перенесён в `h5-a\ref`, его sha256 и вся опись — в git этим коммитом |
| TEMP/TMP процессов П0–П5 из родительского окружения, оба каталога доступны песочнице (1.7) | DESIGN §4 TEMP не ограничивал | ожидает Codex. Для `--version`/help/`login status` с фейками безвредно; с П3x TEMP/TMP внутри home; для П6/П11/M2 — обязательно |
| Критерий П1 «+ CRLF» — ошибка дизайна: обе версии печатают LF (3.4) | DESIGN v1 перенёс формулировку из docstring | ожидает Codex. Критерий продукта — первая непустая строка; docstring `codex_cli.py:33-34` и тест «19 байт CRLF» поправить в A-I1 |

## Мутанты

Не применимо: код продукта и тесты не менялись.

## Чужие правки

Незакоммиченная работа I2b в рабочей копии не читалась на запись и не входит в коммит.
Прочитаны коммиты Codex `2a5bcdd` (решение A) и `80f3370` (runbook B). Проверяющий 2 зафиксировал
появление `%USERPROFILE%\DecemberRehearsal` в 18:12:37 — это подготовка B Codex, не П0–П5.

## Не проверено

- `exec` 0.164.0 вообще (нужен вход) и `-c` после `exec` живьём (только по справке и S164).
- Что телеметрия реально выключена во время работы (нужно сетевое наблюдение).
- Новые режимы входа (access token, agent identity, Bedrock) — фразы только по S164.
- Внутри AppContainer 0.164.0 не запускался (П9 — после A-I1).
- `safe_unpack` не закрывает теоретические случаи (имена устройств, управляющие символы,
  casefold/NFC, лимит объёма; 1.6); на этих архивах их нет — проверено перечнем записей tar.

## Открытые вопросы

Решения Codex (рекомендация Opus первой):

- **Р7. Продукт для B под защищённым корнем.** Runbook B (`R5-CLAUDE-B-RUNBOOK.md:26,46-50`) берёт
  `venv_python` и `conduct_exe` из `run-ready.json` в `$KIT` (запись песочницы); код продукта держит
  границу и relay, угроза Р1 к нему та же (2.3). Рекомендация: venv и wheel B — в
  `%USERPROFILE%\DecemberCommand\product\<sha>`, в `run-ready.json` — sha256 wheel, `python.exe`,
  `conduct.exe`; перед стартом `preflight.ps1` и сверка этих sha256. Runbook это допускает
  («вне `%LOCALAPPDATA%` и исходника»).
- **Р8. TEMP строки провайдера B.** Строка `claude-code` пропускает `TEMP TMP` владельца; по
  проверяющему 1.7, `%LOCALAPPDATA%\Temp` имеет явный Modify для `CodexSandboxUsers`. Токен в
  TEMP не лежит (relay-home защищён), но временные файлы harness — там. Рекомендация: записать
  как известный остаток B; для A после I2b решить, задаёт ли продукт TEMP внутри attempt home.
- **Р9. Каналы маршрута через файлы login-home (3.7).** `<CODEX_HOME>\.env` (все имена, кроме
  `CODEX_*`) и `environments.toml` (удалённые среды) действуют на нерелейных дорогах, где
  `LOGIN_FORBIDDEN = ("config.toml",)`. Рекомендация: оба имени — в отказы login-home в A-I1.
- **Р10. `feedback.enabled` (3.8).** По умолчанию true (загрузка feedback и хранение Guardian
  review), был и в 0.112.0. Рекомендация: `-c feedback.enabled=false` в `TELEMETRY_ARGV` в A-I1
  (меняет argv и digest гранта).
- Список env П5 выше — к утверждению вместе с A-I1.

Без решения, к исполнению:
- Grok 1.0.5 перенести в защищённый корень до первого использования с входом (1.8).
- Откат П11 и §3 DESIGN — на `harnesses\codex\0.112.0`; старый корень `r5\harnesses`
  принадлежит `CodexSandboxOffline` (2.8) и годится только как свидетельство. Строки
  `R5-REHEARSAL-RUNBOOK.md:16,74` устарели.
- Перед П11, П6, M2 и B: `preflight.ps1 -Mode check` с записью; запуски — базовый `python -I -S`,
  TEMP/TMP внутри защищённого home; критерий следа — по конкретным файлам (`auth.json`,
  `config.toml`, `.claude.json`, `logins\**`) в окнах запусков, не по LWT каталога (2.7).
- После B проверить, что ACE RX-аренды сняты (`preflight.ps1` помечает их как note).
- Поправки текста DESIGN: П1 — «первая непустая строка stdout+stderr = `codex-cli 0.164.0`, других
  нет; измерено 18 Б LF»; §2 п. 9 + `environments.toml`; §2 п. 13 «оба поля внутри `tokens`».

## Ревью Codex

Ожидает.

## Передача

- Итоговый commit: этот коммит документов (отчёт + опись); кода нет.
- `git status`: чужая работа I2b не тронута.
- Последний доказанный шаг | первый несделанный: Р1 и П0–П5 выполнены и независимо проверены,
  preflight 0 проблем | A-I1 не начат (ждёт коммита I2b), решения Р7–Р10 не получены.
- Не повторять: П0–П5 | 23.10 18:09–18:41 | этот отчёт и записи `h5-a`.
- Следующий шаг: Codex решает Р7–Р10; ведущий завершает I2b/I3 и готовит B по runbook с Р7.
