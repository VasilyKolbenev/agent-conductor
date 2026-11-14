# R4-O2: неоднозначный ответ после send/check — это unknown (G8)

Дата: 21.10.2026. Автор: Opus 5.5, режим только чтения. HEAD `bcd7213`, ветка
`recovery/2026-10-20`. Основание: решение Codex (`CODEX-REVIEW-CANDIDATE-2cb380d.md`, раздел R4,
пункт «В4 / O2») и рамка владельца 21.10 (`../CONTINUATION-PLAN.md`): узкая правка с тестом.
Сервер, API, спецификация и тексты не меняются.

## 1. Что видит карточка

Транспорт (`desk-transport.js:141-160`, `command-projection.js:265-268`) не передаёт HTTP-статус:
любой не-OK ответ приходит как `{status: "refused", code}`, где `code` равен `store_error` для 500
`store_error`, для иного кода вне `ERROR_LABELS` и для тела, которое не JSON (502 прокси и т. п.).
Сбой чтения сессии до отправки (`submit`, 214-218) тоже может дать `store_error`. Потеря ответа
даёт `{status: "unknown"}`, это уже фаза `unknown`.

Где сервер отвечает `git_failed` (`accept_github.py:74-92`):

- push, до push: `read_facts`, `guard_name` (заняты все 32 имени), `_remote_names`, `OSError`
  при чтении;
- push, после push: push без porcelain-строки, look не нашёл ref (`accept_push.py:242-243`);
  `OSError` в `write_push` после push, который дошёл;
- PR, до создания: `OSError`/`UnicodeError` при чтении;
- PR, после `gh pr create`: `OSError` в `write_pull_request`.

По ответу «до» и «после» не различить: `{reason: "git_failed"}` одинаков. `git_timed_out` на пути
send бывает только до push (`_remote_names`, `push_address`, `gh repo view`); у PR его нет.
500 `store_error` после push закреплён сервером (`test_accept_push_reconcile.py:324-336`).

Сейчас (`desk-accept-host.js:36-41, 78-82, 400-407`):

| Ответ | push после send | push после check | PR после send/check |
| --- | --- | --- | --- |
| `store_error` (500, нечитаемый) | final: условия заново | final: условия заново | final: review |
| `git_failed` | absent: «Отправить снова» | absent: «Отправить снова» | final: снова review |
| `git_timed_out` | absent (верно: push не было) | absent (неверно: look не было) | — |

## 2. Правило

Неоднозначны после send и после check, для обоих шагов: `code === "store_error"` и
`reason === "git_failed"`. После check дополнительно неоднозначны `PUSH_ABSENT`-причины: check
никогда не пушит, отсутствие он сообщает только своим `{push: null}`.

Показ: существующая фаза `unknown`, существующие тексты `desk.accept.push.unknown` /
`desk.accept.pr.unknown` и кнопка `desk.accept.check` («Проверить снова»). Текст причины
(`accept.reason.git_failed`, `error.store_error`) остаётся строкой статуса, как у
`push_unconfirmed`. Новых ключей нет. `terms`, `signer` и `fields` сохраняются, поэтому проверка
несёт тело того нажатия и `check: true` (R4-V1 не затронут).

Итог: `git_failed` уходит из `PUSH_ABSENT`; `push_timed_out` и `git_timed_out` после send остаются
absent; final-отказы (`tool_unavailable`, `push_rejected`, `push_terms_changed`, `pr_mismatch`,
`gh_not_logged_in`, ...) не меняются.

Цена и остаток. Если `git_failed` был до push и устойчив (например, заняты все 32 имени guard),
карточка повторяет «Проверить снова», а раньше повторяла «Отправить снова»; выход в обоих случаях
один — перечитать карточку (новая эпоха сбрасывает шаг в `idle`). Ложный unknown после сбоя сессии
до отправки безвреден: проверка только смотрит. Таблица G8 в `R4-PUSH-PR-RECONCILIATION.md`
указывает на старый модуль; правит её Codex или Opus, не Sonnet.

## 3. Задание для Sonnet (S-R4-O2)

**Файлы, только эти:**
- `src/conductor/panel/desk-accept-host.js`: комментарий 36-38, `PUSH_ABSENT` (40), `outcome`
  (78-82), одна строка в `settle` (402).
- `tests/test_desk_accept_publish_unknown.py` — новый модуль (G8).
- `tests/test_desk_accept_publish.py`: только строка 165 (`"git_failed": ["check"]`) и
  комментарий 160-162. Число строк не растёт (756).
- Отчёт: `docs/recovery/2026-10-20/tasks/R4-O2-REPORT.md`.

**Шаг 1. Красные тесты.** Новый модуль импортирует `_js, PREFIX, PR_PREFIX, PUSH_CLICK` из
`tests.test_desk_accept_publish` (как `test_desk_accept_publish_signer.py`). Ответы задать в теле
JS, параметр `d` — имя строки:

```js
const AMBIGUOUS = {
  store_500: {status: 'refused', code: 'store_error',
    payload: {error: {code: 'store_error', message: 'interrupted'}}},
  unreadable: {status: 'refused', code: 'store_error', payload: null},
  git_failed: refused('git_failed'), git_timed_out: refused('git_timed_out'), lost: unknown};
```

1. `test_an_unclear_answer_to_the_push_leaves_only_check_and_the_check_carries_the_same_body`,
   параметры `store_500, unreadable, git_failed, lost`. `push: [ok('push_terms', TERMS),
   AMBIGUOUS[d], ok('push', PUSHED)]`, нажать `PUSH_CLICK`, затем 3 раза `await tick(); shown(r)`.
   Ожидается: `live == [PREFIX + "check"]`, есть текст `desk.accept.push.unknown`, команда terms
   видна, `kinds == ["terms", "send"]` (автоповтора нет). После `check`: тело 3 = тело 2 плюс
   `check: true`, `actor == "Owner"`, «Sent to GitHub», `kinds.count("send") == 1`.
2. `test_an_unclear_answer_to_the_push_check_keeps_check_and_never_offers_send_again`, параметры
   `store_500, git_failed, git_timed_out, lost`. `push: [terms, refused('push_unconfirmed'),
   AMBIGUOUS[d], ok('push', null)]`. После первой проверки `live == [PREFIX + "check"]`; после
   второй — `[PREFIX + "push.again"]`; `kinds == ["terms", "send", "check", "check"]`.
3. `test_an_unclear_answer_to_the_pull_request_or_its_check_leaves_only_check`, параметры
   `store_500, git_failed`. `rig({facts: {push: PUSHED}, pull: [AMBIGUOUS[d], AMBIGUOUS[d],
   ok('pull_request', PULL)]})`, нажать `review`, `pr.action`. Ожидается
   `[PR_PREFIX + "check"]`, текст `desk.accept.pr.unknown`, поле base `disabled`; после `check`
   то же; после второй `check` есть ссылка `PULL.url`, `kinds == ["send", "check", "check"]`.

Вместе со строкой 165 прогнать на текущем коде: красные `store_500`, `unreadable`, `git_failed`
(тест 1), `store_500`, `git_failed`, `git_timed_out` (тест 2), все строки теста 3 и строка
`git_failed` таблицы `AFTER_PUSH_REFUSAL`; `lost` зелёный. Записать числа в отчёт.

**Шаг 2. Правка** (`desk-accept-host.js`):

```js
const PUSH_ABSENT = Object.freeze(["push_timed_out", "git_timed_out"]);
// ...
const outcome = (step, code, reason, check) => {
  if (code === "store_error" || reason === "git_failed") return "unknown";
  if (step === "pr") return PR_UNKNOWN.includes(reason) ? "unknown" : "refused";
  if (PUSH_UNKNOWN.includes(reason)) return "unknown";
  if (!PUSH_ABSENT.includes(reason)) return "refused";
  return check ? "unknown" : "absent";
};
// settle: const kind = refusal ? outcome(step, answer.code, reason, check) : "unknown";
```

Комментарий 36-38 переписать по разделу 2: `store_error` (500 и нечитаемый ответ) и `git_failed`
(в том числе запись после внешнего действия) — исход неизвестен; absent после send значит «look
после push не нашёл ветку» или «чтение до push не уложилось во время»; check говорит об
отсутствии только своим `null`.

**Шаг 3. Мутанты** на копии `C:\Users\Пользователь\Documents\Codex\work\r4o2-mut\` (`src`, `tests`,
`pyproject.toml`, `PYTHONPATH` на копию; после каждого вернуть файл и сверить хэш):
- M1: строку `step === "pr"` поставить перед проверкой неоднозначности — должен упасть тест 3.
- M2: `return check ? "unknown" : "absent"` заменить на `return "absent"` — тест 2
  (`git_timed_out`).
- M3: убрать `code === "store_error" ||` — тесты 1-3 (`store_500`, `unreadable`).

**Прогоны** (каждый с `. "...\December-Command-Environment.ps1" -Quiet`; каталоги удалить):
- `python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\pt-o2a
  tests/test_desk_accept_host.py tests/test_desk_accept_publish.py
  tests/test_desk_accept_publish_signer.py tests/test_desk_accept_publish_unknown.py
  tests/test_desk_accept_terminal.py tests/test_desk_transport_accept_publish.py`
- то же с `pt-o2b` для `browser_tests/test_desk_accept_publish.py` (было 8 passed);
- `pt-o2c`: `tests/test_command_line_cap.py -k accept`.

**Критерии:** ни в одном тесте число send не растёт; после check никогда нет «Отправить снова»
или «Создать снова» без ответа `null`; новые строки ≤ 100 символов, файлы ≤ 800 строк, один `\n`
в конце, без хвостовых пробелов.

**Чего не делать:** не трогать сервер (`accept_push.py`, `accept_github.py`,
`accept_pull_request.py`), API, спецификацию, `desk-copy.js` и `studio-notice-copy.js`; не менять
signer R4-V1 (`send` 357-363, `confirmed`, `settleAbsent`, `unconfirm`,
`test_desk_accept_publish_signer.py`); не трогать `askTerms`, `makePreview`, `commit`;
не редактировать `tests/test_command_line_cap.py` (в отчёте попросить Codex внести новый модуль в
`CAPPED`); не трогать незакоммиченные R1.6 и документы; без коммита, push, stash, checkout, reset,
настоящих git push/gh и сети.
