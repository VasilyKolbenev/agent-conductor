"""Stream frames trigger reads; disconnects retire answers and session authority."""
from tests.desk_node import run_js

MODULES = {"stream": "desk-stream.js"}
RIG = r"""
const events = new Map(), reads = [], connections = [];
let drops = 0, closes = 0, foreign = 0, opens = 0;
const source = {
  addEventListener: (kind, fn) => events.set(kind, fn),
  removeEventListener: (kind, fn) => { if (events.get(kind) === fn) events.delete(kind); },
  close: () => { closes += 1; },
};
const emit = (kind, data) => events.get(kind)?.({data: JSON.stringify(data)});
const flush = async () => { for (let i = 0; i < 8; i += 1) await Promise.resolve(); };
const door = {openStream: () => { opens += 1; return source; },
  dropSession: () => { drops += 1; }};
const live = stream.connectDeskStream({door,
  refresh: ({runId, current}) => new Promise((resolve, reject) => {
    reads.push({runId, current, resolve, reject});
  }),
  onConnection: (value) => connections.push(value), onForeign: () => { foreign += 1; }});
"""


def probe(body):
    return run_js(RIG + body, MODULES)


def test_reconnect_requires_a_new_read_and_cannot_apply_the_old_answer():
    found = probe(r"""
emit('open');
const first = reads[0];
emit('error');
emit('open');
const before = {oldCurrent: first.current(), reads: reads.length,
  status: connections.at(-1), drops};
first.resolve(true);
await flush();
const afterOld = {reads: reads.length, status: connections.at(-1)};
reads[1].resolve(true);
await flush();
console.log(JSON.stringify({before, afterOld, status: connections.at(-1), opens}));
""")
    assert found == {"before": {"oldCurrent": False, "reads": 1,
                                 "status": "connecting", "drops": 1},
                     "afterOld": {"reads": 2, "status": "connecting"},
                     "status": "open", "opens": 1}


def test_frames_coalesce_to_one_full_read_and_carry_no_displayed_facts():
    found = probe(r"""
emit('open');
emit('message', {kind:'run', run_id:'run-a', status:'succeeded'});
emit('message', {kind:'run', run_id:'run-b'});
emit('message', {kind:'state'});
emit('message', {kind:'run', run_id:'run-c'});
const countWhileHeld = reads.length;
reads[0].resolve(true); await flush();
reads[1].resolve(true); await flush();
emit('message', {kind:'run', run_id:'run-z'});
console.log(JSON.stringify({countWhileHeld, targets:reads.map(row => row.runId)}));
""")
    assert found == {"countWhileHeld": 1, "targets": [None, None, "run-z"]}


def test_unknown_or_malformed_frames_start_no_read_and_a_failed_read_is_not_live():
    found = probe(r"""
emit('open'); reads[0].resolve(false); await flush();
for (const frame of [null, [], {}, {kind:'quota'}, {kind:'run', run_id:1},
  {kind:'run', run_id:'../outside'}]) emit('message', frame);
events.get('message')({data:'{broken'});
console.log(JSON.stringify({reads:reads.length, status:connections.at(-1)}));
""")
    assert found == {"reads": 1, "status": "closed"}


def test_a_foreign_project_ends_even_a_read_retired_by_reconnection():
    found = probe(r"""
emit('open'); emit('error'); emit('open');
reads[0].reject(new Error('project_mismatch')); await flush();
emit('open'); emit('message', {kind:'state'});
console.log(JSON.stringify({foreign, closes, listeners:events.size,
  reads:reads.length, current:reads[0].current()}));
""")
    assert found == {"foreign": 1, "closes": 1, "listeners": 0,
                     "reads": 1, "current": False}


def test_dispose_prevents_pending_answers_from_reopening_and_closes_once():
    found = probe(r"""
emit('open'); emit('message', {kind:'state'});
live.dispose(); live.dispose();
const count = connections.length;
reads[0].resolve(true); await flush();
emit('error'); emit('open');
console.log(JSON.stringify({closes, listeners:events.size, drops,
  unchanged:connections.length === count, reads:reads.length, current:reads[0].current()}));
""")
    assert found == {"closes": 1, "listeners": 0, "drops": 0,
                     "unchanged": True, "reads": 1, "current": False}
