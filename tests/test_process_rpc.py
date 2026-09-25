"""Actual children must answer before EOF; each exit retires both I/O threads."""
from dataclasses import replace
import sys

import pytest

from conductor.command.adapters.process import CommandSpec, CommandSpecError, ProcessRunner
from conductor.command.adapters import process


CHILD = '''import sys,time
mode=sys.argv[1]
sys.stdin.buffer.readline()
if mode=='partial': sys.stdout.buffer.write(b'{"id":3');sys.stdout.flush()
elif mode=='malformed': print('not JSON',flush=True)
elif mode=='stderr': print('{"id":3,"result":{}}',file=sys.stderr,flush=True)
elif mode=='overflow': print('x'*70000,flush=True)
elif mode!='silent':
    body=b'{"id":3,"error":{"code":-1}}\\n' if mode=='error' else b'{"id":3,"result":{}}\\n'
    for part in (body[:5],body[5:]): sys.stdout.buffer.write(part);sys.stdout.flush()
if mode in ('silent','partial','stderr'): time.sleep(20)
else:
    rest=sys.stdin.buffer.read()
    sys.exit(0 if rest==b'' else 9)
'''


def setup(tmp_path, mode, timeout=3):
    (tmp_path / 'work').mkdir()
    child = tmp_path / 'child.py'
    child.write_text(CHILD, encoding='utf-8')
    runner = ProcessRunner(tmp_path, environ={})
    spec = CommandSpec((sys.executable, str(child), mode), 'work', stdin_bytes=b'{}\n',
        separate_stderr=True, stdin_completion_id=3, timeout_seconds=timeout)
    held = []
    actual = runner._spawn
    def spawn(spec):
        owned = actual(spec)
        held.append(owned)
        return owned
    runner._spawn = spawn
    return runner, spec, held


def retired(runner, held):
    assert runner.active_tokens() == ()
    assert len(held) == 1
    child = held[0]
    assert child.proc.poll() is not None
    assert not child._pump.is_alive() and not child._feeder.is_alive()


@pytest.mark.parametrize('mode', ['valid', 'error'])
def test_native_response_releases_eof_without_waiting_for_child_exit(tmp_path, mode):
    runner, spec, held = setup(tmp_path, mode)
    outcome = runner.run(spec)
    assert (outcome.status, outcome.exit_code, outcome.stdin_state) == ('completed', 0, 'delivered')
    assert b'"id":3' in outcome.output
    retired(runner, held)


@pytest.mark.parametrize('mode', ['malformed', 'overflow'])
def test_bad_stream_closes_input_but_never_claims_rpc_input_complete(tmp_path, mode):
    runner, spec, held = setup(tmp_path, mode)
    outcome = runner.run(spec)
    assert outcome.stdin_state == 'incomplete'
    assert outcome.status == 'completed'
    retired(runner, held)


@pytest.mark.parametrize('mode', ['partial', 'stderr', 'silent'])
def test_partial_stderr_or_missing_stdout_cannot_release_success(tmp_path, mode):
    runner, spec, held = setup(tmp_path, mode, .25)
    outcome = runner.run(spec)
    assert outcome.status == 'timed_out' and outcome.stdin_state == 'incomplete'
    retired(runner, held)


def test_interrupted_wait_retires_waiting_rpc_feeder(tmp_path, monkeypatch):
    runner, spec, held = setup(tmp_path, 'silent')
    actual = runner._spawn
    interruption = RuntimeError('controlled wait interruption')
    def spawn(spec):
        owned = actual(spec)
        wait = owned.proc.wait
        first = True
        def interrupted(*args, **kwargs):
            nonlocal first
            if first:
                first = False
                raise interruption
            return wait(*args, **kwargs)
        monkeypatch.setattr(owned.proc, 'wait', interrupted)
        return owned
    runner._spawn = spawn
    with pytest.raises(RuntimeError) as caught:
        runner.run(spec)
    assert caught.value is interruption
    retired(runner, held)


@pytest.mark.parametrize('change', [{'stdin_completion_id':True}, {'stdin_completion_id':-1},
    {'stdin_bytes':None}, {'separate_stderr':False}, {'timeout_seconds':None}, {'timeout_seconds':61}])
def test_rpc_requires_literal_id_finite_timeout_and_stdout_separation(change):
    base = CommandSpec(('not-started',), 'work', stdin_bytes=b'{}\n',
        separate_stderr=True, stdin_completion_id=3, timeout_seconds=1)
    with pytest.raises(CommandSpecError):
        replace(base, **change)


def test_pump_start_failure_precedes_feeder_and_retires_native_child(tmp_path, monkeypatch):
    runner, spec, _ = setup(tmp_path, 'silent')
    children, starts = [], []
    actual = process.subprocess.Popen
    def popen(*args, **kwargs):
        child = actual(*args, **kwargs)
        children.append(child)
        return child
    def start(thread):
        starts.append(thread)
        raise RuntimeError('controlled pump bootstrap failure')
    monkeypatch.setattr(process.subprocess, 'Popen', popen)
    monkeypatch.setattr(process.threading.Thread, 'start', start)
    with pytest.raises(RuntimeError, match='controlled pump'):
        runner.run(spec)
    assert len(starts)==1 and not starts[0].is_alive()
    assert len(children)==1 and children[0].poll() is not None
    assert children[0].stdin.closed and children[0].stdout.closed
    assert runner.active_tokens()==()
