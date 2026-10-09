import time

from cricket_pipeline import throttle


def test_a_cooldown_pauses_everyone_and_grows_each_time(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    assert throttle.seconds_left() == 0
    assert throttle.start_cooldown(0) == 5 and 290 < throttle.seconds_left() <= 300
    assert throttle.start_cooldown(1) == 15 and 890 < throttle.seconds_left() <= 900
    assert throttle.start_cooldown(2) == 30
    assert throttle.start_cooldown(3) is None           # out of pauses, so the scraper gives up


def test_a_shorter_cooldown_never_cuts_a_longer_one_short(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    throttle.start_cooldown(2)
    throttle.start_cooldown(0)
    assert throttle.seconds_left() > 1700


def test_wait_out_returns_at_once_when_there_is_no_cooldown(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    started = time.time()
    throttle.wait_out(lambda text: None)
    assert time.time() - started < 1
