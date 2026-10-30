"""The shared immutable process specification for native headless attempts."""
from __future__ import annotations
from ..execution_boundary import ATTEMPT_MODES
from . import task_file
from .process import CommandSpec
from .harness_profile import TASK_CHANNEL_FILE, bounded_output
from .relay_env import access_only_switch

#: Every harness child is told not to write Python bytecode caches. A review must leave the work
#: tree as it found it, and a reviewer that runs the project's own Python -- its tests, say --
#: would otherwise write `__pycache__/*.pyc` into it. MEASURED live (live-v5-9, 23.09.2026): the
#: review's own check then refused the changed tree. A dispatch loses nothing: bytecode is a cache.
CHILD_ENV = (("PYTHONDONTWRITEBYTECODE", "1"),)


def _named(unset_env):
    """Whether a name is one the spawn runs without, in any casing: Windows folds environment
    names; on other systems dropping a different spelling from this spawn costs nothing."""
    dropped = {name.upper() for name in unset_env}
    return lambda name: name.upper() in dropped


def attempt_spec(adapter, argv, home, cwd, *, timeout, stdin_bytes=None,
                 stdin_completion_id=None, separate_stderr=False, model=None,
                 output_limit=None, unset_env=(), mode=None, extra=()):
    # `mode` is the attempt's mode when it is a TASK attempt, and it decides what the home
    # variable names (`_home_value`). `extra` are values of the relay copy the scan must hold.
    # `unset_env` removes a name from BOTH places a value could come from: a forced
    # switch, and an operator allowlist the runner copies from its own environment.
    # An override cannot delete a name, so the allowlist has to lose it as well.
    # The task of a profile on the FILE channel is written HERE and nowhere else, as one file in
    # the attempt home, for a task attempt only; the child is then given no stdin. A version print
    # or a status question (no `mode`) is not a task and keeps what it was given.
    dropped = _named(unset_env)
    relayed = adapter._relayed(mode)
    forced = {name: value for name, value in adapter.profile.forced_env
              if not dropped(name)
              and (relayed or not access_only_switch(adapter.profile, name, value))}
    by_file = (adapter.profile.task_channel == TASK_CHANNEL_FILE
               and mode in ATTEMPT_MODES and stdin_bytes is not None)
    spec = CommandSpec(
        argv=(*adapter._argv_prefix(),
              *adapter._tokens(argv, home, model)), cwd=cwd,
        env_allow=tuple(name for name in adapter._env_allow() if not dropped(name)),
        # The minted home is written LAST so it cannot be
        # displaced. A `forced_env` pair naming `home_env`
        # would otherwise relocate the child's home and
        # defeat the whole retention promise; the profile
        # refuses that collision at construction, and this
        # ordering means the promise holds even if it did not.
        env={**dict(CHILD_ENV),
             **forced,
             adapter.profile.home_env: adapter._home_value(home, mode)},
        output_limit=bounded_output(adapter.profile, output_limit),
        timeout_seconds=timeout,
        stdin_bytes=None if by_file else stdin_bytes, separate_stderr=separate_stderr,
        stdin_completion_id=stdin_completion_id,
        # The one road a value -- never a name -- crosses this seam: a
        # vendor login lives in a file, so the runner cannot derive it
        # from the environment the way it derives every other credential
        # this build hands a child.
        sensitive_extra=(*adapter._spawn_secrets(), *extra))
    if by_file:
        # After the spec is whole, so a spec that cannot be built leaves no file behind.
        task_file.place(home, stdin_bytes, adapter._workspace.homes_root())
    return spec
