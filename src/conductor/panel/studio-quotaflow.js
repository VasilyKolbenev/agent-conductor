"use strict";
// Serial reads and lifecycle scheduling are separate: the queue owns epochs
// and cancellation, while lifecycle owns one timer and screen visibility.
function quotaReads(door) {
  let epoch = 0, busy = false, queued = false, stop = null;
  async function pump() {
    if (busy || !queued || !door.enabled()) return;
    busy = true;
    queued = false;
    const asked = epoch;
    stop = door.stop();
    door.dispatch({type: "quotas-phase", phase: "loading"});
    let event;
    try {
      event = {type: "quotas-loaded", payload: await door.read("/command/quotas", stop)};
    } catch (_error) {
      event = {type: "quotas-phase", phase: "failed"};
    }
    if (asked === epoch && door.enabled()) door.dispatch(event);
    busy = false;
    stop = null;
    if (queued && door.enabled()) return pump();
    door.settled();
  }
  function refresh() {
    if (!door.enabled()) return;
    door.before();
    epoch += 1;
    queued = true;
    return pump();
  }
  function retire() {
    epoch += 1;
    queued = false;
    if (stop !== null) stop.abort();
  }
  return {refresh, retire};
}

export function quotaFlow(door) {
  let timer = null, disposed = false;
  function enabled() { return !disposed && door.enabled(); }
  function cancelTimer() {
    if (timer !== null) door.cancel(timer);
    timer = null;
  }
  function schedule() {
    cancelTimer();
    if (enabled()) timer = door.schedule(reads.refresh);
  }
  const reads = quotaReads({...door, enabled, before: cancelTimer, settled: schedule});
  function pause() { cancelTimer(); reads.retire(); }
  function syncQuotas() {
    if (enabled()) return reads.refresh();
    pause();
  }
  function disconnectQuotas() {
    pause();
    door.dispatch({type: "quotas-phase", phase: "disconnected"});
  }
  function disposeQuotas() { disposed = true; pause(); }
  return {refreshQuotas: reads.refresh, syncQuotas, disconnectQuotas, disposeQuotas};
}
