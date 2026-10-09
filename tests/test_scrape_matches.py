from cricket_pipeline.scrape_matches import innings_is_complete, missing_overs


def ball(over, over_number):
    return {"over": over, "over_number": over_number}


def full_innings(overs=3):
    return [ball(o - 1 + i / 10, o) for o in range(1, overs + 1) for i in range(1, 7)]


def test_complete_innings_has_every_over_and_the_first_ball():
    assert innings_is_complete(full_innings()) is True
    assert missing_overs(full_innings()) == []


def test_lost_opening_overs_are_reported():
    balls = [b for b in full_innings(5) if b["over_number"] > 2]
    assert missing_overs(balls) == [1, 2]
    assert innings_is_complete(balls) is False


def test_a_gap_in_the_middle_is_caught():
    balls = [b for b in full_innings(5) if b["over_number"] != 3]
    assert missing_overs(balls) == [3]
    assert innings_is_complete(balls) is False


def test_empty_innings_is_never_complete():
    assert innings_is_complete([]) is False
    assert missing_overs([]) == [1]


def test_innings_that_ends_early_is_still_complete_when_nothing_is_missing():
    # A chase can end in over 17, which is fine as long as overs 1 to 17 are all there
    assert innings_is_complete(full_innings(17)) is True


class FakeTab:
    def __init__(self, url="https://www.espncricinfo.com/x", closed=False):
        self.url, self._closed = url, closed

    def is_closed(self):
        return self._closed


class FakeContext:
    def __init__(self, pages):
        self.pages = pages

    def new_page(self):
        tab = FakeTab(url="about:blank")
        tab.goto = lambda *a, **k: setattr(tab, "url", "https://www.espncricinfo.com/")
        self.pages.append(tab)
        return tab


class FakeBrowser:
    def __init__(self, pages):
        self.contexts = [FakeContext(pages)]


def test_a_crash_is_told_apart_from_other_failures():
    from cricket_pipeline.scrape_matches import is_crash

    class TargetClosedError(Exception):
        pass

    assert is_crash(TargetClosedError("x")) and is_crash(Exception("Page.goto: Page crashed"))
    assert not is_crash(TimeoutError("Page.goto: Timeout 45000ms exceeded"))


def test_recovery_moves_to_another_cricinfo_tab_and_never_the_dead_one():
    from cricket_pipeline.scrape_matches import recover_tab

    dead, other = FakeTab(), FakeTab()
    assert recover_tab(FakeBrowser([dead, other]), dead) is other


def test_recovery_opens_a_new_tab_when_none_is_left():
    from cricket_pipeline.scrape_matches import recover_tab

    dead = FakeTab()
    browser = FakeBrowser([dead, FakeTab(closed=True)])
    tab = recover_tab(browser, dead)
    assert tab is not dead and "cricinfo.com" in tab.url


def test_a_closed_browser_counts_as_a_crash_too():
    from cricket_pipeline.scrape_matches import is_crash

    assert is_crash(Exception("Connection closed while reading from the driver"))
    assert is_crash(Exception("Target page, context or browser has been closed"))
    assert not is_crash(ValueError("innings menu not found"))


def test_recycling_visits_a_blank_page_and_never_raises():
    from cricket_pipeline.scrape_matches import recycle_tab

    visited = []

    class Tab:
        def goto(self, url, timeout=0): visited.append(url)
        def wait_for_timeout(self, ms): pass

    recycle_tab(Tab())
    assert visited == ["about:blank"]

    class Broken:
        def goto(self, *a, **k): raise RuntimeError("tab gone")

    recycle_tab(Broken())           # a failed recycle is ignored


def test_a_problem_with_one_match_is_not_a_block():
    from cricket_pipeline.scrape_matches import MatchPageProblem, failure_kind

    assert failure_kind(MatchPageProblem("innings menu not found"), blocked=False) == "match"
    assert failure_kind(MatchPageProblem("x"), blocked=True) == "match"              # the page problem is the match's own
    assert failure_kind(TimeoutError("page load"), blocked=False) == "match"          # a slow page with no bot check showing
    assert failure_kind(TimeoutError("page load"), blocked=True) == "blocked"         # the bot protection page is on screen


def test_the_block_check_reads_the_page_title_and_never_raises():
    from cricket_pipeline.scrape_matches import looks_blocked

    class Page:
        def __init__(self, title): self._t = title
        def title(self):
            if self._t is None: raise RuntimeError("gone")
            return self._t

    assert looks_blocked(Page("Access Denied")) and looks_blocked(Page("Pardon Our Interruption"))
    assert not looks_blocked(Page("Ball by Ball Commentary")) and not looks_blocked(Page(None))


class LoadingPage:
    """A fake page that returns scripted results from the loader and counts how often it was reloaded."""

    def __init__(self, loads, current="A"):
        from cricket_pipeline import scrape_matches as m
        self.m, self.loads, self.current, self.gotos, self.loader_calls = m, list(loads), current, 0, 0

    def evaluate(self, script, arg=None):
        if script == self.m.LOAD_ALL_JS:
            self.loader_calls += 1
            return self.loads.pop(0) if len(self.loads) > 1 else self.loads[0]
        if script == self.m.LIST_INNINGS_JS:
            return {"current": self.current, "labels": ["A", "B"]}
        return True                                            # the innings switch

    def goto(self, *a, **k): self.gotos += 1
    def wait_for_function(self, *a, **k): pass
    def wait_for_timeout(self, ms): pass


COMPLETE = [{"over": 0.1, "over_number": 1}, {"over": 1.1, "over_number": 2}]
SHORT = [{"over": 1.1, "over_number": 2}]                      # the first over never loaded


def test_a_complete_innings_is_loaded_once_with_no_retry():
    from cricket_pipeline.scrape_matches import load_innings

    page = LoadingPage([COMPLETE])
    assert load_innings(page, "https://x/ball-by-ball-commentary", "A", 300) == COMPLETE
    assert page.loader_calls == 1 and page.gotos == 0


def test_a_stalled_innings_is_fixed_by_reloading_the_page():
    from cricket_pipeline.scrape_matches import load_innings

    page = LoadingPage([SHORT, SHORT, COMPLETE], current="B")   # stalls twice on the page, then a fresh load works
    assert load_innings(page, "https://x/ball-by-ball-commentary", "A", 300) == COMPLETE
    assert page.gotos == 1


def test_an_innings_that_never_completes_gives_up_after_the_reloads_and_keeps_the_best_capture():
    from cricket_pipeline.scrape_matches import RELOADS_FOR_AN_INCOMPLETE_INNINGS, load_innings

    bigger = [*SHORT, {"over": 2.1, "over_number": 3}]            # still missing the first over, but with more balls
    page = LoadingPage([SHORT, bigger, SHORT, SHORT])
    assert load_innings(page, "https://x/ball-by-ball-commentary", "A", 300) == bigger
    assert page.gotos == RELOADS_FOR_AN_INCOMPLETE_INNINGS


def test_the_cap_is_300_seconds_for_long_innings():
    from cricket_pipeline.scrape_matches import SECONDS_PER_INNINGS

    assert SECONDS_PER_INNINGS == 300
