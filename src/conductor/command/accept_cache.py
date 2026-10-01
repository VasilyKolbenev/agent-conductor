"""Bounded process/session preview choices, never durable authorization."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock


class AcceptancePreviews:
    def __init__(self, limit=32):
        self._limit, self._lock, self._entries = limit, RLock(), OrderedDict()

    def remember(self, run_id, digest, options):
        with self._lock:
            key = (run_id, digest)
            self._entries[key] = deepcopy(options)
            self._entries.move_to_end(key)
            while len(self._entries) > self._limit:
                self._entries.popitem(last=False)

    def read(self, run_id, digest):
        with self._lock:
            return deepcopy(self._entries.get((run_id, digest)))
