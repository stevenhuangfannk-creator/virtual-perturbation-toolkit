"""Software fixtures only: ensure repeats do not become biological validation."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vpt.evaluate import correlation, evaluate
from vpt.engine import load_engine


class EvidenceTests(unittest.TestCase):
    def fixture(self, effect_constant=False, conflict=False, donors=3, runs=3):
        genes = ['A', 'B', 'C', 'D']
        raw, pred, base = [], [], []
        for run in range(runs):
            for i, gene in enumerate(genes):
                raw.append(dict(target='T', scope='pooled', gene=gene, run_index=run,
                                effect=0 if effect_constant else i + 1, delta=i + 1))
                base.append(dict(target='T', scope='pooled', gene=gene, run_index=run,
                                 effect=i + 1, delta=i + 1, direct=i + 1, expression=i + 1, degree=i + 1))
        for scope in ['pooled'] + [f'D{i}' for i in range(donors)]:
            for i, gene in enumerate(genes):
                pred.append(dict(target='T', scope=scope, gene=gene, delta_mean=-(i + 1) if conflict and scope == 'D0' else i + 1))
        return pd.DataFrame(pred), pd.DataFrame(raw), pd.DataFrame(base)

    def report(self, **kwargs):
        return evaluate(*self.fixture(**kwargs), {'minimum_seed_spearman': .8, 'min_donors': 3}, {'Program': ['A', 'B']})[-1]

    def test_stability_never_implies_biological_validation(self):
        report = self.report()
        self.assertEqual(report['PREDICTION_STABLE']['state'], 'PASS')
        self.assertEqual(report['BIO_VALIDATED']['state'], 'NOT_EVALUATED')
        self.assertEqual(report['baseline_superiority'], 'NOT_EVALUATED_NO_TRUE_KO')

    def test_constant_score_cannot_pass_ranking_stability(self):
        self.assertEqual(self.report(effect_constant=True)['PREDICTION_STABLE']['state'], 'FAIL')

    def test_one_conflicting_donor_is_not_hidden_by_majority_vote(self):
        self.assertEqual(self.report(conflict=True)['PREDICTION_STABLE']['state'], 'FAIL')

    def test_insufficient_donors_are_not_evaluated(self):
        self.assertEqual(self.report(donors=1)['PREDICTION_STABLE']['state'], 'NOT_EVALUATED')

    def test_single_run_is_not_stability(self):
        self.assertEqual(self.report(runs=1)['PREDICTION_STABLE']['state'], 'NOT_EVALUATED')

    def test_no_fixed_program_is_not_a_vacuous_success(self):
        report = evaluate(*self.fixture(), {'minimum_seed_spearman': .8, 'min_donors': 3}, {})[-1]
        self.assertEqual(report['PREDICTION_STABLE']['state'], 'NOT_EVALUATED')

    def test_constant_no_change_has_undefined_correlation(self):
        self.assertIsNone(correlation(np.zeros(4), np.arange(4)))

    def test_unintegrated_engine_cannot_be_called(self):
        with self.assertRaisesRegex(ValueError, 'NOT_INTEGRATED'):
            load_engine({'id': 'celloracle'}, Path.cwd())


if __name__ == '__main__':
    unittest.main()
