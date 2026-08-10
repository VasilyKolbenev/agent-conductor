"""Which real event starts the panel's one movement, and which events may not.

DEC-UI-4 leaves the panel with a single animation: the ring a stage draws once,
when this browser has watched that stage become the current phase. What the
animation *is* — its keyframes, its duration, its reduced-motion override, and
the fact that it is the only one — is held in tests/test_panel_style.py, over the
stylesheet. What this module holds is the other half, and the half the owner's
acceptance criterion names: the class that carries the movement is written from
one decision, and that decision fires only on an event the panel observed.

The owner settled the decision on 2026-08-09 in three conditions. A phase change
may be reported only when a drawing already exists to have changed from, when
this state document and the one before it both arrived through the live stream,
and when the two name different current phases. Six things that are not a
change are pinned one by one here: a page load, a reconnect, the first frame
after either, a new `generated_at`, a new queue — and a response fetched before
the stream dropped. The sixth is why the other five do not simply follow from
the three conditions, as this docstring used to claim: the conditions read a
record, and review finding F1 reproduced a stale response landing after a
reconnect, writing that record, and handing the greeting frame a change the
panel never watched. So every drop ends an epoch, and a response from an ended
epoch is discarded before the record can hear from it.

Scope, and it is the module's whole limit. Everything below reads the panel's
*script* as characters — the same limit tests/test_panel_cascade.py states for
the stylesheet, inherited for the same reason. No browser runs, no timer fires,
nothing is animated while a test watches. So these guards establish which
expression the panel *declares* the movement to depend on; that a browser then
starts and stops the animation accordingly is not established here, and no name
or comment in this module may be read as saying it is. Assertions on a running
panel are §10 post-alpha work.
"""
import re

from tests.test_panel_cascade import (
    free_names, function_body, panel_html, script, script_functions)


def decision() -> list[str]:
    """The conjunction ``noteState`` reports a phase change on, term by term."""
    body = function_body("noteState")
    head, _, tail = body.partition("ARRIVED =")
    assert tail, body
    return [" ".join(term.split()) for term in tail[:tail.index("?")].split("&&")]


def movement_circuit() -> str:
    """The source of everything the decision is computed from."""
    return function_body("noteState") + phase_reader()


def phase_reader() -> str:
    """The expression the decision reads a document's current phase through."""
    found = re.search(r"const phaseOf = (.*?);\n", script(), re.S)
    assert found, "the panel no longer reads a current phase through one expression"
    return found.group(1)


def refresh_calls() -> list[tuple[str, str]]:
    """Every call to ``refresh``: what triggers it, and the argument it passes."""
    out = []
    for line in script().splitlines():
        if "refresh(" not in line or "function refresh(" in line:
            continue
        trigger, _, call = line.partition("refresh(")
        out.append((" ".join(trigger.split()), call.split(")")[0]))
    return out


def naming(token: str) -> set[str]:
    """Every declared function whose body names ``token``."""
    return {name for name in script_functions()
            if re.search(r"(?<![\w$])" + token + r"(?![\w$])", function_body(name))}


# ── the class, and the one expression that writes it ───────────────────────
def test_the_movement_class_is_written_by_the_stage_builder_and_by_nothing_else():
    # One writer, one flag. The stylesheet keys the animation on `.orb--arrived`;
    # the script spells that class exactly once, in the stage builder, behind the
    # flag it was handed. A second writer — a class added on a timer, on a hover,
    # on a re-render — would have to spell the word a second time.
    assert script().count("orb--arrived") == 1
    body = function_body("orbitStage")
    assert 'arrived ? " orb--arrived" : ""' in body
    # the flag itself is read once and not stored; the class name is not it
    assert re.findall(r"(?<![\w$-])arrived(?![\w$])", body) == ["arrived"], body


def test_both_layouts_hand_the_flag_to_the_stage_the_stream_named_and_to_no_other():
    # The flag is not a boolean the drawing invents: it is a comparison between
    # the stage being drawn and the phase the decision reported. Held in both
    # layouts, because a movement present in one and absent in the other would be
    # a movement whose trigger depends on the viewport width.
    for name in ("drawOrbitRing", "drawOrbitColumn"):
        body = function_body(name)
        assert re.search(r"orbitStage\(p, proj\.seatOf\(p\), p === proj\.arrived\)",
                         body), name
        assert body.count("arrived") == 1, name


def test_the_flag_is_spent_by_one_drawing_and_a_redraw_cannot_replay_it():
    # A movement reports an event, and the event happened once. renderOrbit takes
    # the flag out of the module and clears it in the same statement pair, before
    # either layout is called — so the resize redraw, which re-renders the same
    # state document at a new width, draws no arrival. reflowOrbit is where that
    # would otherwise leak: it calls renderOrbit and never the decision.
    body = function_body("renderOrbit")
    assert "arrived: ARRIVED" in body
    assert "ARRIVED = null;" in body
    assert body.index("ARRIVED = null;") < body.index("drawOrbitRing")
    assert "noteState" not in function_body("reflowOrbit")
    assert naming("ARRIVED") == {"noteState", "renderOrbit"}


# ── the owner's three conditions, one check each ───────────────────────────
def test_the_decision_is_the_conjunction_of_the_three_conditions_and_of_nothing_else():
    # The whole of it, in one place, so a fourth term cannot be added quietly and
    # a third cannot be dropped. `framed` and `streamed` are the two halves of
    # one condition — this document came through the stream, and so did the one
    # before it — which is why four terms carry three conditions.
    assert decision() == ["framed", "streamed", "LAST !== null",
                          "phaseOf(s) !== phaseOf(LAST)"]


def test_a_first_drawing_has_to_exist_before_anything_can_be_said_to_have_arrived():
    # The owner's first condition. `LAST` is the state document already drawn,
    # and it is not merely tested for: it is the operand the incoming phase is
    # compared against, so with nothing drawn there is nothing a change could be
    # a change from. The comparison and the test are the same reading.
    assert "LAST !== null" in decision()
    assert "phaseOf(s) !== phaseOf(LAST)" in decision()


def test_the_two_documents_have_to_have_come_through_the_live_stream():
    # The owner's second condition. `framed` is this document's own arrival and
    # `streamed` is the previous one's, and the only place `streamed` is set from
    # a document is the decision itself, where it is set to that document's
    # `framed` — so a document that did not come through the stream always leaves
    # the flag down for whatever follows it.
    assert "framed" in decision() and "streamed" in decision()
    assert "streamed = framed;" in function_body("noteState")
    assert naming("streamed") == {"noteState", "refresh"}


def test_the_current_phase_has_to_have_actually_changed():
    # The owner's third condition, and the reported phase is the changed one:
    # the same expression that decides there was a change supplies the value the
    # drawing is handed, so the movement cannot land on a stage the comparison
    # never mentioned.
    assert "phaseOf(s) !== phaseOf(LAST)" in decision()
    body = function_body("noteState")
    assert re.search(r"\?\s*phaseOf\(s\)\s*:\s*null;", body), body


# ── the five events that are not a change ──────────────────────────────────
def test_a_page_load_draws_the_first_document_and_reports_no_change():
    # Non-trigger 1. The startup fetch is a call to refresh outside every
    # function, and it passes the argument that is not a frame.
    top_level = [arg for trigger, arg in refresh_calls() if not trigger]
    assert top_level == ["false"], refresh_calls()


def test_a_reconnect_re_establishes_the_record_and_reports_no_change():
    # Non-trigger 2. Both halves: the resync a reopened connection asks for is
    # not a frame, and the error that precedes it puts the previous document's
    # flag down — a phase that moved while the panel was not listening was not
    # watched moving.
    assert ("es.onopen = () =>", "false") in refresh_calls()
    assert re.search(r"es\.onerror = \(\) => \{ EPOCH\+\+; streamed = false;", script())


def test_the_first_frame_after_a_connection_opens_reports_no_change():
    # Non-trigger 3, and the reason the second condition has two halves. The
    # frame itself is framed, but the document before it was the reconnect resync
    # or the page load, and neither is — so `streamed` is down when the first
    # frame is weighed, and the frame's own job is to put it up for the next one.
    assert refresh_calls() == [("es.onmessage = () =>", "true"),
                               ("es.onopen = () =>", "false"),
                               ("", "false")]
    assert "streamed = framed;" in function_body("noteState")


def test_a_newly_written_state_document_with_the_same_phase_reports_no_change():
    # Non-trigger 4. `generated_at` moves on every write the merger makes, and
    # the panel reads it — the shell ages it into "last update". The decision
    # cannot: the only field of a state document the movement circuit names is
    # the current phase, reached through one expression.
    assert "generated_at" in function_body("renderShell")
    assert "generated_at" not in movement_circuit()
    assert re.findall(r"\.\s*([A-Za-z_$][\w$]*)", phase_reader()) == \
        ["cycle", "current_phase"]


def test_a_change_in_what_is_waiting_on_a_person_reports_no_change():
    # Non-trigger 5. Same relation, second consequence: `human_queue` is a field
    # the panel reads and redraws on every frame, and it is outside the circuit
    # the movement is decided in. The circuit reaches for four names, and a
    # second reading of the document would have to be one of them.
    assert "human_queue" in function_body("render")
    assert "human_queue" not in movement_circuit()
    assert free_names(function_body("noteState"), {"s", "framed"}) == \
        {"ARRIVED", "streamed", "LAST", "phaseOf"}
    assert free_names(phase_reader(), {"s"}) == {"String"}


def test_a_response_fetched_before_the_stream_dropped_cannot_write_the_record():
    # Non-trigger 6, review finding F1, reproduced live by the reviewer: a
    # frame's fetch held across a drop resolved after the reconnect, raised
    # `streamed`, and the greeting frame after it was handed a change the panel
    # never watched. So the record is written only from the epoch it describes:
    # a drop ends an epoch, a fetch captures the epoch it started under before
    # anything is awaited, and a response from an ended epoch returns before
    # the decision, the drawing or the connection light can hear from it — on
    # the failure path too, where it would otherwise knock down a record the
    # current connection had honestly built.
    body = function_body("refresh")
    discard = "if (epoch !== EPOCH) return;"
    assert body.index("const epoch = EPOCH;") < body.index("await fetch")
    assert body.count(discard) == 2
    assert body.index(discard) < body.index("noteState(")
    assert body.rindex(discard) < body.index("streamed = false;")
    assert script().count("EPOCH++") == 1            # only a drop ends an epoch
    assert naming("EPOCH") == {"refresh"}


def test_the_registry_answering_late_redraws_the_panel_and_reports_no_change():
    # Not one of the owner's five, and the same class: `/harnesses.json` arriving
    # after the first state document re-renders the whole panel from a document
    # that has not changed. It re-renders by calling render, which never reaches
    # the decision — so the redraw carries whatever flag the drawing before it
    # left, and that flag has already been spent.
    body = function_body("loadHarnesses")
    assert "render(LAST)" in body
    assert "noteState" not in body and "refresh" not in body


def test_the_panel_names_no_second_movement_for_a_reader_to_have_to_explain():
    # The acceptance criterion, as an absence that a rewrite cannot satisfy while
    # keeping the thing: one class carries movement, one decision writes it, and
    # the word the deleted permanent glow was attached to is still nowhere in the
    # file. tests/test_panel_style.py holds the stylesheet side of the same count.
    assert "pulse" not in panel_html()
    assert script().count("noteState(") == 2         # the declaration and its caller
