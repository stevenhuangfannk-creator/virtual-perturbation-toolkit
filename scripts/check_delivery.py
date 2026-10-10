"""Portable release checks for maintained sources and the submitted gallery."""
import ast
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def candidates():
    try:
        data = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z'])
        names = data.decode('utf-8').split('\0')
        if any(names):
            return [ROOT / name for name in names if name]
    except subprocess.CalledProcessError:
        pass
    folders = ['src', 'vpt', 'scripts', 'tests', 'docs', 'config', 'examples', 'gallery', 'agents']
    files = [p for folder in folders for p in (ROOT / folder).rglob('*') if p.is_file()]
    files += [p for p in ROOT.iterdir() if p.is_file() and p.name not in ['.gitignore']]
    return [p for p in files if '__pycache__' not in p.parts and 'qa' not in p.parts and not p.name.endswith('.local.json')]


def check_files(paths):
    names = {p.relative_to(ROOT).as_posix() for p in paths}
    errors = []
    maximum = 0
    for path in paths:
        name = path.relative_to(ROOT).as_posix()
        maximum = max(maximum, path.stat().st_size)
        if path.stat().st_size > 5 * 2**20:
            errors.append(name + ': oversized release file')
        if any(part in ['vendor', 'dosedirko', 'environment', 'outputs', 'logs', 'skill'] for part in path.relative_to(ROOT).parts):
            errors.append(name + ': excluded component or local artifacts')
        if path.suffix.lower() in ['.h5ad', '.rds', '.npy', '.npz', '.zip', '.mtx']:
            errors.append(name + ': raw data or model asset')
        if path.suffix.lower() in ['.py', '.r', '.md', '.json', '.yaml', '.ps1', '.csv']:
            source = path.read_text(encoding='utf-8-sig')
            if '\ufffd' in source:
                errors.append(name + ': damaged Unicode')
            if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)', source):
                errors.append(name + ': possible credential')
            if re.search(r'C:[/\\]Users[/\\]', source, re.I):
                errors.append(name + ': machine-specific user path')
            if path.suffix == '.py':
                ast.parse(source, filename=name)
            if path.suffix == '.json':
                json.loads(source)
            if path.suffix == '.md':
                for link in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', source):
                    link = unquote(link.strip('<>').split('#')[0])
                    if not link or link.startswith(('http://', 'https://')):
                        continue
                    target = (path.parent / link).resolve()
                    if not target.is_file() or target.relative_to(ROOT).as_posix() not in names:
                        errors.append(name + ': missing published link ' + link)
    return errors, maximum


def check_gallery():
    manifest = json.loads((ROOT / 'gallery/source_manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['exported_sha256'].items():
        actual = hashlib.sha256((ROOT / 'gallery/data' / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Gallery aggregate hash mismatch: ' + name)
    if hashlib.sha256((ROOT / 'gallery/export_history_summary.py').read_bytes()).hexdigest() != manifest['exporter_sha256']:
        raise ValueError('Gallery exporter source changed after export')
    figure_manifest = json.loads((ROOT / 'gallery/figure_manifest.json').read_text(encoding='utf-8'))
    if hashlib.md5((ROOT / 'gallery/plot_gallery.R').read_bytes()).hexdigest() != figure_manifest['plot_source_md5']:
        raise ValueError('Gallery plotting source changed after rendering')
    # Source file existence is intentionally local-only; published artifacts remain hash-verifiable.
    figures = list((ROOT / 'gallery/figures').glob('*'))
    counts = {ext: len([p for p in figures if p.suffix == ext]) for ext in ['.png', '.pdf', '.svg']}
    if counts != {'.png': 4, '.pdf': 4, '.svg': 4}:
        raise ValueError('Expected four actual figures in PNG/PDF/SVG')
    for path in (ROOT / 'gallery/data').glob('*.csv'):
        with path.open(encoding='utf-8-sig', newline='') as handle:
            fields = next(csv.reader(handle))
        if any(name in fields for name in ['cell_id', 'donor_id', 'sample_id', 'library_id']):
            raise ValueError('Identifiable row-level field in gallery: ' + path.name)
    return {'figures': counts, 'source_manifest_present': bool(manifest), 'scope': 'Aggregate real historical summaries; no experimental validation'}


def main():
    paths = candidates()
    errors, maximum = check_files(paths)
    gallery = check_gallery()
    report = {'state': 'FAIL' if errors else 'PASS', 'files_checked': len(paths),
              'maximum_file_bytes': maximum, 'gallery': gallery, 'errors': errors,
              'scope': 'Source/release checks, NOT biological validation or a general secret detector'}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
