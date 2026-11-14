# Use one recommended budget in Desk and Studio

Desk requests the server's proposed terms with an empty object. Studio
currently computes its own timeout, attempts, checked-step reserve and
permission duration in the browser. Use the same existing preview endpoint
on explicit Review, including after a previous grant. Show the reason from
the returned plan: steps, attempts, checks, previous spend and the uncertainty
of elapsed time/subscription usage.

Design: leave the initial draft without invented numbers. On explicit Review
request `{}` for the current grant. Explicitly opening the limit editor can
fetch the same proposal as a starting point. After a real numeric edit send
the owner's complete manual terms and preserve them across rereads. Return
to server recommendations only by a separate choice. Keep an absent preview
or an exhausted recommendation from becoming a grant. No request on merely
opening the run and no automatic authorization. An alternative automatic
request on page open would replace a session preview without a person.

Use Studio's automation model, flow, render and copy, and its established
tests. The server API and current Grok candidate stay as they are. Compare
real terms from a fresh and a replacement run against Desk's existing
projection and the history-derived server limits. No live model call.
