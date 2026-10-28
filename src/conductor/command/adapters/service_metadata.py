"""A native metadata exchange may repeat the account's own metadata; a key never may be.

``headless_login`` refuses a spawn whose output carries any value of the vendor's login file.
A native metadata exchange (an account read, a quota read) is the one spawn whose reply repeats
some of that file by design, so the transport that drives one says WHICH values its reply may
carry and WHERE, and this mixin is the rest: one spawn's exchange state, the split of the login
values into what the reply may repeat and what it may never, and the same split read again after
the spawn, so the scan before it and the judgement after it cannot disagree.

Split out of ``grok_build`` so that the next provider with such an exchange brings its own file
reader and its own mask and does not copy the circuit. Since then the circuit has been made total
over two of its hooks, split by role instead of by thread, and given the rule of place (below).

What a provider brings, as three hooks (the defaults admit nothing):

- ``_service_for`` -- which exchange a spawn is, known by its exact argv and stdin;
- ``_reply_metadata`` -- login field -> the values its reply may repeat, with a value that
  equals, holds or sits inside a key never among them (the key wins);
- ``_masked_reply`` -- the output with those values blanked in their own reply fields, and
  returned whole when the exchange's decoder does not accept it.

The rule of place: a value is judged at the fields whose admitted samples equal it or hold it,
and the mask is given those samples, not the value alone. So a principal id that stands inside
the id of its own picture is read where that id stands, and a principal id anywhere else in the
reply is an echo, as is any other value outside its own field.

Two of the hooks run under the shared login lease, where an exception poisons the login until
the OS restarts: ``_reply_metadata`` and ``_masked_reply``. The circuit is total over those two.
A ``_reply_metadata`` that fails ends the exchange for the circuit: nothing is admitted from
that call on, and the rest of the spawn is judged as any other spawn's, against every value
seen so far. A ``_masked_reply`` that fails makes the reply an echo. Neither raises out of the
spawn. ``_service_for`` is called in ``_attempt`` BEFORE the lease, which
``harness_attempt._owned_attempt`` and, for a relayed task, ``relay_attempt._relay_attempt``
take further in, so an exception of its own cannot poison the login and it is not guarded.
Reading the login file itself (``login_home``) is outside this circuit: it raises under the
lease for every provider.

Roles, not threads. ``publish()`` reads the login without the workspace's turn, while a quota
read runs on the collector's thread. So the narrowing is carried by what is asked, not by who
asks: ``LoginRoad._login_secrets`` (what publication and the checker read, and what the history
remembers) is never overridden here and is always whole. ``_spawn_secrets`` (what the runner
scans one spawn for) and ``_echoed_login`` (the same spawn judged afterwards) are the only
two narrowed, they are called only inside an attempt, and an attempt stands on the workspace's
turn. Neither touches the exchange state outside an attempt that opened one.

What a mixin needs from the class it is mixed into is stated rather than assumed: ``_attempt``,
``_spawn_secrets`` and ``_echoed_login``, ``HeadlessCliTransport``'s (``LoginRoad``'s for the
last two), and ``_signed_in_road``, ``LoginRoad``'s. It must stand FIRST among the bases: behind
``LoginRoad`` its methods are never reached.
"""
from __future__ import annotations

from .subscription_quota import SubscriptionRpc


class ServiceMetadata:
    """Judge a native metadata exchange's reply against the login it ran on."""

    #: The native metadata exchange the running spawn is, or None for every other spawn.
    _service: SubscriptionRpc | None = None

    # -- what a provider brings ------------------------------------------------

    def _service_for(self, argv, stdin_bytes: bytes | None) -> SubscriptionRpc | None:
        """The exchange a spawn of this argv and stdin is, or None. The base knows none."""
        return None

    def _reply_metadata(self) -> dict[str, frozenset[bytes]]:
        """Login field -> the values a verified reply may repeat. The base admits nothing."""
        return {}

    def _masked_reply(self, output: bytes, service: SubscriptionRpc,
                      own_fields: dict[str, frozenset[bytes]]) -> bytes:
        """The output with ``own_fields`` blanked where they belong. The base blanks nothing."""
        return output

    # -- the circuit -----------------------------------------------------------

    def _attempt(self, argv, cwd, **options):
        """Mark a native metadata exchange, known by its exact argv and stdin, for one spawn."""
        self._service = self._service_for(argv, options.get("stdin_bytes"))
        self._service_metadata: dict[str, frozenset[bytes]] = {}
        self._service_values: tuple[bytes, ...] = ()
        self._service_protected: tuple[bytes, ...] = ()
        try:
            return super()._attempt(argv, cwd, **options)
        finally:
            self._service = None
            self._service_metadata = {}
            self._service_values = self._service_protected = ()

    def _spawn_secrets(self) -> tuple[bytes, ...]:
        """Every login value, less -- on a metadata exchange only -- the metadata its reply repeats.

        The runner scans the whole output for what this returns before the spawn,
        and ``_echoed_login`` reads the same split after it, so the two sides never
        disagree about which values a reply may carry. Every value, with nothing less, for
        any other spawn and, from the call in which its hook fails, for the rest of that spawn.
        """
        values = super()._spawn_secrets()
        if self._service is None:
            return values
        self._service_values = tuple(dict.fromkeys((*self._service_values, *values)))
        try:
            return self._without_admitted(values)
        except Exception:  # noqa: BLE001 -- under the login lease a raise poisons the login
            # The hook failed: the exchange is over for the circuit. Nothing is admitted from
            # here, and every value seen so far is a key, one the spawn has since rotated away
            # included, so the rest of the spawn is judged as any other spawn's.
            self._service = None
            return self._service_values

    def _without_admitted(self, values: tuple[bytes, ...]) -> tuple[bytes, ...]:
        """The exchange's values less the metadata admitted so far, as the hook now answers."""
        metadata = self._reply_metadata()
        admitted = frozenset().union(*metadata.values())
        self._service_protected = tuple(dict.fromkeys((*self._service_protected,
            *(value for value in values if value not in admitted))))
        for field, samples in metadata.items():
            self._service_metadata[field] = self._service_metadata.get(field, frozenset()) | samples
        # A refresh may replace metadata or change a value's role. Keep its old
        # field provenance, while a protected role on either side always wins.
        self._service_metadata = {field: frozenset(value for value in samples
            if not any(value in key or key in value for key in self._service_protected))
            for field, samples in self._service_metadata.items()}
        admitted = frozenset().union(*self._service_metadata.values())
        return tuple(value for value in self._service_values if value not in admitted)

    def _echoed_login(self, output: bytes) -> bool:
        """A key anywhere, or admitted metadata anywhere but its own field of a verified reply."""
        if self._service is None:
            return super()._echoed_login(output)
        if not output or not self._signed_in_road():
            return False
        if any(value in output for value in self._spawn_secrets()):
            return True
        if self._service is None:
            # The hook failed in that very call: it handed back every value seen, and none is here.
            return False
        metadata = self._service_metadata
        for value in frozenset().union(*metadata.values()):
            # Each value is judged at its own places, and only those are masked: masking a
            # sample that does not hold it must not conceal it.
            own_fields = self._places(value, metadata)
            try:
                if value in self._masked_reply(output, self._service, own_fields):
                    return True
            except Exception:  # noqa: BLE001 -- a mask that fails judges nothing: an echo
                return True
        return False

    @staticmethod
    def _places(value: bytes,
                metadata: dict[str, frozenset[bytes]]) -> dict[str, frozenset[bytes]]:
        """The fields whose admitted samples EQUAL or HOLD ``value``, with just those samples.

        The rule of place. A value stands in its own field, and also inside a longer sample of
        another field when that sample is where the vendor put it (a principal id inside the id
        of the picture that belongs to it). The mask blanks those samples, whole, at their own
        reply fields; the same value anywhere else in the reply stays and is an echo.
        """
        held = {field: frozenset(sample for sample in samples if value in sample)
                for field, samples in metadata.items()}
        return {field: samples for field, samples in held.items() if samples}
