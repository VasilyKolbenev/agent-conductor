"""The policy fake whose typed rejection cites a line that no string in the run spells.

Importing this module changes nothing; only the child's `main` retargets the fake's payload, so a
test process that imports `LINE` leaves `_fakepolicy.PAYLOAD` as every other witness expects it.
"""
from tests import _fakepolicy

LINE = 8675309


def main():
    finding = {**_fakepolicy.PAYLOAD["findings"][0], "line": LINE}
    _fakepolicy.PAYLOAD = {**_fakepolicy.PAYLOAD, "findings": [finding]}
    return _fakepolicy.main()
