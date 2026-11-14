"""The few AFD events a reader needs from one decoded trace, and nothing else.

``tracerpt`` turns the stopped trace into event XML that can run to hundreds of
megabytes and holds every socket operation of the runner. What may leave the
runner is much narrower (review ruling 07.10): the test's own loopback events
around each 10055 the gate recorded, without packet contents or identifiers
nobody needs.

So, around each such failure -- a ``requestfailed`` line's ``at=`` time and
server port, or, for a 10055 named only in a traceback, the time its record was
written and the ports its own host snapshot says the test talked to -- this
keeps (and with no port of the test it keeps nothing but counts, because no
other event of the runner is proven to be the test's):

- every AFD event in the window whose address is loopback on that port, and
  every one whose ``Status`` is an NTSTATUS error or warning or whose
  ``Error`` is not zero, in a process that has such loopback events -- the
  connect and the status it ended with, a failed bind before it included.
  Another process's failure on the runner is counted, never published;
- every other event of the same ``Endpoint`` in the window, so a connect can be
  read beside its completion: the PID in an event's header is not always the
  client's, the endpoint is what ties the two;
- of each event, only the fields named in ``KEPT_FIELDS``: an address decoded to
  ``ip:port`` and shown only when it is loopback or unspecified, the kernel's
  process and endpoint pointers replaced by aliases that still link events;
  never a buffer, a message or the raw data.

It also says what it could not see: event counts per kind in the window, the
names of the fields it dropped, whether the trace's first and last events still
span the whole window (a span, not a proof that nothing inside it was lost: the
session header's EventsLost and BuffersLost say that), where decoding broke off,
and every cap it applied. Missing evidence is a stated gap.
"""
from __future__ import annotations

import datetime
import ipaddress
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator
from xml.etree import ElementTree

NO_BUFFER = "ERR_NO_BUFFER_SPACE"
#: 10055 as a failure record can say it: Chromium's own name in a requestfailed
#: line, or the Winsock error in a Python traceback. Never a bare number, which a
#: PID or a count in the same record could be.
ANY_10055 = re.compile(r"ERR_NO_BUFFER_SPACE|WSAENOBUFS|WinError 10055|[Ee]rrno 10055")
#: The lines of a record that report what HAPPENED: the page's own words and
#: pytest's exception lines. A long traceback also reprints source and
#: docstrings, and a docstring naming ERR_NO_BUFFER_SPACE is not a failure.
_EVIDENCE = re.compile(r"^(?:\s*(?:requestfailed \S+://|console-error |pageerror )|E\s)")
PROVIDER = "Microsoft-Windows-Winsock-AFD"
#: The window around a requestfailed time. That time is when the test process
#: handled the event -- the browser's own start time is 0 on a request that got
#: no response -- and the connect failed before it, so most of the window lies before.
BEFORE_SECONDS, AFTER_SECONDS = 10.0, 1.0
#: Before a record that names 10055 only in a traceback: its write time can trail
#: the failure by a whole wait.
RECORD_BEFORE_SECONDS = 40.0
#: The fields an event may publish, compared without case; every other field
#: is dropped and only its NAME is reported.
KEPT_FIELDS = frozenset({"process", "endpoint", "status", "error", "reason", "address",
                         "port", "location", "enterexit", "usermodepid", "sockettype",
                         "protocol", "addressfamily"})
ALIASED = {"process": "P", "endpoint": "E"}
MAX_FAILURES = 5
MAX_SELECTED = 500
MAX_HELD = 50_000
MAX_VALUE = 64
_AT = re.compile(r" at=(\S+)")
_PORT = re.compile(r"^requestfailed https?://(?:127\.0\.0\.1|localhost|\[::1\]):(\d+)/")
_TIME = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$")
_RENDERED = re.compile(r"^(?:(\d{1,3}(?:\.\d{1,3}){3})|\[([0-9A-Fa-f:.]+)\]):(\d{1,5})$")
#: The ports a failing test talked to, as its host snapshot records them.
_SNAPSHOT_PORTS = re.compile(r'"loopback_ports": \[([\d,\s]*)\]')


@dataclass(frozen=True)
class Event:
    """One decoded event: its header, its rendered names, its data fields."""
    provider: str
    id: str
    task: str
    opcode: str
    time: datetime.datetime | None
    pid: str | None
    tid: str | None
    fields: dict[str, str]

    def value(self, name: str) -> str | None:
        """A data field by name, compared without case."""
        return next((value for key, value in self.fields.items() if key.lower() == name), None)


@dataclass
class _Window:
    """One recorded failure and the events held around it."""
    row: dict[str, object]
    at: datetime.datetime
    before: float
    held: list[Event] = field(default_factory=list)
    over: int = 0


def names_10055(line: str) -> bool:
    """Whether one record line reports a 10055 that happened."""
    return bool(_EVIDENCE.match(line) and ANY_10055.search(line))


def _failed_request(record: str, line: str) -> dict[str, object] | None:
    at = _AT.search(line)
    if not (line.startswith("requestfailed") and NO_BUFFER in line and at):
        return None
    found = _PORT.match(line)
    port = int(found.group(1)) if found and 0 < int(found.group(1)) < 65536 else None
    return {"record": record, "anchor": "requestfailed", "url": line.split()[1],
            "at": at.group(1), "ports": [] if port is None else [port],
            "correlation": None if port is None else "requestfailed-url",
            "before_seconds": BEFORE_SECONDS}


def _record_written(path: Path, text: str) -> dict[str, object]:
    """A record that names 10055 only in a traceback: anchored where it was written,
    tied to the test by the ports its own host snapshot says the test talked to."""
    written = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)
    found = _SNAPSHOT_PORTS.search(text)
    ports = sorted({int(port) for port in re.findall(r"\d+", found.group(1))
                    if 0 < int(port) < 65536}) if found else []
    return {"record": path.name, "anchor": "record-written", "url": None,
            "at": written.isoformat(timespec="milliseconds"), "ports": ports,
            "correlation": "record-snapshot" if ports else None,
            "before_seconds": RECORD_BEFORE_SECONDS}


def failures(watch_dir: Path) -> tuple[list[dict[str, object]], int]:
    """The first recorded 10055s in time order, and how many there were in all.

    A record's requestfailed lines answer with their own times and ports; a
    record that names 10055 only elsewhere (a traceback) answers once, with the
    time it was written and the ports of its own host snapshot. A row with no
    port has no proven tie to the test: it is counted, never selected from.
    """
    rows: list[dict[str, object]] = []
    for path in sorted(watch_dir.glob("*.failure.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        found = [row for line in text.splitlines()
                 if (row := _failed_request(path.name, line.strip())) is not None]
        if not found and any(names_10055(line) for line in text.splitlines()):
            found = [_record_written(path, text)]
        rows.extend(found)
    latest = datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
    rows.sort(key=lambda row: _utc(str(row["at"])) or latest)
    return rows[:MAX_FAILURES], len(rows)


def _utc(text: str) -> datetime.datetime | None:
    """An ISO time with any number of fraction digits, in UTC; None without a zone."""
    found = _TIME.match(text.strip())
    if not found:
        return None
    whole, fraction, zone = found.groups()
    zone = "+00:00" if zone == "Z" else zone
    stamp = f"{whole}.{(fraction or '0')[:6].ljust(6, '0')}{zone}"
    return datetime.datetime.fromisoformat(stamp).astimezone(datetime.timezone.utc)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(element: ElementTree.Element | None) -> str:
    return "" if element is None else (element.text or "").strip()


def _event(element: ElementTree.Element) -> Event:
    system: dict[str, ElementTree.Element] = {}
    data: dict[str, str] = {}
    rendering: dict[str, str] = {}
    for part in element:
        kind = _local(part.tag)
        if kind == "System":
            system = {_local(item.tag): item for item in part}
        elif kind == "EventData":
            data = {item.get("Name", ""): (item.text or "").strip() for item in part}
        elif kind == "RenderingInfo":
            rendering = {_local(item.tag): (item.text or "").strip() for item in part}
    provider, execution = system.get("Provider"), system.get("Execution")
    created = system.get("TimeCreated")
    return Event(provider="" if provider is None else provider.get("Name", ""),
                 id=_text(system.get("EventID")),
                 task=rendering.get("Task") or _text(system.get("Task")),
                 opcode=rendering.get("Opcode") or _text(system.get("Opcode")),
                 time=None if created is None else _utc(created.get("SystemTime", "")),
                 pid=None if execution is None else execution.get("ProcessID"),
                 tid=None if execution is None else execution.get("ThreadID"),
                 fields=data)


def events(xml: Path) -> Iterator[Event]:
    """Each event of the file, streamed: the file is never held whole."""
    root = None
    for kind, element in ElementTree.iterparse(xml, events=("start", "end")):
        if root is None:
            root = element
        if kind == "end" and _local(element.tag) == "Event":
            yield _event(element)
            if root is not element:
                root.clear()


def _number(value: str | None) -> int | None:
    text = (value or "").strip().lower()
    try:
        return int(text, 16) if text.startswith("0x") else int(text)
    except ValueError:
        return None


def address(value: str) -> tuple[str, int | None] | None:
    """A sockaddr as hex (AF_INET or AF_INET6), as rendered text (``ip:port``,
    ``[ip]:port``), or a plain address; else None."""
    rendered = _RENDERED.match(value.strip())
    if rendered:
        host, port = rendered.group(1) or rendered.group(2), int(rendered.group(3))
        try:
            return str(ipaddress.ip_address(host)), port
        except ValueError:
            return None
    text = value.strip().lower().removeprefix("0x").replace(" ", "").replace("-", "")
    try:
        raw = bytes.fromhex(text) if len(text) >= 16 else b""
    except ValueError:
        raw = b""
    family = int.from_bytes(raw[0:2], "little") if len(raw) >= 8 else None
    if family == 2:
        return ".".join(str(byte) for byte in raw[4:8]), int.from_bytes(raw[2:4], "big")
    if family == 23 and len(raw) >= 24:
        return str(ipaddress.IPv6Address(raw[8:24])), int.from_bytes(raw[2:4], "big")
    try:
        return str(ipaddress.ip_address(value.strip())), None
    except ValueError:
        return None


def _loopback_on(event: Event, ports: frozenset[int]) -> bool:
    """Loopback on one of the test's own ports -- never "any loopback port"."""
    found = address(event.value("address") or "")
    if not ports or found is None or not ipaddress.ip_address(found[0]).is_loopback:
        return False
    if found[1] is not None:  # the address carries its port in network order: exact only
        return found[1] in ports
    # A separate Port field may come in either byte order; both are the one port.
    seen_port = _number(event.value("port"))
    return any(seen_port in (port, int.from_bytes(port.to_bytes(2, "big"), "little"))
               for port in ports)


def _failed(event: Event) -> bool:
    """An NTSTATUS error or warning (the top bit set), or a non-zero Winsock error."""
    status, error = _number(event.value("status")), _number(event.value("error"))
    return bool(status is not None and status & 0x80000000) or bool(error)


def _shown_address(value: str) -> str:
    """An address as it may leave the runner: loopback or unspecified, or not at all."""
    found = address(value)
    if found is None:
        return "undecoded"
    ip = ipaddress.ip_address(found[0])
    if not (ip.is_loopback or ip.is_unspecified):
        return "non-loopback"
    return found[0] if found[1] is None else f"{found[0]}:{found[1]}"


def _aliases() -> Callable[[str, str], str]:
    """One alias per kernel pointer, the same across every failure of one extract."""
    given: dict[tuple[str, str], str] = {}

    def alias(kind: str, value: str) -> str:
        if (kind, value) not in given:
            count = sum(1 for known in given if known[0] == kind)
            given[(kind, value)] = f"{ALIASED[kind]}{count + 1}"
        return given[(kind, value)]
    return alias


def _public(event: Event, alias: Callable[[str, str], str]) -> dict[str, object]:
    """The event as it may leave the runner."""
    kept: dict[str, str] = {}
    for key, value in event.fields.items():
        name = key.lower()
        if name not in KEPT_FIELDS:
            continue
        if name == "address":
            value = _shown_address(value)
        elif name in ALIASED:
            value = alias(name, value)
        kept[key] = value[:MAX_VALUE]
    return {"time": event.time.isoformat(timespec="microseconds") if event.time else None,
            "id": event.id, "task": event.task, "opcode": event.opcode,
            "pid": event.pid, "tid": event.tid, "fields": kept}


def _owner(event: Event) -> tuple[str, str | None]:
    """Whose socket this is: the kernel process field when the event has one,
    the header PID only when it has not."""
    process = event.value("process")
    return ("process", process) if process else ("pid", event.pid)


def _selected(window: _Window) -> list[Event]:
    """The failure's own events: loopback on its port; failed, in a process that
    has such loopback events (another process's failure is only counted); and
    every other event of the same endpoints. With no port of the test, nothing."""
    ports = window.row.get("ports")
    wanted = frozenset(port for port in ports if isinstance(port, int)) \
        if isinstance(ports, list) else frozenset()
    if not wanted:
        return []
    loopback = [_loopback_on(event, wanted) for event in window.held]
    owners = {_owner(event) for event, mark in zip(window.held, loopback) if mark}
    marked = [mark or (_failed(event) and _owner(event) in owners)
              for event, mark in zip(window.held, loopback)]
    endpoints = {event.value("endpoint") for event, mark in zip(window.held, marked) if mark}
    endpoints.discard(None)
    return [event for event, mark in zip(window.held, marked)
            if mark or event.value("endpoint") in endpoints]


def _report(window: _Window, first: datetime.datetime | None, last: datetime.datetime | None,
            alias: Callable[[str, str], str]) -> dict[str, object]:
    """One failure's selection, with every count a reader needs to judge it."""
    chosen = _selected(window)
    nearest = sorted(chosen, key=lambda event: abs((event.time or window.at) - window.at)
                     )[:MAX_SELECTED]
    names = sorted({key for event in window.held for key in event.fields})
    start = window.at - datetime.timedelta(seconds=window.before)
    end = window.at + datetime.timedelta(seconds=AFTER_SECONDS)
    return {**window.row, "window": [start.isoformat(), end.isoformat()],
            # No port of the test: no event of the runner is published as this failure's.
            "correlation_gap": not window.row.get("ports"),
            "in_trace": bool(first and last and first <= window.at <= last),
            "window_covered": bool(first and last and first <= start and last >= end),
            "events_in_window": len(window.held) + window.over, "held_over_cap": window.over,
            "kinds": dict(Counter(f"{event.id} {event.task}/{event.opcode}"
                                  for event in window.held).most_common()),
            "failed_statuses": dict(Counter(
                f"status={event.value('status')} error={event.value('error')}"
                for event in window.held if _failed(event)).most_common()),
            "selected_total": len(chosen), "selected_dropped": len(chosen) - len(nearest),
            "selected": [_public(event, alias) for event in sorted(
                nearest, key=lambda event: event.time or window.at)],
            "dropped_field_names": [name for name in names if name.lower() not in KEPT_FIELDS]}


def _read(xml: Path, windows: list[_Window]) -> tuple[Counter[str], list[datetime.datetime],
                                                       str | None]:
    """One pass over the file: totals, the times it covers, and where it broke off."""
    totals: Counter[str] = Counter()
    times: list[datetime.datetime] = []
    try:
        for event in events(xml):
            totals["events"] += 1
            if event.provider != PROVIDER:
                # The session header says what ETW itself dropped.
                for name in ("eventslost", "bufferslost"):
                    lost = _number(event.value(name))
                    if lost is not None:
                        totals[name] = max(totals[name], lost)
                continue
            totals["afd_events"] += 1
            totals["afd_without_fields"] += 0 if event.fields else 1
            if event.time is None:
                totals["afd_untimed"] += 1
                continue
            times = [min(times[0], event.time), max(times[1], event.time)] if times \
                else [event.time, event.time]
            for window in windows:
                if -window.before <= (event.time - window.at).total_seconds() <= AFTER_SECONDS:
                    if len(window.held) < MAX_HELD:
                        window.held.append(event)
                    else:
                        window.over += 1
    except ElementTree.ParseError as error:
        return totals, times, str(error)
    return totals, times, None


def extract(xml: Path, rows: list[dict[str, object]], total: int,
            versions: dict[str, object] | None) -> dict[str, object]:
    """Read the decoded trace once and select around every recorded failure."""
    windows = [_Window(row, at, float(str(row["before_seconds"]))) for row in rows
               if (at := _utc(str(row["at"]))) is not None]
    totals, times, broke = _read(xml, windows)
    first, last = (times[0], times[1]) if times else (None, None)
    alias = _aliases()
    return {"decoded": True, "versions": versions,
            "trace": {**totals, "first": first and first.isoformat(),
                      "last": last and last.isoformat(), "parse_error": broke},
            "failures_total": total, "failures_read": len(windows),
            "caps": {"failures": MAX_FAILURES, "selected": MAX_SELECTED, "held": MAX_HELD,
                     "value_chars": MAX_VALUE},
            "failures": [_report(window, first, last, alias) for window in windows]}
