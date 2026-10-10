"""Observe, but do not alter, the official DoseDirKO numerical implementation."""
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .files import resolve, sha256, write_json


def load_engine(spec, base):
    if spec['id'] != 'dosedirko':
        raise ValueError(f"Engine {spec['id']} is NOT_INTEGRATED; no substitute prediction will be made")
    source = resolve(spec['source_dir'], base)
    actual = {p.name: sha256(p) for p in sorted((source / 'dosedirko').glob('*.py'))}
    if not actual or actual != spec['source_sha256']:
        raise ValueError('Official DoseDirKO source hash mismatch; review the new version before running')
    for dependency in spec.get('dependency_paths', []):
        sys.path.insert(0, str(resolve(dependency, base)))
    sys.path.insert(0, str(source))
    api = importlib.import_module('dosedirko.api')
    if Path(api.__file__).resolve().parent != (source / 'dosedirko').resolve():
        raise ValueError('An unrelated DoseDirKO module was already imported')
    return api, actual


def run_engine(api, X, genes, target, alpha, params, folder):
    folder.mkdir(parents=True)
    networks = []
    original = api.denoise_cp

    def observer(values, rank=5):
        result = original(values, rank=rank)
        networks.append(result[1].copy())
        return result

    api.denoise_cp = observer
    try:
        np.random.seed(params['random_state'])
        prediction = api.DoseDirKO(**params).run(
            X, genes, target, alpha, checkpoint_dir=str(folder / 'checkpoint'), resume=False)
    finally:
        api.denoise_cp = original
    if len(networks) != params['n_runs'] or not np.isfinite(prediction[['effect_mean', 'delta_mean']]).all().all():
        raise ValueError('Missing runs or nonfinite official prediction')
    prediction.to_csv(folder / 'official_prediction.csv', index=False)
    filtered, used_genes = api.filter_genes_min_cells(X, genes, max(1, int(X.shape[0] * params['min_cells_frac'])))
    if params['n_top_genes'] is not None:
        raise ValueError('Toolkit freezes the feature panel before the API; n_top_genes must be null')
    normalized = api.normalize_log1p_cp10k(filtered)
    baseline = normalized.mean(axis=0)
    source_index = used_genes.index(target)
    scores, baselines, edges, diagnostics = [], [], [], []
    for run_index, network in enumerate(networks):
        np.save(folder / f'WT_network_run{run_index}.npy', network)
        effect = np.load(folder / 'checkpoint' / f'effect_run{run_index:03d}.npy')
        delta = np.load(folder / 'checkpoint' / f'delta_run{run_index:03d}.npy')
        direct = api.compute_direct_input(network, source_index, alpha, baseline)
        degree = np.abs(network).sum(axis=1)
        scores.extend({'gene': g, 'run_index': run_index, 'effect': float(e), 'delta': float(d)}
                      for g, e, d in zip(used_genes, effect, delta))
        baselines.extend({'gene': g, 'run_index': run_index, 'no_change': 0., 'direct': float(u),
                          'expression': float(m), 'degree': float(k), 'effect': float(e), 'delta': float(d)}
                         for g, u, m, k, e, d in zip(used_genes, direct, baseline, degree, effect, delta))
        edges.extend({'gene': g, 'run_index': run_index, 'weight': float(w)}
                     for g, w in zip(used_genes, network[source_index]))
        row = np.abs(network[source_index])
        diagnostics.append({'run_index': run_index, 'n_genes': len(used_genes),
                            'effective_out_edges': int((row > 1e-6).sum()),
                            'top10_weight_fraction': float(np.sort(row)[-10:].sum() / max(row.sum(), 1e-12)),
                            'symmetry_relative_error': float(np.linalg.norm(network - network.T) / max(np.linalg.norm(network), 1e-12))})
    write_json(folder / 'run_manifest.json', {
        'target': target, 'alpha': alpha, 'params': params, 'n_cells': X.shape[0],
        'genes': used_genes, 'normalization': 'Official log1p CP10k AFTER panel/filter selection',
        'CP_status': 'SKIPPED_OFFICIAL_AVERAGING' if len(used_genes) > 400 or params['cp_rank'] <= 0 or params['n_subsample'] < 2 else 'ELIGIBLE_SUCCESS_NOT_VERIFIED',
        'CP_success_verified': False, 'prediction_evidence': 'Model-predicted',
        'score_meaning': 'effect: unsigned embedding distance; delta: candidate signed propagation; NOT experimental log2FC',
        'uncertainty': 'Algorithm quantiles and sign frequency; NOT biological confidence intervals or probabilities',
        'external_LLM_called': False})
    return prediction, pd.DataFrame(scores), pd.DataFrame(baselines), pd.DataFrame(edges), pd.DataFrame(diagnostics)
