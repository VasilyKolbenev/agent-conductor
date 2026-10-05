"use strict";
// The reads that establish whether a task was closed (spec 5.4: "closed" is a run accepted at its
// final gate). No list the desk reads carries that fact -- a plan that ended `complete` may have
// been approved or refused -- so the run itself is read, and only when its row says it could have
// been accepted (`mayBeClosed`: nothing open, no step asking a person, some action with a result)
// and only for the newest run of a task. A finished project therefore costs one read per finished
// task in every load of the lists (the boot's, each full refresh the stream asks for, the run
// panel's refresh, the wizard's exit): nothing is kept from one load to the next, and a project
// with nothing finished costs none.
//
// The reads go through the door the boot module hands in, so a refusal that says the desk is open
// for another project ends it in the one place that knows how. What a read brought is judged as
// the scene judges a run (`projectRunRead`), and must belong to the task and the run that were
// asked about; anything else, a failed read included, establishes nothing about that task and
// disturbs no other. The answer is a map from task id to the run's digest.
import {digestOf, mayBeClosed} from "./desk-summary-model.js";
import {newestRun} from "./studio-taskruns.js";
import {projectRunRead} from "./studio-situation.js";

//: One newest run, read: its digest, or null when the read establishes nothing.
async function digestFor(read, taskId, runId) {
  try {
    const body = await read(runId);
    if (projectRunRead(body) === null || body.config?.task?.id !== taskId) return null;
    const digest = digestOf(body);
    return digest !== null && digest.run_id === runId ? digest : null;
  } catch (_error) {
    return null;
  }
}

//: The newest run of each readable task that could have been accepted, in the list's order.
function candidates(tasks, runs) {
  return tasks.list.filter((task) => !task.unreadable)
    .map((task) => [task.task_id, newestRun(runs, task.task_id)])
    .filter(([, latest]) => latest.state === "known" && mayBeClosed(latest.row))
    .map(([taskId, latest]) => [taskId, latest.row.run_id]);
}

//: One task with the digest its newest run's read gave, or null.
async function ask(read, taskId, runId) {
  return [taskId, await digestFor(read, taskId, runId)];
}

//: `input.read(runId)` answers a run read or throws; `input.stopped()` says the desk has ended,
//: and then nothing is asked. A list that was not read holds no task, and the newest run of
//: anything is not established without the run list, so such a desk asks for nothing either.
export async function readClosing(input) {
  const {read, tasks, runs, stopped} = input;
  const found = new Map();
  if (stopped()) return found;
  const asked = await Promise.all(candidates(tasks, runs)
    .map(([taskId, runId]) => ask(read, taskId, runId)));
  for (const [taskId, digest] of asked) if (digest !== null) found.set(taskId, digest);
  return found;
}
