"""Case persistence — single JSON file per case directory."""
from __future__ import annotations

import json
from pathlib import Path

from sona_mio.models import Case

CASE_FILENAME = "case.json"


def case_path(case_dir: Path) -> Path:
    return case_dir / CASE_FILENAME


def save(case: Case, case_dir: Path) -> Path:
    case_dir.mkdir(parents=True, exist_ok=True)
    path = case_path(case_dir)
    path.write_text(json.dumps(case.to_json(), indent=2, sort_keys=False))
    return path


def load(case_dir: Path) -> Case:
    path = case_path(case_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"no case found at {path}. Run `sona-mio init` first."
        )
    return Case.from_json(json.loads(path.read_text()))


def exists(case_dir: Path) -> bool:
    return case_path(case_dir).exists()
