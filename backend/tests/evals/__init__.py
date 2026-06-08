from __future__ import annotations

from pathlib import Path

_source_evals = Path(__file__).resolve().parents[2] / "evals"
if _source_evals.is_dir():
    __path__.append(str(_source_evals))
