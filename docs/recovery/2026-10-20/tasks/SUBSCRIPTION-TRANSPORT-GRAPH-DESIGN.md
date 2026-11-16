# Use the established headless CLI facade

The graph module produced 1 failed and 5 passed on the integration candidate.
The structural test stops at Codex; scanning every transport also identifies Grok.
Both import the newly introduced declarations from the shared profile directly alongside
their existing headless transport import. The other three transports use the single site.

Re-export the two existing profile record types through the existing import block in
`headless_cli.py`, alongside `HarnessProfile`. Import from that single block in each
affected transport. Moving the definitions into the facade would change ownership of
declarative types. Moving either import into a function would retain the extra dependency.
The existing graph test exercises both the import source and cycles, the identity test
protects provider ownership and the setup tests cover both selectable reviewed cards.
