# member-space-eval-report

`eval-report <run_id>` — 单次评测运行报告生成器：一次运行产出两份报告：

1. **单文件 HTML 详情**（`{run_id}.html`）：样式与脚本全部内联，不引用任何外部 CDN /
   外部资源（系统字体栈，零 `<link>`、零 `src=`），断网可直接打开。内容含运行元信息
   （suite 与版本、被测 prompt_version、模型、git_sha、触发方式、耗时、token 用量）、
   总体通过率与平均分、与基线对比（升降百分点，**下降标红**）、按 tag 与 difficulty
   分组的通过率表、失败用例列表（输入摘要、期望要点逐条命中、违规项、被测输出全文
   折叠展示）、最慢 10 个用例、judge_unstable 清单；失败用例支持**按 tag 筛选**。
2. **Markdown 摘要**（`{run_id}.md`）：不超过 60 行，供 CI 贴到 PR 评论，含通过率、
   与基线差值（带符号 pp；0.0 显示 `±0.0pp`）、失败最多的 3 个 tag、前 5 个失败用例的
   case_key。

**报告组件与「HTML 模板」交付物对应关系**：订单交付物中的「HTML 模板」即
`eval_report/html_report.py`（`_CSS` 样式模板 + `render_html` 结构模板 +
`TAG_MATCH_JS` 过滤脚本模板，三者内联组装为单文件 HTML）。

**没有基线时显示「无基线」，而不是 0**（差值计算整体跳过；部分基线缺某个 tag 时仅该
行显示「无基线」）。所有样张数据均为虚构，不含任何真实个人/企业信息，不含客户名称。

## 运行

```bash
# Python 3.11+，运行时零第三方依赖
python -m eval_report run_20261120_a --runs-dir fixtures/runs --outdir samples
```

## 测试

```bash
pip install -r requirements.txt   # 仅 pytest（dev 依赖）
python -m pytest tests/ -v
```

可选：`test_filter_logic_dom_free` 用 node（若在 PATH 中）对过滤谓词做无 DOM 单测；
无 node 时自动 skip，不影响其余测试。

## 运行记录 schema（README 对接点）

运行记录为 JSON 文件 `<runs-dir>/<run_id>.json`：

```jsonc
{
  "run_id": "run_20261120_a",
  "suite": "ms-agent-eval-suite", "suite_version": "1.4.0",
  "prompt_version": "assistant-v7.2",
  "model": "glm-4.6-air",
  "git_sha": "3f9c1ab77e2d4c05a8b6d1e94f7a02c3b45d6e7f",
  "trigger": "scheduled | manual | ci",
  "started_at": "2026-11-20T03:00:00Z",
  "elapsed_ms": 512340,
  "tokens": { "input": 184300, "output": 42110 },
  "baseline": {                    // 可为 null（无基线）
    "run_id": "run_20261113_a",
    "pass_rate": 0.80, "avg_score": 3.90,
    "by_tag": {"kb": 0.75},        // tag -> 通过率
    "by_difficulty": {"easy": 1.00}
  },
  "cases": [{
    "case_key": "KB-0003",
    "tags": ["kb", "tone"],        // 一条用例可属多个 tag，分组时逐 tag 计入
    "difficulty": "easy | medium | hard",
    "input": "...",                // 被测输入原文（HTML 里显示摘要，最多 140 字）
    "expected_points": [{"point": "引用条款编号", "hit": true}],
    "violations": ["..."],
    "passed": true,
    "score": 4.5,                  // 5 分制
    "duration_ms": 4100,
    "judge": {"verdict": "pass", "stable": true, "repeats": ["pass", "pass"]},
    "output": "..."                // 被测输出全文（HTML 折叠展示）
  }]
}
```

**真实平台对接点**：`eval_report/loader.py::load_run` 是唯一读存储的函数，接真实
run-store 时替换该函数（保持相同返回 schema）即可，其余模块零改动。

## 重新生成样张

```bash
python scripts/make_samples.py   # 重新生成 fixtures/runs/*.json 与 samples/*.{html,md}
```

## 交付样张与验证记录

- `samples/run_20261120_a.html|md` — 有基线运行（含下降标红、3-tag 失败用例、judge 不稳定用例）
- `samples/run_20261121_b.html|md` — 无基线运行（显示「无基线」）
- `screenshots/` — AC1 断网打开样张（浏览器网络面板无外部请求）与 AC4 tag 筛选生效截图
- 测试结果（Windows 11 / Python 3.13.14 / pytest 9.2.0）：见交付正文与 `verification/` 记录

## 边界

不做评测 runner 本体、不做 judge/LLM 集成、不做 CI 平台接线（只产出可贴的 Markdown
片段）、不接真实运行数据。修订范围内含报告布局、摘要字段与测试调整。
