"""
Transcript extraction for individual TikTok video pages.

Primary method:  intercept network responses for WebVTT/subtitle payloads,
                 or parse subtitle URLs from the page's embedded JSON.
Fallback method: read native closed-captions container from the DOM.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import BrowserContext, Page, Response

from scraper.browser import new_stealth_page

# Patterns that identify TikTok subtitle/caption network responses
SUBTITLE_URL_RE = re.compile(r"(subtitle|caption|captions)", re.IGNORECASE)
VIDEO_ID_RE = re.compile(r"/video/(\d+)")

# DOM selectors (fallback)
CAPTION_SELECTORS = [
    "span.tiktok-caption-text",
    ".caption-container span",
    "[data-e2e='video-desc']",
    "h1[data-e2e='video-desc']",
]

MAX_RETRIES = 2
RETRY_DELAY = 5  # seconds


def _parse_webvtt(vtt_text: str) -> tuple[str, list[dict]]:
    """
    Parse a WebVTT string into (transcript_text, segments).
    segments = [{"start": "00:00:01.000", "end": "00:00:03.000", "text": "..."}]
    """
    segments = []
    lines = vtt_text.splitlines()
    i = 0
    # Skip WEBVTT header block
    while i < len(lines) and not re.match(r"\d+:\d+", lines[i]):
        i += 1

    while i < len(lines):
        line = lines[i].strip()
        # Timestamp line
        ts_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})",
            line,
        )
        if ts_match:
            start, end = ts_match.group(1), ts_match.group(2)
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            text = " ".join(text_lines).strip()
            if text:
                segments.append({"start": start, "end": end, "text": text})
        else:
            i += 1

    # Deduplicate consecutive identical segments
    deduped = []
    for seg in segments:
        if not deduped or deduped[-1]["text"] != seg["text"]:
            deduped.append(seg)

    transcript_text = " ".join(s["text"] for s in deduped)
    return transcript_text, deduped


def _extract_subtitle_url_from_page_json(page_json: dict) -> Optional[str]:
    """
    Walk TikTok's __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON to find a subtitle URL.
    Prefers English ("eng-US") but falls back to the first available entry.
    """
    try:
        # Path varies by TikTok version; try common paths
        item_struct = None

        # Path 1: webapp.video-detail
        try:
            item_struct = (
                page_json["__DEFAULT_SCOPE__"]["webapp.video-detail"]
                ["itemInfo"]["itemStruct"]
            )
        except (KeyError, TypeError):
            pass

        # Path 2: flat itemInfo
        if item_struct is None:
            try:
                item_struct = page_json["itemInfo"]["itemStruct"]
            except (KeyError, TypeError):
                pass

        if item_struct is None:
            return None

        subtitle_infos = item_struct.get("video", {}).get("subtitleInfos", [])
        if not subtitle_infos:
            subtitle_infos = item_struct.get("SubtitleInfos", [])

        if not subtitle_infos:
            return None

        # Prefer English
        for info in subtitle_infos:
            lang = info.get("LanguageCodeName", "") or info.get("languageCodeName", "")
            if "eng" in lang.lower():
                return info.get("Url") or info.get("url")

        # Fall back to first entry
        first = subtitle_infos[0]
        return first.get("Url") or first.get("url")

    except Exception:
        return None


def _extract_metadata_from_page_json(page_json: dict) -> dict:
    """Extract title and upload_date from TikTok's page JSON."""
    title = ""
    upload_date = ""

    try:
        item_struct = None
        try:
            item_struct = (
                page_json["__DEFAULT_SCOPE__"]["webapp.video-detail"]
                ["itemInfo"]["itemStruct"]
            )
        except (KeyError, TypeError):
            pass
        if item_struct is None:
            try:
                item_struct = page_json["itemInfo"]["itemStruct"]
            except (KeyError, TypeError):
                pass

        if item_struct:
            title = item_struct.get("desc", "")
            create_time = item_struct.get("createTime")
            if create_time:
                upload_date = datetime.fromtimestamp(
                    int(create_time), tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    return {"title": title, "upload_date": upload_date}


async def _get_page_json(page: Page) -> Optional[dict]:
    """
    Extract TikTok's embedded page data.

    Tries three sources in order:
      1. window['__UNIVERSAL_DATA_FOR_REHYDRATION__'] JS variable (most reliable,
         avoids parsing the raw script-tag text which is a JS assignment not JSON)
      2. window.__NEXT_DATA__ (legacy/SSR TikTok routes)
      3. Raw textContent of the script tag as last resort, stripping the
         assignment prefix before JSON-parsing
    """
    # Source 1: evaluate the live window variable directly
    try:
        data = await page.evaluate("() => window['__UNIVERSAL_DATA_FOR_REHYDRATION__']")
        if data and isinstance(data, dict):
            return data
    except Exception:
        pass

    # Source 2: Next.js data (some TikTok routes)
    try:
        data = await page.evaluate("() => window.__NEXT_DATA__")
        if data and isinstance(data, dict):
            return data
    except Exception:
        pass

    # Source 3: raw script tag text — strip JS assignment prefix if present
    try:
        raw = await page.evaluate(
            """() => {
                const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                return el ? el.textContent : null;
            }"""
        )
        if raw:
            # Strip leading JS assignment: `window['...'] = ` or `window["..."] = `
            json_str = re.sub(r'^[^{]*', '', raw.strip())
            if json_str:
                return json.loads(json_str)
    except Exception:
        pass

    return None


async def _extract_once(context: BrowserContext, video_url: str) -> Optional[dict]:
    """Single attempt at transcript extraction for a video URL."""
    page: Page = await new_stealth_page(context)
    captured_vtt: list[str] = []

    async def on_response(response: Response):
        url = response.url
        content_type = response.headers.get("content-type", "")
        if "text/vtt" in content_type or SUBTITLE_URL_RE.search(url):
            try:
                body = await response.text()
            except Exception:
                try:
                    body = (await response.body()).decode("utf-8", errors="replace")
                except Exception:
                    return
            if body.strip().startswith("WEBVTT"):
                captured_vtt.append(body)

    page.on("response", on_response)

    try:
        print(f"[transcript] Loading {video_url}")
        await page.goto(video_url, wait_until="networkidle", timeout=30_000)

        # Extract video ID from URL
        vid_match = VIDEO_ID_RE.search(video_url)
        video_id = vid_match.group(1) if vid_match else "unknown"

        # Get page JSON for metadata + subtitle URL
        page_json = await _get_page_json(page)
        metadata = _extract_metadata_from_page_json(page_json) if page_json else {}

        # Fallback title from page <title>
        if not metadata.get("title"):
            metadata["title"] = await page.title()

        vtt_text = None

        # Primary: use captured network response
        if captured_vtt:
            vtt_text = captured_vtt[0]
            print("[transcript] Got captions via network interception")

        # Primary alt: extract subtitle URL from page JSON and fetch it
        if vtt_text is None and page_json:
            sub_url = _extract_subtitle_url_from_page_json(page_json)
            if sub_url:
                print(f"[transcript] Fetching subtitle from page JSON: {sub_url}")
                try:
                    resp = await context.request.get(sub_url)
                    body = await resp.text()
                    if body.strip().startswith("WEBVTT"):
                        vtt_text = body
                except Exception as e:
                    print(f"[transcript] Failed to fetch subtitle URL: {e}")

        if vtt_text:
            transcript_text, segments = _parse_webvtt(vtt_text)
        else:
            # Fallback: DOM captions
            print("[transcript] Falling back to DOM caption extraction")
            texts = []
            for selector in CAPTION_SELECTORS:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    t = await el.inner_text()
                    if t.strip():
                        texts.append(t.strip())
            transcript_text = " ".join(texts)
            segments = []

        if not transcript_text:
            print(f"[transcript] No transcript found for {video_url}")

        return {
            "url": video_url,
            "video_id": video_id,
            "title": metadata.get("title", ""),
            "upload_date": metadata.get("upload_date", ""),
            "transcript_text": transcript_text,
            "transcript_segments": segments,
        }

    finally:
        await page.close()


async def extract_transcript(
    context: BrowserContext, video_url: str
) -> Optional[dict]:
    """
    Extract transcript for a video URL with up to MAX_RETRIES retries.
    Returns None if all attempts fail.
    """
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            result = await _extract_once(context, video_url)
            return result
        except Exception as e:
            print(f"[transcript] Attempt {attempt} failed for {video_url}: {e}")
            if attempt <= MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)
            else:
                print(f"[transcript] Giving up on {video_url} after {attempt} attempts")
                return None
