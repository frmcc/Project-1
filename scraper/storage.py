"""
Persist transcript data as JSON files under the /data directory.
"""

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _sanitize(name: str) -> str:
    """Strip @ and replace non-alphanumeric characters with underscores."""
    name = name.lstrip("@")
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def save_transcript(profile: str, data: dict) -> Path:
    """
    Save transcript data dict to data/tiktok_{profile}_{video_id}.json.
    Creates the data/ directory if it does not exist.
    Returns the Path of the written file.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    safe_profile = _sanitize(profile)
    video_id = data.get("video_id", "unknown")
    filename = f"tiktok_{safe_profile}_{video_id}.json"
    output_path = DATA_DIR / filename

    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path
