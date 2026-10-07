"""The scratch repository of the first-commit probes builds its index with the product's own argv.

A probe that builds the bytes with another command line than the product's proves nothing about
the product's bytes: on Git 2.31 the flags of every Git call (the file monitor among them) change
what the index holds, and a helper that left them out reported a pass for bytes the product would
have refused. The witness spies on the commands the helper sends and compares each with the argv the
product modules name, read from the product and not from the helper.
"""
import pytest

from conductor.command.git_setup_first_index import INDEX_PIN
from conductor.command.project_git import GIT_FLAGS
from tests import git_first_scratch
from tests.git_first_scratch import scratch
from tests.git_repo_helpers import git, needs_git

pytestmark = needs_git


def commands_of_base(tmp_path, monkeypatch, **keywords):
    """The argument lists the helper sends while it builds the base bytes of a one-file tree."""
    box = scratch(tmp_path, "current", "sha1")
    tree = box.tree({"a.txt": "one\n"})
    sent = []

    def spy(*args, **kwargs):
        sent.append(args)
        return git(*args, **kwargs)

    monkeypatch.setattr(git_first_scratch, "git", spy)
    box.base(tree, 1, **keywords)
    return sent


def subcommand(args):
    """The first word after the options: the Git subcommand."""
    return next(word for word in args if not word.startswith("-") and "=" not in word)


def test_the_scratch_builds_its_base_bytes_behind_the_flags_of_every_git_call_then_the_pin(
        tmp_path, monkeypatch):
    sent = commands_of_base(tmp_path, monkeypatch)
    product = (*GIT_FLAGS, *INDEX_PIN)
    assert [args[:len(product)] for args in sent] == [product, product]
    assert [subcommand(args[len(product):]) for args in sent] == ["read-tree", "update-index"]


@pytest.mark.parametrize("flags", [(), INDEX_PIN], ids=["no_flags", "the_pin_alone"])
def test_the_scratch_puts_exactly_the_flags_it_is_given_before_each_command(
        tmp_path, monkeypatch, flags):
    sent = commands_of_base(tmp_path, monkeypatch, flags=flags)
    assert [args[:len(flags)] for args in sent] == [flags, flags]
    assert all("-c" not in args[len(flags):] for args in sent)
