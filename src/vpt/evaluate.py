"""Report stability without inventing independent KO truth."""
import itertools

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def correlation(x, y):
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    value = float(spearmanr(x, y).statistic)
    return value if np.isfinite(value) else None


def evaluate(predictions, scores, baselines, criteria, programs):
    seed_rows, base_rows, donor_rows = [], [], []
    for target in predictions.target.unique():
        main = scores[(scores.target == target) & (scores.scope == 'pooled')]
        for metric in ['effect', 'delta']:
            matrix = main.pivot(index='gene', columns='run_index', values=metric)
            for first, second in itertools.combinations(matrix.columns, 2):
                x, y = matrix[first], matrix[second]
                k = min((criteria or {}).get('top_k', 30), len(matrix))
                a = set(x.abs().nlargest(k).index) if metric == 'delta' else set(x.nlargest(k).index)
                b = set(y.abs().nlargest(k).index) if metric == 'delta' else set(y.nlargest(k).index)
                seed_rows.append({'target': target, 'metric': metric, 'pair': f'{first}-{second}',
                                  'spearman': correlation(x, y), 'top_k_jaccard': len(a & b) / len(a | b)})
        group = baselines[(baselines.target == target) & (baselines.scope == 'pooled')]
        for run_index, rows in group.groupby('run_index'):
            base_rows.append({'target': target, 'run_index': int(run_index),
                              'delta_vs_direct_spearman': correlation(rows.delta, rows.direct),
                              'effect_vs_expression_spearman': correlation(rows.effect, rows.expression),
                              'effect_vs_degree_spearman': correlation(rows.effect, rows.degree),
                              'no_change_correlation': None,
                              'accuracy_comparison': 'NOT_EVALUATED_NO_TRUE_KO'})
        pooled = predictions[(predictions.target == target) & (predictions.scope == 'pooled')].set_index('gene')
        donor = predictions[(predictions.target == target) & (predictions.scope != 'pooled')]
        for _, row in donor.iterrows():
            if row.gene not in pooled.index:
                continue
            value = float(pooled.loc[row.gene, 'delta_mean'])
            donor_rows.append({'target': target, 'donor_id': row.scope, 'gene': row.gene,
                               'delta': float(row.delta_mean), 'pooled_delta': value,
                               'conflict': bool(np.sign(row.delta_mean) != np.sign(value))})
    seed = pd.DataFrame(seed_rows, columns=['target', 'metric', 'pair', 'spearman', 'top_k_jaccard'])
    baseline = pd.DataFrame(base_rows)
    donor = pd.DataFrame(donor_rows, columns=['target', 'donor_id', 'gene', 'delta', 'pooled_delta', 'conflict'])
    fixed = list(dict.fromkeys(gene for genes in programs.values() for gene in genes))
    conflicts = donor[donor.gene.isin(fixed) & donor.conflict]
    reasons = ['No independent true genetic perturbation experiment was provided.']
    counts = donor.groupby('target').donor_id.nunique()
    enough_donors = len(counts) == predictions.target.nunique() and (counts >= (criteria or {}).get('min_donors', 3)).all()
    program_evaluable = bool(fixed) and not donor[donor.gene.isin(fixed)].empty
    if not criteria or len(seed) == 0 or not enough_donors or (criteria.get('require_no_fixed_program_pooled_donor_conflicts', True) and not program_evaluable):
        stable = {'state': 'NOT_EVALUATED', 'reason': 'Insufficient prespecified criteria, repeats, target-wise independent donor networks or fixed-program coverage'}
    else:
        medians = seed.groupby(['target', 'metric']).spearman.median()
        complete = len(medians) == 2 * predictions.target.nunique() and medians.notna().all()
        ranks_ok = complete and all(float(value) >= criteria['minimum_seed_spearman'] for value in medians)
        signs_ok = len(conflicts) == 0 if criteria.get('require_no_fixed_program_pooled_donor_conflicts', True) else True
        stable = {'state': 'PASS' if ranks_ok and signs_ok else 'FAIL',
                  'reason': 'Prespecified reporting rubric: both score ranks and fixed-program pooled/donor signs',
                  'rank_criterion_passed': bool(ranks_ok), 'donor_sign_criterion_passed': bool(signs_ok),
                  'fixed_program_conflicts': len(conflicts), 'criteria': criteria,
                  'boundary': 'Historical-informed rubric is not a new prospective biological validation'}
    return seed, baseline, donor, {
        'PREDICTION_STABLE': stable,
        'BIO_VALIDATED': {'state': 'NOT_EVALUATED', 'reason': reasons[0]},
        'scientific_decision': 'PARTIAL',
        'independent_true_KO': False,
        'baseline_superiority': 'NOT_EVALUATED_NO_TRUE_KO',
        'evidence': 'Model-predicted; no experimentally validated counterfactual response'}
