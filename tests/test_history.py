"""Numerical-artifact integrity tests use tiny software-only files."""
import csv
from pathlib import Path
import tempfile
import unittest

from scripts.verify_history import verify
from vpt.files import sha256


class HistoryTests(unittest.TestCase):
    def test_rehash_catches_changed_product_even_when_manifest_says_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output, history = root / 'output', root / 'history'
            (output / 'results').mkdir(parents=True)
            (output / 'models').mkdir()
            (history / 'results/virtual_ko').mkdir(parents=True)
            new = output / 'models/result.csv'
            old = history / 'results/virtual_ko/result.csv'
            new.write_bytes(b'SOFTWARE_FIXTURE\n1\n')
            old.write_bytes(new.read_bytes())
            with (output / 'results/historical_comparison.csv').open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=['file', 'old_sha256', 'new_sha256', 'matches'])
                writer.writeheader()
                writer.writerow(dict(file='result.csv', old_sha256=sha256(old), new_sha256=sha256(new), matches=True))
            self.assertEqual(verify(output, history)['state'], 'PASS')
            new.write_bytes(b'SOFTWARE_FIXTURE\n2\n')
            self.assertEqual(verify(output, history)['state'], 'FAIL')

    def test_empty_manifest_cannot_claim_reproducibility(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'results').mkdir()
            (root / 'results/historical_comparison.csv').write_text('file,old_sha256,new_sha256\n')
            with self.assertRaisesRegex(ValueError, 'Empty'):
                verify(root, root)
