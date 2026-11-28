"""Small text and time helpers (moved over unchanged from job_radar.py)."""

import html
import re
from datetime import datetime


def words_re(words):
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)", re.I)


def html_lines(markup):
    """HTML -> text, one line per block, so a negation stays in its own sentence."""
    return html.unescape(re.sub(r"<[^>]+>", "\n", markup or ""))


def to_epoch(value):
    """Unix seconds from seconds, milliseconds or an ISO date (None if unknown)."""
    try:
        if value in (None, ""):
            return None
        if isinstance(value, str) and not value.isdigit():
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        value = float(value)
        return value / 1000 if value > 1e11 else value
    except (ValueError, TypeError):
        return None