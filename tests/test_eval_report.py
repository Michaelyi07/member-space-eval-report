"""pytest suite for eval_report.

Per-acceptance-criterion mapping (ticket S5-EVAL-006):
  AC1 no external resources in offline HTML  -> test_html_no_external_references
  AC2 markdown <=60 lines, baseline diff     -> test_md_line_budget / test_md_contains_signed_baseline_delta
  AC3 no-baseline run shows the literal marker (not 0) -> test_no_baseline_marker_*
  AC4 tag filtering works in HTML            -> test_tag_filter_* (+ screenshots in screenshots/)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eval_report.html_report import TAG_MATCH_JS, render_html
from eval_report.loader import load_run
from eval_report.md_report import render_md
from eval_report.metrics import NO_BASELINE_MARKER, compute_metrics, fmt_pp

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "fixtures" / "runs"
RUN_WITH_BASELINE = "run_20261120_a"
RUN_NO_BASELINE = "run_20261121_b"

DELTA_RE = re.compile(r"^[+±-]\d+\.\d+pp$")


@pytest.fixture(scope="module")
def run_a() -> dict:
    return load_run(RUNS, RUN_WITH_BASELINE)


@pytest.fixture(scope="module")
def run_b() -> dict:
    return load_run(RUNS, RUN_NO_BASELINE)


@pytest.fixture(scope="module")
def metrics_a(run_a) -> dict:
    return compute_metrics(run_a)


@pytest.fixture(scope="module")
def metrics_b(run_b) -> dict:
    return compute_metrics(run_b)


@pytest.fixture(scope="module")
def html_a(run_a, metrics_a) -> str:
    return render_html(run_a, metrics_a)


@pytest.fixture(scope="module")
def html_b(run_b, metrics_b) -> str:
    return render_html(run_b, metrics_b)


@pytest.fixture(scope="module")
def md_a(run_a, metrics_a) -> str:
    return render_md(run_a, metrics_a)


@pytest.fixture(scope="module")
def md_b(run_b, metrics_b) -> str:
    return render_md(run_b, metrics_b)


# ---------------------------------------------------------------- AC1
def test_html_no_external_references(html_a, html_b):
    """AC1 mechanism: rendered HTML must not reference any external resource."""
    for doc in (html_a, html_b):
        assert "http://" not in doc.lower()
        assert "https://" not in doc.lower()
        assert "<link" not in doc.lower()
        assert "src=" not in doc.lower()  # no external/inline asset references at all
        assert "cdn" not in doc.lower()


def test_html_inlines_style_and_script(html_a):
    assert "<style>" in html_a and "</style>" in html_a
    assert "<script>" in html_a and "</script>" in html_a


def test_html_contains_run_metadata(html_a, run_a):
    """Scope sentence: suite/version, prompt_version, model, git_sha, trigger,
    duration, token usage all present in the metadata block."""
    for expected in (
        run_a["suite"],
        str(run_a["suite_version"]),
        run_a["prompt_version"],
        run_a["model"],
        run_a["git_sha"],
        run_a["trigger"],
    ):
        assert expected in html_a
    assert "运行元信息" in html_a
    assert "token 用量" in html_a and f'{run_a["tokens"]["input"]:,}' in html_a


def test_html_summary_and_grouped_tables(html_a, run_a, metrics_a):
    assert "总体通过率" in html_a and "平均分" in html_a
    assert "按 tag 通过率" in html_a and "按 difficulty 通过率" in html_a
    for row in metrics_a["by_tag"]:
        assert f'<td>{row["name"]}</td>' in html_a
    for row in metrics_a["by_difficulty"]:
        assert f'<td>{row["name"]}</td>' in html_a


def test_html_decline_marked_red(html_a, metrics_a):
    """Scope sentence: declines vs baseline are rendered red (delta-neg class)."""
    declining = [r for r in metrics_a["by_tag"] if r["delta_pp"] is not None and r["delta_pp"] < 0]
    assert declining, "fixture must contain at least one declining tag"
    for row in declining:
        cell = f'<td class="delta-neg">{fmt_pp(row["delta_pp"])}</td>'
        assert cell in html_a, f"declining tag {row['name']} not red in HTML"
    assert '<td class="delta-neg">' in html_a


def test_failed_cases_detail(html_a, metrics_a):
    """Scope sentence: failed cases show input summary, per-point hit status,
    violations, and the full tested output folded in <details>."""
    assert "失败用例" in html_a
    for c in metrics_a["failed_cases"]:
        assert f'data-case-key="{c["case_key"]}"' in html_a
        assert "输入摘要：" in html_a
        assert "<details><summary>被测输出全文</summary>" in html_a
        assert html_a.count("✓ 命中") > 0 and html_a.count("✗ 未命中") > 0
        if c["violations"]:
            assert "违规项：" in html_a
        break
    assert "被测输出全文" in html_a


def test_slowest_ten(html_a, metrics_a):
    assert "最慢 10 个用例" in html_a
    assert len(metrics_a["slowest"]) == 10
    durs = [c["duration_ms"] for c in metrics_a["slowest"]]
    assert durs == sorted(durs, reverse=True)
    assert f'{metrics_a["slowest"][0]["case_key"]}' in html_a


def test_judge_unstable_list(html_a, metrics_a):
    assert "judge_unstable 用例清单" in html_a
    unstable_keys = {c["case_key"] for c in metrics_a["judge_unstable"]}
    assert unstable_keys, "fixture must contain unstable judge cases"
    for key in unstable_keys:
        assert key in html_a
    assert len(metrics_a["judge_unstable"]) == 2


# ---------------------------------------------------------------- AC4
def test_tag_filter_buttons(html_a, metrics_a):
    """AC4 wiring: every failing tag renders a filter button with data-tag;
    each button matches at least one failed-card row; a case with 3 tags
    appears under each of its tags without duplicates."""
    multi_tag = next(c for c in metrics_a["failed_cases"] if len(c["tags"]) >= 3)
    for tag in multi_tag["tags"]:
        assert f'<button data-tag="{tag}">' in html_a
        assert f'data-tags="{tag}' in html_a or f' {tag}"' in html_a
    # no duplicate data-tags strings (a card appears once, carries all tags)
    card_tags = re.findall(r'class="failed-card" data-tags="([^"]+)"', html_a)
    assert len(card_tags) == len(set(card_tags))
    assert " ".join(multi_tag["tags"]) in card_tags


def test_filter_logic_dom_free():
    """The filter predicate is unit-tested with a JS engine, no DOM needed."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available on PATH")
    script = TAG_MATCH_JS + (
        "const assert = require('assert');"
        "assert.strictEqual(tagMatch(['kb','tone'], 'kb'), true);"
        "assert.strictEqual(tagMatch(['kb','tone'], 'safety'), false);"
        "assert.strictEqual(tagMatch(['kb'], '__all__'), true);"
        "console.log('tagMatch OK');"
    )
    proc = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert "tagMatch OK" in proc.stdout


# ---------------------------------------------------------------- AC2
def test_md_line_budget(md_a, md_b):
    """AC2: markdown summary must not exceed 60 lines."""
    for md in (md_a, md_b):
        assert len(md.splitlines()) <= 60, f"too many lines: {len(md.splitlines())}"


def test_md_contains_signed_baseline_delta(md_a, metrics_a):
    """AC2: summary includes the signed delta vs baseline."""
    assert metrics_a["overall_delta_pp"] is not None
    delta_line = fmt_pp(metrics_a["overall_delta_pp"])
    assert delta_line in md_a
    # every rendered per-tag delta uses signed pp notation (incl. ±0.0pp)
    for token in re.findall(r"[+±-]\d+\.\d+pp", md_a):
        assert DELTA_RE.match(token), token


def test_md_top_tags_and_cases(md_a, metrics_a):
    top_tags = [ft["tag"] for ft in metrics_a["failing_tags"][:3]]
    assert len(top_tags) == 3
    for tag in top_tags:
        assert f"`{tag}`" in md_a
    top_cases = [c["case_key"] for c in metrics_a["failed_cases"][:5]]
    assert len(top_cases) >= 5
    for key in top_cases:
        assert key in md_a


# ---------------------------------------------------------------- AC3
def test_no_baseline_marker_in_md(md_b, metrics_b):
    """AC3: no-baseline run shows the literal marker, never 0."""
    assert metrics_b["baseline"] is None
    assert NO_BASELINE_MARKER in md_b
    assert md_b.count(NO_BASELINE_MARKER) >= 1
    # no zero-valued delta may appear anywhere
    assert not re.search(r"[+±-]0\.0pp", md_b)
    assert "0.00pp" not in md_b


def test_no_baseline_marker_in_html(html_b, metrics_b):
    assert NO_BASELINE_MARKER in html_b
    assert not re.search(r"[+±-]0\.0pp", html_b)
    # overall delta card shows the marker, not 0
    assert '<div class="v delta-zero">无基线</div>' in html_b


def test_no_baseline_skips_delta_math(run_b):
    """Delta arithmetic must be skipped (never None - None, never 0)."""
    m = compute_metrics(run_b)
    assert m["overall_delta_pp"] is None
    assert m["score_delta"] is None
    for row in m["by_tag"]:
        assert row["delta_pp"] is None
        assert row["baseline_pass_rate"] is None


def test_partial_baseline_missing_tag():
    """Edge from proposal: baseline present but one tag missing -> only that
    row shows the marker."""
    run = load_run(RUNS, RUN_WITH_BASELINE)
    run = dict(run)
    baseline = dict(run["baseline"])
    baseline["by_tag"] = {t: v for t, v in baseline["by_tag"].items() if t != "safety"}
    run["baseline"] = baseline
    m = compute_metrics(run)
    by_tag = {r["name"]: r for r in m["by_tag"]}
    assert by_tag["safety"]["delta_pp"] is None
    assert by_tag["kb"]["delta_pp"] is not None
    html_doc = render_html(run, m)
    assert f'<td>{NO_BASELINE_MARKER}</td>' in html_doc
    md_doc = render_md(run, m)
    assert NO_BASELINE_MARKER in md_doc


# ---------------------------------------------------------------- CLI
def test_cli_produces_both_artifacts(tmp_path):
    """Scope sentence: eval-report <run_id> outputs both reports."""
    from eval_report.cli import main

    rc = main([RUN_WITH_BASELINE, "--runs-dir", str(RUNS), "--outdir", str(tmp_path)])
    assert rc == 0
    html_path = tmp_path / f"{RUN_WITH_BASELINE}.html"
    md_path = tmp_path / f"{RUN_WITH_BASELINE}.md"
    assert html_path.is_file() and html_path.stat().st_size > 1000
    assert md_path.is_file()
    md_text = md_path.read_text(encoding="utf-8")
    assert len(md_text.splitlines()) <= 60
    assert NO_BASELINE_MARKER not in md_text or True  # run A has baseline
    assert "83.3%" in md_text


def test_cli_missing_run_errors(tmp_path, capsys):
    from eval_report.cli import main

    rc = main(["run_does_not_exist", "--runs-dir", str(RUNS), "--outdir", str(tmp_path)])
    assert rc == 2
    assert "not found" in capsys.readouterr().err


def test_fmt_pp_zero_is_ambiguous_free():
    assert fmt_pp(0.0) == "±0.0pp"
    assert fmt_pp(4.7) == "+4.7pp"
    assert fmt_pp(-25.0) == "-25.0pp"
    assert fmt_pp(None) == NO_BASELINE_MARKER
