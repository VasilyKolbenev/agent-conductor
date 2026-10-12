"use strict";
// The words of the git block of the wizard's second step: connecting git, the first commit, the
// wait while a request works, a lost answer, an unfinished first commit and the wait for the
// owner's signature. English first, Russian second; `studio-i18n.js` spreads this catalogue into
// the one table. A count is a named parameter ("files: 4"), never a plural form.
//
// Three rules the words keep. A busy, lost or unsent word carries no figure and never says an
// outcome it does not know (nothing cancelled, nothing failed). A signature is "present, not
// verified": the product checks that a signature header is on the commit and nothing more. The
// notices of a refusal are the shared ones (`git_setup.reason.<reason>`, `error.<code>`); the
// lines here say only what the person does next.
export const WIZARD_GIT_COPY = Object.freeze({
  // -- connecting git ------------------------------------------------------------------
  "wizard.first.connect.effect": ["Connecting git runs git init in the project folder and "
    + "records who did it:", "Подключение git выполнит git init в папке проекта и запишет, кто "
    + "это сделал:"],
  "wizard.first.connect.exclude": ["It also writes a block into the repository's local exclude "
    + "file, so the product's own folders stay out of your commits.", "Оно также запишет блок в "
    + "локальный файл исключений репозитория, чтобы служебные папки продукта не попали в ваши "
    + "коммиты."],
  "wizard.first.connect.starter": ["This starter needs a repository with a first commit: "
    + "connect git, then make an empty first commit.", "Этому стартеру нужен репозиторий с "
    + "первым коммитом: подключите git, затем сделайте пустой первый коммит."],
  "wizard.first.exclude.effect": ["The product's block in the local exclude file is not written "
    + "yet. Writing it adds a few lines to .git/info/exclude and touches nothing else.",
    "Блок продукта в локальном файле исключений ещё не записан. Запись добавит несколько строк "
    + "в .git/info/exclude и больше ничего не тронет."],
  "wizard.first.exclude.button": ["Write the exclusions", "Записать исключения"],
  "wizard.first.actor": ["Your name (it signs this step)", "Ваше имя (оно подписывает этот шаг)"],
  // -- the first commit ----------------------------------------------------------------
  "wizard.first.commit.heading": ["First commit", "Первый коммит"],
  "wizard.first.commit.effect_snapshot": ["The product commits the files listed in the preview "
    + "as the first commit. It does not change your files.", "Продукт закоммитит файлы из "
    + "предпросмотра первым коммитом. Ваши файлы он не меняет."],
  "wizard.first.commit.effect_empty": ["The product makes an empty first commit: no files, only "
    + "a starting point for the agents.", "Продукт сделает пустой первый коммит: без файлов, "
    + "только точка отсчёта для агентов."],
  "wizard.first.mode.label": ["Kind of first commit", "Вид первого коммита"],
  "wizard.first.mode.snapshot": ["Snapshot of the files", "Снимок файлов"],
  "wizard.first.mode.empty": ["Empty first commit", "Пустой первый коммит"],
  "wizard.first.mode.starter": ["An empty first commit: this starter needs no files",
    "Пустой первый коммит: этому стартеру файлы не нужны"],
  "wizard.first.preview.prepare": ["Prepare a preview", "Подготовить предпросмотр"],
  "wizard.first.preview.again": ["Prepare a new preview", "Подготовить новый предпросмотр"],
  "wizard.first.preview.heading": ["Preview", "Предпросмотр"],
  "wizard.first.preview.branch": ["Branch: {ref}", "Ветка: {ref}"],
  "wizard.first.preview.author": ["Author: {name} <{email}>", "Автор: {name} <{email}>"],
  "wizard.first.preview.files": ["Files: {count}", "Файлов: {count}"],
  "wizard.first.preview.empty": ["No files: an empty first commit", "Файлов нет: пустой "
    + "первый коммит"],
  "wizard.first.preview.list_show": ["Show the list of files", "Показать список файлов"],
  "wizard.first.preview.list_hide": ["Hide the list of files", "Скрыть список файлов"],
  "wizard.first.preview.file_meta": ["bytes: {length} · mode {mode}", "байт: {length} · режим "
    + "{mode}"],
  "wizard.first.preview.manual": ["Not committed, add these yourself:", "Не попадут в коммит, "
    + "добавьте их сами:"],
  "wizard.first.confirm": ["Make the first commit", "Сделать первый коммит"],
  "wizard.first.warning.suspicious_name": ["Some file names look like secrets: check the list "
    + "before you confirm.", "Некоторые имена файлов похожи на секреты: проверьте список перед "
    + "подтверждением."],
  "wizard.first.warning.signing_required": ["Git is set to sign commits: the product will not "
    + "make this commit, you will get two commands to run.", "Git настроен на подпись коммитов: "
    + "продукт не сделает этот коммит сам, вы получите две команды для запуска."],
  "wizard.first.warning.nested_repository": ["The folder above this project is under git as "
    + "well.", "Папка выше этого проекта тоже под git."],
  "wizard.first.warning.other": ["Warning: {code}", "Предупреждение: {code}"],
  "wizard.first.manual.symlink": ["a link", "ссылка"],
  "wizard.first.manual.junction": ["a junction", "точка соединения"],
  "wizard.first.manual.reparse_point": ["a reparse point", "точка повторной обработки"],
  "wizard.first.manual.hard_link": ["a hard link", "жёсткая ссылка"],
  "wizard.first.manual.irregular_file": ["not a regular file", "не обычный файл"],
  "wizard.first.manual.unportable_name": ["a name that does not travel between systems",
    "имя, которое нельзя переносить между системами"],
  "wizard.first.manual.other": ["reason: {code}", "причина: {code}"],
  // -- why a control waits -------------------------------------------------------------
  "wizard.first.why.door_missing": ["This build of the desk has no door to the git setup step "
    + "yet.", "В этой сборке у экрана ещё нет двери к шагу подключения git."],
  "wizard.first.why.project_not_active": ["The project is open for viewing: git changes wait "
    + "until it becomes active.", "Проект открыт для просмотра: изменения git ждут, пока он "
    + "станет активным."],
  "wizard.first.why.git_reading": ["Reading the project's git state…", "Читаем состояние git "
    + "проекта…"],
  "wizard.first.why.not_offered": ["Not available in the project's present state.",
    "Недоступно при нынешнем состоянии проекта."],
  "wizard.first.why.confirm_door_closed": ["The first commit cannot be made from here yet: its "
    + "door is not open.", "Первый коммит отсюда пока нельзя сделать: его дверь ещё не открыта."],
  "wizard.first.why.busy": ["A request is working: wait for its answer.", "Запрос выполняется: "
    + "дождитесь ответа."],
  "wizard.first.why.actor_invalid": ["Type your name first: letters, digits, dot, dash, "
    + "underscore.", "Сначала введите своё имя: буквы, цифры, точка, дефис, подчёркивание."],
  "wizard.first.why.preview_missing": ["Prepare a preview first: the confirmation is for "
    + "exactly what it shows.", "Сначала подготовьте предпросмотр: подтверждение относится "
    + "ровно к тому, что он показывает."],
  // -- a request that works -----------------------------------------------------------
  "wizard.first.busy.init": ["Connecting git: working. Do not close this window.",
    "Подключаем git: идёт работа. Не закрывайте окно."],
  "wizard.first.busy.exclude": ["Writing the exclusions: working. Do not close this window.",
    "Записываем исключения: идёт работа. Не закрывайте окно."],
  "wizard.first.busy.preview": ["Preparing the preview: working. Reading a large project takes "
    + "a while.", "Готовим предпросмотр: идёт работа. Чтение большого проекта занимает время."],
  "wizard.first.busy.confirm": ["Making the first commit: working. A large project takes a "
    + "while. Do not close this window.", "Делаем первый коммит: идёт работа. Большой проект "
    + "занимает время. Не закрывайте окно."],
  "wizard.first.busy.continue": ["Continuing the first commit: working. A large project takes a "
    + "while. Do not close this window.", "Продолжаем первый коммит: идёт работа. Большой "
    + "проект занимает время. Не закрывайте окно."],
  "wizard.first.close_anyway": ["Close anyway", "Закрыть всё равно"],
  "wizard.first.close_busy": ["A request is still working. Closing the window does not stop it, "
    + "but you will not see its answer: open the wizard again to read the project.",
    "Запрос ещё выполняется. Закрытие окна его не остановит, но ответа вы не увидите: откройте "
    + "мастер снова, чтобы прочитать проект."],
  // -- an answer that did not come -----------------------------------------------------
  "wizard.first.lost.head": ["The outcome of this step is unknown: its answer did not arrive. "
    + "Nothing is sent again by itself.", "Исход этого шага неизвестен: ответ не пришёл. Само "
    + "ничего не отправляется повторно."],
  "wizard.first.lost.reading": ["Reading the project to find out…", "Читаем проект, чтобы "
    + "выяснить…"],
  "wizard.first.lost.pending": ["The project keeps a first commit the product did not finish. "
    + "It is shown below.", "В проекте есть первый коммит, который продукт не закончил. Он "
    + "показан ниже."],
  "wizard.first.lost.done": ["The project shows that the step was done.", "Проект показывает, "
    + "что шаг выполнен."],
  "wizard.first.lost.none": ["The project shows no record of this step. You may press the "
    + "button again.", "В проекте нет записи об этом шаге. Кнопку можно нажать снова."],
  "wizard.first.lost.other": ["The project is in a state this step does not explain: read what "
    + "the block above says.", "Проект в состоянии, которое этот шаг не объясняет: прочитайте, "
    + "что сказано в блоке выше."],
  "wizard.first.lost.nothing_written": ["A preview writes nothing. Prepare it again if you "
    + "need it.", "Предпросмотр ничего не пишет. Подготовьте его снова, если он нужен."],
  "wizard.first.unsent.route_not_found": ["Nothing was sent: this build of the desk has no "
    + "door to the git setup step.", "Ничего не отправлено: в этой сборке у экрана нет двери "
    + "к шагу подключения git."],
  "wizard.first.unsent.project_mismatch": ["Nothing was sent: this window belongs to another "
    + "project.", "Ничего не отправлено: это окно относится к другому проекту."],
  // -- what was done -------------------------------------------------------------------
  "wizard.first.done.init": ["Git is connected: the project is now a repository.",
    "Git подключён: проект теперь репозиторий."],
  "wizard.first.done.exclude": ["The exclusions are written to the local exclude file.",
    "Исключения записаны в локальный файл исключений."],
  "wizard.first.done.confirm": ["The first commit is made on {ref}: commit {commit}, files: "
    + "{count}.", "Первый коммит сделан в {ref}: коммит {commit}, файлов: {count}."],
  "wizard.first.done.signature_present": ["Signature present, not verified.",
    "Подпись есть, не проверена."],
  "wizard.first.tool": ["Tool: {tool} ({reason})", "Инструмент: {tool} ({reason})"],
  // -- what to do after a refusal ------------------------------------------------------
  "wizard.first.next.already_git": ["The folder is already a repository: read the state again.",
    "Папка уже репозиторий: перечитайте состояние."],
  "wizard.first.next.not_a_git_repository": ["Connect git first, then try again.",
    "Сначала подключите git, потом повторите."],
  "wizard.first.next.project_not_repo_root": ["The project folder must be the root of its "
    + "repository: choose the root as the project.", "Папка проекта должна быть корнем своего "
    + "репозитория: выберите корень как проект."],
  "wizard.first.next.tracks_product_dir": ["Stop tracking the product's own folders in git, "
    + "then read the state again.", "Перестаньте отслеживать служебные папки продукта в git и "
    + "перечитайте состояние."],
  "wizard.first.next.unsafe_directory": ["Tell git to trust this folder with the command shown "
    + "above, then read the state again.", "Разрешите git доверять этой папке командой выше и "
    + "перечитайте состояние."],
  "wizard.first.next.unsafe_git_route": ["The product does not write through a link or a "
    + "linked worktree in git's folder: use a plain repository.", "Продукт не пишет через "
    + "ссылку или связанное рабочее дерево в папке git: используйте обычный репозиторий."],
  "wizard.first.next.git_exclude_failed": ["Nothing else was changed. Make .git/info writable, "
    + "then write the exclusions again.", "Больше ничего не изменено. Сделайте .git/info "
    + "доступной для записи и запишите исключения снова."],
  "wizard.first.next.git_identity_missing": ["Set user.name and user.email in git in a "
    + "terminal, then prepare a new preview.", "Задайте user.name и user.email в git в "
    + "терминале и подготовьте новый предпросмотр."],
  "wizard.first.next.head_exists": ["Nothing was changed. The branch already holds a commit the "
    + "product did not make, and the product never moves or removes a branch.",
    "Ничего не изменено. В ветке уже есть коммит, который сделал не продукт, а продукт никогда "
    + "не переносит и не убирает ветку."],
  "wizard.first.next.head_exists_signing": ["The branch already holds a commit that is not the "
    + "one the two commands make, an unsigned commit included. Nothing was changed and the wait "
    + "stays. The product never moves or removes a branch: make sure the branch holds the commit "
    + "made by the two commands, then check again.", "В ветке уже есть коммит, который сделан не "
    + "этими двумя командами, в том числе неподписанный. Ничего не изменено, ожидание остаётся. "
    + "Продукт никогда не переносит и не убирает ветку: проверьте, что в ветке коммит, сделанный "
    + "двумя командами, и проверьте снова."],
  "wizard.first.next.index_exists": ["Your staged work was left untouched. Commit it or "
    + "unstage it yourself, then prepare a new preview.", "Ваши подготовленные изменения не "
    + "тронуты. Закоммитьте их или снимите с подготовки сами и подготовьте новый предпросмотр."],
  "wizard.first.next.index_locked": ["Another git process holds the index. Try again when it is "
    + "done.", "Другой процесс git держит индекс. Повторите, когда он закончит."],
  "wizard.first.next.too_many_files": ["Exclude or move some files (the limit is 5000), then "
    + "prepare a new preview.", "Исключите или уберите часть файлов (предел 5000) и "
    + "подготовьте новый предпросмотр."],
  "wizard.first.next.paths_changed": ["The files changed since the preview: prepare a new "
    + "one.", "Файлы изменились после предпросмотра: подготовьте новый."],
  "wizard.first.next.setup_damaged": ["Nothing was deleted. This version has nothing safe to "
    + "send: look at the project's git yourself.", "Ничего не удалено. В этой версии нечего "
    + "безопасно отправить: посмотрите git проекта сами."],
  "wizard.first.next.setup_terms_changed": ["Another name or git author is acting now, and a "
    + "confirmation is not inherited. Only the person who confirmed this step can finish it, "
    + "under their own name. If the git author changed, set user.name and user.email back.",
    "Сейчас действует другое имя или другой автор git, а чужое подтверждение не наследуется. "
    + "Закончить шаг может только тот, кто его подтвердил, под своим именем. Если автор git "
    + "изменился, верните прежние user.name и user.email."],
  "wizard.first.next.task_run_active": ["A run holds the project: wait for it, then try "
    + "again.", "Проект занят запуском: дождитесь его и повторите."],
  "wizard.first.next.git_failed": ["Git did not answer: check git in a terminal, then read the "
    + "state again.", "Git не ответил: проверьте git в терминале и перечитайте состояние."],
  "wizard.first.next.git_timed_out": ["Git did not finish in time. You may press the button "
    + "again.", "Git не успел закончить. Кнопку можно нажать снова."],
  "wizard.first.next.signing_required": ["Run the two commands shown below in the project "
    + "folder, then check again.", "Выполните две команды ниже в папке проекта и проверьте "
    + "снова."],
  "wizard.first.next.signing_ref_unsupported": ["Rename the branch to letters, digits, dot, "
    + "dash, underscore and slash only, then prepare a new preview.", "Переименуйте ветку, "
    + "оставив буквы, цифры, точку, дефис, подчёркивание и косую черту, и подготовьте новый "
    + "предпросмотр."],
  // -- an unfinished first commit and the wait for a signature --------------------------
  "wizard.first.pending.unfinished": ["The product started a first commit and did not finish "
    + "it. These are the terms it stored:", "Продукт начал первый коммит и не закончил его. "
    + "Вот условия, которые он сохранил:"],
  "wizard.first.pending.awaiting_signature": ["The product stored a first commit and waits for "
    + "your signature. These are the terms it stored:", "Продукт сохранил первый коммит и ждёт "
    + "вашу подпись. Вот условия, которые он сохранил:"],
  "wizard.first.pending.damaged": ["A saved record of a first commit cannot be proven. This "
    + "version has no way forward from here.", "Сохранённую запись первого коммита подтвердить "
    + "нельзя. В этой версии отсюда нет пути дальше."],
  "wizard.first.pending.unreadable": ["The project sent a record of a first commit this desk "
    + "cannot read. Nothing is sent from here.", "Проект прислал запись первого коммита, "
    + "которую экран не может прочитать. Отсюда ничего не отправляется."],
  "wizard.first.pending.by": ["Confirmed by: {name}", "Подтвердил: {name}"],
  "wizard.first.continue": ["Continue", "Продолжить"],
  "wizard.first.check_again": ["Check again", "Проверить снова"],
  "wizard.first.sign.intro": ["Run these two commands in a terminal in the project folder. The "
    + "product never signs and never makes this commit itself.", "Выполните эти две команды в "
    + "терминале в папке проекта. Продукт никогда не подписывает и не делает этот коммит сам."],
  "wizard.first.sign.commit": ["1. Make the signed commit; it prints an id:", "1. Сделайте "
    + "подписанный коммит; он напечатает идентификатор:"],
  "wizard.first.sign.update": ["2. Put the branch on it:", "2. Поставьте на него ветку:"],
  "wizard.first.sign.label_commit": ["Command 1: make the signed commit", "Команда 1: сделать "
    + "подписанный коммит"],
  "wizard.first.sign.label_update": ["Command 2: put the branch on the commit", "Команда 2: "
    + "поставить ветку на коммит"],
  "wizard.first.sign.oid": ["Replace <oid> in the second command with the id the first command "
    + "printed.", "Замените <oid> во второй команде на идентификатор, который напечатала "
    + "первая."],
  "wizard.first.sign.level": ["The product checks only that a signature is present on the "
    + "commit. It does not verify the signature or trust the key.", "Продукт проверяет только, "
    + "что на коммите есть подпись. Подпись он не проверяет и ключу не доверяет."],
});
