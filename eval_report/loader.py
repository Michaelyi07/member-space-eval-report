"""Run-record loader.

A run record is a JSON file named ``{run_id}.json`` inside the runs
directory. The schema is documented in README.md. In the real platform the
run store will be swapped in here (integration point: ``load_run`` — the
only function that touches storage).
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED_TOP_KEYS = (
    "run_id",
    "suite",
    "suite_version",
    "prompt_version",
    "model",
    "git_sha",
    "trigger",
    "elapsed_ms",
    "tokens",
    "cases",
)
REQUIRED_CASE_KEYS = (
    "case_key",
    "tags",
    "difficulty",
    "input",
    "expected_points",
    "violations",
    "passed",
    "score",
    "duration_ms",
    "judge",
    "output",
)


class EvalReportError(ValueError):
    """Raised when a run record is missing or malformed."""


def load_run(runs_dir: str | Path, run_id: str) -> dict:
    path = Path(runs_dir) / f"{run_id}.json"
    if not path.is_file():
        raise EvalReportError(f"run record not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        run = json.load(f)
    validate_run(run)
    return run


def validate_run(run: dict) -> None:
    if not isinstance(run, dict):
        raise EvalReportError("run record must be a JSON object")
    for key in REQUIRED_TOP_KEYS:
        if key not in run:
            raise EvalReportError(f"run record missing required key: {key}")
    if not isinstance(run["cases"], list) or not run["cases"]:
        raise EvalReportError("run.cases must be a non-empty list")
    for i, case in enumerate(run["cases"]):
        for key in REQUIRED_CASE_KEYS:
            if key not in case:
                raise EvalReportError(f"run.cases[{i}] missing required key: {key}")
        if not isinstance(case["tags"], list) or not case["tags"]:
            raise EvalReportError(f"run.cases[{i}].tags must be a non-empty list")
        for tag in case["tags"]:
            if not isinstance(tag, str) or not tag.strip():
                raise EvalReportError(f"run.cases[{i}] has an empty/non-string tag")
            if tag != tag.strip() or any(ch.isspace() for ch in tag):
                raise EvalReportError(
                    f"run.cases[{i}] tag {tag!r} contains whitespace — "
                    "tags must be single tokens (HTML tag filtering joins on spaces)"
                )
