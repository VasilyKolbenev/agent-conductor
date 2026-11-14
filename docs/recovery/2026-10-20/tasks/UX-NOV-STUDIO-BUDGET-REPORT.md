# One recommended budget — locally verified

Studio and Desk now review the same terms and digest for the same frozen
run and journal. Source, limit, checker and replacement decisions remain
server-owned. TASK/DESIGN a289fa6, implementation 6809558, based on 716ced7.

Opening a Studio run performs its ordinary read. Review or the first opening
of the limit editor explicitly asks for the recommendation with an empty
preview request. The response supplies the limits, attempts and earlier spend.
Opening or resetting the editor only prepares fields. Editing a number switches
to explicit manual terms. A failed reset preserves the edits and requires
another review. Transitioning to a changed grant invalidates a pending or
previous preview. No preview authorizes a run.

The same fresh and replacement project snapshots were passed through the real
budget service and the shipped Studio and Desk paths. The previous grant in
the replacement actually spent one action and reserved 60 s on a deterministic
adapter. Both recommended terms and digests matched. A real standard cycle
preview showed four possible attempts for Do and eight permitted actions in
this deployment. An incompatible manual ceiling is still refused. No inference
latency, quota forecast or paid account was measured.

The before-change witness failed twice: Studio sent locally calculated
numbers instead of the empty request. Verification after the change included
the served bilingual Studio browser, stale preview, pending reply after
grant change, manual failure/recovery, module graph and line cap: 265 passed.
The system-encoding affected selection added 64 passing cases. In isolated
copies M0 passed all four comparison/race cases. Substituting a local numeric
request, discarding manual limits on failure, or accepting the late reply each
made its own regression witness fail. File digests were restored afterwards.

Last proven: reviewed terms in a local served project. First remaining:
integrate into the release branch and run candidate gates there. The current
Grok rehearsal was not changed or rerun for this slice.
