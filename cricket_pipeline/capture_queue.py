"""Which matches to capture, in what order, and what is already done.

The order puts the matches most likely to have Cricinfo data first, using the coverage survey, and the
ones with nothing last. Anything already captured is skipped, so the run can be stopped and started
whenever there is time. A match that stays incomplete after a few tries is set aside, not retried forever.
"""
import gzip
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from cricket_pipeline.config import SOURCES, data_dir, work_dir

MAX_ATTEMPTS = 3
# A match is left alone until its page is settled. An early capture comes back incomplete, and three failed attempts end the retries for good.
# Tests count from their first day, so 8 days covers five days of play plus the usual 3.
MIN_AGE_DAYS = {"tests": 8}
DEFAULT_MIN_AGE_DAYS = 3


def raw_dir() -> Path:
    path = data_dir() / "matches" / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_path(match_id: int) -> Path:
    return raw_dir() / f"{match_id}.json.gz"


def save_raw(match_id: int, result: dict) -> None:
    # Compressed, because a captured match shrinks to about a seventh of its size.
    # Written to a temporary name first, so a stop in the middle never leaves a half file behind.
    final = raw_path(match_id)
    temporary = final.with_name(final.name + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(result, handle)
    temporary.replace(final)


def load_raw(match_id: int) -> dict | None:
    """The saved capture of a match, or None. Reads the older uncompressed files too."""
    gz = raw_path(match_id)
    if gz.exists():
        with gzip.open(gz, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    plain = raw_dir() / f"{match_id}.json"
    if plain.exists():
        return json.loads(plain.read_text())
    return None


def is_finished(result: dict | None, attempts: int) -> bool:
    """Done when the capture is complete, there is no commentary to capture, or the tries ran out.

    A match that fails outright (a page that never loads) also stops being retried after
    MAX_ATTEMPTS, so one bad page can never hold up the rest of the queue.
    """
    if attempts >= MAX_ATTEMPTS:
        return True
    if result is None:
        return False
    if result.get("no_commentary") or result.get("no_useful_data"):
        return True
    complete = bool(result.get("innings")) and all(i.get("complete", True) for i in result["innings"])
    return complete or attempts >= MAX_ATTEMPTS


def attempts_path(worker: int = 0) -> Path:
    """Each worker writes only its own file, so two workers never overwrite each other's counts."""
    name = "attempts.json" if worker == 0 else f"attempts_w{worker}.json"
    return data_dir() / "matches" / name


def load_attempts() -> dict[int, int]:
    """Every worker's counts, merged. A match keeps the highest count anyone recorded."""
    merged: dict[int, int] = {}
    folder = data_dir() / "matches"
    for path in sorted(folder.glob("attempts*.json")) if folder.exists() else []:
        for key, value in json.loads(path.read_text()).items():
            merged[int(key)] = max(merged.get(int(key), 0), value)
    return merged


def save_attempts(attempts: dict[int, int], worker: int = 0) -> None:
    path = attempts_path(worker)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({str(k): v for k, v in attempts.items()}))
    temporary.replace(path)


def belongs_to(match_id: int, worker: int, workers: int) -> bool:
    """A fixed rule, so two workers never take the same match and the split never shifts as matches finish.

    Halving the id first spreads odd and even ids over every worker. Plain id % 4 gave two workers the even ids
    and two the odd ones, and there are more odd ids, so two workers finished early and left the rest idle."""
    return (match_id // 2) % workers == worker


def cell_value(survey: pd.DataFrame | None) -> dict[tuple, float]:
    """For each competition and year, the share of surveyed matches that had anything useful on Cricinfo."""
    if survey is None or survey.empty:
        return {}
    useful = (survey[["line", "shot", "wagon", "timestamp", "win_probability", "events", "text"]].fillna(0) > 0).any(axis=1)
    frame = survey.assign(useful=useful)
    return frame.groupby(["archive", "year"])["useful"].mean().to_dict()


def build_queue(survey: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every match in scope, best bets first. Newer matches come first among equals."""
    parts = []
    for source in SOURCES:
        matches = pd.read_csv(work_dir() / f"cricsheet_{source.archive}.csv", usecols=["match_id", "start_date"]).drop_duplicates("match_id")
        matches["archive"] = source.archive
        matches["year"] = matches["start_date"].str[:4].astype(int)
        parts.append(matches)
    queue = pd.concat(parts, ignore_index=True)
    values = cell_value(survey)
    archive_mean = pd.Series(values).groupby(level=0).mean().to_dict() if values else {}
    queue["value"] = [values.get((a, y), archive_mean.get(a, 0.5)) for a, y in zip(queue.archive, queue.year)]
    return queue.sort_values(["value", "year", "match_id"], ascending=[False, False, False]).reset_index(drop=True)


def load_survey() -> pd.DataFrame | None:
    results = data_dir() / "survey" / "results.jsonl"
    sample = data_dir() / "survey" / "sample.csv"
    if not results.exists() or not sample.exists():
        return None
    rows = [json.loads(line) for line in open(results, encoding="utf-8")]
    frame = pd.DataFrame([r for r in rows if r.get("status") == 200 and not r.get("error")])
    return frame.merge(pd.read_csv(sample), on="match_id") if not frame.empty else None


def has_incomplete_capture(result: dict | None) -> bool:
    return bool(result and result.get("innings") and not all(i.get("complete", True) for i in result["innings"]))


def too_recent(archive: str, start_date: str, today: date | None = None) -> bool:
    today = today or date.today()
    return start_date > (today - timedelta(days=MIN_AGE_DAYS.get(archive, DEFAULT_MIN_AGE_DAYS))).isoformat()


def remaining(queue: pd.DataFrame, worker: int = 0, workers: int = 1, today: date | None = None) -> list[int]:
    """What this worker still has to do, in this order: incomplete captures with attempts left (to see if the
    loader fixes now finish them), then matches never tried, then matches that failed with nothing saved.
    Matches too recent to be settled are left out."""
    attempts = load_attempts()
    incomplete, fresh, failed = [], [], []
    dated = {"archive", "start_date"} <= set(queue.columns)
    for row in queue.itertuples():
        m = int(row.match_id)
        if not belongs_to(m, worker, workers) or (dated and too_recent(row.archive, row.start_date, today)):
            continue
        result = load_raw(m)
        tried = attempts.get(m, 0)
        if is_finished(result, tried):
            continue
        (incomplete if has_incomplete_capture(result) else fresh if not tried else failed).append(m)
    return incomplete + fresh + failed
