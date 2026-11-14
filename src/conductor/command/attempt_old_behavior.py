"""Static comparison of a changed length-returning function with sealed unittest assertions."""
import ast
from collections import Counter, defaultdict


def _body(node):
    body = node.body
    return body[1:] if ast.get_docstring(node) is not None else body


def _parse(raw):
    try:
        return _body(ast.parse(raw.decode("utf-8")))
    except (SyntaxError, UnicodeError, ValueError, RecursionError):
        return []


def _named(node, name):
    return isinstance(node, ast.Name) and node.id == name


def _plain_function(fn):
    if (not isinstance(fn, ast.FunctionDef) or fn.decorator_list or fn.returns
            or getattr(fn, "type_params", ())):
        return False
    a = fn.args
    return (len(a.args) == 1 and not a.args[0].annotation and not a.defaults and not a.posonlyargs
            and not a.vararg and not a.kwonlyargs and not a.kwarg)


def _length_return(fn):
    body = _body(fn)
    if len(body) == 1 and isinstance(body[0], ast.Return):
        call = body[0].value
        if (isinstance(call, ast.Call) and _named(call.func, "len") and len(call.args) == 1
                and not call.keywords and _named(call.args[0], fn.args.args[0].arg)):
            return body[0].lineno
    return None


def _old_function(old, new):
    # This small module grammar excludes shadowing of len, rebinding, decorators and side effects.
    src, dst = _parse(old), _parse(new)
    if len(src) != 1 or len(dst) != 1 or not all(_plain_function(f) for f in (src[0], dst[0])):
        return None
    a, b = src[0], dst[0]
    if a.name != b.name or a.name == "len" or a.args.args[0].arg == "len":
        return None
    line = _length_return(a)
    if line is not None and _length_return(b) is None:
        return {"function": a.name, "expression": f"len({a.args.args[0].arg})", "line": line}
    return None


def _literal(node, depth=0, *, key=False):
    # Count top-level items only if creating the literal cannot call code or fail.
    if depth > 32:
        return False
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Tuple) or isinstance(node, ast.List) and not key:
        return all(_literal(v, depth + 1, key=key) for v in node.elts)
    return (not key and isinstance(node, ast.Dict)
            and all(_literal(k, depth + 1, key=True) for k in node.keys)
            and all(_literal(v, depth + 1) for v in node.values))


def _comparison(method, case):
    if not _plain_function(method) or method.args.args[0].arg != "self":
        return None
    statements = _body(method)
    if not statements or len(statements) > 2 or not isinstance(statements[-1], ast.Expr):
        return None
    check = statements[-1].value
    if (not isinstance(check, ast.Call) or check.lineno != case["line"]
            or not isinstance(check.func, ast.Attribute) or not _named(check.func.value, "self")
            or check.func.attr != "assertEqual" or len(check.args) != 2 or check.keywords):
        return None
    call, expected = check.args
    if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
            or len(call.args) != 1 or call.keywords or not isinstance(expected, ast.Constant)
            or type(expected.value) is not int or abs(expected.value) >= 2**53):
        return None
    values = call.args[0]
    if len(statements) == 2:
        assign = statements[0]
        if (not isinstance(assign, ast.Assign) or len(assign.targets) != 1
                or not isinstance(values, ast.Name) or values.id in (call.func.id, "self")
                or not _named(assign.targets[0], values.id)):
            return None
        values = assign.value
    if isinstance(values, ast.List) and _literal(values):
        return call.func.id, len(values.elts), expected.value
    return None


def _test_module(tree):
    imports, classes, unittest = {}, [], 0
    for item in tree:
        if isinstance(item, ast.Import) and len(item.names) == 1:
            name = item.names[0]
            if name.name != "unittest" or name.asname:
                return {}, []
            unittest += 1
        elif isinstance(item, ast.ImportFrom) and not item.level and item.module:
            for alias in item.names:
                if alias.asname or alias.name == "*" or alias.name in imports:
                    return {}, []
                imports[alias.name] = item.module
        elif isinstance(item, ast.ClassDef):
            if (item.decorator_list or item.keywords or len(item.bases) != 1
                    or not isinstance(item.bases[0], ast.Attribute)
                    or not _named(item.bases[0].value, "unittest")
                    or item.bases[0].attr != "TestCase" or getattr(item, "type_params", ())):
                return {}, []
            if any(not isinstance(f, ast.FunctionDef) or not f.name.startswith("test_")
                   or not _plain_function(f) for f in _body(item)):
                return {}, []
            classes.append(item)
        else:
            return {}, []
    names = set(imports) | {"unittest"}
    if unittest != 1 or "unittest" in imports or any(c.name in names for c in classes):
        return {}, []
    if len(classes) != len({c.name for c in classes}):
        return {}, []
    return imports, [method for cls in classes for method in _body(cls)]


def _export_path(package, name, raw):
    body = _parse(raw)
    if len(body) != 1 or not isinstance(body[0], ast.ImportFrom):
        return None
    imp = body[0]
    if (imp.level == 1 and imp.module and imp.module.isidentifier() and len(imp.names) == 1
            and imp.names[0].name == name and not imp.names[0].asname):
        return f"{package}/{imp.module}.py"
    return None


def annotate_cases(cases, before, snapshot, files, public_source):
    if not cases or not before:
        return
    rows = {r.path: r for r in snapshot.rows}
    visible = {f["path"] for f in files if f["diff_status"] == "available"}
    candidates = {}
    for path in visible:
        row = rows[path]
        if path.endswith(".py") and row.state == "modified" and path in before:
            old = _old_function(before[path], snapshot.blobs[row.sha256])
            if old:
                candidates[path] = {**old, "path": path}
    if not candidates:
        return
    by_file = defaultdict(list)
    for case in cases:
        if case["path"] in visible and case["assertion"]:
            by_file[case["path"]].append(case)
    for path, entries in by_file.items():
        imports, methods = _test_module(_parse(snapshot.blobs[rows[path].sha256]))
        counts = Counter(m.name for m in methods)
        unique = {m.name: m for m in methods if counts[m.name] == 1}
        for case in entries:
            method = unique.get(case["name"])
            values = _comparison(method, case) if method else None
            if values is None:
                continue
            name, actual, expected = values
            module = imports.get(name)
            if not module:
                continue
            target = module.replace(".", "/") + ".py"
            if target not in candidates and module.isidentifier():
                initializer = f"{module}/__init__.py"
                raw = before.get(initializer)
                if raw is None or initializer in rows or not public_source(initializer, raw):
                    continue
                target = _export_path(module, name, raw)
            old = candidates.get(target)
            if old and old["function"] == name:
                case["old_length"] = {**old, "actual": actual, "expected": expected}
