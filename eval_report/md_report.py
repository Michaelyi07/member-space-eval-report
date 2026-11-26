"""Markdown CI summary renderer (<= 60 lines, for PR comments)."""

from __future__ import annotations

from eval_report.metrics import (
    NO_BASELINE_MARKER,
    fmt_pass_rate,
    fmt_pp,
    fmt_score,
)

MAX_LINES = 60
TOP_TAGS = 3
TOP_CASES = 5
MD_TAG_LINE_BUDGET = 12  # max per-tag deltas on one bullet; overflow folds to HTML


def render_md(run: dict, m: dict) -> str:
    b = run.get("baseline")
    lines: list[str] = []
    lines.append(f"# 评测摘要 · {m['run_id']}")
    lines.append("")
    lines.append(
        f"- Suite: {run['suite']} v{run['suite_version']} · 模型: {run['model']} · "
        f"prompt: {run['prompt_version']} · 触发: {run['trigger']}"
    )
    lines.append(
        f"- git_sha: `{run['git_sha'][:8]}` · 耗时 {_fmt_duration(run['elapsed_ms'])} · "
        f"tokens {run['tokens']['input']:,} in / {run['tokens']['output']:,} out"
    )
    lines.append(
        f"- **通过率 {fmt_pass_rate(m['pass_rate'])}（{m['passed']}/{m['total']}）** · "
        f"平均分 {m['avg_score']:.2f}/5.00 · 失败 {m['failed']}"
    )
    if b:
        delta = fmt_pp(m["overall_delta_pp"])
        lines.append(
            f"- 基线 {b['run_id']}：{fmt_pass_rate(m['pass_rate'])} vs "
            f"{fmt_pass_rate(b['pass_rate'])} → 差值 **{delta}** · 平均分 {fmt_score(m['score_delta'])}"
        )
        tag_bits = [f"{r['name']} {fmt_pp(r['delta_pp'])}" for r in m["by_tag"]]
        if len(tag_bits) > MD_TAG_LINE_BUDGET:
            shown = tag_bits[:MD_TAG_LINE_BUDGET]
            shown.append(f"…（其余 {len(tag_bits) - MD_TAG_LINE_BUDGET} 个 tag 见 HTML）")
            tag_bits = shown
        lines.append(f"- 按 tag 差值：{' · '.join(tag_bits)}")
    else:
        lines.append(f"- 基线：**{NO_BASELINE_MARKER}**")
    lines.append("")

    lines.append(f"## 失败最多的 {TOP_TAGS} 个 tag")
    if m["failing_tags"]:
        for i, ft in enumerate(m["failing_tags"][:TOP_TAGS], 1):
            lines.append(f"{i}. `{ft['tag']}` — {ft['failures']} 个失败")
    else:
        lines.append("无失败用例。")
    lines.append("")

    lines.append(f"## 前 {TOP_CASES} 个失败用例")
    if m["failed_cases"]:
        for i, c in enumerate(m["failed_cases"][:TOP_CASES], 1):
            miss = sum(1 for p in c["expected_points"] if not p["hit"])
            bits = [f"`{c['case_key']}`", f"tags: {', '.join(c['tags'])}", f"{miss} 项要点未命中"]
            if c["violations"]:
                bits.append(f"{len(c['violations'])} 项违规")
            lines.append(f"{i}. " + " · ".join(bits))
    else:
        lines.append("无失败用例。")

    if len(lines) > MAX_LINES:  # defensive; expected ~20 lines
        raise ValueError(f"markdown summary exceeded {MAX_LINES} lines: {len(lines)}")
    return "\n".join(lines) + "\n"


def _fmt_duration(ms: int) -> str:
    s = ms // 1000
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"
