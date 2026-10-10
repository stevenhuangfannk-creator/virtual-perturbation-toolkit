"""Bound resources only for processes launched by this toolkit."""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vpt.files import resolve, write_json


def guarded(command, env, limits, logdir, name):
    record = {'command': command, 'status': 'RUNNING', 'peak_working_set_mib': 0.,
              'peak_private_mib': 0., 'minimum_free_ram_mib': psutil.virtual_memory().available / 2**20}
    started = time.monotonic()
    if record['minimum_free_ram_mib'] < limits['minimum_free_ram_mib']:
        record['status'] = 'BLOCKED_RESOURCE_PREFLIGHT'
    else:
        with (logdir / f'{name}.log').open('w', encoding='utf-8') as handle:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
            process = psutil.Process(child.pid)
            while child.poll() is None:
                try:
                    tree = [process] + process.children(recursive=True)
                    memory = [p.memory_info() for p in tree if p.is_running()]
                    working = sum(m.rss for m in memory) / 2**20
                    private = sum(getattr(m, 'private', 0) for m in memory) / 2**20
                    free = psutil.virtual_memory().available / 2**20
                    record['peak_working_set_mib'] = max(record['peak_working_set_mib'], working)
                    record['peak_private_mib'] = max(record['peak_private_mib'], private)
                    record['minimum_free_ram_mib'] = min(record['minimum_free_ram_mib'], free)
                    if (working > limits['maximum_working_set_mib'] or private > limits['maximum_private_mib']
                            or free < limits['minimum_free_ram_mib'] or time.monotonic() - started > limits['maximum_seconds_per_stage']):
                        for p in reversed(tree):
                            try:
                                p.terminate()
                            except psutil.NoSuchProcess:
                                pass
                        record['status'] = 'BLOCKED_RESOURCE_LIMIT'
                        break
                except psutil.NoSuchProcess:
                    pass
                time.sleep(.5)
            child.wait()
            record['exit_code'] = child.returncode
            if record['status'] == 'RUNNING':
                record['status'] = 'COMPLETE' if child.returncode == 0 else 'FAILED'
    record['elapsed_seconds'] = time.monotonic() - started
    write_json(logdir / f'{name}_resource.json', record)
    print(json.dumps(record, ensure_ascii=False), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--output')
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    base = config_path.parent
    runtime, limits = config['runtime'], config['resources']
    stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')
    out = Path(args.output).resolve() if args.output else resolve(config['output_dir'], base)
    if out.exists() and any(out.iterdir()) and not args.output:
        out = out.with_name(out.name + '_' + stamp)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Explicit output already contains files; choose a new path')
    logdir = ROOT / 'logs' / stamp
    logdir.mkdir(parents=True)
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS=str(limits['threads']), OPENBLAS_NUM_THREADS=str(limits['threads']),
               MKL_NUM_THREADS=str(limits['threads']), NUMBA_NUM_THREADS=str(limits['threads']),
               NUMBA_CACHE_DIR=str(ROOT / 'environment/numba_cache'))
    command = [str(resolve(runtime['python_data'], base)), str(ROOT / 'vpt_cli.py'),
               'run', '--config', str(config_path), '--output', str(out)]
    records = [guarded(command, env, limits, logdir, 'model')]
    if records[0]['status'] == 'COMPLETE':
        env.update(R_LIBS_USER=str(resolve(runtime['R_library'], base)), LC_ALL='', LC_CTYPE='')
        figure = config['figures']
        command = [str(resolve(runtime['Rscript'], base)), str(ROOT / 'scripts/plot_results.R'), str(out),
                   figure['font'], str(figure['width_mm']), str(figure['dpi']), str(resolve(runtime['R_library'], base))]
        records.append(guarded(command, env, limits, logdir, 'figures'))
    summary = {'output_dir': str(out), 'stage_records': records,
               'pipeline_complete': len(records) == 2 and all(r['status'] == 'COMPLETE' for r in records),
               'sampling_seconds': .5, 'resource_guard': 'Only this toolkit child process tree; no user applications closed'}
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / 'pipeline_execution.json', summary)
    if not summary['pipeline_complete']:
        status_path = out / 'results/status.json'
        status_path.parent.mkdir(exist_ok=True)
        status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.is_file() else {
            key: {'state': 'NOT_EVALUATED', 'reason': 'Resource preflight prevented execution'}
            for key in ['INPUT_OK', 'RUN_OK', 'PREDICTION_STABLE', 'BIO_VALIDATED']}
        if records[0]['status'].startswith('BLOCKED_RESOURCE'):
            status['RUN_OK'] = {'state': 'NOT_EVALUATED', 'reason': records[0]['status'] + ': no complete algorithm result'}
        status['guard_execution'] = records[0]['status']
        status['figure_execution'] = records[-1]['status'] if len(records) == 2 else 'NOT_RUN'
        write_json(status_path, status)
    print('OUTPUT_DIR=' + str(out), flush=True)
    raise SystemExit(0 if summary['pipeline_complete'] else 2)
