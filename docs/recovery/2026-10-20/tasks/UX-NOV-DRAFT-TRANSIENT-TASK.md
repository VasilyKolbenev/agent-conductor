# Restore the unsubmitted first-task draft without storing text in the browser

Base `0148af5`, integrated with the model-field feature from `ce77ba5`. Replace the browser session storage used by first-task F5 in the actual Desk. Keep the current draft in the editor, optionally remember it in the verified active project's server memory, and mark whether F5 can restore the latest edit. Explicit close discards it; no account, file, task, prepare, grant, CLI or durable run is created by this service.

Preserve the existing transport, CSRF, project identity and the SEALED guard. Tests cover unknown/foreign keys, late saves after discard, parallel writes, expiry, size/capacity, exact draft shape, materials/pins and the actual served page on reload. Do not put editable text in browser storage, the URL, history or logs.
