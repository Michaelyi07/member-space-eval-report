"""CLI entry: ``eval-report <run_id>`` (or ``python -m eval_report <run_id>``).

Usage:
    python -m eval_report <run_id> [--runs-dir DIR] [--outdir DIR]

Produces ``{outdir}/{run_id}.html`` (self-contained detail report) and
``{outdir}/{run_id}.md`` (CI summary, <= 60 lines).

Integration point: real platform run storage replaces ``loader.load_run``
(same return schema, one-line swap — see README).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval_report.html_report import render_html
from eval_report.loader import EvalReportError, load_run
from eval_report.md_report import render_md
from eval_report.metrics import compute_metrics


def _ensure_utf8_stdio() -> None:
    """Windows GBK console hardening (idempotent, capture-safe)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if enc and enc != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # captured/non-tty streams may not support reconfigure


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(prog="eval-report", description="单次评测运行报告生成器")
    parser.add_argument("run_id", help="运行记录 ID（对应 <runs-dir>/<run_id>.json）")
    parser.add_argument("--runs-dir", default="fixtures/runs", help="运行记录目录（默认 fixtures/runs）")
    parser.add_argument("--outdir", default=".", help="报告输出目录（默认当前目录）")
    args = parser.parse_args(argv)

    try:
        run = load_run(args.runs_dir, args.run_id)
    except (EvalReportError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    m = compute_metrics(run)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    html_path = outdir / f"{args.run_id}.html"
    md_path = outdir / f"{args.run_id}.md"
    html_path.write_text(render_html(run, m), encoding="utf-8")
    md_path.write_text(render_md(run, m), encoding="utf-8")

    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "html": str(html_path),
                "markdown": str(md_path),
                "pass_rate": round(m["pass_rate"] * 100, 1),
                "failed": m["failed"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
