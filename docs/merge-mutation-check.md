# Testing the merge engine with mutations

From the checkout, run `python scripts/mutate_merge.py` with pytest installed.
The script makes one deliberate change at a time and runs the tests that should catch it.

## 1. Workspace and restore guarantees

- `scripts/mutate_merge.py` copies the sources and targeted tests into a temporary
  directory outside the checkout. Before applying a mutation, it verifies that Python
  imports the copied merge engine and that the tests pass on the unmodified copy.
- Each mutation changes only the copy. The script retries a failed restore and verifies
  the restored file by hash. A hard kill can leave the temporary directory behind.
  The original checkout remains intact.
- Use `python scripts/mutate_merge.py --verify-only` to check import provenance.
  For a mutation score, run the full command. A pytest exit code of 1 on a mutation
  means the tests caught it. An invalid measurement produces no score.
