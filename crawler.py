"""
Headless crawler to pull application statuses and auto-normalize them.

Usage example (selectors will vary per site):
    python crawler.py \
      --login-url "https://example.com/login" \
      --target-url "https://example.com/applications" \
      --username "$WW_USERNAME" --password "$WW_PASSWORD" \
      --row-selector "table#jobs tr" \
      --company-selector "td:nth-child(1)" \
      --role-selector "td:nth-child(2)" \
      --status-selector "td:nth-child(3)" \
      --location-selector "td:nth-child(4)"

You can pass credentials via env vars WW_USERNAME/WW_PASSWORD.
Install Playwright browser once: `python -m playwright install chromium`
"""

import argparse
import asyncio
import os
from datetime import date
from typing import Optional

from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from app import ensure_database, get_db, normalize_status, upsert_application


async def extract_text(element, selector: str) -> str:
    if not selector:
        return ""
    target = await element.query_selector(selector)
    if not target:
        return ""
    text = (await target.inner_text()) or ""
    return text.strip()


async def try_login(page, username: str, password: str, wait_ms: int) -> None:
    user_selector = "input[type='email'], input[name='username'], input[id='UserName'], input[name='userid']"
    pass_selector = "input[type='password'], input[id='Password'], input[name='password']"
    submit_selector = "button[type='submit'], input[type='submit']"
    try:
        await page.fill(user_selector, username)
        await page.fill(pass_selector, password)
        await page.click(submit_selector)
        await page.wait_for_timeout(wait_ms)
    except PlaywrightTimeoutError:
        pass


async def crawl_and_sync(
    login_url: str,
    target_url: str,
    username: Optional[str],
    password: Optional[str],
    row_selector: str,
    company_selector: str,
    role_selector: str,
    status_selector: str,
    location_selector: Optional[str],
    nav_link_text: Optional[str],
    headful: bool,
    login_wait_ms: int,
    source_label: str,
) -> int:
    ensure_database()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headful)
        page = await browser.new_page()
        await page.goto(login_url or target_url)
        if username and password:
            await try_login(page, username, password, login_wait_ms)
        if nav_link_text:
            try:
                await page.get_by_text(nav_link_text, exact=False).click()
                await page.wait_for_timeout(1500)
            except PlaywrightTimeoutError:
                pass
        if target_url:
            await page.goto(target_url)

        rows = await page.query_selector_all(row_selector)
        conn = get_db()
        imported = 0

        for row in rows:
            status_raw = await extract_text(row, status_selector)
            company = await extract_text(row, company_selector)
            role = await extract_text(row, role_selector)
            if not (company and role and status_raw):
                continue

            status = normalize_status(status_raw)
            location = await extract_text(row, location_selector) if location_selector else ""
            upsert_application(
                conn,
                {
                    "company": company,
                    "role": role,
                    "location": location,
                    "status": status,
                    "applied_date": date.today().isoformat(),
                    "follow_up_date": None,
                    "source": source_label,
                    "notes": f"Imported via crawler from {target_url}",
                    "url": target_url,
                },
            )
            imported += 1

        await browser.close()
        return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl a job portal and sync statuses.")
    parser.add_argument("--preset", choices=["waterlooworks"], help="Use built-in selector presets")
    parser.add_argument("--login-url", help="Login page URL", default=None)
    parser.add_argument("--target-url", help="Page containing the application table")
    parser.add_argument("--username", help="Login username (or set WW_USERNAME)", default=os.environ.get("WW_USERNAME"))
    parser.add_argument("--password", help="Login password (or set WW_PASSWORD)", default=os.environ.get("WW_PASSWORD"))
    parser.add_argument("--row-selector", default="table tr", help="CSS selector for each row")
    parser.add_argument("--company-selector", default="td:nth-child(1)", help="CSS selector for company within a row")
    parser.add_argument("--role-selector", default="td:nth-child(2)", help="CSS selector for role within a row")
    parser.add_argument("--status-selector", default="td:nth-child(3)", help="CSS selector for status within a row")
    parser.add_argument("--location-selector", default=None, help="Optional CSS selector for location")
    parser.add_argument("--nav-link-text", default=None, help="Optional nav link text to click after login")
    parser.add_argument("--login-wait-ms", type=int, default=4000, help="Wait after logging in before scraping")
    parser.add_argument("--headful", action="store_true", help="Run browser visibly for debugging")
    parser.add_argument("--source-label", default="Crawler", help="Value for the 'source' field in the DB")

    args = parser.parse_args()

    if args.preset == "waterlooworks":
        args.login_url = args.login_url or "https://waterlooworks.uwaterloo.ca/myAccount/dashboard.htm"
        args.target_url = args.target_url or "https://waterlooworks.uwaterloo.ca/myAccount/dashboard.htm"
        args.row_selector = args.row_selector or "table tbody tr"
        args.company_selector = args.company_selector or "td:nth-child(2)"
        args.role_selector = args.role_selector or "td:nth-child(3)"
        args.status_selector = args.status_selector or "td:nth-child(4)"
        args.location_selector = args.location_selector or "td:nth-child(5)"
        args.nav_link_text = args.nav_link_text or "Postings / Applications"
        args.source_label = args.source_label or "WaterlooWorks"

    count = asyncio.run(
        crawl_and_sync(
            login_url=args.login_url or args.target_url,
            target_url=args.target_url,
            username=args.username,
            password=args.password,
            row_selector=args.row_selector,
            company_selector=args.company_selector,
            role_selector=args.role_selector,
            status_selector=args.status_selector,
            location_selector=args.location_selector,
            nav_link_text=args.nav_link_text,
            headful=args.headful,
            login_wait_ms=args.login_wait_ms,
            source_label=args.source_label,
        )
    )
    print(f"Imported or updated {count} applications.")


if __name__ == "__main__":
    main()
