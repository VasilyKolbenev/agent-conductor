# K2a review — no activation on design ba83a60

The Kimi-specific layout in option B is the right direction. The existing generic
copy/cleanup and grant paths do not establish the required identity invariants
for that layout. Do not enable the Kimi relay or relax the rules for existing
providers. Local CLI startup is independently proven in H5-KIMI-NATIVE-BASELINE.

Windows security lens:

1. Relative creation. The present allocator uses mkdir and later reopens by
   pathname. Pin the parent. Create the one literal child relative to that
   handle, exclusively, and keep the handle returned by creation. Capture
   identity before any write or grant. The same applies to the attempt root.
2. The grant currently reacquires the home by pathname. It must compare the
   originally created object and hold it across grant/attach. A task may write
   only to scratch. Measure whether this CLI can operate with the credential
   subtree protected. A hardlinked credential or substituted object must refuse.
3. Rollback must never follow a replaced path, ignore cleanup failure or infer
   ownership from a prefix. Record ownership before writing any sensitive bytes.
   Require handle-bound deletion, crash recovery, refusal if identity is unclear,
   and evidence that an external sentinel survives every partial-create case.
4. The current loan audit checks immediate children of configured login homes.
   Kimi keeps its actual credential one level deeper. Verify whether an explicit
   read ACE on that file allows an unrelated AppContainer direct access, including
   when the active task belongs to another harness. W4 has its own native red test
   and fix track. This finding was initially from inspection, not a measured leak.

Compatibility lens:

1. Preserve the serialized transport facts, grant digest and flat-path behavior
   of Claude, Codex and Grok. Compare actual old/new bytes for each. Bind the
   Kimi layout to its own facts. Recheck the selected region before each effect.
2. Distinguish discovery of configured login roots from authorization to read
   their contents. Use protocol from the same configuration read. A user can
   choose a different folder name. The ACL audit must never read token bytes.
3. Recovery, loan and sweep readers must agree on the typed Kimi home. A new
   name prefix alone cannot establish ownership of data. Keep old journal
   records recoverable when the Kimi route is disabled or a provider is removed.
4. Do not write new API fields solely to satisfy the browser. The browser should
   accept bounded transport facts and display only documented capabilities.
   Test an actual preview and grant digest including the new profile.

Next proof: a no-secret Windows prototype of create/hold/reopen/delete relative
to pinned directory handles, plus the W4 regression. After those proofs review
K2a again before wiring access-token bytes or enabling dispatch.
