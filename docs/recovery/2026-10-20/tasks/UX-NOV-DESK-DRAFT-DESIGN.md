# Reload an unsubmitted task

Task: preserve the ordinary Desk draft on refresh. Closing it and starting
another task must give a blank form. Once preparing starts, use the existing
server-backed recovery address.

Use the current tab's navigation entry. Store editable answers, never the
reducer, credentials, CSRF/session values, preview, authorization, execution
requests, receipts, provider metadata or materialized project documents.
Bind the snapshot to the active project's verified activation ID and the
generated task ID. Restore only into the same entry, before preparation and
after a fresh project read. With no confirmed identity use the in-memory
draft. A new click starts fresh. Reopen on the first page so the owner can
inspect their answers against the current source and providers.

Persistent localStorage shared across unrelated tabs is the alternative.
The tab entry better matches this feature's scope. The Desk's URL writer
must preserve its entry's state when normalizing a hash. Node/browser
witnesses cover reopening, explicit close, changed identity and absence
of authority. The owner still confirms the immutable grant in the app.
