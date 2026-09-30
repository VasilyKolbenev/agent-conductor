"""A child that only sleeps (helper of `test_hub_job.py`, not a test).

The spawner gives it the flags of `conduct up`, which it ignores. It writes its own pid where
`SLEEPER_PIDFILE` says, so that a test can ask the OS whether it is still there.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

Path(os.environ["SLEEPER_PIDFILE"]).write_text(str(os.getpid()), encoding="ascii")
time.sleep(120)
