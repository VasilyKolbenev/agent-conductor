# ALPHA-CORE-REPAIR — дизайн v3

## Контракт и варианты

A (выбран): pure account-proof helper целиком перенести в adapters; payload,
hash domain, closed validation, freeze и unverified evidence остаются побайтно
прежними. ArtifactHandoff импортирует owning adapter value module, relay_attempt
использует sibling import. CAPPED и внутренние tests imports следуют за файлом.
Это устраняет vendor literals в request-path и SDK upward import без guard waiver.

B: разделить neutral proof model и provider mapping через registry. Отклонён:
новый интерфейс и больший diff без второго потребителя/необходимости менять поведение.
Старый module не объявлен публичным SDK API; compatibility shim не нужен.

## Фикстуры и стражи

Partial Checker должен вызывать настоящий LoginRoad reset/account hook с явно
отсутствующим account proof, иметь действительный verifier identity. Не добавлять
production getattr(False), не подменять check outcome/events/runtime substitution.

Evidence census проверяет exact prepared seal/verification и отдельно ровно два
Q6 subscription_account_v1/unverified с actor/role/request/attempt bindings.
Не фильтровать все None или все unverified: это спрятало бы потерю/подмену provenance.

Login fixtures создают plain fake primary credential в реальном tmp_path и pin
именно его. Seed действует на ВСЕ cases method/config parametrization, чтобы
negative tests ловили свой запрет, а не ранний Q10 refusal. Tokens только fake.
Snapshots: адресно изменить два Claude facts по утверждённому ALPHA-AUTH-CLOSE;
сохранить strict equality, остальные snapshots и все existing deny assertions.

## Швы и пределы доказательств

- Два существующих architecture guards ловят placement/import; positive account
  tests доказывают сохранение proof semantics, не server identity.
- Полные login modules ловят allowed/denied configs, env и pinned homes; fake CLI
  не доказывает реальную подписку/доступность vendor.
- Existing checker/census tests плюс Q6/Q10 guards ловят exact evidence/state,
  read-back refusal и сохранение test-before-checker порядка. Не live boundary proof.
- Golden equality ловит drift всей модели фактов; mutation утверждённого Q8 поля
  должен снова сделать snapshot красным.
- Full core в двух modes не заменяет остальные OS/browser/installed/owner gates.

До реализации: две независимые линзы (границы source/SDK и достоверность fixtures),
находки обозначить A1/B1; v2 с ответами коммитом. Затем ограниченный diff,
targeted checks/mutants/cross-review, новый immutable candidate/core/conditionalCI.

## Ревью v1 и решения v2

A1 принят: byte SHA helper до/после одинаков; оба imports остаются deferred,
без adapters.__init__ re-export. Существующие SDK stdlib/sibling guards достаточны.
A2 принят: полный rg census — два product imports, два test imports, один CAPPED
path; старый путь не опубликован, pickle/importlib/entry-point зависимостей нет.
B1 принят: кроме точных seal/verification и двух Q6 rows сохранить общий evidence
count и запрет любых лишних rows; account rows связаны с durable request_ref,
action/attempt и actor/role. Один filter/count недостаточен.
B2 принят: реальные LoginRoad reset/account hooks, явно None proof и действительный
verifier.instance_id; без production defaults или no-op account override.
Обе линзы дали GO, blockers нет; root утвердил выбранный вариант A.

## C1: валидное наблюдение heartbeat

По trace последняя read_int вернула None; OS-причина неизвестна. По коду текущий
while считает None!=before ростом, затем повторное чтение теряет уже наблюдённый
результат. Даже initial baseline теряется после wait_for_int из-за нового read.
A выбран: использовать возвращённый wait_for_int int как baseline, в прежнем
5-секундном окне получать по одному sample, считать доказательством только sample
не None и >baseline, проверять сохранённый sample без нового чтения после loop.
B отклонён: менять atomic writer/read_int или подавлять None в последнем assert —
OS-причина не измерена, а подавление не доказывает живое потомство.
Новые детерминированные случаи через InterruptedRun.spawn/owned.proc.wait должны
поймать transient unknown/last-reread и fail-closed never-progress. Existing real
четыре interruption случая сохраняют точные identity/token/thread/beat assertions.
Независимое чтение C1 до реализации; новый факт допускает этот дополнительный срез.

C1.1 независимо подтверждён, GO: контракт int|None и atomic writer не менять.
C1.2 принят: отдельно проверить transient None, valid growth без последнего
reread, persistent None и stagnant/decreasing ints. Два последних обязаны дать
именованный отказ о прогрессе в прежний deadline, не synthetic interruption.
Root утвердил реализацию только observer/test seam; real retirement cases прежние.
