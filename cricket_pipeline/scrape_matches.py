"""Capture a match's ball-by-ball commentary from a Chrome that Cricinfo lets through.

Attaches to the Chrome started for the player scrape (debug port 9222).
For each match it opens the commentary page, then for each innings in the team menu
it loads every over and reads the ball records from the page's own state. The loading
method comes from testing on real pages:

- Hide the ads first, with the notebook's rule.
- Jump to the last loaded row, never to the bottom of the page. The ads sit below
  the commentary and swallow a jump to the bottom, and steps larger than a few
  hundred pixels skip past the point that triggers the next batch.
- Stop when over 1 (shown as 0.x) is in.
"""
import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from cricket_pipeline import throttle
from cricket_pipeline.usefulness import from_ball, is_useful
from cricket_pipeline.capture_queue import belongs_to, load_attempts, load_raw, load_survey, build_queue, is_finished, remaining, save_attempts, save_raw

CDP_URL = os.environ.get("CRICKET_CHROME_URL", "http://127.0.0.1:9222")   # a second Chrome can use another port
ENGINE_URL = "https://www.espncricinfo.com/matches/engine/match/{match_id}.html"
PAUSE_SECONDS = 2.0
GIVE_UP_AFTER_FAILURES = 3
IN_PAGE_RETRIES = 1                    # a second pass on the same page, which is cheap
RELOADS_FOR_AN_INCOMPLETE_INNINGS = 2  # then a fresh load of the page, which fixed a stalled innings in testing
SECONDS_PER_INNINGS = 300              # the loader stops sooner when nothing new arrives, so a long cap only matters for long innings
CRASHES_BEFORE_STOPPING = 3
SYSTEMIC_AFTER_MATCH_PROBLEMS = 6   # this many match-only failures in a row look like a bigger problem, such as the network
TAB_KEEPS_CRASHING = 4
CHROME_GONE = 5
RECYCLE_EVERY = 100      # matches between a visit to a blank page, which lets Chrome free the tab's memory
LOOK_SECONDS = 12   # hard cap on one look
LOOK_BATCHES = 2    # a look loads this many batches in each innings, then judges
LOOK_STALLS = 2     # and gives up after this many scrolls that bring nothing new

# Finds each ball record held in the rendered commentary rows
_COLLECT_JS = """
() => {
  const seen = new Map(); let lastEl = null, lastBottom = -1;
  for (const el of document.querySelectorAll('*')) {
    if (el.children.length !== 0) continue;
    const fk = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
    if (!fk) continue;
    let node = el[fk], depth = 0;
    while (node && depth < 16) {
      const c = node.memoizedProps && node.memoizedProps.ballComment;
      if (c && c.id) {
        if (!seen.has(c.id)) seen.set(c.id, c);
        const b = el.getBoundingClientRect().bottom + window.scrollY;
        if (b > lastBottom) { lastBottom = b; lastEl = el; }
        break;
      }
      node = node.return; depth++;
    }
  }
  return {seen, lastEl};
}
"""

# The innings menu only exists in the page while it is open, so both helpers open it first
_FIND_BUTTON_JS = """
  // The innings button sits between the page tabs and the first ball. A match with a Super Over
  // has no "Full commentary" button, so the button is found by position, not by its neighbours.
  let firstTop = null;
  for (const el of document.querySelectorAll('*')) {
    if (el.children.length !== 0) continue;
    const fk = Object.keys(el).find(k => k.startsWith('__reactFiber$'));
    if (!fk) continue;
    let node = el[fk], depth = 0, found = false;
    while (node && depth < 16) { if (node.memoizedProps && node.memoizedProps.ballComment) { found = true; break; } node = node.return; depth++; }
    // A row hidden by the ad filter reports a top of 0 and would push the first ball above the innings button
    if (found && el.getBoundingClientRect().height > 0) { const t = el.getBoundingClientRect().top + window.scrollY; if (firstTop === null || t < firstTop) firstTop = t; }
  }
  const tab = [...document.querySelectorAll('a')].find(a => a.textContent.trim() === 'Commentary' && a.getBoundingClientRect().height > 0);
  const tabsBottom = tab ? tab.getBoundingClientRect().bottom + window.scrollY : 0;
  if (firstTop === null) return null;
  const sel = [...document.querySelectorAll('button')].find(b => {
    const r = b.getBoundingClientRect(); const top = r.top + window.scrollY; const t = b.textContent.trim();
    return r.height > 0 && t && t.length <= 24 && top > tabsBottom && top < firstTop && !/commentary|wicket|four|six|highlight|prev|next/i.test(t);
  });
  if (!sel) return null;
"""

LIST_INNINGS_JS = """
async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
""" + _FIND_BUTTON_JS + """
  const current = sel.textContent.trim();
  const menuItems = () => [...document.querySelectorAll('li.ds-w-full.ds-flex')];
  if (!menuItems().some(li => li.textContent.trim() === current)) { sel.click(); await sleep(800); }
  const labels = [...new Set([...document.querySelectorAll('li.ds-w-full.ds-flex')].map(li => li.textContent.trim()).filter(t => t && !/^\\d+$/.test(t)))];
  return {current, labels};
}
"""

SWITCH_INNINGS_JS = """
async (label) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
""" + _FIND_BUTTON_JS + """
  const find = () => [...document.querySelectorAll('li.ds-w-full.ds-flex')].filter(li => li.textContent.trim() === label);
  // Once opened, the items stay in the page. A second click on the button would close the menu.
  if (!find().length) { sel.click(); await sleep(800); }
  const items = find();
  if (!items.length) return false;
  (items[0].querySelector('.ds-cursor-pointer') || items[0]).click();
  return true;
}
"""

LOAD_ALL_JS = """
async ([maxSeconds, maxBatches, maxIdle]) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const collect = %s;
  const strip = items => (items || []).map(t => (t && (t.html || t.text)) || '').join(' ').replace(/<[^>]+>/g, '').replace(/\\s+/g, ' ').trim();
  const hideAds = () => document.querySelectorAll("[id*='ad'], [class*='ad']").forEach(el => el.style.display = 'none');
  window.scrollTo(0, 0); await sleep(300); hideAds();
  let {seen, lastEl} = collect(); let lastN = seen.size, idle = 0, batches = 0;
  const t0 = Date.now();
  // The next batch is normally triggered by the last row at the bottom edge. In some matches
  // the final batch only loads when the row is centred, so a stall tries the other alignments.
  const alignments = ['end', 'center', 'start'];
  while (Date.now() - t0 < maxSeconds * 1000) {
    // A re-render can replace the row last scrolled to, so the bottom row is read again every time
    const fresh = collect().lastEl; if (fresh) lastEl = fresh;
    if (idle >= 2) { window.scrollBy(0, -400); await sleep(150); }   // a small step back, like a hand on the wheel, when stuck
    if (lastEl) lastEl.scrollIntoView({block: alignments[idle %% 3]});
    let grew = false; const w0 = Date.now();
    const oldest = Math.min(...[...collect().seen.values()].map(c => c.oversActual));
    // The last batches, near over 1, were seen to load more slowly
    const patience = oldest <= 4 ? 4500 : 2500;
    while (Date.now() - w0 < patience) {
      await sleep(60); const r = collect();
      if (r.seen.size > lastN) { lastN = r.seen.size; lastEl = r.lastEl; grew = true; batches++; break; }
    }
    const cur = [...collect().seen.values()];
    if (cur.length && Math.min(...cur.map(c => c.oversActual)) < 1) break;
    if (maxBatches && batches >= maxBatches) break;   // a short look stops after a few batches
    if (grew) idle = 0; else { idle++; hideAds(); if (idle >= maxIdle) break; }
  }
  // Anything Cricinfo sends that is not saved above is kept here when it has a value, so a new field never needs a rescrape.
  // The over object is left out because Cricsheet already has everything in it.
  const used = new Set(['id','inningNumber','oversActual','oversUnique','overNumber','ballNumber','title','batsmanPlayerId','nonStrikerPlayerId','bowlerPlayerId','outPlayerId',
    'batsmanRuns','totalRuns','wides','noballs','byes','legbyes','penalties','isFour','isSix','isWicket','dismissalType','dismissalText','pitchLine','pitchLength','shotType',
    'shotControl','wagonX','wagonY','wagonZone','timestamp','totalInningRuns','totalInningWickets','predictions','events','over','commentTextItems','commentPreTextItems',
    'commentPostTextItems','_uid']);
  const hasValue = v => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0) && typeof v !== 'function';
  const extraFields = x => { const o = {}; for (const [k, v] of Object.entries(x)) { if (!used.has(k) && hasValue(v)) o[k] = v; } return Object.keys(o).length ? o : null; };
  // Players inside events are reduced to their ids so the saved file stays small
  const slimPlayer = p => p ? {id: p.id, objectId: p.objectId, name: p.name} : null;
  const slimEvent = e => { const o = {}; for (const [k, v] of Object.entries(e || {})) { o[k] = (v && typeof v === 'object') ? slimPlayer(v) : v; } return o; };
  return [...collect().seen.values()].map(x => ({
    id: x.id, innings: x.inningNumber, over: x.oversActual, over_unique: x.oversUnique, over_number: x.overNumber, ball_number: x.ballNumber, title: x.title,
    batter: x.batsmanPlayerId, non_striker: x.nonStrikerPlayerId, bowler: x.bowlerPlayerId, out_player: x.outPlayerId,
    runs: x.batsmanRuns, total_runs: x.totalRuns, wides: x.wides, noballs: x.noballs, byes: x.byes, legbyes: x.legbyes, penalties: x.penalties,
    four: x.isFour, six: x.isSix, wicket: x.isWicket, dismissal: x.dismissalType, dismissal_text: x.dismissalText ? x.dismissalText.short : null,
    line: x.pitchLine, length: x.pitchLength, shot: x.shotType, control: x.shotControl,
    wx: x.wagonX, wy: x.wagonY, wz: x.wagonZone, timestamp: x.timestamp,
    inning_runs: x.totalInningRuns, inning_wickets: x.totalInningWickets,
    win_probability: x.predictions ? x.predictions.winProbability : null, predicted_score: x.predictions ? x.predictions.score : null,
    events: (x.events || []).map(slimEvent),
    over_summary: x.over ? {is_super_over: x.over.isSuperOver, over_number: x.over.overNumber, over_runs: x.over.overRuns, over_wickets: x.over.overWickets,
      is_maiden: x.over.isMaiden, is_complete: x.over.isComplete, target: x.over.target, over_limit: x.over.overLimit, ball_limit: x.over.ballLimit} : null,
    text: strip(x.commentTextItems), pre_text: strip(x.commentPreTextItems), post_text: strip(x.commentPostTextItems),
    extra: extraFields(x)
  }));
}
""" % _COLLECT_JS.strip()

HAS_COMMENTS_JS = """
() => {
  try {
    const d = JSON.parse(document.getElementById('__NEXT_DATA__').textContent).props.appPageProps.data;
    return ((d.content && d.content.comments) || []).length > 0;
  } catch (e) { return true; }   // if the page data cannot be read, let the normal capture try and report
}
"""

# What the page's own data holds for each ball, for the usefulness check
PAGE_BALLS_JS = """
() => {
  try {
    const d = JSON.parse(document.getElementById('__NEXT_DATA__').textContent).props.appPageProps.data;
    return ((d.content && d.content.comments) || []).map(x => ({
      structured: !!(x.pitchLine || x.pitchLength || x.shotType || x.shotControl || (x.wagonZone > 0 && !(x.wagonX === 0 && x.wagonY === 0)) ||
        x.timestamp || (x.predictions && x.predictions.winProbability !== null && x.predictions.winProbability !== undefined) || (x.events && x.events.length)),
      text: ((x.commentTextItems || []).map(t => t.html || t.text || '').join(' ') + ' ' + (x.commentPreTextItems || []).map(t => t.html || t.text || '').join(' ')).replace(/<[^>]*>/g, ' ')
    }));
  } catch (e) { return null; }   // unreadable page data: capture normally and let the checks speak
}
"""

PLAYERS_JS = """
() => {
  const out = {};
  try {
    const d = JSON.parse(document.getElementById('__NEXT_DATA__').textContent).props.appPageProps.data;
    for (const inn of (d.content.innings || []))
      for (const row of [...(inn.inningBatsmen || []), ...(inn.inningBowlers || [])]) {
        const p = row.player;
        if (p && p.id) out[p.id] = {objectId: p.objectId, name: p.name, batting: p.battingStyles || null, bowling: p.bowlingStyles || null};
      }
  } catch (e) {}
  return out;
}
"""


# True once rows are on screen and, after an innings switch, none of them still belong to the previous innings
ROWS_READY_JS = """
(previous) => {
  const rows = [...(%s)().seen.values()];
  return rows.length > 0 && (previous === null || rows.every(c => c.inningNumber !== previous));
}
""" % _COLLECT_JS.strip()
SETTLE_MS = 300     # a short breath after the rows appear, so the last ones finish rendering
READY_TIMEOUT_MS = 4000


def wait_for_rows(page, previous_innings: int | None = None) -> None:
    """Wait until the commentary rows are on screen, instead of sleeping a fixed time.

    Gives up quietly after READY_TIMEOUT_MS, because a match with no rows must still go on to its own checks.
    """
    try:
        page.wait_for_function(ROWS_READY_JS, arg=previous_innings, polling=100, timeout=READY_TIMEOUT_MS)
    except Exception:
        pass
    page.wait_for_timeout(SETTLE_MS)


def innings_number(balls: list[dict]) -> int | None:
    return balls[0]["innings"] if balls else None


def missing_overs(balls: list[dict]) -> list[int]:
    """Over numbers that should be there but are not. Over 1 counts, so a lost opening shows up."""
    overs = {b["over_number"] for b in balls if b.get("over_number") is not None}
    if not overs:
        return [1]
    return [over for over in range(1, max(overs) + 1) if over not in overs]


def innings_is_complete(balls: list[dict]) -> bool:
    """Every over from 1 to the last is present, and the first ball (over 0.1) is in."""
    if not balls:
        return False
    return min(b["over"] for b in balls) < 1 and not missing_overs(balls)




def _worth_scrolling(page, order: list[str]) -> tuple[bool, str, int | None]:
    """Look before committing to a full capture: the page's own data first, then a short scroll in every innings.

    The page data holds only the last overs, so a match is dropped only when a short load from each innings
    also shows no tracking, timestamps, win probability, events or text that names a delivery.
    Returns the verdict, the innings left on screen and its number, so the full capture knows where it starts.
    """
    on_page = page.evaluate(PAGE_BALLS_JS)
    if on_page is None or is_useful(on_page):
        return True, order[0], None    # useful, or unreadable and so left to the normal capture
    shown = order[0]
    on_screen = None            # the innings number of the rows now on screen, once a load has read them
    for label in order:
        if label != shown:
            if not page.evaluate(SWITCH_INNINGS_JS, label):
                return True, shown, on_screen   # cannot look, so do not throw the match away
            shown = label
            wait_for_rows(page, on_screen)
        looked = page.evaluate(LOAD_ALL_JS, [LOOK_SECONDS, LOOK_BATCHES, LOOK_STALLS])
        on_screen = innings_number(looked) or on_screen
        if is_useful([from_ball(b) for b in looked]):
            return True, shown, on_screen
    return False, shown, on_screen


def open_commentary(page, commentary_url: str) -> None:
    page.goto(commentary_url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_function("() => document.getElementById('__NEXT_DATA__') !== null", polling=500, timeout=30000)
    wait_for_rows(page)


def load_innings(page, commentary_url: str, label: str, seconds: int) -> list[dict]:
    """Load one innings. If it stops early, try again on the page, then reload the page and try again.

    A stalled page rarely recovers by waiting, but a fresh page load did (13 seconds for an innings that had
    stalled for 113). The best capture of the attempts is kept.
    """
    balls = page.evaluate(LOAD_ALL_JS, [seconds, 0, 9])
    for _ in range(IN_PAGE_RETRIES):
        if innings_is_complete(balls):
            return balls
        page.wait_for_timeout(1500)
        balls = page.evaluate(LOAD_ALL_JS, [seconds, 0, 9])
    for _ in range(RELOADS_FOR_AN_INCOMPLETE_INNINGS):
        if innings_is_complete(balls):
            break
        open_commentary(page, commentary_url)
        menu = page.evaluate(LIST_INNINGS_JS)
        if menu and menu["current"] != label:
            if not page.evaluate(SWITCH_INNINGS_JS, label):
                break
            wait_for_rows(page)
        fresh = page.evaluate(LOAD_ALL_JS, [seconds, 0, 9])
        if len(fresh) >= len(balls):
            balls = fresh
    return balls


def capture_match(page, match_id: int, max_seconds_per_innings: int = SECONDS_PER_INNINGS, check_usefulness: bool = True) -> dict:
    """Open one match and read every innings. Raises if the page cannot be read.

    check_usefulness=False captures every innings in full even when the first look finds nothing. Only the
    empty match check test uses it, to see whether the look ever hides data."""
    started = time.time()
    page.goto(ENGINE_URL.format(match_id=match_id), wait_until="domcontentloaded", timeout=45000)
    if "/matches/engine/" in page.url:
        raise MatchPageProblem("the match link did not resolve to a page")
    commentary_url = page.url.rsplit("/", 1)[0] + "/ball-by-ball-commentary"
    page.goto(commentary_url, wait_until="domcontentloaded", timeout=45000)
    if (page.title() or "").lower().startswith("oops"):
        raise MatchPageProblem("Cricinfo says this page does not exist")
    page.wait_for_function("() => document.getElementById('__NEXT_DATA__') !== null", polling=500, timeout=30000)
    # Rows render a moment after the page data arrives
    wait_for_rows(page)
    if not page.evaluate(HAS_COMMENTS_JS):
        # Cricinfo has no commentary for this match. Recorded so that it is not tried again.
        return {"match_id": match_id, "url": commentary_url, "menu": [], "players": {}, "innings": [], "no_commentary": True,
                "seconds": round(time.time() - started, 1)}

    menu = page.evaluate(LIST_INNINGS_JS)
    if not menu:
        raise MatchPageProblem("innings menu not found")
    page.wait_for_timeout(300)
    # The innings on screen first, then the others. Switching away and back is avoided.
    order = [menu["current"]] + [label for label in menu["labels"] if label != menu["current"]]
    worth, shown, on_screen = _worth_scrolling(page, order) if check_usefulness else (True, order[0], None)
    if not worth:
        # Nothing to use in any innings after a real look. Recorded so that it is not scrolled or retried.
        return {"match_id": match_id, "url": commentary_url, "menu": order, "players": {}, "innings": [], "no_useful_data": True,
                "seconds": round(time.time() - started, 1)}
    innings = []
    for label in order:
        if label != shown:
            if not page.evaluate(SWITCH_INNINGS_JS, label):
                raise MatchPageProblem(f"could not select {label!r}")
            shown = label
            wait_for_rows(page, on_screen)
        balls = load_innings(page, commentary_url, label, max_seconds_per_innings)
        on_screen = innings_number(balls) or on_screen
        innings.append({"label": label, "balls": balls, "complete": innings_is_complete(balls), "missing_overs": missing_overs(balls)})
    return {
        "match_id": match_id,
        "url": commentary_url,
        "menu": order,
        "players": page.evaluate(PLAYERS_JS),
        "innings": innings,
        "seconds": round(time.time() - started, 1),
    }


def find_tab(browser):
    for context in browser.contexts:
        for tab in context.pages:
            if "cricinfo.com" in tab.url:
                return tab
    return None


class MatchPageProblem(RuntimeError):
    """This one match's page is unusable (no page, no innings menu). It says nothing about Cricinfo blocking the scraper."""


def looks_blocked(page) -> bool:
    """True when the page on screen is Cricinfo's bot protection, not an ordinary page."""
    try:
        title = (page.title() or "").lower()
    except Exception:
        return False
    return any(word in title for word in ("access denied", "pardon our interruption", "are you a robot", "blocked"))


def failure_kind(error: Exception, blocked: bool) -> str:
    """'match' for a problem with this match alone, 'blocked' when Cricinfo's protection is showing."""
    return "match" if isinstance(error, MatchPageProblem) or not blocked else "blocked"


class ChromeGone(Exception):
    """The whole Chrome went away, so no other tab can be tried."""


def is_crash(error: Exception) -> bool:
    """Chrome lost the tab or itself. This is not Cricinfo blocking and not a problem with the match."""
    text = str(error).lower()
    return type(error).__name__ == "TargetClosedError" or any(m in text for m in ("crashed", "connection closed", "browser has been closed", "disconnected"))


def recycle_tab(page) -> None:
    """Visit a blank page so Chrome drops the memory the last pages built up. Never fatal."""
    try:
        page.goto("about:blank", timeout=15000)
        page.wait_for_timeout(1500)
    except Exception:
        pass


def recover_tab(browser, dead):
    """A crashed tab cannot be used again. Use another Cricinfo tab in the same Chrome, or open a new one there."""
    for context in browser.contexts:
        for tab in context.pages:
            if tab is not dead and not tab.is_closed() and "cricinfo.com" in tab.url:
                return tab
    tab = browser.contexts[0].new_page()
    tab.goto("https://www.espncricinfo.com/", wait_until="domcontentloaded", timeout=45000)
    return tab


def run(match_ids: list[int], redo: bool = False) -> int:
    todo = [m for m in match_ids if redo or load_raw(m) is None]
    print(f"{len(todo)} matches to capture ({len(match_ids) - len(todo)} already saved)")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as error:
            print(f"Could not reach Chrome on {CDP_URL}: {error}")
            return 1
        page = find_tab(browser)
        if page is None:
            print("No Cricinfo tab is open in that Chrome. Open one by hand first.")
            return 3
        failures = 0
        for count, match_id in enumerate(todo, start=1):
            try:
                result = capture_match(page, match_id)
                save_raw(match_id, result)
                balls = sum(len(i["balls"]) for i in result["innings"])
                wagon = sum(1 for i in result["innings"] for b in i["balls"] if b["wz"])
                flag = "" if all(i["complete"] for i in result["innings"]) else "  INCOMPLETE: " + str([(i["label"], i["missing_overs"]) for i in result["innings"] if not i["complete"]])
                print(f"[{count}/{len(todo)}] {match_id}: {len(result['innings'])} innings, {balls} balls, {wagon} with wagon, {result['seconds']}s{flag}", flush=True)
                failures = 0
            except Exception as error:
                failures += 1
                print(f"[{count}/{len(todo)}] {match_id}: FAILED {type(error).__name__}: {str(error)[:100]}")
                if failures >= GIVE_UP_AFTER_FAILURES:
                    print(f"{GIVE_UP_AFTER_FAILURES} failures in a row, stopping.")
                    return 2
            time.sleep(PAUSE_SECONDS)
    return 0


def run_queue(limit: int | None = None, worker: int = 0, workers: int = 1) -> int:
    """Capture the queue in order, skipping what is done. Safe to stop with Ctrl+C and run again."""
    from tqdm import tqdm

    queue = build_queue(load_survey())
    todo = remaining(queue, worker, workers)
    total = sum(1 for m in queue.match_id if belongs_to(int(m), worker, workers))
    todo = todo[:limit] if limit else todo
    print(f"Worker {worker + 1} of {workers}: {total - len(remaining(queue, worker, workers)):,} of {total:,} matches finished, {len(todo):,} to capture this run (best bets first)")
    if not todo:
        return 0
    attempts = load_attempts()
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as error:
            print(f"Could not reach Chrome on {CDP_URL}: {error}")
            return 1
        page = find_tab(browser)
        if page is None:
            print("No Cricinfo tab is open in that Chrome. Open one by hand first.")
            return 3
        failures = incomplete = empty = cooldowns = crashes = since_recycle = match_problems = 0
        bar = tqdm(total=len(todo), unit="match", dynamic_ncols=True)
        try:
            for match_id in todo:
                throttle.wait_out(bar.write)
                try:
                    try:
                        result = capture_match(page, match_id)
                    except Exception as error:
                        if not is_crash(error):
                            raise
                        # A crashed tab is Chrome's fault, so nothing is counted against the match and nobody pauses
                        if not browser.is_connected():
                            raise ChromeGone()
                        bar.write(f"{match_id}: the tab crashed, moving to a fresh tab")
                        page = recover_tab(browser, page)
                        result = capture_match(page, match_id)
                    crashes = 0
                    cooldowns = 0
                    match_problems = 0
                    since_recycle += 1
                    if since_recycle >= RECYCLE_EVERY:
                        recycle_tab(page)
                        since_recycle = 0
                    save_raw(match_id, result)
                    attempts[match_id] = attempts.get(match_id, 0) + 1
                    save_attempts(attempts, worker)
                    empty += bool(result.get("no_commentary") or result.get("no_useful_data"))
                    incomplete += not is_finished(result, attempts[match_id]) or (bool(result.get("innings")) and not all(i["complete"] for i in result["innings"]))
                    failures = 0
                except ChromeGone:
                    bar.close()
                    print("Chrome closed. It needs to be started again.")
                    return CHROME_GONE
                except Exception as error:
                    if is_crash(error):
                        if not browser.is_connected():
                            bar.close()
                            print("Chrome closed. It needs to be started again.")
                            return CHROME_GONE
                        crashes += 1
                        bar.write(f"{match_id}: the tab crashed again ({crashes} in a row)")
                        if crashes >= CRASHES_BEFORE_STOPPING:
                            bar.close()
                            print("The tab keeps crashing. Close that Chrome window, then run again.")
                            return TAB_KEEPS_CRASHING
                        continue
                    attempts[match_id] = attempts.get(match_id, 0) + 1
                    save_attempts(attempts, worker)
                    kind = failure_kind(error, looks_blocked(page))
                    bar.write(f"{match_id}: FAILED ({kind}) {type(error).__name__}: {str(error)[:90]}")
                    if kind == "match":
                        # A hard match is not a block. Only a long unbroken run of them is treated as a systemic problem.
                        match_problems += 1
                        if match_problems < SYSTEMIC_AFTER_MATCH_PROBLEMS:
                            bar.update(1)
                            time.sleep(PAUSE_SECONDS)
                            continue
                        match_problems = 0
                    failures += 1
                    if failures >= GIVE_UP_AFTER_FAILURES:
                        # Failures in a row usually mea Cricinfo is blocking, so every scraper pauses
                        minutes = throttle.start_cooldown(cooldowns)
                        if minutes is None:
                            bar.close()
                            print(f"Still failing after every cool-down, stopping. Reload the Cricinfo tab by hand and run again.")
                            return 2
                        bar.write(f"{GIVE_UP_AFTER_FAILURES} failures in a row. Pausing all scrapers for {minutes} minutes.")
                        cooldowns += 1
                        failures = 0
                bar.update(1)
                bar.set_postfix(nothing_useful=empty, incomplete=incomplete)
                time.sleep(PAUSE_SECONDS)
        except KeyboardInterrupt:
            bar.close()
            print("\nStopped. Run the same command again to carry on from here.")
            return 130
        bar.close()
    return 0
