"""
Browser context factory with Playwright + stealth configuration.
"""

import glob
import os
import re
import urllib.parse
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth

_stealth = Stealth()

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


def _get_proxy() -> dict | None:
    """
    Read the system HTTPS_PROXY env var and return a Playwright proxy dict.
    Playwright needs {server, username, password} split out explicitly —
    embedding credentials in the server URL string doesn't work reliably.
    """
    raw = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
    if not raw:
        return None
    p = urllib.parse.urlparse(raw)
    proxy: dict = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
    if p.username:
        proxy["username"] = urllib.parse.unquote(p.username)
    if p.password:
        proxy["password"] = urllib.parse.unquote(p.password)
    return proxy


def _find_chromium() -> str | None:
    """
    Return the path to a usable Chromium/headless-shell binary.

    Playwright downloads browsers to ~/.cache/ms-playwright/.  If the version
    the current package expects isn't downloaded yet (e.g. network is blocked),
    fall back to the highest-numbered headless_shell that IS present.
    Returns None to let Playwright raise its own helpful error if nothing found.
    """
    cache = os.path.expanduser("~/.cache/ms-playwright")

    # Names Playwright uses across versions
    for pattern, binary in [
        ("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell", None),
        ("chromium_headless_shell-*/chrome-linux/headless_shell", None),
        ("chromium-*/chrome-linux/chrome", None),
    ]:
        matches = sorted(glob.glob(os.path.join(cache, pattern)), reverse=True)
        for path in matches:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None


@asynccontextmanager
async def create_browser_context():
    """
    Async context manager that yields (browser, context).
    Apply stealth to each new page via apply_stealth(page).
    """
    async with async_playwright() as pw:
        executable_path = _find_chromium()
        proxy = _get_proxy()
        browser: Browser = await pw.chromium.launch(
            headless=True,
            args=BROWSER_ARGS,
            executable_path=executable_path,  # None = let Playwright auto-resolve
            proxy=proxy,  # None = no proxy override (use system default)
        )
        context: BrowserContext = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            timezone_id="America/New_York",
            ignore_https_errors=True,
            java_script_enabled=True,
            proxy=proxy,  # also set on context for request API calls
        )
        # Block static assets that are irrelevant to scraping.
        # Playwright globs don't support {a,b} brace expansion; use a regex instead.
        _asset_re = re.compile(
            r"\.(png|jpg|jpeg|gif|webp|svg|ico|woff2?|ttf|eot)(\?.*)?$",
            re.IGNORECASE,
        )

        async def _block_assets(route):
            # route.abort() / route.continue_() are coroutines — must be awaited.
            # A plain lambda would return the coroutine un-awaited (silent no-op).
            if _asset_re.search(route.request.url):
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", _block_assets)
        try:
            yield browser, context
        finally:
            await context.close()
            await browser.close()


async def new_stealth_page(context: BrowserContext) -> Page:
    """Create a new page with stealth patches applied."""
    page = await context.new_page()
    await _stealth.apply_stealth_async(page)
    return page
