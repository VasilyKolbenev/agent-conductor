"""Bounded stdout-only completion marker for a finite native RPC batch.

This value knows no method or provider. It never accepts input from HTTP and
does not turn an RPC error into success: the caller must validate the complete
transcript after process retirement. It only decides when stdin may see EOF.
"""
from __future__ import annotations

import json


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON member')
        result[key] = value
    return result


def decode_line(line: bytes) -> dict:
    value = json.loads(line.decode('utf-8', 'strict'), object_pairs_hook=_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if type(value) is not dict:
        raise ValueError('RPC message must be an object')
    return value


class JsonlCompletion:
    """A complete final response, malformed line, overflow or EOF ends waiting."""

    def __init__(self, response_id: int, limit: int) -> None:
        self.response_id, self.limit = response_id, min(limit, 65536)
        self.buffer = bytearray()
        self.complete = self.finished = False
        self.total = 0

    def observe(self, chunk: bytes) -> None:
        if self.finished:
            return
        self.total += len(chunk)
        if self.total > self.limit:
            self.finished = True
            return
        self.buffer.extend(chunk)
        while b'\n' in self.buffer:
            line, _, remaining = self.buffer.partition(b'\n')
            self.buffer[:] = remaining
            try:
                row = decode_line(bytes(line))
                if type(row.get('id')) is int and row['id'] == self.response_id:
                    self.complete = ('result' in row) != ('error' in row) and 'method' not in row
                    self.finished = True
                    return
            except (ValueError, UnicodeError, RecursionError):
                self.finished = True
                return
