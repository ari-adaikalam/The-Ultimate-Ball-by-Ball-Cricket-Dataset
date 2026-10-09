"""Fetch Cricinfo player profiles through a Chrome the user started with a debugging port.

Cricinfo turns away scripted browsers and plain HTTP clients. A normal Chrome, started
by hand, is let through, so this script attaches to it and fetches each profile
from inside the page. Run Chrome first, then open any Cricinfo page in it by hand
and let it load. A page the script opened itself was blocked in testing, so the
script will not navigate for you:

    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port=9222 --user-data-dir="$HOME/.cricket-chrome"
"""
import json
import os
import random
import time
from collections import deque
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright
from tqdm import tqdm

from cricket_pipeline import throttle
from cricket_pipeline.players import players_dir

CDP_URL = os.environ.get("CRICKET_CHROME_URL", "http://127.0.0.1:9222")
PAUSE_SECONDS = (0.7, 1.8)   # a random pause in this range, so the requests are not evenly spaced
GIVE_UP_AFTER_BLOCKS = 5

# Runs inside the page. The timeout stops one stuck request from hanging the whole run.
FETCH_PROFILE = """
async (id) => {
  const row = {cricinfo_id: id};
  try {
    const r = await fetch(`/cricketers/x-${id}`, {redirect: 'follow', signal: AbortSignal.timeout(20000)});
    row.status = r.status;
    row.url = r.url.replace(location.origin, '');
    const html = await r.text();
    const m = html.match(/<script id="__NEXT_DATA__"[^>]*>(.*?)<\\/script>/s);
    if (!m) {
      // A bot-check page comes back as a normal 200, so keep a trace of what it was
      row.error = 'no __NEXT_DATA__';
      row.html_length = html.length;
      row.page_title = ((html.match(/<title>(.*?)<\\/title>/s) || [])[1] || '').slice(0, 80);
      return row;
    }
    const d = JSON.parse(m[1]).props.appPageProps.data;
    const p = d.player || {};
    row.full_name = p.fullName || null;
    row.name = p.longName || null;
    row.country = (p.country && p.country.name) || null;
    row.batting_style = p.longBattingStyles || null;
    row.bowling_style = p.longBowlingStyles || null;
    row.playing_roles = p.playingRoles || null;
    row.image_url = p.imageUrl || null;
    row.gender = p.gender || null;
    row.career_span = p.intlCareerSpan || null;
    row.fielding_styles = p.fieldingStyles || [];
    row.dob = p.dateOfBirth || null;
    row.teams = ((d.content || {}).teams || []).map(t => t.team && t.team.name).filter(Boolean);
  } catch (e) {
    row.error = String(e).slice(0, 80);
  }
  return row;
}
"""


NEEDS_A_PERSON = 3


def find_loaded_tab(browser, wait_seconds: int = 45):
    """Wait for a Cricinfo tab that Chrome opened and finished loading.

    The launcher gives Chrome the page address at startup. A page this script
    navigated to itself was blocked in testing, so it never navigates.
    """
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        for context in browser.contexts:
            for tab in context.pages:
                if "cricinfo.com" not in tab.url:
                    continue
                try:
                    tab.wait_for_function("() => document.getElementById('__NEXT_DATA__') !== null", polling=500, timeout=15000)
                    return tab
                except Exception:
                    pass  # still loading, or a bot-check page. Keep waiting.
        time.sleep(1)
    return None


def profiles_path() -> Path:
    path = players_dir() / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path / "profiles.jsonl"


def done_ids(path: Path) -> set[int]:
    """Ids that need no further fetching. A 404 is final, a block, an error or an out of date row is retried."""
    if not path.exists():
        return set()
    done = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue        # a half written line from a stop, the profile is fetched again
            # A profile saved before gender, career span and styles were captured has no
            # fielding_styles key, so it is fetched again to pick them up
            current = row.get("status") == 404 or "fielding_styles" in row
            if row.get("status") in (200, 404) and not row.get("error") and current:
                done.add(int(row["cricinfo_id"]))
    return done


def run(limit: int | None = None) -> int:
    ids = pd.read_csv(players_dir() / "player_ids.csv", dtype=str)["cricinfo_id"].dropna().astype(int)
    path = profiles_path()
    already_done = done_ids(path)
    todo = [i for i in ids if i not in already_done]
    remaining = len(todo)
    todo = todo[:limit] if limit else todo
    print(f"{len(todo)} profiles to fetch this run ({remaining} still to do, {len(already_done)} done)")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as error:
            print(f"Could not reach Chrome on {CDP_URL}. Start it with the command in this file's docstring.\n{error}")
            return 1
        page = find_loaded_tab(browser)
        if page is None:
            print("No loaded Cricinfo tab found in that Chrome.")
            return NEEDS_A_PERSON
        blocked_in_a_row = 0
        cooldowns_in_a_row = 0
        not_found = 0
        # The bar counts the whole job, so a resumed run starts from where the last one stopped
        progress = tqdm(total=len(ids), initial=len(already_done), unit="profile", dynamic_ncols=True)
        try:
            with open(path, "a", encoding="utf-8") as out:
                queue = deque(todo)
                recent = deque(maxlen=GIVE_UP_AFTER_BLOCKS)
                while queue:
                    throttle.wait_out(progress.write)
                    cricinfo_id = queue.popleft()
                    recent.append(cricinfo_id)
                    row = page.evaluate(FETCH_PROFILE, cricinfo_id)
                    out.write(json.dumps(row) + "\n")
                    out.flush()
                    not_found += row.get("status") == 404
                    blocked = row.get("status") == 403 or row.get("error") == "no __NEXT_DATA__"
                    blocked_in_a_row = blocked_in_a_row + 1 if blocked else 0
                    progress.update(1)
                    progress.set_postfix(not_found=not_found, blocked=blocked_in_a_row)
                    cooldowns_in_a_row = 0 if not blocked else cooldowns_in_a_row
                    if blocked_in_a_row >= GIVE_UP_AFTER_BLOCKS:
                        minutes = throttle.start_cooldown(cooldowns_in_a_row)
                        if minutes is None:
                            progress.close()
                            print("Still blocked after every cool-down, stopping. Reload the Cricinfo tab by hand, browse a little, and run again.")
                            return 2
                        progress.write(f"{GIVE_UP_AFTER_BLOCKS} blocked responses in a row. Pausing all scrapers for {minutes} minutes.")
                        progress.update(-len(recent))
                        queue.extendleft(reversed(recent))      # the blocked profiles are fetched again after the pause
                        recent.clear()
                        blocked_in_a_row = 0
                        cooldowns_in_a_row += 1
                    time.sleep(random.uniform(*PAUSE_SECONDS))
        except KeyboardInterrupt:
            # Every row is already on disk, so stopping loses nothing
            progress.close()
            print("\nStopped. Run the same command again to carry on from here.")
            return 130
        progress.close()
    return 0
