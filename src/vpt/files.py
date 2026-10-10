import hashlib
import json
from pathlib import Path


def resolve(value, base):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (Path(base) / path).resolve()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
