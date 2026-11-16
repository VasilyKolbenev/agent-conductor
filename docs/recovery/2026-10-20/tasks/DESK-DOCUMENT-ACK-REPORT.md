# DESK-DOCUMENT-ACK

The selected run now consumes the accepted document draft when its controls are being reread.

[Ubuntu job 133140469805](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/43819936893/job/133140469805)
failed only `test_document_and_manual_step_are_written_for_the_selected_task_run` in forward
order. The official artifact 14209112877 has SHA-256
`7fca005561263f0b27f7572548d6df39d8fcfbbbf7bffdf8d53d3ce2b776035b`. The document
POST returned 201, then the editor retained the submitted text until the 30-second timeout.
The reverse run passed. CI did not record the precise order of the two responses.

On `dbdfc2e` the local Chromium witness holds the real server's 201 response, publishes
a state event, holds the ensuing controls GET, and delivers the acknowledgement. The
expected empty textarea failed deterministically before the correction and passed afterwards,
both before and after the GET landed. New writes still require fresh controls; the shared
writers retain their run, task and draft-generation checks.

Windows UTF-8: 15 tests passed across the host, real document write, decision rereads,
decisions, live selection and run view. CP1251: the changed Chromium witness and Node host
passed. This reproduces the Ubuntu symptom locally. A fresh Linux CI job remains release
evidence for the integrated candidate. The tests used the local server and fixture provider.
