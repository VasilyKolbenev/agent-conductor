# TEST-FAKE-SEAM — задание исполнителю (Sonnet), 30.10.2026

Ведущий — Opus 5.5 (PROC-NO-CODEX). Основание: два красных полного core только в cp1251 —
`test_login_ownership.py::test_two_real_projects_share_one_resource_through_post_spawn_cleanup`
(`56d0a22`, «причина не установлена») и
`test_relay_road_lifecycle.py::test_the_home_left_standing_stops_the_next_road_until_it_can_be_removed`
(`14f94cf`, `work\lead-final4\cp1251-chunk0.log`: `OSError [WinError 4551]` при запуске фейкового
`claude.exe`, затем `recovery_required`).

## Причина (по коду, ведущий)

На Windows неподписанный PE фейков запускать нельзя: шов `tests/_fakeprocess.py` подменяет
`subprocess.Popen` и запускает зарегистрированный фейк текущим Python. Шов ставит
`tests/conftest.py` через фикстуру `monkeypatch` — ту же, что получает тест. Поэтому:

1. тест, вызвавший `monkeypatch.undo()` (`test_relay_road_lifecycle.py:234` и ещё около 15 мест),
   снимает и шов: следующий запуск фейка уходит в настоящий PE, и App Control Windows то пропускает
   его, то блокирует (WinError 4551) — отсюда красный только в одном из двух прогонов;
2. дочерний интерпретатор `python -c ...` (`test_login_ownership.py:29`, `ATTEMPT`) строит фейк
   через `a_harness`, но шва в нём нет вовсе.

## Сделать

1. `tests/conftest.py`: шов ставится собственным `pytest.MonkeyPatch.context()` (или эквивалентом),
   не общей фикстурой `monkeypatch`; `undo()` теста его не снимает. Поведение вне Windows прежнее.
2. Дочерние интерпретаторы, которые запускают зарегистрированные фейки (найти все: `sys.executable,
   "-c"` и подобное рядом с `a_harness`, `Site`, `_fakeexe`), ставят шов сами в начале своего кода
   (`subprocess.Popen = _fakeprocess.popen_for(subprocess.Popen, windows=os.name == "nt")`).
   Детей, которые фейки не запускают, не трогать.
3. Свидетели, красные до правки на сравнении: (а) после `monkeypatch.undo()` в тесте
   `subprocess.Popen` на Windows всё ещё обёртка шва; (б) код `ATTEMPT` (и каждого найденного
   ребёнка) ставит шов — проверка, что запуск фейка в ребёнке идёт через `sys.executable` (например,
   фейк сообщает своё `sys.executable`/`argv[0]`, или ребёнок печатает тип `subprocess.Popen`).
   Мутанты в копии по стандарту §3 (шов снова через общую фикстуру; ребёнок без шва).

## Можно трогать

`tests/conftest.py`, `tests/_fakeprocess.py` (только если нужно), `tests/test_login_ownership.py`,
другие тестовые файлы с найденными детьми — каждый назвать в отчёте; новый тест-свидетель (в
`CAPPED`). `src/` — нельзя (стоп).

## Проверка

Затронутые файлы и все тесты с `monkeypatch.undo()` — `run-scoped.ps1` в обеих кодировках; полный
core — ведущий на итоговой версии.
