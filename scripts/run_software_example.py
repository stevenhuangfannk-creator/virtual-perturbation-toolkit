"""Small synthetic software smoke test, never a biological demonstration."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
from scipy import io, sparse

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description='仅软件夹具，需已有合法外部核心；不重做JUND分析')
    parser.add_argument('--source-config', type=Path, required=True, help='提供已有engine/runtime/resource配置')
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--launcher', type=Path, default=ROOT / 'scripts/run_toolkit.py')
    args = parser.parse_args()
    source = args.source_config.resolve()
    original = json.loads(source.read_text(encoding='utf-8-sig'))
    config = json.loads((ROOT / 'examples/new_project.template.json').read_text(encoding='utf-8'))
    for key in ['engine', 'runtime', 'resources']:
        config[key] = copy.deepcopy(original[key])
    def absolute(value):
        path = Path(value)
        return str(path.resolve() if path.is_absolute() else (source.parent / path).resolve())
    config['engine']['source_dir'] = absolute(config['engine']['source_dir'])
    config['engine']['dependency_paths'] = [absolute(p) for p in config['engine'].get('dependency_paths', [])]
    config['runtime'] = {k: absolute(v) for k, v in config['runtime'].items()}
    work = args.work_dir.resolve()
    if work.exists():
        raise ValueError('Software example workspace must be new')
    tenx = work / 'input'
    tenx.mkdir(parents=True)
    genes = [f'FIXTURE_G{i:02}' for i in range(24)]
    cells = [f'fixture_cell_{i:02}' for i in range(48)]
    counts = np.random.default_rng(314159).poisson(4, size=(48, 24))
    # Passing a Unicode filename to older SciPy native writers is unreliable on Windows.
    with (tenx / 'matrix.mtx').open('wb') as handle:
        io.mmwrite(handle, sparse.coo_matrix(counts.T))
    pd.DataFrame({0: genes, 1: genes, 2: ['Gene Expression'] * 24}).to_csv(tenx / 'features.tsv', sep='\t', header=False, index=False)
    (tenx / 'barcodes.tsv').write_text('\n'.join(cells) + '\n', encoding='utf-8')
    pd.DataFrame({'cell_id': cells, 'sample_id': ['synthetic_sample'] * 48,
                  'donor_id': ['UNKNOWN'] * 48, 'cell_state': ['software_fixture'] * 48}).to_csv(work / 'metadata.csv', index=False)
    config['input'].update(format='10x', path=str(tenx), cell_metadata=str(work / 'metadata.csv'),
        species='SYNTHETIC_SOFTWARE_FIXTURE', accession='NO_BIOLOGICAL_DATA', counts_origin='Integer Poisson fixture, software testing only',
        qc_status='STRUCTURAL_FIXTURE_ONLY_NOT_BIOLOGICAL_QC', qc_completed=True,
        annotation={'kind': 'operational', 'label': 'software_fixture', 'source': 'SYNTHETIC: no real cells or donors'})
    config['features'] = {'mode': 'all', 'maximum_genes': 30, 'maximum_cells': 50}
    config['targets'] = [genes[0]]
    config['engine']['params'].update(n_subsample=2, pca_k=5, cp_rank=0, embed_dim=5, n_runs=2, random_state=271828)
    config['donor_analysis']['enabled'] = False
    config['programs'] = {}
    config['output_dir'] = str(work / 'output')
    config['software_fixture_only'] = True
    job = work / 'job.local.json'
    job.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    code = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(args.launcher), '--config', str(job)], check=False).returncode
    print('SOFTWARE_FIXTURE_ONLY: synthetic input; no biological inference. Exit=' + str(code))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
