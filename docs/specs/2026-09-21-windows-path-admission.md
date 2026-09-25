# Windows path admission for new writes — 2026-09-21

This is separate from F1 work-scope ownership. The durable ID grammar, frozen
task bindings, template documents and journal readers do not change. IDs are
never trimmed, case-folded, shortened, renamed or merged.

## New filesystem names and budgets

New run/task/workflow directory IDs, task work scopes, and deep dispatch/review
work item/scope names refuse a trailing dot or space and Windows device
basenames, including case variants and extension suffixes. The rule is portable
across hosts; the existing ASCII ID grammar remains the prerequisite.

Windows path budgets count UTF-16 code units of the full absolute path, not ID
length, Python scalar count, UTF-8 bytes or the relative route. They apply only
to Windows path objects:

- A native work cwd is at most 258 units, reserving separator and NUL.
- A new store directory is at most 247 units; a new store file at most 259.
- The store budget includes its actual private directory/file staging names
  and run creation's `decisions` subdirectory. The current eight-character
  CPython tempfile suffix is explicitly witnessed against real store staging.

These are this build's conservative supported-operation limits. They are not a
claim that all Windows APIs share MAX_PATH: long-path-aware file APIs may accept
more, while Microsoft's SetCurrentDirectory documentation warns that an
overlong cwd can make CreateProcessW fail. No registry or host settings change.

## Admission placement

`command/path_admission.py` contains pure name/path predicates and typed
`WindowsNameError`/`WindowsPathError` (ContractError subclasses). `new_work_admission`
applies them only to dispatch/review under the registry's already-frozen
`deep-arguments-v1` schema. It takes the trusted RunStore project root and uses
the single pure `work_layout.work_parts` layout, re-exported through the original
`harness_workspace` seam. The caller first validates the entire registered
argument schema; admission consumes those fields without importing adapters.
There is no new registry callback or mutable
adapter discovery. The production server constructs its stores and provider
workspaces using the same project root; transports additionally check their
own root before any work effect.

- Stores check new paths before their first mkdir/staging write.
- New task/run/workflow HTTP writes check missing directory identities before
  Windows metadata can turn an invalid basename into an unrelated route fault.
  Existing directories follow the original comparison/read branch first.
- `CommandService.propose` checks new work after schema and F1 scope validation,
  before proposal append. A full candidate with a standing proposal ID follows
  the existing store comparison/RecordConflict arbitration, bypassing only the
  new admission rule. HTTP proposals use this same service. This HTTP door does
  not accept a caller-supplied proposal ID: a
  resubmission is a new proposal, not an exact durable retry.
- The common HTTP plan-binding judgment checks every capable node after its
  registered schema. Raw graph, from-template and run-open invoke it only for a
  new plan. A plan embedded in a new run is refused before the run is created.
- Transport prepare and direct execution check again before home sweep,
  instruction materialization, version probe, work mkdir, marker or task spawn.
  The workspace creation door checks before its first work-root mkdir.

## Public refusals

Two new frozen 422 codes carry empty detail and fixed messages:

- `windows_name_unsafe`: choose an identifier without a trailing dot or space
  and without a reserved Windows basename such as NUL.
- `windows_path_too_long`: shorten the identifier or move the project to a
  shorter path; the Windows path budget is exceeded.

Mapping is by exception type, before generic ContractError handling. Arbitrary
exception prose, submitted values, root paths and OS messages are never copied
into the public refusal. The existing response envelope is unchanged.

## Historical behavior and limits

Existing task/run/graph exact repeats return their standing records before new
admission. Template revisions compare existing bytes before staging; identical
draft bytes write nothing. Reading an old unsafe ID or plan remains allowed by
the original grammar. A new revision or changed draft under an unsafe legacy
workflow ID is a new write and is refused; saving under a new safe workflow ID
is the operator's explicit next action. No migration is performed.

Historical authorization exact-repeat/grant rules, runtime recovery and F1 are
unchanged. New proposals against an old unsafe plan are refused by admission;
old authorized requests do not gain new execution authority after a restart.
The CLI dispatch preview translates these two new refusal types through its
existing PreviewError diagnostic door. Existing run/task directories retain
their Exists arbitration before the new creation budget.

This slice does not promise to restore listability of directories already
trimmed by Windows, solve general case-fold aliases, or predict arbitrary files
created by a child. Future decision-receipt/artifact/home naming is separate
from the reported run/task/workflow/work-item tail.

Sources: [Windows naming](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file),
[SetCurrentDirectory](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setcurrentdirectory),
[path length and long-path opt-in](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation).
