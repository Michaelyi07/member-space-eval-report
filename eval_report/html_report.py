"""Single-file HTML report builder.

Every style and script is inlined; system font stacks only; zero external
resource references (no <link>, no src/href to remote hosts, no CDN).
pytest asserts the rendered output contains no ``http://``/``https://`` and
no ``<link`` — see tests/test_eval_report.py.
"""

from __future__ import annotations

import html

from eval_report.metrics import (
    NO_BASELINE_MARKER,
    fmt_pass_rate,
    fmt_pp,
    fmt_score,
)

# DOM-free filter predicate, kept as its own snippet so a JS engine (node)
# can unit-test it without a browser. Also inlined into the page script.
TAG_MATCH_JS = (
    "function tagMatch(tags, tag) {"
    " return tag === '__all__' || tags.indexOf(tag) >= 0; }"
)

_CSS = """
:root { --ink:#1c2430; --muted:#5b6b7c; --line:#d8e0ea; --bg:#f5f7fa;
        --card:#ffffff; --neg:#c62838; --pos:#1a7f37; --accent:#2b5cad; }
* { box-sizing:border-box; }
body { margin:0; padding:24px; background:var(--bg); color:var(--ink);
       font:14px/1.55 "Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif; }
h1 { font-size:20px; margin:0 0 4px; }
h2 { font-size:16px; margin:28px 0 10px; border-bottom:2px solid var(--line); padding-bottom:6px; }
.sub { color:var(--muted); margin:0 0 18px; }
table { border-collapse:collapse; width:100%; background:var(--card); }
th,td { border:1px solid var(--line); padding:6px 10px; text-align:left; }
th { background:#eef2f7; font-weight:600; }
.cards { display:flex; gap:14px; flex-wrap:wrap; margin:14px 0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:12px 18px; min-width:150px; }
.card .k { color:var(--muted); font-size:12px; }
.card .v { font-size:22px; font-weight:600; margin-top:2px; }
.delta-neg { color:var(--neg); font-weight:600; }
.delta-pos { color:var(--pos); }
.delta-zero { color:var(--muted); }
.meta td:first-child { color:var(--muted); width:180px; }
.filterbar { margin:12px 0; }
.filterbar button { border:1px solid var(--line); background:var(--card); color:var(--ink);
        padding:5px 12px; margin:0 6px 6px 0; border-radius:16px; cursor:pointer; font-size:13px; }
.filterbar button.active { background:var(--accent); color:#fff; border-color:var(--accent); }
.failed-card { background:var(--card); border:1px solid var(--line); border-radius:8px;
        padding:12px 16px; margin:10px 0; }
.failed-card .head { display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }
.case-key { font-weight:700; font-size:15px; }
.badge { font-size:11px; border-radius:10px; padding:1px 8px; background:#e8eef6; color:#33506e; }
.badge.hard { background:#f9e3e5; color:#8c2f39; }
.badge.easy { background:#e2f2e8; color:#22633a; }
.chip { font-size:11px; border-radius:10px; padding:1px 8px; background:#eef2f7; color:var(--muted); }
.input-summary { color:var(--muted); margin:6px 0; }
.pts { margin:6px 0; padding:0; list-style:none; }
.pts li { margin:2px 0; }
.hit { color:var(--pos); font-weight:600; }
.miss { color:var(--neg); font-weight:600; }
.viol { color:var(--neg); }
details { margin:8px 0; }
details pre { background:#0f1720; color:#d7e3f0; padding:12px; border-radius:6px;
        overflow:auto; max-height:320px; white-space:pre-wrap; word-break:break-word; }
.muted { color:var(--muted); }
.note { color:var(--muted); font-size:12px; margin-top:28px; }
"""


def render_html(run: dict, m: dict) -> str:
    e = html.escape
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="zh-CN"><head><meta charset="utf-8">')
    parts.append(f"<title>{e('评测运行报告 · ' + m['run_id'])}</title>")
    parts.append(f"<style>{_CSS}</style>")
    parts.append("</head><body>")
    parts.append(f"<h1>评测运行报告 · {e(m['run_id'])}</h1>")
    parts.append(
        f'<p class="sub">{e(run["suite"])} v{e(str(run["suite_version"]))} · '
        f"单次运行详情（虚构样张数据）</p>"
    )

    # ---- run metadata ----
    meta_rows = [
        ("Suite / 版本", f'{run["suite"]} v{run["suite_version"]}'),
        ("被测 prompt_version", run["prompt_version"]),
        ("模型", run["model"]),
        ("git_sha", run["git_sha"]),
        ("触发方式", run["trigger"]),
        ("开始时间", run.get("started_at", "—")),
        ("耗时", _fmt_duration(run["elapsed_ms"])),
        ("token 用量", f'输入 {run["tokens"]["input"]:,} / 输出 {run["tokens"]["output"]:,}'),
    ]
    parts.append('<h2>运行元信息</h2><table class="meta">')
    for k, v in meta_rows:
        parts.append(f"<tr><td>{e(k)}</td><td>{e(str(v))}</td></tr>")
    parts.append("</table>")

    # ---- summary cards ----
    ov = m["overall_delta_pp"]
    ov_cls = "delta-neg" if ov is not None and ov < 0 else ("delta-pos" if ov is not None else "delta-zero")
    sc = m["score_delta"]
    sc_cls = "delta-neg" if sc is not None and sc < 0 else ("delta-pos" if sc is not None else "delta-zero")
    parts.append('<div class="cards">')
    parts.append(
        f'<div class="card"><div class="k">总体通过率</div>'
        f'<div class="v">{e(fmt_pass_rate(m["pass_rate"]))}</div>'
        f'<div class="k">{m["passed"]}/{m["total"]} 通过</div></div>'
    )
    parts.append(
        f'<div class="card"><div class="k">平均分（5 分制）</div>'
        f'<div class="v">{m["avg_score"]:.2f}</div></div>'
    )
    parts.append(
        f'<div class="card"><div class="k">与基线差值（通过率）</div>'
        f'<div class="v {ov_cls}">{e(fmt_pp(ov))}</div>'
        f'<div class="k">基线 {e((run.get("baseline") or {}).get("run_id", NO_BASELINE_MARKER))}</div></div>'
    )
    parts.append(
        f'<div class="card"><div class="k">平均分差值</div>'
        f'<div class="v {sc_cls}">{e(fmt_score(m["score_delta"]))}</div></div>'
    )
    parts.append(
        f'<div class="card"><div class="k">失败用例</div>'
        f'<div class="v delta-neg">{m["failed"]}</div></div>'
    )
    parts.append("</div>")

    # ---- grouped pass-rate tables ----
    for title, rows in (("按 tag 通过率", m["by_tag"]), ("按 difficulty 通过率", m["by_difficulty"])):
        parts.append(f"<h2>{e(title)}</h2><table>")
        parts.append(
            "<tr><th>分组</th><th>用例数</th><th>通过</th><th>失败</th><th>通过率</th>"
            "<th>基线通过率</th><th>差值</th></tr>"
        )
        for r in rows:
            delta_txt = fmt_pp(r["delta_pp"])
            raw = r["delta_pp"]
            if raw is None:
                cls = "delta-zero"
            elif raw < 0:  # any real decline is red, even when it rounds to ±0.0pp
                cls = "delta-neg"
            elif raw == 0:
                cls = "delta-zero"
            else:
                cls = "delta-pos"
            base_cell = e(fmt_pass_rate(r["baseline_pass_rate"])) if r["baseline_pass_rate"] is not None else e(NO_BASELINE_MARKER)
            parts.append(
                f'<tr><td>{e(r["name"])}</td><td>{r["total"]}</td><td>{r["passed"]}</td>'
                f'<td>{r["failed"]}</td><td>{e(fmt_pass_rate(r["pass_rate"]))}</td>'
                f'<td>{base_cell}</td><td class="{cls}">{e(delta_txt)}</td></tr>'
            )
        parts.append("</table>")

    # ---- failed cases with tag filter ----
    tag_counts: dict[str, int] = {}
    for c in m["failed_cases"]:
        for t in c["tags"]:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    parts.append('<h2 id="failed">失败用例</h2>')
    parts.append('<div class="filterbar" id="tag-filter">')
    parts.append('<button data-tag="__all__" class="active">全部</button>')
    for t in sorted(tag_counts):
        parts.append(f'<button data-tag="{e(t)}">{e(t)} ({tag_counts[t]})</button>')
    parts.append("</div>")

    if not m["failed_cases"]:
        parts.append('<p class="muted">本运行无失败用例。</p>')
    for c in m["failed_cases"]:
        parts.append(
            f'<div class="failed-card" data-tags="{e(" ".join(c["tags"]))}" '
            f'data-case-key="{e(c["case_key"])}">'
        )
        diff_badge = f'<span class="badge {e(c["difficulty"])}">{e(c["difficulty"])}</span>'
        chips = " ".join(f'<span class="chip">{e(t)}</span>' for t in c["tags"])
        parts.append(
            f'<div class="head"><span class="case-key">{e(c["case_key"])}</span>'
            f"{diff_badge}{chips}"
            f'<span class="muted">耗时 {c["duration_ms"]:,} ms · 评分 {c["score"]:.1f}</span></div>'
        )
        parts.append(f'<div class="input-summary">输入摘要：{e(_summarize(c["input"]))}</div>')
        parts.append('<ul class="pts">')
        for p in c["expected_points"]:
            mark = '<span class="hit">✓ 命中</span>' if p["hit"] else '<span class="miss">✗ 未命中</span>'
            parts.append(f"<li>{mark} — {e(p['point'])}</li>")
        parts.append("</ul>")
        if c["violations"]:
            parts.append('<div class="viol">违规项：</div><ul class="viol">')
            for v in c["violations"]:
                parts.append(f"<li>{e(v)}</li>")
            parts.append("</ul>")
        else:
            parts.append('<div class="muted">违规项：无</div>')
        parts.append("<details><summary>被测输出全文</summary>")
        parts.append(f"<pre>{e(c['output'])}</pre></details>")
        parts.append("</div>")

    # ---- slowest 10 ----
    parts.append("<h2>最慢 10 个用例</h2><table>")
    parts.append("<tr><th>#</th><th>case_key</th><th>tags</th><th>难度</th><th>耗时</th><th>结果</th></tr>")
    for i, c in enumerate(m["slowest"], 1):
        res = "通过" if c["passed"] else "失败"
        res_cls = "" if c["passed"] else ' class="delta-neg"'
        parts.append(
            f"<tr><td>{i}</td><td>{e(c['case_key'])}</td>"
            f"<td>{e(' '.join(c['tags']))}</td><td>{e(c['difficulty'])}</td>"
            f'<td>{c["duration_ms"]:,} ms</td><td{res_cls}>{res}</td></tr>'
        )
    parts.append("</table>")

    # ---- judge unstable ----
    parts.append("<h2>judge_unstable 用例清单</h2>")
    if not m["judge_unstable"]:
        parts.append('<p class="muted">无 judge 不稳定用例。</p>')
    else:
        parts.append("<table><tr><th>case_key</th><th>tags</th><th>judge 结论</th><th>用例判定</th></tr>")
        for c in m["judge_unstable"]:
            parts.append(
                f"<tr><td>{e(c['case_key'])}</td><td>{e(' '.join(c['tags']))}</td>"
                f"<td>{e(str(c['judge'].get('verdict', '—')))}</td>"
                f"<td>{'通过' if c['passed'] else '失败'}</td></tr>"
            )
        parts.append("</table>")

    parts.append(
        '<p class="note">本报告由 eval-report 生成；样式与脚本全部内联，'
        "无任何外部资源引用。样张数据均为虚构。</p>"
    )
    parts.append("<script>")
    parts.append(TAG_MATCH_JS)
    parts.append(
        "(function(){"
        "var bar=document.getElementById('tag-filter');"
        "if(!bar) return;"
        "function apply(tag){"
        "var cards=document.querySelectorAll('.failed-card');"
        "for(var i=0;i<cards.length;i++){"
        "var tags=cards[i].getAttribute('data-tags').split(' ');"
        "cards[i].style.display = tagMatch(tags, tag) ? '' : 'none';"
        "}"
        "var btns=bar.querySelectorAll('button');"
        "for(var j=0;j<btns.length;j++){"
        "btns[j].className = btns[j].getAttribute('data-tag')===tag ? 'active' : '';"
        "}"
        "}"
        "bar.addEventListener('click',function(ev){"
        "var b=ev.target.closest('button'); if(b) apply(b.getAttribute('data-tag'));"
        "});"
        "})();"
    )
    parts.append("</script>")
    parts.append("</body></html>")
    return "\n".join(parts)


def _summarize(text: str, limit: int = 140) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _fmt_duration(ms: int) -> str:
    s = ms // 1000
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"
