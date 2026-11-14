"""Public credential collection and quota admission tolerate decoded bounded depth."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from conductor.command.adapters.codex_quota import reply_metadata
from conductor.command.adapters.login_home import (
    CREDENTIAL_LIMIT, credential_readback_trusted, credential_values)


class CredentialDepthTests(unittest.TestCase):
    def setUp(self):
        self.limit = sys.getrecursionlimit()
        self.home = Path(tempfile.mkdtemp(prefix="credential-depth-"))
        self.leaf = self.home / "auth.json"

    def tearDown(self):
        self.assertEqual(sys.getrecursionlimit(), self.limit)
        for path in self.home.iterdir():
            self.assertEqual(path.resolve().parent, self.home.resolve())
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            path.unlink()
        self.home.rmdir()

    def bounded(self, content):
        data = content.encode("ascii")
        self.assertLess(len(data), CREDENTIAL_LIMIT)
        self.leaf.write_bytes(data)
        # Establish the real parser's acceptance before either public reader is called.
        parsed = json.loads(self.leaf.read_bytes())
        self.assertIsInstance(parsed, dict)
        self.assertEqual(sys.getrecursionlimit(), self.limit)
        return data

    def depth(self):
        return 1100 if sys.version_info[:2] == (3, 12) else 600

    def test_deep_strings_keep_both_real_json_neighbors(self):
        depth = self.depth()
        for opening, closing in (("[", "]"), ('{"next":', "}")):
            with self.subTest(python=sys.version.split()[0], depth=depth, opening=opening):
                data = self.bounded('{"first":"SYNTHETIC-neighbor-0123456789","deep":'
                    + opening * depth + '"SYNTHETIC-deep-secret-0123456789"'
                    + closing * depth + '}')
                self.assertEqual(credential_values(str(self.home), ("auth.json",)),
                    (b"SYNTHETIC-neighbor-0123456789", b"SYNTHETIC-deep-secret-0123456789"))
                self.assertEqual(self.leaf.read_bytes(), data)

    def test_deep_quota_document_keeps_the_exact_account_path(self):
        depth = self.depth()
        data = self.bounded('{"tokens":{"account_id":"fake-quota-account-012345"},"deep":'
            + '[' * depth + '"SYNTHETIC-deep-key-0123456789"' + ']' * depth + '}')
        self.assertEqual(reply_metadata(str(self.home), ("auth.json",)),
                         {"tokens.account_id": frozenset({b"fake-quota-account-012345"})})
        self.assertEqual(self.leaf.read_bytes(), data)

    def test_shallow_order_threshold_duplicates_and_unicode_stay_exact(self):
        document = {"first": "FIRST-secret-012345", "short": "x" * 11,
            "nested": ["SECOND-secret-012345", {"unicode": "\u00e9" * 12,
                "duplicate": "FIRST-secret-012345", "short_unicode": "\u00e9" * 11}],
            "bad_scalar": "\ud800" * 12, "last": "SECOND-secret-012345"}
        self.bounded(json.dumps(document, ensure_ascii=True))
        self.assertEqual(credential_values(str(self.home), ("auth.json",)),
            (b"FIRST-secret-012345", b"SECOND-secret-012345", b"\xc3\xa9" * 12,
             b"\xed\xa0\x80" * 12))

    def test_a_nested_lookalike_is_not_the_native_account_cell(self):
        self.bounded('{"nested":{"tokens":{"account_id":"fake-quota-account-012345"}}}')
        self.assertEqual(reply_metadata(str(self.home), ("auth.json",)), {})
        self.bounded('{"tokens":{"account_id":"fake-quota-account-012345"},'
                     '"key":"prefix-fake-quota-account-012345-suffix"}')
        self.assertEqual(reply_metadata(str(self.home), ("auth.json",)), {})

    def test_malformed_and_oversize_inputs_stay_unreadable_for_q10(self):
        for data in (b'{"broken":', b'{"token":"' + b'x' * CREDENTIAL_LIMIT + b'"}'):
            with self.subTest(bytes=len(data)):
                self.leaf.write_bytes(data)
                self.assertEqual(credential_values(str(self.home), ("auth.json",)), ())
                self.assertFalse(credential_readback_trusted(
                    str(self.home), ("auth.json",), ("auth.json",)))
                self.assertEqual(reply_metadata(str(self.home), ("auth.json",)), {})


if __name__ == "__main__":
    unittest.main()
