"""Recheck frozen numerical products without rerunning a scientific analysis."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vpt.files import sha256


def verify(output, history):
    output, history = Path(output), Path(history)
    comparison = output / 'results/historical_comparison.csv'
    with comparison.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    failed = []
    for row in rows:
        rel = Path(row['file'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Invalid relative path in historical manifest')
        new, old = output / 'models' / rel, history / 'results/virtual_ko' / rel
        if sha256(new) != sha256(old) or sha256(new) != row['new_sha256'] or sha256(old) != row['old_sha256']:
            failed.append(rel.as_posix())
    if not rows:
        raise ValueError('Empty comparison manifest cannot pass')
    return {'state': 'FAIL' if failed else 'PASS', 'files_compared': len(rows),
            'files_failed': failed, 'all_exact': not failed,
            'scope': 'Fresh SHA256 of existing historical products, no new algorithm execution or biological validation'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='核对已有历史产物；不重做JUND分析')
    parser.add_argument('--output', required=True)
    parser.add_argument('--history', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = verify(args.output, args.history)
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report['state'] == 'PASS' else 2)
