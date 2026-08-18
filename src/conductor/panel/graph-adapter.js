"use strict";
// The input adapter, and deliberately nothing else: the single place where an
// external payload becomes the panel-internal fixture shape graph-store.js
// validates. fixture_schema 1 is PANEL-INTERNAL — it is NOT the wire
// contract. The runtime side has not frozen its JSON forms yet (provider
// availability, controls, execution projection, graph definition are all
// still its open questions); when those forms land, their mapping into the
// internal shape is written HERE and nowhere else, so the store, the reducer
// and the visual layer stay still while the wire arrives.
//
// Until then this adapter accepts exactly the internal shape and refuses any
// other schema version out loud — it never guesses at a mapping the runtime
// side has not stated.

export const INTERNAL_SCHEMA = 1;

export function adaptPayload(external) {
  if (!external || typeof external !== "object" || Array.isArray(external)) {
    return null;
  }
  if (external.fixture_schema !== INTERNAL_SCHEMA) return null;
  // The schema pin is this adapter's own fact and travels no further: the
  // store never sees the field, so a load that skipped this function would
  // hand the store a key it refuses — every fixture in the suite then pins
  // the call site behaviourally, not by a source grep.
  const {fixture_schema: _, ...internal} = external;
  return internal;
}
