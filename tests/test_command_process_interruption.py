"""An interrupted wait must retire the real child group before losing its token.

The wrapper keeps the native group handle alive on close, as POSIX permits.
This makes explicit retirement observable on Windows without claiming POSIX
platform coverage. Every test finally retires its own saved native group.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from conductor.command.adapters.process import CommandSpec, ProcessRunner
from tests._fakeproc import (
    HEARTBEAT_FILE, HEARTBEAT_INTERVAL, SPAWN_HB_FILE,
    fake_argv, read_int, wait_for_int,
)


class CancelWait(BaseException):
    pass


class _NoImplicitRetirement:
    def __init__(self, native):
        self.native = native

    def terminate(self):
        self.native.terminate()

    def close(self):
        # ProcessGroup.close does not promise to terminate on every platform.
        # The test finally owns the real handle and closes it after cleanup.
        pass


class InterruptedRun:
    def __init__(self, tmp_path, error_type, input_bytes):
        root = tmp_path / 'project'
        (root / 'work').mkdir(parents=True)
        self.parent_beat, self.child_beat = tmp_path / 'parent', tmp_path / 'child'
        self.runner = ProcessRunner(root, environ={})
        self.original_spawn = self.runner._spawn
        self.original_release = self.runner._release
        self.captured = []
        self.release_observations = []
        self.interruption = error_type('synthetic wait interruption')
        self.input_bytes = input_bytes
        self.runner._spawn = self.spawn
        self.runner._release = self.checked_release

    def beats(self):
        return read_int(self.parent_beat), read_int(self.child_beat)

    def checked_release(self, owned):
        assert owned.token in self.runner.active_tokens(), 'token must still be owned here'
        assert owned.proc.poll() is not None, 'leader alive at release'
        assert not owned._pump.is_alive(), 'output pump alive at release'
        if self.input_bytes is not None:
            assert owned._feeder is not None
            assert not owned._feeder.is_alive(), 'input feeder alive at release'
        settled = self.beats()
        assert all(value is not None for value in settled)
        time.sleep(.1)
        assert self.beats() == settled
        self.release_observations.append(settled)
        self.original_release(owned)

    def spawn(self, spec):
        owned = self.original_spawn(spec)
        self.captured.append(owned)
        owned.group = _NoImplicitRetirement(owned.group)
        original_wait = owned.proc.wait

        def interrupted_wait(*args, **kwargs):
            # Restore before raising: cleanup must be able to reap normally.
            owned.proc.wait = original_wait
            wait_for_int(self.parent_beat)
            before = wait_for_int(self.child_beat)
            if self.input_bytes is not None:
                assert owned._feeder is not None, 'control: input has its own feeder'
            deadline = time.monotonic() + 5
            sample = None
            while time.monotonic() < deadline:
                sample = read_int(self.child_beat)
                if sample is not None and sample > before:
                    break
                time.sleep(.01)
            assert sample is not None and sample > before, 'control: descendant really writes'
            raise self.interruption

        owned.proc.wait = interrupted_wait
        return owned

    def close(self):
        for owned in self.captured:
            native = owned.group.native
            try:
                native.terminate()
                owned.proc.wait(timeout=5)
                owned.finish('stopped')
            finally:
                native.close()
                for stream in (owned.proc.stdin, owned.proc.stdout, owned.proc.stderr):
                    if stream is not None:
                        stream.close()
                self.original_release(owned)


@pytest.mark.parametrize('samples,progresses', [
    ((None, 9, 10, 11, None), True),
    ((10,), False),
    ((None,), False),
], ids=['unknown-then-advance', 'no-advance', 'unknown-only'])
def test_heartbeat_observer_requires_and_keeps_a_valid_increase(
        tmp_path, monkeypatch, samples, progresses):
    """Drive the real wait wrapper with controlled IO and time, without a child."""
    case = InterruptedRun(tmp_path, CancelWait, None)
    original_wait = lambda *args, **kwargs: None
    owned = SimpleNamespace(proc=SimpleNamespace(wait=original_wait), group=object())
    case.original_spawn = lambda spec: owned
    initial_reads, observed, ticks, sleeps = [], [], [], []

    def initial(path):
        initial_reads.append(path)
        return 10

    def read(path):
        assert path == case.child_beat
        sample = samples[min(len(observed), len(samples) - 1)]
        observed.append(sample)
        return sample

    def monotonic():
        tick = len(ticks)
        ticks.append(tick)
        return float(tick)

    monkeypatch.setitem(globals(), 'wait_for_int', initial)
    monkeypatch.setitem(globals(), 'read_int', read)
    monkeypatch.setitem(globals(), 'time', SimpleNamespace(
        monotonic=monotonic, sleep=sleeps.append))
    assert case.spawn(object()) is owned
    expected = CancelWait if progresses else AssertionError
    with pytest.raises(expected) as caught:
        owned.proc.wait(timeout=10)
    if progresses:
        assert caught.value is case.interruption
    else:
        assert 'control: descendant really writes' in str(caught.value)
    assert owned.proc.wait is original_wait
    assert initial_reads == [case.parent_beat, case.child_beat]
    assert observed == ([None, 9, 10, 11] if progresses else [samples[0]] * 4)
    assert ticks == list(range(5 if progresses else 6))
    assert sleeps == [.01] * (3 if progresses else 4)


@pytest.mark.parametrize('error_type', [CancelWait, RuntimeError])
@pytest.mark.parametrize('input_bytes', [None, b'x' * 65536], ids=['no_input', 'with_input'])
def test_interrupted_wait_retires_both_heartbeats_and_io_threads_before_release(
        tmp_path, error_type, input_bytes):
    case = InterruptedRun(tmp_path, error_type, input_bytes)
    try:
        with pytest.raises(error_type) as caught:
            case.runner.run(CommandSpec(
                argv=fake_argv(), cwd='work', timeout_seconds=10,
                stdin_bytes=input_bytes,
                env={HEARTBEAT_FILE: str(case.parent_beat), SPAWN_HB_FILE: str(case.child_beat),
                     HEARTBEAT_INTERVAL: '.02'}))
        assert caught.value is case.interruption
        assert len(case.release_observations) == 1
        owned = case.captured[0]
        settled = case.beats()
        assert all(value is not None for value in settled)
        time.sleep(.2)
        assert case.beats() == settled
        assert owned.proc.poll() is not None
        assert not owned._pump.is_alive()
        if input_bytes is not None:
            assert owned._feeder is not None and not owned._feeder.is_alive()
        assert case.runner.active_tokens() == ()
    finally:
        case.close()
