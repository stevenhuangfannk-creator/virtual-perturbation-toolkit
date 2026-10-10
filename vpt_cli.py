"""One frozen-input, local perturbation run; no cell-state discovery or LLM."""
import argparse
import json
import sys
from pathlib import Path

from vpt.files import resolve, sha256, write_json


def select_features(X, genes, spec, targets, programs, base):
    import numpy as np
    import pandas as pd
    if spec['mode'] == 'frozen_list':
        path = resolve(spec['path'], base)
        if sha256(path) != spec['sha256']:
            raise ValueError('Frozen feature list changed')
        panel = pd.read_csv(path)[spec.get('column', 'gene')].astype(str).tolist()
    elif spec['mode'] == 'variance':
        # Uses only observed input counts, never a KO response or inferred direction.
        mean = np.asarray(X.mean(axis=0)).ravel()
        variance = np.asarray(X.astype(float).multiply(X).mean(axis=0)).ravel() - mean ** 2
        panel = [genes[i] for i in np.argsort(-variance, kind='stable')[:spec['n_genes']]]
        protected = targets + [g for group in programs.values() for g in group]
        panel += [g for g in dict.fromkeys(protected) if g in genes and g not in panel]
    elif spec['mode'] == 'all':
        panel = list(genes)
    else:
        raise ValueError('Unknown feature mode; choose frozen_list, variance or all explicitly')
    if len(panel) != len(set(panel)) or not set(panel).issubset(genes):
        raise ValueError('Duplicate or missing panel genes; no silent gene remapping')
    if not set(targets).issubset(panel) or len(panel) > spec['maximum_genes']:
        raise ValueError('Target absent or explicit feature budget exceeded')
    if len(panel) < 10:
        raise ValueError('Too few genes for a meaningful network')
    lookup = {g: i for i, g in enumerate(genes)}
    return X[:, [lookup[g] for g in panel]], panel


def history_compare(models, history, out):
    """Exact historical data reproduction, not new independent validation."""
    import csv
    rows = []
    for folder in sorted(models.iterdir()):
        paths = [folder / 'official_prediction.csv', *folder.glob('WT_network_run*.npy'),
                 *sorted((folder / 'checkpoint').glob('effect_run*.npy')),
                 *sorted((folder / 'checkpoint').glob('delta_run*.npy'))]
        for path in paths:
            old = history / 'results/virtual_ko' / path.relative_to(models)
            new_hash = sha256(path)
            old_hash = sha256(old) if old.is_file() else ''
            rows.append({'file': path.relative_to(models).as_posix(), 'matches': new_hash == old_hash,
                         'old_sha256': old_hash, 'new_sha256': new_hash})
    with (out / 'historical_comparison.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return {'state': 'PASS' if all(row['matches'] for row in rows) else 'FAIL',
            'files_compared': len(rows), 'all_exact': all(row['matches'] for row in rows),
            'scope': 'Official CSV and algorithm/network NPY hashes; source replay, NOT independent validation'}


def run(config_path, output_override):
    import importlib.metadata
    import numpy as np
    import pandas as pd
    from vpt.inputs import load_input
    from vpt.engine import load_engine, run_engine
    from vpt.evaluate import evaluate

    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    base = config_path.parent
    out = Path(output_override).resolve() if output_override else resolve(config['output_dir'], base)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output directory is not empty; select a new output path to preserve runs')
    out.mkdir(parents=True, exist_ok=True)
    result = out / 'results'
    result.mkdir()
    layers = {name: {'state': 'NOT_EVALUATED', 'reason': 'Not reached'}
              for name in ['INPUT_OK', 'RUN_OK', 'PREDICTION_STABLE', 'BIO_VALIDATED']}
    write_json(result / 'status.json', layers)
    try:
        if config.get('claim_scope', 'exploratory_subset') != 'exploratory_subset':
            raise ValueError('This observational adapter supports exploratory_subset claims; state-specific or causal claims need separate evidence')
        kind, alpha = config['perturbation']['type'], config['perturbation']['alpha']
        if kind not in ['KO', 'KD'] or not 0 <= alpha <= 1 or (kind == 'KO' and alpha != 1):
            raise ValueError('KO requires alpha=1; KD requires an explicit alpha in [0,1]')
        targets = config['targets']
        if not targets or len(targets) != len(set(targets)) or any('/' in t or '\\' in t for t in targets):
            raise ValueError('Targets must be unique gene symbols without path separators')
        api, source_hashes = load_engine(config['engine'], base)
        if not config['input'].get('qc_completed', False):
            raise ValueError('Upstream QC completion must be explicitly declared; this toolkit does not perform QC')
        X, genes, metadata, provenance = load_input(config['input'], base)
        if provenance['zero_count_cells']:
            raise ValueError('Zero-count cells require upstream QC resolution before modeling')
        expected = config['input'].get('sha256')
        if expected:
            locked = {str(resolve(path, base)): value for path, value in expected.items()}
            actual = {str(Path(path).resolve()): value['sha256'] for path, value in provenance['files'].items()}
            if locked != actual:
                raise ValueError('Input provenance hashes do not match the frozen source files')
        if len(metadata) > config['features']['maximum_cells']:
            raise ValueError('Input cell budget exceeded; supply a prespecified smaller subset')
        metadata.to_csv(result / 'cell_metadata.csv', index=False, encoding='utf-8-sig')
        write_json(result / 'input_summary.json', provenance)
        programs = config.get('programs', {})
        parameters = config['engine']['params']
        if parameters['n_top_genes'] is not None:
            raise ValueError('Freeze toolkit features first; engine n_top_genes must be null')
        panel, names = select_features(X, genes, config['features'], targets, programs, base)
        np_sub = parameters['n_subsample']
        estimated = 220 + (32 * np_sub * len(names) ** 2 + 64 * panel.shape[0] * len(names)) / 2**20
        if estimated > config['resources']['maximum_estimated_engine_mib']:
            raise ValueError(f'Conservative network memory estimate {estimated:.1f} MiB exceeds configured budget')
        pd.DataFrame({'gene': names, 'source_column': [genes.index(g) for g in names]}).to_csv(result / 'feature_panel.csv', index=False)
        coverage = []
        for target in targets:
            for gene in dict.fromkeys(targets + [g for group in programs.values() for g in group]):
                present = gene in genes
                col = X[:, genes.index(gene)] if present else None
                coverage.append({'target': target, 'gene': gene, 'in_counts': present, 'in_panel': gene in names,
                                 'detection_rate': float((col > 0).mean()) if present else None,
                                 'mean_raw': float(col.mean()) if present else None})
        pd.DataFrame(coverage).to_csv(result / 'gene_coverage.csv', index=False)
        warnings = provenance.get('warnings', [])
        if config['input']['annotation']['kind'] == 'operational':
            warnings += ['Operational expression-defined enrichment; not a independently validated fine subtype.']
        layers['INPUT_OK'] = {'state': 'PASS', 'reason': 'Raw counts, identifiers and provenance audited for exploratory subset use',
                              'allowed_claim': 'exploratory_subset', 'warnings': warnings}
        config['resolved_input_provenance'] = provenance
        config['estimated_engine_memory_mib'] = estimated
        write_json(out / 'config_resolved.json', config)
        write_json(out / 'run_provenance.json', {
            'config_path': str(config_path), 'config_sha256': sha256(config_path), 'engine_source_sha256': source_hashes,
            'toolkit_source_sha256': {str(p.relative_to(Path(__file__).parent)): sha256(p)
                                     for p in [Path(__file__), *sorted((Path(__file__).parent / 'src/vpt').glob('*.py'))]},
            'Python': sys.version, 'packages': {name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scipy', 'tensorly']},
            'core_math_modified': False, 'external_LLM_called': False})
        predictions, scores, baselines, edges, diagnostics = [], [], [], [], []
        scopes = [('pooled', np.arange(panel.shape[0]))]
        stratification = config.get('donor_analysis', {})
        skipped = []
        if stratification.get('enabled'):
            if not provenance.get('donor_stratification_allowed', True):
                raise ValueError('Unknown donor identities: requested donor analysis cannot be performed')
            for donor, rows in metadata.groupby('donor_id', sort=True).indices.items():
                if len(rows) < stratification['min_cells']:
                    skipped.append({'donor_id': str(donor), 'n_cells': len(rows), 'reason': 'Below prespecified minimum'})
                else:
                    scopes.append((str(donor), rows))
        models = out / 'models'
        models.mkdir()
        write_json(result / 'skipped_donors.json', skipped)
        for target in targets:
            for scope, indices in scopes:
                label = f'pooled_{target}_alpha{alpha}' if scope == 'pooled' else f'donor_{scope}_{target}'
                if '/' in label or '\\' in label or scope in ['.', '..']:
                    raise ValueError('Invalid donor path identifier')
                params = dict(parameters)
                if scope != 'pooled':
                    params['n_runs'] = stratification['n_runs']
                frames = run_engine(api, panel[indices], names, target, alpha, params, models / label)
                for collection, frame in zip([predictions, scores, baselines, edges, diagnostics], frames):
                    frame['target'], frame['scope'] = target, scope
                    collection.append(frame)
                print(f'RUN_OK {label}: {len(indices)} cells; {len(frames[0])} genes', flush=True)
        prediction = pd.concat(predictions, ignore_index=True)
        raw = pd.concat(scores, ignore_index=True)
        baseline = pd.concat(baselines, ignore_index=True)
        prediction.to_csv(result / 'predictions.csv', index=False)
        raw.to_csv(result / 'raw_scores.csv.gz', index=False, compression='gzip')
        baseline.to_csv(result / 'baseline_scores.csv.gz', index=False, compression='gzip')
        pd.concat(edges, ignore_index=True).to_csv(result / 'target_edges.csv', index=False)
        pd.concat(diagnostics, ignore_index=True).to_csv(result / 'network_diagnostics.csv', index=False)
        seed, comparisons, donor, evaluation = evaluate(prediction, raw, baseline, config.get('stability_criteria'), programs)
        seed.to_csv(result / 'seed_stability.csv', index=False)
        comparisons.to_csv(result / 'baseline_comparison.csv', index=False)
        donor.to_csv(result / 'donor_predictions.csv', index=False)
        layers['RUN_OK'] = {'state': 'PASS', 'reason': 'Official numerical runs completed; reproducibility assessed separately'}
        layers.update(evaluation)
        if config.get('historical_reference'):
            layers['historical_replay'] = history_compare(models, resolve(config['historical_reference'], base), result)
            if layers['historical_replay']['state'] != 'PASS':
                layers['RUN_OK'] = {'state': 'FAIL', 'reason': 'Algorithm completed but historical numerical reproduction failed'}
        write_json(result / 'status.json', layers)
        print(json.dumps(layers, ensure_ascii=False), flush=True)
        return 0 if layers['RUN_OK']['state'] == 'PASS' else 2
    except Exception as error:
        reached = layers['INPUT_OK']['state'] == 'PASS'
        layers['RUN_OK' if reached else 'INPUT_OK'] = {'state': 'FAIL', 'reason': str(error)}
        layers['BIO_VALIDATED'] = {'state': 'NOT_EVALUATED', 'reason': 'No applicable independent true perturbation experiment'}
        write_json(result / 'status.json', layers)
        write_json(out / 'failure.json', {'error': repr(error), 'synthetic_substitution': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Local Virtual Perturbation Toolkit; no reclustering or LLM')
    parser.add_argument('command', choices=['run', 'engines'])
    parser.add_argument('--config')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.command == 'engines':
        print((Path(__file__).parent / 'config/engines.json').read_text(encoding='utf-8'))
    else:
        if not args.config:
            parser.error('run requires --config')
        raise SystemExit(run(Path(args.config).resolve(), args.output))
