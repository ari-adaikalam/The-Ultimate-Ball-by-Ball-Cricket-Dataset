import pandas as pd
import pytest

from cricket_pipeline import capture_queue as q
from cricket_pipeline.config import SOURCES


@pytest.fixture
def data_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    return tmp_path


def test_a_saved_capture_reads_back_the_same(data_folder):
    result = {"match_id": 5, "innings": [{"label": "A", "balls": [{"id": 1}], "complete": True}]}
    q.save_raw(5, result)
    assert q.load_raw(5) == result and q.raw_path(5).suffix == ".gz"
    assert q.load_raw(6) is None


def test_older_uncompressed_captures_are_still_readable(data_folder):
    (q.raw_dir() / "7.json").write_text('{"match_id": 7, "innings": []}')
    assert q.load_raw(7)["match_id"] == 7


def test_what_counts_as_finished():
    complete = {"innings": [{"complete": True}, {"complete": True}]}
    assert q.is_finished(complete, 1) is True
    assert q.is_finished({"innings": [], "no_commentary": True}, 1) is True            # nothing to capture, so do not retry
    broken = {"innings": [{"complete": True}, {"complete": False}]}
    assert q.is_finished(broken, 1) is False and q.is_finished(broken, q.MAX_ATTEMPTS) is True   # retried, then set aside
    assert q.is_finished(None, 0) is False
    assert q.is_finished(None, q.MAX_ATTEMPTS) is True           # a page that never loads is set aside, not retried forever


def test_best_bets_come_first_and_empty_ones_last(data_folder):
    for source in SOURCES:
        pd.DataFrame({"match_id": [1000 + len(source.archive), 2000 + len(source.archive)], "start_date": ["2024-05-01", "2010-05-01"]}).to_csv(q.work_dir() / f"cricsheet_{source.archive}.csv", index=False)
    survey = pd.DataFrame({
        "archive": ["ipl", "ipl", "t20s", "t20s"], "year": [2024, 2010, 2024, 2010], "line": [10, 0, 0, 0], "shot": [10, 5, 0, 0],
        "wagon": [10, 0, 0, 0], "timestamp": [10, 0, 0, 0], "win_probability": [0, 0, 0, 0], "events": [0, 0, 0, 0], "text": [10, 10, 0, 0],
    })
    queue = q.build_queue(survey)
    ranked = queue.set_index(["archive", "year"]).value
    assert ranked[("ipl", 2024)] == 1.0 and ranked[("ipl", 2010)] == 1.0 and ranked[("t20s", 2024)] == 0.0
    assert queue.iloc[0].archive == "ipl" and queue.iloc[0].year == 2024            # useful and recent first
    assert queue.iloc[-1].value == min(queue.value)                                 # the empty cells at the end


def test_remaining_skips_what_is_finished(data_folder):
    for source in SOURCES:
        pd.DataFrame({"match_id": [1 + SOURCES.index(source)], "start_date": ["2024-01-01"]}).to_csv(q.work_dir() / f"cricsheet_{source.archive}.csv", index=False)
    q.save_raw(1, {"match_id": 1, "innings": [{"complete": True}]})
    queue = q.build_queue(None)
    assert 1 not in q.remaining(queue) and 2 in q.remaining(queue)
    q.save_attempts({2: 1}); assert q.load_attempts() == {2: 1}


def test_a_match_with_nothing_useful_on_its_page_is_finished_and_not_retried():
    assert q.is_finished({"innings": [], "no_useful_data": True}, 1) is True


def test_a_stop_during_a_save_leaves_no_half_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    q.save_raw(7, {"match_id": 7, "innings": []})
    assert q.load_raw(7)["match_id"] == 7 and not list(q.raw_dir().glob("*.tmp"))


def test_a_half_written_profile_line_is_ignored_and_fetched_again(tmp_path):
    from cricket_pipeline.scrape_players import done_ids

    path = tmp_path / "profiles.jsonl"
    path.write_text('{"cricinfo_id": 1, "status": 200, "fielding_styles": []}\n{"cricinfo_id": 2, "sta')
    assert done_ids(path) == {1}


def test_two_workers_split_the_queue_without_overlap_or_gaps():
    ids = range(1000, 1200)
    first = [i for i in ids if q.belongs_to(i, 0, 2)]
    second = [i for i in ids if q.belongs_to(i, 1, 2)]
    assert set(first).isdisjoint(second) and sorted(first + second) == list(ids)
    assert all(q.belongs_to(i, 0, 1) for i in ids)          # a single worker takes everything


def test_odd_ids_alone_still_spread_over_four_workers():
    # With id % 4 the odd ids all landed on workers 2 and 4, which left the other two idle at the end
    odd = range(1001, 1401, 2)
    shares = [sum(1 for i in odd if q.belongs_to(i, k, 4)) for k in range(4)]
    assert shares == [50, 50, 50, 50]


def test_each_worker_writes_its_own_attempts_file_and_loading_merges_them(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    q.save_attempts({1: 1, 2: 2}, worker=0)
    q.save_attempts({2: 1, 3: 3}, worker=1)
    assert q.load_attempts() == {1: 1, 2: 2, 3: 3}           # the higher count wins, nobody's file is overwritten
    assert q.attempts_path(0).name == "attempts.json" and q.attempts_path(1).name == "attempts_w1.json"


def test_remaining_only_lists_the_workers_own_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    queue = pd.DataFrame({"match_id": [10, 11, 12, 13]})
    assert q.remaining(queue, worker=0, workers=2) == [12, 13]
    assert q.remaining(queue, worker=1, workers=2) == [10, 11]
    assert q.remaining(queue) == [10, 11, 12, 13]


def test_incomplete_captures_come_first_then_fresh_matches_then_failed_ones(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    q.save_attempts({10: 1, 12: 2, 14: 1})
    q.save_raw(12, {"match_id": 12, "innings": [{"complete": False, "balls": []}]})     # saved but incomplete, attempts left
    q.save_raw(14, {"match_id": 14, "innings": [{"complete": True, "balls": []}]})      # complete, so finished
    queue = pd.DataFrame({"match_id": [10, 11, 12, 13, 14]})
    assert q.remaining(queue) == [12, 11, 13, 10]      # incomplete 12, fresh 11 and 13, failed 10, and 14 is done


def test_an_incomplete_capture_that_used_all_its_attempts_is_not_retried_again(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    q.save_attempts({12: q.MAX_ATTEMPTS})
    q.save_raw(12, {"match_id": 12, "innings": [{"complete": False, "balls": []}]})
    assert q.remaining(pd.DataFrame({"match_id": [12]})) == []


def test_recent_matches_are_left_until_their_page_is_settled(tmp_path, monkeypatch):
    from datetime import date

    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    queue = pd.DataFrame({"match_id": [1, 2, 3, 4], "archive": ["ipl", "ipl", "tests", "tests"],
                          "start_date": ["2026-10-05", "2026-10-07", "2026-10-01", "2026-10-03"]})
    assert q.remaining(queue, today=date(2026, 10, 9)) == [1, 3]
