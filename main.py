#!/usr/bin/env python3
"""
TikTok Transcript Scraper
Usage:
    python main.py --profile @username --limit 10
"""

import argparse
import asyncio
import random
import sys

from scraper.browser import create_browser_context, new_stealth_page
from scraper.profile import scrape_profile_urls
from scraper.storage import save_transcript
from scraper.transcript import extract_transcript

INTER_VIDEO_DELAY = (3, 7)  # seconds between video requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape transcripts from a TikTok profile.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--profile",
        required=True,
        metavar="@HANDLE",
        help="TikTok profile handle, e.g. @username",
    )
    parser.add_argument(
        "--limit",
        required=True,
        type=int,
        metavar="N",
        help="Number of most-recent videos to process (must be > 0)",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit must be a positive integer")

    return args


async def run(profile: str, limit: int) -> None:
    print(f"\n=== TikTok Transcript Scraper ===")
    print(f"Profile : {profile}")
    print(f"Limit   : {limit} video(s)\n")

    async with create_browser_context() as (browser, context):
        # --- Step 1: collect video URLs from the profile page ---
        profile_page = await new_stealth_page(context)
        try:
            video_urls = await scrape_profile_urls(profile_page, profile, limit)
        finally:
            await profile_page.close()

        if not video_urls:
            print("[main] No video URLs found. Exiting.")
            return

        print(f"\n[main] Processing {len(video_urls)} video(s)...\n")

        # --- Step 2: extract transcript for each video ---
        success = 0
        failed = 0

        for idx, url in enumerate(video_urls, start=1):
            print(f"[main] [{idx}/{len(video_urls)}] {url}")
            data = await extract_transcript(context, url)

            if data:
                output_path = save_transcript(profile, data)
                print(f"[main]   Saved → {output_path}")
                success += 1
            else:
                print(f"[main]   Failed to extract transcript")
                failed += 1

            # Polite delay between requests (skip after last video)
            if idx < len(video_urls):
                delay = random.uniform(*INTER_VIDEO_DELAY)
                print(f"[main]   Waiting {delay:.1f}s before next video...")
                await asyncio.sleep(delay)

        # --- Summary ---
        print(f"\n=== Done ===")
        print(f"Succeeded : {success}")
        print(f"Failed    : {failed}")
        print(f"Output    : ./data/\n")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args.profile, args.limit))
    except KeyboardInterrupt:
        print("\n[main] Interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
