# Shared first-run form

Base 03b56d7. The default wizard asks for six separate screens in desk-wizard.js. Its
existing reducer already checks every earlier gate on forward navigation. Keep that contract
and group task/materials, cycle/roles and prepare/run into three pages. The last page keeps
the durable prepare and the fresh grant as two explicit operations. Detailed mode projects
the very same draft, without copying answers or emitting writes by switching views.

The alternative was an independent dialog with its own draft and request sequence. That
would need to keep two previews and the task/run identifiers in sync after an edit. Use the
existing reducer, seed handling, preview, and authorize door instead. The UI may propose the
task title from the first nonempty line of the user's goal. Preserve the whole goal verbatim
and keep an explicitly edited title. Only offer a Dalio shortcut when the server enumerates
the shipped checked starter. Keep existing saved cycles and explicit choices.

Use the served Desk browser fixture with a deterministic adapter. Observe the number of
visible stages, the checked starter, unchanged draft through Back, the immutable project
task, reviewed grant and absence of execution before the owner's click. Unit witnesses
cover fields that the renderer merges and old advanced navigation. Fake accounts cannot
prove a real subscription or model outcome. Server preview owns all budgets.
