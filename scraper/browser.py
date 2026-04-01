"""
Browser context factory with Playwright + stealth configuration.
"""

import re
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import stealth_async

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-infobars",
    "--window-size=1280,720",
]


@asynccontextmanager
async def create_browser_context():
    """
    Async context manager that yields (browser, context).
    Apply stealth to each new page via apply_stealth(page).
    """
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=True,
            args=BROWSER_ARGS,
        )
        context: BrowserContext = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="America/New_York",
            ignore_https_errors=True,
            java_script_enabled=True,
        )
        # Block static assets that are irrelevant to scraping.
        # Playwright globs don't support {a,b} brace expansion; use a regex instead.
        _asset_re = re.compile(
            r"\.(png|jpg|jpeg|gif|webp|svg|ico|woff2?|ttf|eot)(\?.*)?$",
            re.IGNORECASE,
        )
        await context.route(
            "**/*",
            lambda route: route.abort()
            if _asset_re.search(route.request.url)
            else route.continue_(),
        )
        try:
            yield browser, context
        finally:
            await context.close()
            await browser.close()


async def new_stealth_page(context: BrowserContext) -> Page:
    """Create a new page with stealth patches applied."""
    page = await context.new_page()
    await stealth_async(page)
    return page
