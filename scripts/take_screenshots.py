"""Capture reviewer screenshots from a running AuditTrace UI (Docker on :8080 or Vite).

Does not upload files or call Gemini/Vision. Uses documents already in data/.

From the repository root, with the UI running:

    pip install playwright
    python -m playwright install chromium
    python scripts/take_screenshots.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "screenshots"
DEFAULT_URL = "http://localhost:8080"


def _shot(page: Page, name: str) -> None:
    target = OUT_DIR / name
    page.screenshot(path=str(target), full_page=False)
    print(f"Wrote {target.relative_to(ROOT).as_posix()}")


def _wait_ui(page: Page) -> None:
    page.wait_for_selector("text=AuditTrace", timeout=30_000)


def capture(base_url: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.goto(base_url, wait_until="networkidle")
        _wait_ui(page)

        page.get_by_role("link", name="Findings").click()
        page.wait_for_selector("text=Vendor mismatch")
        page.wait_for_timeout(400)
        _shot(page, "findings.png")

        page.get_by_role("link", name="Vendor mismatch").first.click()
        page.wait_for_selector("img[alt='Page 1']")
        page.wait_for_timeout(800)
        _shot(page, "evidence_side_by_side.png")

        page.goto(f"{base_url}/documents/1", wait_until="networkidle")
        page.wait_for_selector("text=invoice.pdf")
        page.wait_for_selector("img[alt='Page 1']")
        page.get_by_text("Vendor name", exact=True).first.click()
        page.wait_for_timeout(800)
        _shot(page, "document_review.png")

        page.get_by_text("Currency", exact=True).first.click()
        card = page.locator("[role='button']").filter(has_text="Suggested currency")
        card.wait_for()
        card.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        _shot(page, "currency_flag.png")

        page.goto(f"{base_url}/documents/2", wait_until="networkidle")
        page.wait_for_selector("text=Exact copy of")
        page.wait_for_timeout(400)
        _shot(page, "duplicate_banner.png")

        page.get_by_role("link", name="Audit log").click()
        page.wait_for_selector("text=Approvals and rejections")
        page.wait_for_timeout(400)
        _shot(page, "audit_log.png")

        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Save AuditTrace reviewer screenshots.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_URL,
        help="Running UI origin. Default: http://localhost:8080 (Docker).",
    )
    args = parser.parse_args()
    try:
        capture(args.base_url.rstrip("/"))
    except Exception as exc:
        print(f"Screenshot capture failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
