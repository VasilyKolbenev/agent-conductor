# H5-CREDENTIAL-READ: дизайн v1

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
Мутанты ловят игнорирование плохого scalar, no-op и возврат recursive traversal.
Caller quota masking остаётся строгим и не меняется; отказ metadata не ослаблять.
