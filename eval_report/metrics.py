"""Pure metric computation over one evaluation run record.

Baseline handling:
- ``run["baseline"]`` is a dict (or None) shaped like:
    {"run_id": str, "pass_rate": float(0-1), "avg_score": float,
     "by_tag": {tag: pass_rate}, "by_difficulty": {difficulty: pass_rate}}
- When baseline is absent, every delta renders ``NO_BASELINE_MARKER`` —
  never 0 — and delta arithmetic is skipped entirely.
- Partial baseline: a tag/difficulty missing from the baseline map shows
  the marker on that row only.
"""

from __future__ import annotations

from eval_report.loader import EvalReportError

NO_BASELINE_MARKER = "无基线"

SLOWEST_LIMIT = 10


def compute_metrics(run: dict) -> dict:
    cases = run["cases"]
    total = len(cases)
    if total == 0:
        raise EvalReportError("run has no cases")
    passed = sum(1 for c in cases if c["passed"])
    failed_cases = [c for c in cases if not c["passed"]]

    baseline = run.get("baseline")
    by_tag = _group(cases, "tags", baseline)
    by_difficulty = _group(cases, "difficulty", baseline)

    overall_delta = None
    score_delta = None
    if baseline:
        overall_delta = (passed / total - baseline["pass_rate"]) * 100.0
        score_delta = _avg(cases) - baseline["avg_score"]

    return {
        "run_id": run["run_id"],
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total,
        "avg_score": _avg(cases),
        "by_tag": by_tag,
        "by_difficulty": by_difficulty,
        "baseline": baseline,
        "overall_delta_pp": overall_delta,
        "score_delta": score_delta,
        "failed_cases": failed_cases,
        "failing_tags": _failing_tags(failed_cases),
        "slowest": sorted(cases, key=lambda c: c["duration_ms"], reverse=True)[:SLOWEST_LIMIT],
        "judge_unstable": [c for c in cases if not c.get("judge", {}).get("stable", True)],
    }


def _avg(cases: list[dict]) -> float:
    return sum(c["score"] for c in cases) / len(cases)


def _group(cases: list[dict], key: str, baseline: dict | None) -> list[dict]:
    """Group pass rates by the ``tags`` list (a case counts under each of its
    tags) or by scalar ``difficulty``. Rows sorted by failure count desc,
    then name asc. Baseline pass rate / delta attached per row from the
    baseline's flat map; missing group -> None (renders the marker)."""
    buckets: dict[str, list[dict]] = {}
    if key == "tags":
        for c in cases:
            for tag in c["tags"]:
                buckets.setdefault(tag, []).append(c)
    else:
        for c in cases:
            buckets.setdefault(c[key], []).append(c)

    base_map: dict[str, float] = {}
    if baseline:
        base_map = baseline.get("by_tag" if key == "tags" else "by_difficulty", {}) or {}

    rows = []
    for name, members in buckets.items():
        p = sum(1 for c in members if c["passed"])
        bp = base_map.get(name)
        rows.append(
            {
                "name": name,
                "total": len(members),
                "passed": p,
                "failed": len(members) - p,
                "pass_rate": p / len(members),
                "baseline_pass_rate": bp,
                "delta_pp": (p / len(members) - bp) * 100.0 if bp is not None else None,
            }
        )
    rows.sort(key=lambda r: (-r["failed"], r["name"]))
    return rows


def fmt_pp(delta_pp: float | None) -> str:
    """Format a percentage-point delta. Exact-zero renders ±0.0pp (no sign
    ambiguity); missing baseline renders the literal no-baseline marker."""
    if delta_pp is None:
        return NO_BASELINE_MARKER
    if abs(delta_pp) < 0.05:
        return "±0.0pp"
    return f"{delta_pp:+.1f}pp"


def fmt_pass_rate(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def fmt_score(delta: float | None) -> str:
    if delta is None:
        return NO_BASELINE_MARKER
    if abs(delta) < 0.005:
        return "±0.0分"
    return f"{delta:+.1f}分"


def _failing_tags(failed_cases: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for c in failed_cases:
        for tag in c["tags"]:
            counts[tag] = counts.get(tag, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"tag": t, "failures": n} for t, n in ordered]
