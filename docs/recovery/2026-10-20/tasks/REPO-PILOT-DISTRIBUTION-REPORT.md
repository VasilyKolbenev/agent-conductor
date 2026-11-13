# Windows Pilot 1 из GitHub Releases

14 ноября 2026 года в 00:31 МСК опубликован [Windows Pilot 1](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.0-pilot.1).
Его ZIP повторно собран побайтно из чистого Git-экспорта
рецепта `cd028f7` и исходного CI-wheel продукта `7f6b825`.

| Файл | SHA-256 |
| --- | --- |
| Arachnid-Windows-Pilot-7f6b825.zip | `7bff7440611c009782885d7eb47d1e4aef48efa42a56f6aa2ac40005dc468dd2` |
| agent_conductor-0.1.0-py3-none-any.whl | `214bf5e5beb0822f4616ded0dce44161e76e1f9d557d9c5507ec40939acd40fe` |

В GitHub Releases доступны ZIP, его SHA-256, сам wheel и START-HERE.txt. Тег
`v0.1.0-pilot.1` указывает на исходный SHA `7f6b8254d2d621af4b636aa9eef1997f17f68ad6`.
По решению владельца выпуск доступен публично с пометкой Pre-release. Приёмка версии 2.0
ведётся отдельно в [плане альфы](../../../plans/2026-11-13-v2-alpha-review.ru.md).

## Что проверено

- Из коммита с рецептом выполнен `git archive`. Из распакованных исходников сборщик
  на Windows создал ZIP размером 2 236 768 байт. После публикации ZIP скачан
  по прямой ссылке без входа в GitHub. Размер и SHA-256 совпали с локальной сборкой.
- В ZIP десять файлов, учебный проект содержит 19 файлов. Проверены CRC внешнего
  и внутреннего архивов. В независимом экспорте с `core.autocrlf=true` байты совпали.
- Подмена wheel, изменение учебного примера и изменение времени ZIP привели к отказам
  до замены выходного файла. Девять проверок окончаний файлов прошли после коммита.
- Чистая установка и просмотр Codex + Grok описаны в [отчёте репетиции](COLLEAGUE-WINDOWS-PACK-REPORT.md).
  Повторная упаковка исходного wheel не запускала модели.

[Рецепт сборки](../../../../distribution/windows-pilot/README.md) ·
[Исходный CI](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/43454184474).
