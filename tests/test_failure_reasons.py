"""The runtime says WHY a step failed in its own closed words, and never copies adapter prose."""
from pathlib import Path
import re

import pytest

from conductor.command.failure_reasons import REASONS, reason_words

ADAPTERS = Path(__file__).resolve().parents[1] / "src/conductor/command/adapters"


def _joined_source() -> str:
    """Every adapter module, with adjacent string literals joined as Python joins them."""
    text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(ADAPTERS.glob("*.py")))
    return re.sub(r'"\s*\n\s*f?"', "", text)


@pytest.mark.parametrize(("fragment", "_words"), REASONS)
def test_every_fragment_is_one_a_built_in_transport_really_writes(fragment, _words):
    """A reworded transport sentence would silently fall out of the table; this reds instead."""
    assert fragment in _joined_source(), fragment


def test_a_recognized_sentence_earns_only_the_runtimes_words():
    secret = "sk-ant-oat01-SYNTHETIC-NOT-A-CREDENTIAL"
    sentence = f"the review wrote past the capture bound {secret}, so its result was never read whole"
    said = reason_words(sentence)
    assert said == "its output was longer than the capture bound"
    assert secret not in said and said in {words for _fragment, words in REASONS}


@pytest.mark.parametrize("sentence", [None, 7, "", "adapter said something this build never writes",
                                      "the pinned harness build 9.9.9 printed a version"])
def test_an_unrecognized_sentence_earns_nothing(sentence):
    assert reason_words(sentence) is None
