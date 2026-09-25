# Acceptance: two tasks, one team, nothing mixed

Russian version: [acceptance-two-tasks.ru.md](acceptance-two-tasks.ru.md).

`docs/owner-acceptance.md` walks one task from a blank workflow to a verified result. This script asks the
question the V1 scope adds on top of it: **when two tasks run the same workflow with the same team, does
anything of one show up in the other?** Ten steps. Every step names what you must see. A step you cannot
complete from the screen alone is a finding, and the finding is the product's.

The words in quotation marks are the product's own labels, English first and Russian in parentheses, as the
Studio shows them with the language switched. You never open a text editor or a terminal log; the shell is
used only to install and start the product, exactly as in [first-run-v1.en.md](first-run-v1.en.md).

## 1. Start with a clean project and an open Studio

Follow [first-run-v1.en.md](first-run-v1.en.md) through `conduct up`: a new project, `ownership status`
reporting `active`, providers configured, the Studio open in a browser.

**You must see** the five screens across the top: "Overview" (Обзор), "Workflow" (Процесс), "Runs" (Запуски),
"Decisions" (Решения), "Agents" (Участники), and the "Theme" and "Language" selectors beside each other in the
header. Switch the language to Russian and back once: every screen label changes, and nothing you typed is lost.

## 2. Publish one workflow revision

On "Workflow" (Процесс), start from the offered standard cycle («Стандартный цикл», revision 5) and publish it
with "Publish revision" (Опубликовать версию) without changing it. If you have already published a revision in
this project, use that one; the test needs one immutable revision that both runs will share.

**You must see** the revision listed under the published revisions with a number, and the draft unchanged.

## 3. Create two tasks

On "Runs" (Запуски), in the task rail on the left, press "New task" (Новая задача), type `Task A — payment
config` into "Task name" (Название задачи), press "Create task" (Создать задачу). Repeat for `Task B — release
notes`.

**You must see** both tasks in the rail, each with "No outcome recorded" beneath it, and "Task creation history"
(История создания задач) listing both creations in order. Creating a task opened no run and started no work.

## 4. Open a run for each task with the same team

Select Task A in the rail, press "Create a new run" (Создать новый запуск), choose the revision from step 2,
keep "Confirm each step" (Подтверждение шагов) as the mode, assign every role to a configured provider, and
press "Open the run" (Создать запуск). Then select Task B and open a run against the **same** revision with the
**same** assignments.

**You must see**, after each opening, the sentence that the run is open with its task, participants and plan
frozen and that nothing has executed; and in the rail, the task you selected shows that run as its newest.
Selecting Task A now shows run A, selecting Task B shows run B. "All tasks" (Все задачи) lists both runs under
"Switch run" (Другой запуск).

## 5. Read the two run teams

With run A on screen, look at "Run team" (Команда запуска): the "Trace" (Трасса) lens shows the plan on the
horizon with the human decisions on their own contour beneath it; "Orbit" (Орбита) shows the same participants
on a ring with the decisions on the outer contour. Select a participant; the inspector under the scene opens
on it. Switch to run B.

**You must see** the same participant names in both runs and the same plan, and the inspector of run B
opening on run B's participant with no step or document of run A in its "Input" or "Result" stages. Each run's
"Your controls" (Ваш пульт) says "No action is needed" (Ваше действие не требуется) — no step has been proposed.

## 6. Publish a document into run A only

In run A, on the first step's stage, use "Publish a document" (Опубликовать документ) to publish an instruction
document with the reference the step expects and a sentence that names Task A. Switch to run B.

**You must see** the document under run A's step as its input source ("Sources: 1" (Источники: 1)), and run
B's same step still reporting "No recorded document" (Документ не записан) for that reference. Read run B again with "Read runs again" (Перечитать запуски):
still nothing of Task A.

## 7. Propose and confirm the first step of run A only

In run A, press "Propose this step" (Предложить этот шаг) on the first step, fill in who proposes and why, and
then "Confirm this proposal" (Подтвердить это предложение) and "Confirm and authorize" (Подтвердить и
разрешить). Switch to run B.

**You must see** run A's step reported as awaiting its result (or already settled, if the provider answered),
and run B's first step still "Ready in the plan" (Готов по плану) with no proposal, no attempt and no result.
Run B's "Your controls" still says no action is needed. The "Attention queue" (Очередь внимания) names run A
only if run A is now waiting for you, and never names run B for something that happened in run A.

## 8. Words typed in run B survive a switch to run A

In run B, start a proposal on the first step and type a rationale, but do not send it. Switch to Task A and run
A, then back to Task B and run B.

**You must see** the words exactly as you typed them, still unsent. Now send it, and while the answer is
arriving switch tasks again: whatever the answer is, it lands on run B's step and on nobody else's; the status
line never announces run B's outcome on run A's screen.

## 9. Decide at a gate in one run only

Drive run A until its first human gate waits for you ("Decision needed" (Нужно решение) on the gate, "You are
needed" (Нужно ваше участие) in "Your controls"). On "Decisions" (Решения), answer that gate. Return to run B.

**You must see** run A's gate reported as answered with your reason, run B's gate untouched and still not
open, and the attention queue no longer naming run A for that gate.

## 10. Reload, reconnect, and read the shared usage

Reload the page with run B selected. Then open "Agents" (Участники).

**You must see** Task B and run B selected again after the reload. The lens is back on "Trace", and the selected
participant is the one at the run's current position (or the first), not the one you picked: which lens and
whom you were inspecting live only in the open window and are not kept across a reload (§4.8 of the agreed UI
spec). And under "Usage now" (Ресурсы сейчас), one reading per connected provider — opening the second
run added no row and doubled no number, and readings for a provider whose account is unknown are marked as
shown separately, never merged.

## The verdict

Every "you must see" above is a fact the screen shows or a fact it refuses to invent. Anything else — a
document, a proposal, a decision or a status sentence of one task appearing under the other; unsent words
lost on a task switch; a late answer landing on the wrong run — is a release blocker for the two-task
requirement, and the finding is recorded against the run and step where it appeared.

## What this script does not cover

Two people operating two tasks at once from two browsers; two servers on one project (`conduct up` refuses the
second with `owner_busy`, which is the ownership layer's own script); bounded automatic runs (the Policy mode
has its own preview and permission road); Linux and macOS.
