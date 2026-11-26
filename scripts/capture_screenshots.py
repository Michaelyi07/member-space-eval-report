"""Dev-only: capture AC4 tag-filter screenshots and record all network
requests made while loading the sample HTML (AC1 machine evidence:
exactly one request — the document itself, no external resources).

Usage: python scripts/capture_screenshots.py   (requires playwright + local Chrome)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "samples" / "run_20261120_a.html"
SHOTS = ROOT / "screenshots"


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    requests: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("request", lambda r: requests.append(r.url))
        page.goto(SAMPLE.as_uri())
        page.wait_for_timeout(800)

        page.locator("#failed").scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        page.screenshot(path=SHOTS / "ac4_before_filter.png")

        # click the safety tag chip in the filter bar
        page.locator('#tag-filter button[data-tag="safety"]').click()
        page.wait_for_timeout(400)
        page.screenshot(path=SHOTS / "ac4_tag_filter_safety.png")

        visible = page.eval_on_selector_all(
            ".failed-card",
            "els => els.filter(e => e.style.display !== 'none')"
            ".map(e => e.getAttribute('data-case-key'))",
        )
        buttons = page.eval_on_selector_all(
            "#tag-filter button",
            "els => els.map(e => e.getAttribute('data-tag'))",
        )
        browser.close()

    report = {
        "requests_observed": requests,
        "non_document_requests": [u for u in requests if not u.startswith("file:")],
        "filter_buttons": buttons,
        "visible_cases_after_safety_filter": visible,
    }
    (SHOTS / "network_request_log.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["non_document_requests"] else 1


if __name__ == "__main__":
    sys.exit(main())
