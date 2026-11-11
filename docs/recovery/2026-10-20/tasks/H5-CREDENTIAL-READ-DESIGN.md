# H5-CREDENTIAL-READ: дизайн v2

A: сохранить тип tuple[bytes], как login_relay.every_text кодировать surrogatepass;
итерировать parsed tree стеком DFS в прежнем порядке. Корректный Unicode побайтно
прежний, некорректный scalar не удаляет себя или валидный token рядом с ним.
JSON file size и parser bounds прежние; не добавлять silently-skipping depth cutoff.

B: новый typed unreadable result и сквозной отказ publication под lease.
Этот контракт связан с отдельным Q10 и существующим test, который допускает
нечитаемый login после admitted preflight. Его нельзя честно исправить локальным
catch-return-empty без изменения нескольких путей и тестов границы полномочий.

Выбор A для RS1: total string collection без нового разрешения/обхода и без
расширения whitelist. Q10 сохраняется отдельным открытым gate.
Независимые линзы native_test_runner_v2 (callers/lease) и do_rejected_inspector
(безопасность/стандарт); v2 перед кодом учитывает замечания.

Public seam credential_values на настоящем временном declared JSON с fake values:
12 lone surrogate + валидный сосед -> оба представлены bytes, нет исключения,
порог/дубликаты прежние. Deep test обязан явно назвать предусловия parser boundary;
нельзя называть синтетический parsed tree живым сбойным файлом Python 3.12.
Мутанты ловят игнорирование плохого scalar, no-op и возврат строгого encoding.
Caller quota masking остаётся строгим и не меняется; отказ metadata не ослаблять.

## Уточнение по независимым линзам до кода

1.1 native_test_runner_v2: deep600 не воспроизведён на 3.12.14; не рефакторить
walker без различающего RED. В этой итерации заменить только строгий encoding
подтверждённого surrogate-сбоя. Recursive traversal и его платформенное измерение
остаются в исходном RS1, статус этого полного долга не перескакивает в закрыт.
1.2: непрочитанный файл по прежнему контракту возвращает пустой scan; изменять это
значит решать Q10. В этой итерации не добавлять новый catch/skip или admission.
2.1 do_rejected_inspector: отдельное независимое ревью безопасности/контракта
для узкого варианта до исполнения; итог будет записан в отчёте.

TASK в части iterative traversal/его мутанта сужен этим v2: только доказанный
surrogate error; существующий tuple bytes/порог/дедуп/валидные соседи сохраняются.
