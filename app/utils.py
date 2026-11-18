"""Small shared helpers."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def safe_filename(name: str) -> str:
    """Strip directories and characters that are invalid on Windows."""
    name = Path(name or "document").name
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = "document"
    stem, suffix = Path(name).stem, Path(name).suffix
    if len(stem) > 100:
        stem = stem[:100]
    return f"{stem}{suffix.lower()}"