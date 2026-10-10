"""Compatibility imports for existing local callers; maintained code lives in src."""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[1] / 'src' / 'vpt')]
