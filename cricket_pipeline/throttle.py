"""One shared cool-down for every scraper running at the same time.

Cricinfo sees both Chromes as one visitor. When either scraper is blocked, both stop asking for a
while, and the pause grows each time it happens in a row. A scraper that is still blocked after
the last pause gives up, so a person can look.
"""
import time
from pathlib import Path

from cricket_pipeline.config import data_dir

COOLDOWN_MINUTES = (5, 15, 30)


def _file() -> Path:
    return data_dir() / "cooldown_until"


def seconds_left() -> float:
    try:
        return max(0.0, float(_file().read_text()) - time.time())
    except (OSError, ValueError):
        return 0.0


def start_cooldown(step: int, now: float | None = None) -> int | None:
    """Pause every scraper. step counts the blocks in a row, from 0. Returns the minutes, or None when out of pauses."""
    if step >= len(COOLDOWN_MINUTES):
        return None
    minutes = COOLDOWN_MINUTES[step]
    until = (now or time.time()) + minutes * 60
    # Keep a longer pause another scraper already started
    current = 0.0
    if _file().exists():
        try:
            current = float(_file().read_text())
        except ValueError:
            pass
    if until > current:
        _file().write_text(str(until))
    return minutes


def wait_out(announce=print) -> None:
    """Sleep until the shared cool-down is over. Checks often, so a stop with Ctrl+C is quick."""
    told = False
    while (left := seconds_left()) > 0:
        if not told:
            announce(f"Cooling down for {left / 60:.0f} more minutes, Cricinfo was blocking requests.")
            told = True
        time.sleep(min(5, left))
