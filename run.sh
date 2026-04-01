#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
#  TikTok Transcript Scraper — one-shot runner
#  Usage:
#    ./run.sh @username 10 cookies.json
#    ./run.sh              ← prompts you for all values
# ─────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

PROFILE="${1:-}"
LIMIT="${2:-}"
COOKIES="${3:-}"

if [[ -z "$PROFILE" ]]; then
  read -rp "TikTok profile (e.g. @soma.reset.toronto): " PROFILE
fi
if [[ -z "$LIMIT" ]]; then
  read -rp "Number of videos to scrape: " LIMIT
fi
if [[ -z "$COOKIES" ]]; then
  read -rp "Path to cookies.json (press Enter to skip — may hit login wall): " COOKIES
fi

echo ""
echo "▶  Checking dependencies..."
pip install -q -r requirements.txt

echo "▶  Checking Playwright browser..."
playwright install chromium 2>/dev/null || true

echo ""
if [[ -n "$COOKIES" ]]; then
  python main.py --profile "$PROFILE" --limit "$LIMIT" --cookies "$COOKIES"
else
  python main.py --profile "$PROFILE" --limit "$LIMIT"
fi
