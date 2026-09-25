"""Claude Code's quota readings: the statusline road and the native control road.

Split out of ``claude_code`` when it passed the 800-line cap with the fixes the first
REAL subscription login required (23.09.2026): the plan is named twice by the vendor
(`"Claude Max"` in the initialize reply, `"max"` in get_usage), and get_usage re-renders
each window's reset time on every reply. ``claude_code`` imports every name back, so
no importer moved. This module imports nothing of ``claude_code``.
"""
from __future__ import annotations

import re

from . import login_home
from .quota_connection import NativeQuotaReadError, NativeQuotaSample, NativeQuotaUnconfirmed
from .quota_contracts import NativeQuotaReading, NativeQuotaWindow, QuotaPolicy, quota_object
from .subscription_quota import ControlRpc

FIRST_PARTY = "firstParty"
#: The plan value that means the vendor's own login is paid for as API usage.
#: MEASURED on 2.1.239 with two synthetic credential files of the SAME shape:
#: one carrying `subscriptionType: "max"` and one carrying `"console"` both
#: answer `authMethod: "claude.ai"`, `apiProvider: "firstParty"` and exit 0, and
#: the plan is the only field that separates them. The vendor's own login
#: command offers exactly this pair -- `--claudeai` and `--console` -- so
#: admitting the method alone would have taken the road the owner forbade.
#:
#: Refused by knowledge, like the method used to be, and for a reason that does
#: not apply to the method: the plan names a subscription can carry are an open
#: set nobody here has enumerated, while the one that means API billing is
#: measured. A missing plan refuses too -- an answer that does not say cannot
#: say it is not this one.
API_BILLING_PLAN = "console"


def plan_value(text):
    """A plan as one comparable word: trimmed, case-folded, without the vendor's `Claude ` label.

    MEASURED on the first real subscription login (2.1.239, 23.09.2026): `auth status`
    and get_usage say `"max"`, the initialize reply says `"Claude Max"`. Read through
    this one function by the quota road AND the dispatch login check, so a label-form
    `"Claude Console"` is the API-billing plan wherever it appears.
    """
    word = text.strip().casefold()
    return word[len("claude "):].strip() if word.startswith("claude ") else word


def _native_quota(payload):
    """Native statusline subscription windows; monetary spend limits stay separate."""
    body = quota_object(payload)
    windows = []
    limits = body.get("rate_limits")
    if limits is not None:
        limits = quota_object(limits)
        for name, duration in (("five_hour", 300), ("seven_day", 10080)):
            raw = limits.get(name)
            if raw is not None:
                row = quota_object(raw)
                windows.append(NativeQuotaWindow("claude-subscription", name,
                    row.get("used_percentage"), row.get("resets_at"), duration))
    return NativeQuotaReading(tuple(windows), policy=QUOTA_POLICY)


QUOTA_POLICY = QuotaPolicy("anthropic", "claude-account", "claude-statusline",
                           "quota", "unix", _native_quota)


def _same_plan(label, machine):
    """Whether the account's plan LABEL and get_usage's plan VALUE name one plan.

    MEASURED on the first real subscription login (2.1.239, 23.09.2026): the
    initialize reply's account says `"Claude Max"` while get_usage says `"max"`,
    so plain equality refused every real subscription as `not_authenticated`.
    Both are read through `plan_value`, so the two measured spellings name one
    plan and nothing looser does.
    """
    return plan_value(label) == plan_value(machine)


def _control_usage(payload):
    """Pinned 2.1.239 get_usage: plan facts, never session cost or behaviours."""
    body = quota_object(payload)
    account = quota_object(body.get("account"))
    usage = quota_object(body.get("usage"))
    plan, machine = account.get("subscriptionType"), usage.get("subscription_type")
    if (account.get("apiProvider") != FIRST_PARTY or "apiKeySource" in account
            or "tokenSource" in account or type(plan) is not str or not plan.strip()
            or type(machine) is not str or not machine.strip()
            or API_BILLING_PLAN in (plan_value(plan), plan_value(machine))
            or not _same_plan(plan, machine)):
        raise NativeQuotaReadError("not_authenticated")
    if usage.get("rate_limits_available") is not True:
        raise NativeQuotaReadError("not_supported")
    if usage.get("rate_limits") is None:
        raise NativeQuotaReadError()
    return quota_object(usage["rate_limits"])


#: The windows a reading SHOWS, with their lengths in minutes.
CONTROL_WINDOWS = (("five_hour", 300), ("seven_day", 10080), ("seven_day_oauth_apps", 10080),
                   ("seven_day_opus", 10080), ("seven_day_sonnet", 10080))
#: How far one snapshot's reset time may move between get_usage and the vendor's own cache.
RESET_JITTER_SECONDS = 60


_RFC3339 = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d{1,9})?(Z|[+-]\d{2}:\d{2})")


def _epoch_seconds(value):
    """An RFC 3339 instant WITH a zone as seconds since 1970, by arithmetic, or None.

    This package imports no time module (it holds no clock), so the civil date is
    counted directly (days-from-civil). A string without a zone is not an instant
    two replies can be compared by, and answers None.
    """
    found = _RFC3339.fullmatch(value) if type(value) is str else None
    if found is None:
        return None
    year, month, day, hour, minute, second = (int(found.group(at)) for at in range(1, 7))
    zone = found.group(8)
    offset = 0 if zone == "Z" else (1 if zone[0] == "+" else -1) * (
        int(zone[1:3]) * 3600 + int(zone[4:6]) * 60)
    shifted = year - (month <= 2)
    era, within = divmod(shifted, 400)
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = within * 365 + within // 4 - within // 100 + day_of_year
    days = era * 146097 + day_of_era - 719468
    fraction = float(found.group(7) or 0)
    return days * 86400 + hour * 3600 + minute * 60 + second + fraction - offset


def _same_windows(live, cached):
    """Whether two rate-limit objects show the same facts for every window a reading shows.

    MEASURED on the first real subscription login (23.09.2026): get_usage re-renders
    each `resets_at` on every reply (12:59:59.98 in the cache, 13:00:00.43 in the reply,
    for one snapshot) and `seven_day_breakdown` carries its own `as_of`, so whole-object
    equality never held and every real reading lost its age. What must agree is what a
    reading shows: the same windows, the same utilization, and reset times no further
    apart than RESET_JITTER_SECONDS.
    """
    if type(live) is not dict or type(cached) is not dict:
        return False
    for name, _minutes in CONTROL_WINDOWS:
        mine, theirs = live.get(name), cached.get(name)
        if mine is None and theirs is None:
            continue
        if (type(mine) is not dict or type(theirs) is not dict
                or mine.get("utilization") != theirs.get("utilization")):
            return False
        if mine.get("resets_at") == theirs.get("resets_at"):
            continue
        at, then = _epoch_seconds(mine.get("resets_at")), _epoch_seconds(theirs.get("resets_at"))
        if at is None or then is None or abs(at - then) > RESET_JITTER_SECONDS:
            return False
    return True


def _control_quota(payload):
    limits = _control_usage(payload)
    windows = []
    for name, minutes in CONTROL_WINDOWS:
        row = limits.get(name)
        if row is not None:
            row = quota_object(row)
            windows.append(NativeQuotaWindow("claude-subscription", name,
                row.get("utilization"), row.get("resets_at"), minutes))
    return NativeQuotaReading(tuple(windows), policy=CONTROL_QUOTA_POLICY)


#: 2.1.239 rewrites cachedUsageUtilization at most every 300 s: its writer returns early below
#: that age (read from the pinned binary by the M review, 25.09.2026). Without the traffic switch
#: get_usage fetches live on every call, so inside that window a moved reply is newer than the
#: cache that would date it -- unconfirmed, not wrong. Past it, a mismatch is an inconsistency.
CACHE_WRITE_THROTTLE_SECONDS = 300


def _control_sample(adapter, payload):
    """Native get_usage hides cached fallback age; recover its declared cache age.

    The native writer throttles cache updates to five minutes. An unmatched
    reply is unavailable rather than silently borrowing a different snapshot's
    timestamp. Matching older facts keep their original time on every poll.
    This projection runs under the same workspace lock as the native attempt.
    """
    limits = _control_usage(payload)
    cached = login_home.quota_metadata(adapter._signed_in_road(), ".claude.json",
                                       "cachedUsageUtilization")
    if type(cached) is not dict:
        raise NativeQuotaReadError()
    if not _same_windows(limits, cached.get("utilization")):
        now, fetched = _epoch_seconds(adapter._clock()), cached.get("fetchedAtMs")
        if now is not None and type(fetched) is int and 0 <= now - fetched / 1000 < CACHE_WRITE_THROTTLE_SECONDS:
            raise NativeQuotaUnconfirmed()
        raise NativeQuotaReadError()
    return NativeQuotaSample(payload, cached.get("fetchedAtMs"))


CONTROL_QUOTA_POLICY = QuotaPolicy("anthropic", "claude-account", "claude-control",
                                  "quota", "rfc3339", _control_quota)
#: MEASURED live (live-v5-7, 23.09.2026, acceptance-log\live-v5-7\claude-cache-refresh.txt): with
#: CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC set, 2.1.239's get_usage never fetches -- it echoes the
#: vendor's own cache, and the cache is never refreshed; with only DISABLE_AUTOUPDATER it fetches
#: live and rewrites fetchedAtMs. So this one spawn runs without that switch (Codex ruling,
#: CODEX-REVIEW-OPUS-LIVE-2026-09-23.md). Spelled here because this module imports nothing of
#: claude_code; a test holds it equal to claude_code.CLAUDE_NONESSENTIAL_ENV.
CONTROL_UNSET_ENV = ("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",)
CONTROL_QUOTA_RPC = ControlRpc(
    ("--safe-mode", "-p", "--input-format", "stream-json", "--output-format",
     "stream-json", "--verbose", "--no-session-persistence"),
    b'{"type":"control_request","request_id":"init","request":{"subtype":"initialize"}}\n'
    b'{"type":"control_request","request_id":"usage","request":{"subtype":"get_usage"}}\n',
    ("init", "usage"), unset_env=CONTROL_UNSET_ENV)
