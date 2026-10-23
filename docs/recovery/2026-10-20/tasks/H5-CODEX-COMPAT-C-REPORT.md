Итог: локально проверено | база 61a629f | 1 сессия metadata, exit 0, без inference | нет | Codex: A.

# H5-CODEX-COMPAT C: каталог аккаунта на pinned Codex 0.112.0

Opus 5.5, 23.10.2026. Задание: [H5-CODEX-COMPAT-TASK.md](H5-CODEX-COMPAT-TASK.md) из `61a629f`
(прочитано на HEAD `61a629f`). Сырая запись без секретов:
`C:\Users\Пользователь\Documents\Codex\work\h5-m\M1-M2-claude-codex.txt`, раздел «C Codex».

## Что сделано

Одна сессия `codex -c cli_auth_credentials_store=file app-server` (pinned 0.112.0), 2026-10-23
12:29:16 UTC, 1,2 с, exit 0: `initialize`, `initialized`, `account/read {"refreshToken": false}`,
`model/list {"limit": 100, "includeHidden": false}`. Ни `exec`, ни `thread/start`/`turn/start`.
Временный home с access-only копией (`refresh_token: ""`), окружение как у M2 (SYSTEMROOT, WINDIR,
PATH, TEMP/TMP/LOCALAPPDATA на runtime, CODEX_HOME). Сервера продукта и других процессов на
login-home в момент сессии не было (проверено по списку процессов); lease продукта не бралась —
отклонение от задания: читался только файл, запись обратно отсутствует.

## Факты

| Метод | Ответ | Источник и свежесть |
| --- | --- | --- |
| `initialize` | ok, поле `userAgent` | клиент |
| `account/read` | `type: chatgpt`, `planType: unknown`, `requiresOpenaiAuth: true` | сервер принял вход; план `prolite` из JWT клиенту неизвестен |
| `model/list` | 6 моделей, `nextCursor` нет: `gpt-5.3-codex` (isDefault, upgrade `gpt-5.4`), `gpt-5.4`, `gpt-5.2-codex`, `gpt-5.1-codex-max`, `gpt-5.2`, `gpt-5.1-codex-mini`; efforts low/medium/high/xhigh (mini — medium/high) | **встроенный/запасной список клиента**: в stderr `models_manager` — «failed to refresh available models … failed to decode models response: unknown variant `max`» |

После сессии в home: `.personality_migration`, `auth.json`, `state_5.sqlite` (+`-shm`, `-wal`),
`skills\.system`, `tmp`. `refresh_token` в копии пуст, настоящий `auth.json` не изменился, копия
удалена.

## Вывод по гипотезам

- **H1 (версия клиента)** — сильное свидетельство: сервер отдал каталог, но 0.112.0 не смог его
  разобрать (неизвестное значение reasoning effort `max`), а план аккаунта для него `unknown`.
  Видимый список — запасной и содержит модель, которую сервер уже отклонил (M2a).
- **H3 (форма access-only)** — маловероятна: сервер ответил на `account/read` и на запрос каталога.
- **H2 (доступ плана)** — не различена: живой каталог аккаунта не прочитан.
- Пригодной модели на 0.112.0 эта сессия не доказывает; новых модельных запусков не было.
  Значит, для Claude → Codex нужен A (обновление pinned CLI); B (Claude → Claude) — промежуточно.

## Не проверено

Живой каталог аккаунта; доступ к какой-либо модели; поведение новой версии CLI. Мутанты: не
применимо (измерение, без кода).

## Ревью Codex

Статус: ожидает.

## Передача

Последний доказанный шаг | первый несделанный: C выполнен, каталог не декодирован клиентом |
DESIGN A (кандидат версии, integrity, матрица проверок) не подготовлен.
Не повторять: C | одна сессия, запасной список, ошибка декодирования | запись выше.
Следующий шаг: Opus готовит DESIGN A; Codex решает кандидата и один M2 новой связки.
