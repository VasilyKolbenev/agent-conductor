# Bounded run execution and correction integration

New workflows may explicitly declare `execution_contract: "bounded-run-v1"`.
This permits dispatch without a gate before each action and permits an explicit
`on_failed` correction road. The workflow can only materialize into a new Policy
run whose frozen configuration declares `automation_contract: "bounded-run-v1"`.
Omission retains historical topology and wire semantics; null and unknown values
are refused. Drafts preserve the optional marker. Existing human gates still
require real human decisions. No automatic gate decision is synthesized.

The read-only automation preview includes provider facts from the same configured
authority used for its provider digest. No credentials are returned: environment
variable names, selected model, contract/profile pins and effective limits describe
the chosen configuration. The server checks that the facts match the digest in
the preview. Authorization consumes the exact preview, not a newly resolved set.

`CorrectionFeedback` is a new closed journal record (`correction_feedback`). Its
runtime attribution includes run and authorization ID/digest, source action,
attempt, node and lap, checker instance and adapter, checked result manifest and
manifest digest, feedback ID and timestamp. Its payload is exactly the bounded
`conduct.feedback.v1` schema documented in the typed feedback specification.
It is not a successful result artifact and grants no execution authority.

Only explicitly authorized Policy dispatch checks opt into the new response
protocol. Parser refusal, missing actionable findings, unknown execution outcome,
or orphaned feedback without a definitive checker-rejected terminal receipt stops
automatic correction. The checker scans semantic fields against the doer's sampled
secrets and its own retained credential samples before serialization/publication.
Historical Confirm checks retain their original verdict semantics.

The opted-in frame names one reply shape: reasons may follow `VERDICT: accept`; after
`VERDICT: reject` nothing but the one JSON object. The findings bound it states is the smaller of
8192 bytes and the reply bound less the verdict line and two line breaks. Measured live
(`live-nc-1`, 25.09.2026): a frame that also asked for reasons after the verdict lost a real
checker's rejection. A reject whose findings the parser refuses (malformed, over a bound, or
quoting a sensitive value) is recorded as that checker's rejection with the reason
`rejected_findings_refused`, never as an absent verdict; it still carries no correction.

Correction follows only the first executable actions on the explicit failure
frontier. The ordinary scheduler still decides whether a branch, human gate or
bounded loop permits the action. A correction proposal pins `feedback_ids` in its
content digest. The source is selected from that proposal's exact journal prefix;
execution never substitutes later feedback. A permitted next lap may consume its
predecessor's findings. A settled corrective action consumes that predecessor,
while a new rejection supplies its own attributed findings.

Instructions and initial documents remain those fixed by the authorization.
Findings are a separate data section and cannot change arguments, scope,
participants, budgets or tools. This is an authority boundary, not a promise to
detect the semantic intent of arbitrary model-written text.

Dispatch manifests bind action/attempt, ordered input artifact IDs and sorted
relative result paths. Present entries contain full byte length and SHA-256;
deleted entries contain zero length and null digest. The checker materializer
must independently match every present file's actual full bytes and every deletion
before spawn. Existing file/frame limits remain in force. Oversized files are
refused rather than accepted from hashes alone. Work-tree hashing and scope checks
do not constitute a general filesystem sandbox.

Acceptance status and executable evidence belong to the current handoff report;
this specification alone does not mark native-account or release acceptance done.
