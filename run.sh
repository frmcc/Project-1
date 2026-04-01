#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
#  TikTok Transcript Scraper — one-shot runner
#  Usage:
#    ./run.sh @username 10
#    ./run.sh              ← prompts you for both values
# ─────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

# ── 1. Grab args or prompt ───────────────────────────
PROFILE="${1:-}"
LIMIT="${2:-}"

if [[ -z "$PROFILE" ]]; then
  read -rp "TikTok profile (e.g. @charlidamelio): " PROFILE
fi
if [[ -z "$LIMIT" ]]; then
  read -rp "Number of videos to scrape: " LIMIT
fi

# ── 2. Install Python deps (skips if already installed) ──
echo ""
echo "▶  Checking dependencies..."
pip install -q -r requirements.txt

# ── 3. Install Chromium browser (skips if already installed) ──
echo "▶  Checking Playwright browser..."
playwright install chromium --with-deps 2>/dev/null || playwright install chromium

# ── 4. Run the scraper ───────────────────────────────
echo ""
python main.py --profile "$PROFILE" --limit "$LIMIT"
