"""The AST gate memo preserves cycle context, aliases and source provenance."""
import ast

from tests import provider_identity_source as source


def test_shared_dag_is_settled_once_per_module_without_losing_origin(monkeypatch):
    trees = {"leaf": ast.parse('TOKEN = "codex-cli"\n')}
    previous = "leaf"
    for depth in range(12):
        left, right, parent = f"left{depth}", f"right{depth}", f"parent{depth}"
        trees[left] = ast.parse(f"from {previous} import TOKEN\n")
        trees[right] = ast.parse(f"from {previous} import TOKEN\n")
        trees[parent] = ast.parse(f"from {left} import TOKEN\nfrom {right} import TOKEN\n")
        previous = parent
    calls = []
    original = source._settled
    def counted(module, *args):
        calls.append(module)
        return original(module, *args)
    monkeypatch.setattr(source, "_settled", counted)
    result = source._OfferResolver(trees).resolve(previous)
    assert result.strings["TOKEN"] == "codex-cli"
    assert result.origins["TOKEN"] == ("leaf", "TOKEN")
    assert len(calls) == len(trees)


def test_cycle_context_cannot_reuse_a_less_restricted_offer():
    trees = {
        "a": ast.parse("from b import TOKEN\nALIAS = TOKEN\n"),
        "b": ast.parse('from a import ALIAS\nTOKEN = "codex-cli"\n'),
    }
    resolver = source._OfferResolver(trees)
    assert resolver.resolve("a").strings["ALIAS"] == "codex-cli"
    # Resolving b cuts b -> a -> b. a cannot see TOKEN in that context.
    assert "ALIAS" not in resolver.resolve("b").strings
    assert "ALIAS" not in resolver.resolve("a", frozenset({"b"})).strings
    other = {"a": ast.parse('ALIAS = "kimi-code"\n')}
    assert source._exported_offer("a", other).strings["ALIAS"] == "kimi-code"


def test_reexport_shadow_does_not_borrow_another_symbols_origin():
    trees = {
        "menu": ast.parse('ALLOWED = ("codex-cli",)\nOTHER = ("kimi-code",)\n'),
        "pkg.__init__": ast.parse("from menu import ALLOWED as FORWARDED\n"),
        "middle": ast.parse('from pkg import FORWARDED\nFORWARDED = ("kimi-code",)\n'),
    }
    resolver = source._OfferResolver(trees)
    assert resolver.resolve("pkg").containers["FORWARDED"].origin == ("menu", "ALLOWED")
    row = resolver.resolve("middle").containers["FORWARDED"]
    assert row.held == ("kimi-code",)
    assert row.origin == ("middle", "FORWARDED")
