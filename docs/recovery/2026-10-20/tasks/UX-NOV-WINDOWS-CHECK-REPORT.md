# Windows rehearsal follow-up

The full main-branch rehearsal exposed three outdated UI witnesses and an
ambiguous subscription receipt. Each has a targeted passing witness. All four
paid harnesses and the mixed Dalio cycle still need live acceptance.

| Evidence that failed | Correction and local result |
| --- | --- |
| On a77637a the Node wizard host test stopped at the missing browser event target. | 0241f44 supplies a real EventTarget and an empty history. Its two reentrant-close checks still run. The test counts both unload listeners and their removal. Omitting removal in a copy fails the test. |
| Six Chromium Git recovery scenarios tried to fill a title which is hidden on the first guided screen. | ecfa0a9 uses the first screen where the project source actually appears. Signed commit, recovery after a crash and disabled setup controls remain covered. Nine tests passed in each Windows encoding. |
| Two Chromium subscription refusal scenarios expected the old login-directory instruction. | ecfa0a9 checks the chosen translation, independent English and Russian guidance to select a compatible harness, no run written and no browser errors. All 46 tests passed in each encoding; a generic retry message fails both language cases. |
| On 0241f44 the host under load timed out before Claude answered its login question. Its receipt incorrectly said it reported no subscription login. | 2206d7f distinguishes that condition from a completed negative answer and from the prompt exceeding its time. Both receipts are tested at their actual stages. The prompt test sees a claimed action and exactly one synthetic task. All 59 relay lifecycle and subscription tests passed in each encoding. |

The full core runs on a77637a and 0241f44 correctly stopped on their failing
batches. No wheel was promoted from them. The earlier 42-group green build
a9044e1 is reserved for Grok diagnostics and does not contain the guided UX.

## Final results of the 61f9269 rehearsal

The Chromium gate ran all 114 modules. 113 passed and one failed. The failed
English queue test observed a retry request before Playwright had forwarded it
to the server. Delaying that request by 250 ms reproduced the same failure.
b26c470 waits for the dialog to close and then checks the server's queue and
the exact POST sequence. All 15 tests in the corrected queue module passed.

The core gate ran 23 of 46 groups. 22 passed; the remaining group caught six
direct closes in the wizard test's Chromium contexts. The gate stopped after
that UTF-8 batch. 7a479cd drains route handlers using the shared browser harness
before closing. All 19 guard tests and all 10 wizard-host Chromium tests passed.
The two corrected browser modules and the guard passed together in the system
encoding (44 tests). The login timeout classification also reaches the durable
runtime vocabulary in 713d845 (302 targeted tests passed in each encoding).

These results leave an exact full core and browser run, CI wheel and installed
owner acceptance outstanding. No public release was made. See
H5-GROK-G6-ALPHA-REPORT.md for the independent single live Grok attempt.
The offline fixtures and Chromium checks above use no provider subscription.
