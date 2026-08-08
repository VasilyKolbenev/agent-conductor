"""What `scripts/mutate_merge.py` says about itself, against what it is.

Nothing here runs the harness. These read the shipped file — its abstract
syntax tree, and the prose in its docstrings — and compare a claim with
something that can be computed from the code, or pin a shape the code has to
keep. They are separate from tests/test_mutate_harness.py, which runs the
instrument, because they need no fixture, no interpreter and no subprocess, and
because the two circuits together no longer fit one file under the 800-line
rule. The split is the rule's own remedy: a self-contained circuit moves to its
own module, and nothing moves into `conftest.py`.

The defect class they exist for is prose about code that the code stopped
supporting: a docstring, a comment or a table that was true when it was written
and stayed after the code moved. A guard that requires or forbids a WORD cannot
hold that, because a rewrite into the opposite claim keeps the vocabulary — and
because an innocent true sentence can carry the forbidden word and redden a
suite for nothing. Both of those happened here and are pinned below.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "mutate_merge.py"


def harness_ast() -> ast.Module:
    """The shipped script, parsed — structure is read, never grepped for."""
    return ast.parse(HARNESS.read_text(encoding="utf-8"))


def module_doc() -> str:
    """The shipped script's module docstring, read from the file that ships."""
    return ast.get_docstring(harness_ast())


def function_doc(name: str) -> str:
    """The docstring of one function of the shipped script."""
    function = next(node for node in ast.walk(harness_ast())
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_docstring(function)


# --- the exit-code contract: a code describes the mode that was requested ---


def _returns_exit_invalid(node) -> bool:
    """Whether an AST node is the harness's invalid-measurement exit code."""
    if isinstance(node, ast.Name):
        return node.id == "EXIT_INVALID"
    return isinstance(node, ast.Constant) and node.value == 2


def _returned(tree: ast.Module, name: str) -> list[ast.expr]:
    """Every expression the named function returns, in source order."""
    function = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == name)
    return [n.value for n in ast.walk(function) if isinstance(n, ast.Return)]


def _shape(node: ast.expr) -> str:
    """Name a returned expression by its shape: a constant name, or a call."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return f"{node.func.id}(...)"
    return ast.unparse(node)


def test_exit_two_is_returned_by_one_helper_and_by_nothing_else_in_the_module():
    # Sixteen independent `print(...); return 2` sites are the design in which
    # the seventeenth forgets to stay silent. Matching the SPELLING of the exit
    # code is not enough to hold that: `_QUIET_FAILURE = EXIT_INVALID` followed
    # by `return _QUIET_FAILURE` is a second door under a different name. So
    # the whole exit surface of the process is pinned instead — the three
    # expressions `main` may return, and what each of those returns in turn.
    # Nothing can leave this module with a 2 without passing the helper.
    # (`argparse` also exits 2 on a usage error — that happens inside argparse,
    # not in this module, and the module docstring names the overlap.)
    tree = harness_ast()
    assert {_shape(node) for node in _returned(tree, "main")} == {
        "EXIT_OK", "_invalid_measurement(...)", "report_score(...)"}
    assert [_shape(node) for node in _returned(tree, "_invalid_measurement")] \
        == ["EXIT_INVALID"]
    assert [ast.unparse(node) for node in _returned(tree, "report_score")] \
        == ["EXIT_OK if killed == total else EXIT_SURVIVORS"]

    returners = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Return) and _returns_exit_invalid(inner.value):
                returners.add(node.name)
    assert returners == {"_invalid_measurement"}
    exits = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and ast.unparse(n.func) in ("sys.exit", "SystemExit", "exit")
             and any(_returns_exit_invalid(a) for a in n.args)]
    assert exits == []


def test_nothing_main_does_after_reading_its_arguments_runs_outside_the_funnel():
    # The companion of the exit surface, and the reason exit 1 cannot be
    # produced by an accident: every statement that touches the measuring path
    # sits inside one `try`, and that `try` ends in a handler for anything at
    # all. A statement added after it, or the catch-all narrowed back to
    # InvalidMeasurement, would put a traceback and an exit 1 back on the table.
    main = next(node for node in ast.walk(harness_ast())
                if isinstance(node, ast.FunctionDef) and node.name == "main")
    assert [type(statement).__name__ for statement in main.body] \
        == ["Expr", "Assign", "Try"]         # docstring, parse_args, everything else
    assert ast.unparse(main.body[1].value.func) == "parse_args"
    assert [ast.unparse(handler.type) for handler in main.body[-1].handlers] \
        == ["InvalidMeasurement", "Exception"]


def test_one_place_in_the_module_starts_a_pytest_and_it_is_run_pytest():
    # The baseline and every mutant run must come from one environment, and the
    # test that compares them compares two recorded calls: a SECOND builder is
    # caught by that only while it disagrees. This is the half that forbids the
    # second builder outright, so agreeing today is not a defence.
    launchers = [function.name
                 for function in ast.walk(harness_ast())
                 if isinstance(function, ast.FunctionDef)
                 for call in ast.walk(function)
                 if isinstance(call, ast.Call) and ast.unparse(call.func) == "subprocess.run"
                 and {"-m", "pytest"} <= {ast.unparse(a).strip("'\"")
                                          for a in ast.walk(call) if isinstance(a, ast.Constant)}]
    assert launchers == ["run_pytest"]


# --- prose about this code is code: these pin claims, not wording ---


def test_the_docstring_states_the_kill_rule_the_scorer_actually_applies():
    doc = module_doc()
    assert "nonzero pytest exit" not in doc      # only exit 1 is a kill
    assert "exit 1" in doc


def _restore_writes_in_place() -> bool:
    """Whether the restore still rewrites the target where it stands.

    The crash window exists exactly while it does: a process killed between
    the mutation write and the restore leaves the mutation on disk. Writing
    beside the target and renaming would close it, so the presence of a rename
    is what turns the requirement below off — the guard follows the design
    rather than a promise about the design.
    """
    tree = harness_ast()
    renamed = [call for call in ast.walk(tree) if isinstance(call, ast.Call)
               and ast.unparse(call.func) in ("os.replace", "os.rename", "shutil.move")]
    restore = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "restore_source")
    in_place = [call for call in ast.walk(restore) if isinstance(call, ast.Call)
                and ast.unparse(call.func) == "path.write_bytes"]
    return bool(in_place) and not renamed


def _admits_the_crash_window(doc: str) -> bool:
    """Whether some sentence names the outcome the restore design really has.

    Two independent elements, not one banned word: a process that stops
    abruptly, and a mutated file surviving it. Rewriting the paragraph into a
    promise that the tree is always left clean removes both.
    """
    sentences = [" ".join(part.split()) for part in re.split(r"(?<=\.)\s+", doc)]
    return any(re.search(r"hard kill|killed|crash|interrupt", sentence)
               and re.search(r"leaves a mutated|still (mutated|carries)"
                             r"|mutation (is )?(left|still)", sentence)
               for sentence in sentences)


def test_the_docstring_admits_the_window_the_restore_design_leaves_open():
    # A hard kill between the mutation write and the restore leaves a mutated
    # file and says nothing. While that is the design — the condition below is
    # read from the code, so a crash-safe restore would retire this — the
    # docstring may not offer a pair of exhaustive outcomes instead.
    assert _restore_writes_in_place(), \
        "the restore no longer writes in place: this requirement must be revisited"
    assert _admits_the_crash_window(module_doc())
    assert "separate task" in module_doc()      # and it is queued, not forgotten


def test_the_restore_window_guard_reads_the_claim_and_not_the_word_always():
    # The guard this replaced banned the word "always" from the docstring, so a
    # true and unrelated sentence carrying it turned the suite red while the
    # claim itself stayed unguarded. Both halves, executed on the predicate.
    innocent = module_doc() + "\nThe baseline always runs before the first mutation.\n"
    assert _admits_the_crash_window(innocent)
    exhaustive = re.sub(
        r"A hard kill[^.]*\.[^.]*\.",
        "The working tree is always left clean - or the run stops saying, "
        "unmistakably, that it is not.", module_doc())
    assert "always left clean" in exhaustive         # the rewrite really landed
    assert not _admits_the_crash_window(exhaustive)


_POINTER = re.compile(r"(?P<path>docs/[\w./-]+\.md)\s+§(?P<section>\d+)")


def test_the_backlog_item_the_docstring_points_at_describes_the_script_that_exists():
    # The docstring sends a reader to a numbered section of the plan. A pointer
    # into prose that describes code which is no longer there is the same
    # defect as a false docstring, one file further away — and that section
    # once said the restore was "verified by an `assert`" that "disappears
    # under `python -O`", which is the very defect this instrument closed.
    pointer = _POINTER.search(module_doc())
    assert pointer, "the docstring no longer says where the open work is queued"
    plan = ROOT / pointer.group("path")
    assert plan.is_file(), plan
    body = plan.read_text(encoding="utf-8")
    heading = f"\n## {pointer.group('section')}. "
    assert heading in body, f"{plan} has no section {pointer.group('section')}"
    section = body.split(heading, 1)[1].split("\n## ", 1)[0]
    item = next((block for block in section.split("\n- ") if "mutate_merge.py" in block),
                None)
    assert item, "the section no longer carries the item the docstring points at"
    if "assert" in item:
        assert [n for n in ast.walk(harness_ast()) if isinstance(n, ast.Assert)], \
            "the plan describes a verification `assert` the script does not contain"


def test_the_pythonnousersite_reason_is_the_one_that_holds():
    # PYTHONPATH precedes every site directory, so the flag does not keep a
    # user-site install from shadowing the source root. What it does do is hide
    # a user-site pytest, which is why the probe imports pytest at all.
    doc = function_doc("subprocess_env")
    assert "from shadowing the source root" not in doc
    assert "pytest" in doc
