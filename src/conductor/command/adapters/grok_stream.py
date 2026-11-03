"""Decode Grok's bounded, non-partial streaming-messages-json review.

At xai-org/grok-build 9fabade, headless/reducer/messages/mod.rs appends every
agent text chunk to an assistant block. The result repeats the last flushed
frame's text. It can be empty after a tool-only frame.
"""
from __future__ import annotations

from .jsonl_completion import decode_line

STREAM_OUTPUT_LIMIT = 48 * 1024
_INVALID = "the Grok diagnostic stream did not establish a result"
_OPEN = "the Grok diagnostic reported an opened session before the error"
_NO_ID = "the Grok diagnostic reported no session ID before the error"
_RESULT_FIELDS = frozenset((
    "type", "subtype", "is_error", "result", "stop_reason", "errors", "session_id", "uuid",
    "usage", "modelUsage", "duration_ms", "duration_api_ms", "total_cost_usd", "num_turns",
))


def decode_stream(output: bytes, exit_code: int | None) -> tuple[bytes, str | None]:
    """Consume one complete stdout capture. Only successful assistant text may escape."""
    if (type(output) is not bytes or len(output) > STREAM_OUTPUT_LIMIT
            or not output.endswith(b"\n") or type(exit_code) is not int):
        return b"", _INVALID
    try:
        lines = output[:-1].split(b"\n")
        init = decode_line(lines[0])
        terminal = decode_line(lines[-1])
        session = init.get("session_id")
        if (init.get("type") != "system" or init.get("subtype") != "init"
                or type(session) is not str or (session and not session.strip())
                or terminal.get("type") != "result" or terminal.get("session_id") != session
                or not terminal.keys() <= _RESULT_FIELDS):
            return b"", _INVALID
        frames = []
        for line in lines[1:-1]:
            row = decode_line(line)
            if not session or row.get("session_id") != session:
                return b"", _INVALID
            text = _frame_text(row)
            if text is not None:
                frames.append(text)
        if exit_code != 0:
            if _is_error(terminal):
                return b"", _OPEN if session else _NO_ID
            return b"", _INVALID
        if (terminal.get("subtype") != "success" or terminal.get("is_error") is not False
                or terminal.get("stop_reason") != "end_turn" or "errors" in terminal
                or not frames or terminal.get("result") != frames[-1]):
            return b"", _INVALID
        content = "".join(frames)
        return (content.encode("utf-8"), None) if content.strip() else (b"", _INVALID)
    except (ValueError, RecursionError):
        return b"", _INVALID


def _is_error(terminal: dict) -> bool:
    errors = terminal.get("errors")
    if (terminal.get("is_error") is not True or "result" in terminal
            or "stop_reason" not in terminal or not isinstance(errors, list) or not errors
            or not all(isinstance(item, str) for item in errors)):
        return False
    stop = terminal["stop_reason"]
    if terminal.get("subtype") == "error_during_execution":
        return stop in (None, "max_tokens", "refusal", "cancelled")
    return (terminal.get("subtype") == "error_max_turns"
            and stop in ("end_turn", "max_tokens", "max_turn_requests", "refusal", "cancelled"))


def _frame_text(row: dict) -> str | None:
    role = row.get("type")
    if role == "system" and row.get("subtype") == "compact_boundary":
        meta = row.get("compact_metadata")
        if (isinstance(meta, dict) and meta.get("trigger") == "auto"
                and type(meta.get("pre_tokens")) is int and meta["pre_tokens"] >= 0):
            return None
        raise ValueError
    message = row.get("message")
    if (role not in ("assistant", "user") or row.get("parent_tool_use_id") is not None
            or not isinstance(message, dict) or message.get("role") != role):
        raise ValueError
    blocks = message.get("content")
    if not isinstance(blocks, list) or not blocks or not all(isinstance(b, dict) for b in blocks):
        raise ValueError
    if role == "user":
        if not all(b.get("type") == "tool_result" and isinstance(b.get("tool_use_id"), str)
                   and isinstance(b.get("content"), str) and type(b.get("is_error")) is bool
                   for b in blocks):
            raise ValueError
        return None
    if message.get("type") != "message":
        raise ValueError
    return "".join(_assistant_block_text(block) for block in blocks)


def _assistant_block_text(block: dict) -> str:
    kind = block.get("type")
    if kind == "text" and isinstance(block.get("text"), str):
        return block["text"]
    if kind == "thinking" and all(isinstance(block.get(k), str) for k in ("thinking", "signature")):
        return ""
    if kind in ("tool_use", "server_tool_use") and isinstance(block.get("input"), dict):
        if all(isinstance(block.get(k), str) for k in ("id", "name")):
            return ""
    if kind == "web_search_tool_result" and isinstance(block.get("tool_use_id"), str):
        if isinstance(block.get("content"), (dict, list)):
            return ""
    raise ValueError
