# H5-CODEX-A-I1 — подключение 0.164.0

Итог: A-I1 закоммичен, P8/P9/P11 подтверждены; полная проверка не завершена | `522bbf0`,
`8a4fe5fbd8c6b751b361398f8e2a2843895642f5` | UTF-8 ordinary: 18 970 passed / 409 skipped /
1 failed (Win206 в тесте границы argv), исправлен `3b9208a` | следующий шаг: P6, полный core.

Промежуточный отчёт, 28.10.2026. Полный green, работа квот, M2 и цикл с Codex не заявлены.

## Основание и объём

Владелец 28.10.2026 поручил Codex подключить Codex к продукту. Отдельный worktree
`Documents\Codex\work\cdx164`, база `d6e4331`. TASK последовательно уточнён коммитами
`29b8479`, `62b39ac`, `1a3beee`, `6a4bb0f`, `c39e8c3`, `51ab991`.
Последующие решения по test PE/P8: `7712108`, `97ad1c6`, `eb546a8`; по границе argv — `d742f5f`;
по окружению P8 и SystemRoot — `f25172a`, `6c3a757`, `7561cfd` (дописано ведущим 30.10 по
ревью ветки, п. 10).
Применены DESIGN `69c2a7d`, A-REVIEW `2a5bcdd`, П0–П5 `2deece6`, I2B-DECISION `f6dbd65`.
Установка/П0–П5 не повторялись. Защищённый продукт B3 `52f3d505d7fb` не изменён.

## Реализовано

- Pin 0.164.0, фактическая фраза API status, `feedback.enabled=false`, новый путь bin/codex.exe.
- Закрытая форма tokens.login_owner_id/oauth_provenance. Owner ID сохраняется; provenance и
  refresh из источника не копируются. Источник остаётся неизменным.
- Перепись env П5: неизвестный маршрут/альтернативный credential отказывает до spawn, в том числе
  через direct pin и в другом регистре. API road сохраняется.
- Code-owned loopback refresh override только для access-only попытки; actual login/status/quota
  source и вход/выход владельца его не получают. Пользовательское совпадение значения не допускается.
- `.env`/`environments.toml` в login-home отказывают по наличию и без учёта регистра Windows.
- Свидетель P8 проверяет результаты процессов, а не одно отсутствие final-message файла.
  P9 проходит через настоящий ProcessRunner/AppContainer; fake auth, без inference.
- `522bbf0`: Windows test-only Popen seam запускает только зарегистрированные fixture-файлы
  через Python, проверяя digest и явные копии. Реальные CLI/native не перехватываются; fallback
  после ошибки нет. Это свидетель pipes/timeout/cleanup, а не нативного запуска PE.

## Проверки и границы доказательств

Все служебные записи ниже — в `Documents\Codex\work`, вне Git, если явно не указан protected путь.
P11 уже проверил настоящий отдельный вход под lease; в отчётах только типы/имена и booleans.
Секреты и account/claim values не приводятся. P6 и M2 ещё не подтверждены.

| Набор | Красная фаза | UTF-8 | cp1251 |
|---|---|---|---|
| Relay schema | 5 failed, 96 passed | 101 passed | 101 passed |
| Env/relay, включая direct credentials | исходный red частично загрязнён fixture-сбоями | 259 passed | 259 passed |
| Compatibility + login method, casefold guard | 8 failed, 18 passed | 70 passed | 70 passed |
| P8 final offline guards + retention | поэтапный red ниже | 41 passed | 41 passed |
| P9 offline JSON/log guards | новый диагностический контракт | 17 passed | 17 passed |
| Fake checker final-message exit branch | 2 failed, 2 passed | 4 passed | ожидает |
| Caps/endings/adapter graph | не поведенческая правка | 215 passed | ожидает |
| Windows fixture launch + builder + fakegh | 3 failed, 2 passed | 35 passed | 35 passed |

`cdx-targeted-python-u8.log`: 856 passed, 5 skipped после замены fixture launch. Это целевой
набор, а не замена полного прогона. Старые строки таблицы сохраняют границы своих измерений.

Root initial public-transport red: 17 failed (`cdx-root-red-01.log`); первый запуск с неверным
temp и setup errors не засчитан. В `cdx-root-targeted-02.log` — 410 passed, 6 failed: четыре
устаревших контрактных ожидания исправлены; два запуска fake Claude блокированы Windows 4551.
Поздний зелёный повтор этих тестов не отменяет исходные отказы.

`cdx-targeted-final-u8.log` прерван после уведомления владельца о Windows Security: полный итог
не засчитан. `codex-a-codeintegrity-cxt3.json` содержит 12 событий 3033/3077 для test PE в cxt3.
В том же просмотренном временном окне событий для защищённого Codex 0.164.0 не найдено.
Поддельные exe — PE launcher + ZIP; два сравниваемых файла отличаются только ZIP timestamp,
один исполнен, другой блокирован. Защита не отключалась, исключения не добавлялись.

## Нативные измерения

Fresh preflight 28.10 13:02 МСК: 61 files, 0 problems, 0 notes, ref
`8a757acbe2421597ed45bfbb9c5e1b1c09edc7ca71049e4a273120f20b39cd46`.

P9: `codex-p9-u8.log` — version-dispatch и status-review прошли; doctor exit 1 нарушил ошибочный
assert exit 0. `codex-p9-doctor-diagnostic.log` — один повтор сохранил лишь tail2048, причина
не была доказана полным выводом. Решение `51ab991` исправляет предпосылку по закреплённому source.
`codex-p9-doctor-json.log` — 1 passed; `codex-p9-doctor-full.json` сохранён целиком. Единственный
fail — `auth.credentials: no Codex credentials were found`; bundled search helper найден по
точному защищённому пути. Его исполнение doctor этим не доказывает. Профиль/папки удалены,
ACL восстановлены, журнал retired, lease переиспользуемая. Остальные warnings сохранены в JSON.

P8: `codex-p8-u8.log` — 1 failed, clean attempt timed_out; тест успел вызвать также poisoned
attempt до проверки первого результата (суммарно 120,45 с). Trusted control не выполнялся.
Вывод CLI не сохранился вне памяти. Дальнейшие исходы не стирают этот неуспех:

- `codex-p8-clean-diagnostic.json`: после fail-fast/scoped stderr capture — 60,078 с,
  Windows DNS 11003 и сетевые повторы. Signed-Python DNS witness `codex-dns-env-witness.json`
  различил env={} (11003) и env+SystemRoot (адрес разрешён), без CLI/model call.
- `codex-p8-systemroot-diagnostic.json`: декларации SystemRoot оказалось недостаточно —
  Windows snapshot Python содержит SYSTEMROOT, exact allowlist не передала смешанный регистр.
  Guard усилен проверкой actual runner environment; production defaults не изменены.
- `codex-p8-env-selected-diagnostic.json`: clean/poison оба completed exit 1, 15,859/18,469 с,
  без truncation/env echo/PROBE, HTTP401 на Responses. Whole-line hash оказался неверным
  критерием из-за включённых S164 trace-полей. Terminal bodies утрачены при redaction;
  их равенство не доказано. Будущий canonical удаляет только cf-ray/request id после URL.
- `codex-p8-trusted-control.log`: прежний trusted control тоже не сработал. S164 удаляет
  model_provider из project-local config даже для trusted; этот poison не различал trust.
  Решение `eb546a8`: невалидный TOML `[PROBE_INVALID_PROJECT_LAYER` + newline в обоих плечах.
- **Итоговый P8**: `codex-p8-trust-discriminator.log` — **2 passed за 36,01 с**. Новый trusted
  control требует nonzero и точное `Error parsing project config file <planted-path>:`;
  untrusted сохраняет auth-отказ. Оба плеча ограничены 60 с. Это новый различающий эксперимент,
  а не объявление предыдущих исходов зелёными. Inference не выполнялся.

## Защищённая сборка и P11

Продукт `8a4fe5fbd8c6` собран из полного SHA выше и установлен отдельно от B3.
`codex-a-product-build.log`, `codex-a-product-preflight.json`: 61 files, 0 problems, 0 notes.
Protected manifest: `%USERPROFILE%\DecemberCommand\product\8a4fe5fbd8c6.manifest.json`.
Wheel SHA256: `d6fb0fc02cc4f84c67ffaeae6808fb58dfe3f7a86befa12d905555fca244b359`.
Manifest SHA256: `cc15ffac4ff961aa43bce43db301aedcad413f80b83b08b90ecf8731095937dd`.

P11 выполнялся отдельными действиями, каждый с protected preflight и source/native lease:

- `codex-p11-source-before.log`: exit 0, ChatGPT, auth_unchanged=true.
- Владелец вошёл в отдельный пустой P11 home. `codex-p11-inspect.log`: admit=true,
  refresh/provenance stripped, owner-id preserved, auth_unchanged=true; status 0.112.0 и
  0.164.0 оба exit 0 / ChatGPT. Зафиксированы только имена/типы полей, home names auth.json/log/tmp.
- `codex-p11-logout.log`: exit 0, auth.json отсутствует, остаются log/tmp.
  **Server-side revocation не доказан** (`server_revocation_proven=false`).
- `codex-p11-source-after.log` (14:34:08 МСК): exit 0, ChatGPT, auth_unchanged=true;
  preflight снова 61 files / 0 problems / 0 notes. Этот шаг завершился после начала отчёта.

Обычный status подтверждает сохранность dedicated source; он не доказывает live access-only
metadata, entitlement конкретной модели или inference. P6 draft ожидает ревью/запуска; M2 не был.

## Полный прогон: остановлен на одном отказе

`cdx-full-164/run-20261028T105831641518Z/results.json`: чистый snapshot `8a4fe5f` в `cdx164-check`,
статус `stopped_failed_batch`. Семь UTF-8 ordinary shards: **18 970 passed, 409 skipped, 1 failed**.
`utf8-shard6.log`: `test_check_road_limits.py::test_the_argv_channel_counts_its_pins_and_flags_and_refuses_one_unit_past_the_bound[0]`
получил WinError 206. Ошибка относится к тесту точной границы argv после добавления Python в
физический запуск fixture; test-only исправление `3b9208a` выполнено по `d742f5f`.
Продуктовый предел не ослаблен. Целый файл: 18 passed в каждой кодировке; caps: 203 passed.
Логическая пара теперь доказывает admission до Popen; отдельная реальная пара Python доказала
физический предел Windows 32767/32768. Мутанты снятого gate, лимита +1 и пустого dispatch пойманы.
Отчёт/логи: `cdx-testlaunch-argv/REPORT.md`, `mutants/RESULT.json`, `final-utf8.log`,
`final-cp1251.log`. Эти целевые проверки не заменяют новый полный прогон.
После failed batch полный runner остановлен: его native batch и полный cp1251 ещё не выполнялись.
Skipped не считаются доказательством; причины сохранены в shard logs. Полный core не зелёный.

## Мутанты

Auth: keep provenance, open shape, drop owner, empty strip, mutate source — все пойманы;
записи `cdx164-auth-mut-check.py` и отчёт исполнителя.
Env: пять исходных мутантов и удаление credential set — пойманы; для последнего M0 28 passed,
M1 14 failed/14 passed, восстановление SHA подтверждено (`e164-env-checks/credential-mutant.json`).
P8: fail-fast/stderr/diagnostic red — 5 failed; удаление fail-fast даёт 6 failed, записи
диагностики — 3, stderr capture — 12. Canonical red — 5 failed/7 passed; мутанты отсутствия
нормализации/игнорирования body/URL/auth-fields/потери digest дают 4/3/1/2/1 failures.
Final trusted discriminator: red 4 failed; generic failure / wrong path / exit-zero accepted /
lost failure artifact — 2/1/1/4 failures. Все мутанты делались на временных копиях; исходный SHA
восстановлен/не менялся. Source-auth values в эти проверки не входили.

## Чужие правки

Основной checkout на старте был чистым; все изменения этой задачи в отдельном worktree.
Исполнители работали только в названных TASK файлах, коммитов от них нет. B3 не заменялся.

## Отклонения

- Root выполняет реализацию по прямому поручению владельца; независимые проверки делегированы.
- Sandbox запрещает `os.link` даже на синтетических файлах. Минимальный witness подтверждён
  вне sandbox; тесты с hardlink запускались с повышенным разрешением, без снятия продуктовых защит.
- P9 criterion исправлен решением Codex `51ab991`, исходные неудачи сохранены выше.
- Windows App Control блокировал часть generated test PE. Причина конкретного решения доверия
  Windows не доказана; подпись NotSigned и timestamp-различие измерены. Test-only seam `522bbf0`
  устраняет запуск таких PE; Windows policy и product security не менялись.

## Открытые вопросы и передача

Последний доказанный шаг: P8/P9, защищённый продукт `8a4fe5f`, P11 до source-after включительно.
Первый несделанный: завершение full core и live P6. Свидетель argv исправлен и проверен.
Далее: П6/P7 по измеренным metadata, возможная одна R4 correction только по фактам; один M2
на gpt-6.1-sol лишь после выполнения его предусловий. Автоматических inference/retry нет.
Не повторять: П0–П5, завершённые P8/P9/P11, исторические doctor/P8/cxt3 неудачи без нового основания.
Quota notifications и login/cache census уточнять только по реальным P6/P7 наблюдениям.
Узкое ревью A/B выполнено; full green, CI, квоты, M2 и приёмка владельца не заявлены.
