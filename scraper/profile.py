"""
TikTok profile page scraper: navigates to a profile and extracts video URLs.
"""

import asyncio
import random
from typing import List

from playwright.async_api import Page

TIKTOK_BASE = "https://www.tiktok.com"
VIDEO_LINK_SELECTOR = 'a[href*="/video/"]'
MAX_STALL_ROUNDS = 3


async def scrape_profile_urls(page: Page, profile: str, limit: int) -> List[str]:
    """
    Navigate to @profile and scroll until `limit` video URLs are collected.

    Returns a deduplicated list of up to `limit` absolute video URLs.
    """
    handle = profile.lstrip("@")
    profile_url = f"{TIKTOK_BASE}/@{handle}"

    print(f"[profile] Navigating to {profile_url}")
    # "networkidle" times out on TikTok due to constant analytics pings.
    # Use "load" then wait for the first video card to appear.
    await page.goto(profile_url, wait_until="load", timeout=30_000)
    try:
        await page.wait_for_selector(VIDEO_LINK_SELECTOR, timeout=15_000)
    except Exception:
        print("[profile] Warning: video grid did not appear within 15s, continuing anyway")

    seen: dict[str, None] = {}  # ordered set via dict keys
    stall_count = 0

    while len(seen) < limit:
        # Collect all visible video links
        anchors = await page.query_selector_all(VIDEO_LINK_SELECTOR)
        for anchor in anchors:
            href = await anchor.get_attribute("href")
            if href and "/video/" in href:
                full = href if href.startswith("http") else f"{TIKTOK_BASE}{href}"
                seen[full] = None

        if len(seen) >= limit:
            break

        prev_count = len(seen)

        # Human-like scroll: random distance between 600 and 1000px
        scroll_px = random.randint(600, 1000)
        await page.evaluate(f"window.scrollBy(0, {scroll_px})")

        # Random pause between 1.5s and 3.5s
        await asyncio.sleep(random.uniform(1.5, 3.5))

        # Re-collect after scroll
        anchors = await page.query_selector_all(VIDEO_LINK_SELECTOR)
        for anchor in anchors:
            href = await anchor.get_attribute("href")
            if href and "/video/" in href:
                full = href if href.startswith("http") else f"{TIKTOK_BASE}{href}"
                seen[full] = None

        if len(seen) == prev_count:
            stall_count += 1
            print(f"[profile] Scroll stalled ({stall_count}/{MAX_STALL_ROUNDS}), found {len(seen)} URLs so far")
            if stall_count >= MAX_STALL_ROUNDS:
                print("[profile] Stall limit reached, stopping scroll")
                break
        else:
            stall_count = 0
            print(f"[profile] Found {len(seen)}/{limit} video URLs")

    result = list(seen.keys())[:limit]
    print(f"[profile] Collected {len(result)} video URLs")
    return result
