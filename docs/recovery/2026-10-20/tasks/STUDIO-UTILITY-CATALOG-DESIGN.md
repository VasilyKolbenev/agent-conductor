# Keep translated setup instructions as data

`studio_source_messages._messages` reads bilingual arrays as JSON. JavaScript
string concatenation in an array renders in the browser but breaks that shared
reader even when the currently displayed screen asks for an unrelated message.

Express the two instructions as ordinary bilingual rows. The existing disclosure
renders each instruction in its own paragraph. Keep each edited translation line
within 100 UTF-8 bytes. This preserves the source reader and its independent checks.

Use the existing routing regression for catalogue syntax. Extend the provider
card's browser check to open the disclosure and read both instructions in each
locale. Reintroducing concatenation and omitting the Python alternative must
each fail a corresponding check.
