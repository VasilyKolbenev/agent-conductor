"""What may leave the runner from one decoded AFD trace: the failing connect,
what ended it, the rest of its endpoint -- and only the fields that say so.

The XML is written here in the shape `tracerpt -of XML` gives: the Windows event
schema's namespace, a System header, named EventData fields, RenderingInfo.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

import pytest

from browser_tests import afd_extract

AFD = "Microsoft-Windows-Winsock-AFD"
#: sockaddr_in, as the trace renders it: family 2 (little-endian), port 50123
#: (big-endian), 127.0.0.1, eight bytes of zero.
SERVER = "0x0200C3CB7F0000010000000000000000"
OTHER_PORT = "0x0200C3377F0000010000000000000000"
FAILED_AT = "2026-10-09T10:00:05.000+00:00"
SECRET = "the message text of the event"


def _event(time: str, number: int, fields: dict[str, str], provider: str = AFD) -> str:
    data = "".join(f'<Data Name="{key}">{value}</Data>' for key, value in fields.items())
    return (
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System>'
        f'<Provider Name="{provider}" Guid="{{e53c6823-7bb8-44bb-90dc-3f86090d48a6}}"/>'
        f"<EventID>{number}</EventID><Level>4</Level><Task>0</Task><Opcode>0</Opcode>"
        f'<TimeCreated SystemTime="{time}"/><Execution ProcessID="2588" ThreadID="7"/>'
        f"</System><EventData>{data}</EventData><RenderingInfo Culture=\"en-US\">"
        f"<Task>Task{number}</Task><Opcode>Info</Opcode><Message>{SECRET}</Message>"
        "</RenderingInfo></Event>")


def _trace(tmp_path: Path, *events: str, close: bool = True) -> Path:
    xml = tmp_path / "trace.xml"
    xml.write_text('<?xml version="1.0" encoding="UTF-8"?><Events>' + "".join(events)
                   + ("</Events>" if close else ""), encoding="utf-8")
    return xml


def _row(port: int | None = 50123, at: str = FAILED_AT,
         before: float = afd_extract.BEFORE_SECONDS) -> dict[str, object]:
    return {"record": "x.failure.txt", "anchor": "requestfailed",
            "url": "http://127.0.0.1:50123/panel/desk.js", "at": at, "port": port,
            "before_seconds": before}


def test_the_failing_connect_and_its_completion_are_kept_and_nothing_else(
        tmp_path: Path) -> None:
    xml = _trace(
        tmp_path,
        _event("2026-10-09T09:59:50.0000000Z", 13, {"Endpoint": "0xA"}),  # before the window
        _event("2026-10-09T10:00:04.9000000Z", 4,
               {"Process": "0xP", "Endpoint": "0xA", "Address": SERVER}),
        _event("2026-10-09T10:00:04.9010000Z", 6,
               {"Process": "0xP", "Endpoint": "0xA", "Status": "0xC000009A", "Error": "10055"}),
        _event("2026-10-09T10:00:04.9020000Z", 18,
               {"Endpoint": "0xA", "Buffer": "0xDEADBEEF", "BufferLength": "512"}),
        _event("2026-10-09T10:00:04.9500000Z", 4,
               {"Endpoint": "0xB", "Address": OTHER_PORT, "Status": "0x0"}),
        _event("2026-10-09T10:00:04.9600000Z", 1, {"Endpoint": "0xA"}, provider="Other"),
        # The test's own process failing a bind: no address yet, still its own.
        _event("2026-10-09T10:00:04.9700000Z", 40,
               {"Process": "0xP", "Endpoint": "0xD", "Error": "10055"}),
        # Another process on the runner failing too: counted, not published.
        _event("2026-10-09T10:00:04.9800000Z", 6,
               {"Process": "0xQ", "Endpoint": "0xE", "Error": "10055"}),
        # The test's own process failing to reach an outside host: kept, address hidden.
        _event("2026-10-09T10:00:04.9840000Z", 4,
               {"Process": "0xP", "Endpoint": "0xF", "Address": "140.82.112.4:443"}),
        _event("2026-10-09T10:00:04.9850000Z", 6,
               {"Process": "0xP", "Endpoint": "0xF", "Error": "10055"}),
        _event("2026-10-09T10:00:04.9900000Z", 4,
               {"Process": "0xQ", "Endpoint": "0xE", "Address": "140.82.112.3:443"}),
    )
    found = afd_extract.extract(xml, [_row()], 1, {"chromium": "131.0"})

    assert found["trace"] == {"events": 11, "afd_events": 10, "afd_without_fields": 0,
                              "first": "2026-10-09T09:59:50+00:00",
                              "last": "2026-10-09T10:00:04.990000+00:00", "parse_error": None}
    (failure,) = found["failures"]
    assert failure["in_trace"] is False  # the failure time is after the trace's last event
    assert [event["id"] for event in failure["selected"]] == ["4", "6", "18", "40", "4", "6"]
    connect, completion, posted, bind, outside, refused = failure["selected"]
    # Kernel pointers become aliases that still tie the events together.
    assert connect["fields"] == {"Process": "P1", "Endpoint": "E1", "Address": "127.0.0.1:50123"}
    assert connect["time"] == "2026-10-09T10:00:04.900000+00:00" and connect["pid"] == "2588"
    assert completion["fields"] == {"Process": "P1", "Endpoint": "E1", "Status": "0xC000009A",
                                    "Error": "10055"}
    assert posted["fields"] == {"Endpoint": "E1"}
    assert bind["fields"] == {"Process": "P1", "Endpoint": "E2", "Error": "10055"}
    assert outside["fields"] == {"Process": "P1", "Endpoint": "E3", "Address": "non-loopback"}
    assert refused["fields"] == {"Process": "P1", "Endpoint": "E3", "Error": "10055"}
    assert failure["dropped_field_names"] == ["Buffer", "BufferLength"]
    assert failure["failed_statuses"] == {"status=None error=10055": 3,
                                          "status=0xC000009A error=10055": 1}
    assert failure["events_in_window"] == 9 and failure["selected_total"] == 6
    # No message, no buffer, no pointer, no other port, process or outside host.
    public = json.dumps(found)
    for gone in (SECRET, "0xDEADBEEF", "0xP", "0xA", "0xB", "0xD", "0xE", "0xF", "0xQ",
                 "49975", "140.82"):
        assert gone not in public, gone


def test_the_extract_says_whether_the_trace_still_held_the_whole_window(
        tmp_path: Path) -> None:
    middle = (_event("2026-10-09T10:00:04.0000000Z", 4, {"Endpoint": "0xA", "Address": SERVER}),
              _event("2026-10-09T10:00:06.0000000Z", 13, {"Endpoint": "0xA"}))
    lost_start = afd_extract.extract(_trace(tmp_path, *middle), [_row()], 1, None)["failures"][0]
    assert lost_start["in_trace"] is True and lost_start["window_covered"] is False
    assert lost_start["selected_total"] == 2
    whole = _trace(tmp_path, _event("2026-10-09T09:59:54.0000000Z", 13, {"Endpoint": "0xZ"}),
                   *middle, _event("2026-10-09T10:00:07.0000000Z", 13, {"Endpoint": "0xZ"}))
    held = afd_extract.extract(whole, [_row()], 1, None)["failures"][0]
    assert held["in_trace"] is True and held["window_covered"] is True
    gone = afd_extract.extract(whole, [_row(at="2026-10-09T09:00:00.000+00:00")], 1,
                               None)["failures"][0]
    assert gone["in_trace"] is False and gone["window_covered"] is False
    assert gone["selected"] == [] and gone["events_in_window"] == 0


def test_the_selection_keeps_the_events_nearest_the_failure_and_counts_the_rest(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(afd_extract, "MAX_SELECTED", 2)
    times = ("10:00:00.0", "10:00:04.5", "10:00:04.9", "10:00:05.3")
    xml = _trace(tmp_path, *(_event(f"2026-10-09T{time}Z", 4,
                                    {"Endpoint": f"0x{index}", "Address": SERVER})
                             for index, time in enumerate(times)))
    failure = afd_extract.extract(xml, [_row()], 1, None)["failures"][0]
    assert [event["time"][11:22] for event in failure["selected"]] == [
        "10:00:04.90", "10:00:05.30"]
    assert failure["selected_total"] == 4 and failure["selected_dropped"] == 2


def test_an_event_without_fields_or_time_is_counted_never_guessed(tmp_path: Path) -> None:
    xml = _trace(tmp_path,
                 _event("2026-10-09T10:00:04.9000000Z", 4, {}),
                 _event("2026-10-09 10:00:04", 4, {"Endpoint": "0xA", "Address": SERVER}))
    found = afd_extract.extract(xml, [_row()], 1, None)
    assert found["trace"]["afd_without_fields"] == 1 and found["trace"]["afd_untimed"] == 1
    assert found["failures"][0]["selected"] == []


def test_what_etw_itself_dropped_is_reported_from_the_session_header(tmp_path: Path) -> None:
    header = _event("2026-10-09T09:00:00.0000000Z", 0,
                    {"EventsLost": "17", "BuffersLost": "0x2"}, provider="MSNT_SystemTrace")
    found = afd_extract.extract(_trace(tmp_path, header), [_row()], 1, None)
    assert found["trace"]["eventslost"] == 17 and found["trace"]["bufferslost"] == 2


def test_a_trace_cut_short_keeps_what_was_read_and_says_where_it_broke(tmp_path: Path) -> None:
    xml = _trace(tmp_path,
                 _event("2026-10-09T10:00:04.9000000Z", 4, {"Endpoint": "0xA", "Address": SERVER}),
                 '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event"><System>',
                 close=False)
    found = afd_extract.extract(xml, [_row()], 1, None)
    assert found["trace"]["parse_error"] and found["trace"]["afd_events"] == 1
    assert found["failures"][0]["selected_total"] == 1


def test_failures_come_from_the_gate_records_in_time_order_with_their_port(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "b.call.failure.txt").write_text(
        "page said:\n"
        "  requestfailed http://127.0.0.1:61000/panel/a.js net::ERR_NO_BUFFER_SPACE"
        " at=2026-10-09T10:00:09.000+00:00\n"
        "  console-error Failed to load resource: net::ERR_NO_BUFFER_SPACE\n"
        "  requestfailed http://127.0.0.1:61000/panel/b.js net::ERR_ABORTED"
        " at=2026-10-09T10:00:01.000+00:00\n", encoding="utf-8")
    (tmp_path / "a.setup.failure.txt").write_text(
        "  requestfailed http://127.0.0.1:50123/panel/desk.js net::ERR_NO_BUFFER_SPACE"
        " at=2026-10-09T10:00:05.000+00:00\n"
        "  requestfailed http://127.0.0.1:50123/panel/old.js net::ERR_NO_BUFFER_SPACE\n",
        encoding="utf-8")
    rows, total = afd_extract.failures(tmp_path)
    assert total == 2 and [(row["record"], row["port"], row["before_seconds"])
                           for row in rows] == [("a.setup.failure.txt", 50123, 10.0),
                                                ("b.call.failure.txt", 61000, 10.0)]
    monkeypatch.setattr(afd_extract, "MAX_FAILURES", 1)
    rows, total = afd_extract.failures(tmp_path)
    assert total == 2 and len(rows) == 1


def test_a_10055_named_only_in_a_traceback_is_anchored_where_its_record_was_written(
        tmp_path: Path) -> None:
    record = tmp_path / "c.call.failure.txt"
    record.write_text("E   OSError: [WinError 10055] An operation on a socket could not be "
                      "performed\n  owner pid 10055\n", encoding="utf-8")
    written = datetime.datetime(2026, 10, 9, 10, 0, 30, tzinfo=datetime.timezone.utc)
    os.utime(record, (written.timestamp(), written.timestamp()))
    (tmp_path / "d.call.failure.txt").write_text("  owner pid 10055\n", encoding="utf-8")
    # A long traceback reprints source; a docstring there is not a failure.
    (tmp_path / "e.call.failure.txt").write_text(
        "    def _the_window_itself_raised_nothing(said):\n"
        '        """A module answering `net::ERR_NO_BUFFER_SPACE` or WSAENOBUFS."""\n',
        encoding="utf-8")
    rows, total = afd_extract.failures(tmp_path)
    assert total == 1 and rows == [{
        "record": "c.call.failure.txt", "anchor": "record-written", "url": None,
        "at": "2026-10-09T10:00:30.000+00:00", "port": None,
        "before_seconds": afd_extract.RECORD_BEFORE_SECONDS}]


def test_a_separate_port_field_matches_in_either_byte_order(tmp_path: Path) -> None:
    swapped = int.from_bytes((50123).to_bytes(2, "big"), "little")
    xml = _trace(tmp_path, *(
        _event("2026-10-09T10:00:04.9000000Z", 4,
               {"Endpoint": f"0x{port}", "Address": "127.0.0.1", "Port": str(port)})
        for port in (50123, swapped, 50124)))
    selected = afd_extract.extract(xml, [_row()], 1, None)["failures"][0]["selected"]
    assert [event["fields"]["Port"] for event in selected] == ["50123", str(swapped)]


@pytest.mark.parametrize(("raw", "decoded"), [
    (SERVER, ("127.0.0.1", 50123)),
    ("1700C3CB00000000" + "00" * 15 + "01" + "00000000", ("::1", 50123)),
    ("02-00-C3-CB-7F-00-00-01-00-00-00-00-00-00-00-00", ("127.0.0.1", 50123)),
    ("127.0.0.1:50123", ("127.0.0.1", 50123)),
    ("[::1]:50123", ("::1", 50123)),
    ("999.0.0.1:50123", None),
    ("127.0.0.1", ("127.0.0.1", None)),
    ("C3CB7F000001", None),
    ("0xZZ", None),
    ("<a name>", None),
])
def test_an_address_is_decoded_or_refused_never_passed_raw(
        raw: str, decoded: tuple[str, int | None] | None) -> None:
    assert afd_extract.address(raw) == decoded
