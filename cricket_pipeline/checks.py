"""Integrity checks on the built files in data/output.

    python -m cricket_pipeline check

Each check says what it found. A problem means a published file would be wrong, so the run exits with an error.
A note is something to know that is not an error. The checks read only the built files, so they also work on a
fresh clone that has built the Cricsheet part alone: files that are not there are skipped.
"""
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

KEY = ["match_id", "innings", "delivery_number"]
BALL_COLUMNS = [
    "match_id", "innings", "delivery_number", "scorecard_ball", "over", "ball_in_over", "wides", "noballs", "is_legal_delivery", "striker", "striker_id", "bowler_id",
    "striker balls faced",
]


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    def record(self, name: str, problem: str | None) -> None:
        (self.problems if problem else self.passed).append(problem or name)


def duplicate_keys(frame: pd.DataFrame, key: list[str], name: str) -> str | None:
    count = int(frame.duplicated(key).sum())
    return f"{name} has {count:,} rows whose key {key} is not unique" if count else None


def delivery_numbers(ball: pd.DataFrame) -> str | None:
    """Every innings numbers its deliveries 1, 2, 3 and so on, with none missing."""
    d = ball.groupby(["match_id", "innings"]).delivery_number.agg(["min", "max", "size"])
    bad = d[(d["min"] != 1) | (d["max"] != d["size"])]
    return f"{len(bad):,} innings do not number their deliveries 1 to n with no gaps" if len(bad) else None


def over_and_position(ball: pd.DataFrame) -> str | None:
    """over and ball_in_over tell every delivery of an innings apart. The position counts 1, 2, 3 inside an over and
    starts again at 1 in the next, and the over agrees with scorecard_ball, which Cricsheet writes separately."""
    duplicates = int(ball.duplicated(["match_id", "innings", "over", "ball_in_over"]).sum())
    if duplicates:
        return f"{duplicates:,} deliveries share an over and a position in the over"
    ordered = ball.sort_values(KEY)
    same_innings = (ordered.match_id == ordered.match_id.shift()) & (ordered.innings == ordered.innings.shift())
    same_over = same_innings & (ordered.over == ordered.over.shift())
    expected = np.where(same_over, ordered.ball_in_over.shift() + 1, 1)
    if (ordered.ball_in_over.to_numpy() != expected).any():
        return "ball_in_over does not count 1, 2, 3 inside an over and start again at 1 in the next"
    if (same_innings & (ordered.over < ordered.over.shift())).any():
        return "over goes backwards inside an innings"
    if (np.floor(ordered.scorecard_ball.astype(float) + 1e-9) != ordered.over.astype(float)).any():
        return "scorecard_ball does not start with the over on some rows"
    return None


def legal_deliveries(ball: pd.DataFrame) -> str | None:
    """is_legal_delivery is False exactly for wides and no balls, and legal deliveries have their own scorecard_ball."""
    illegal = (pd.to_numeric(ball.wides, errors="coerce").fillna(0) > 0) | (pd.to_numeric(ball.noballs, errors="coerce").fillna(0) > 0)
    wrong = int((ball.is_legal_delivery.astype(bool) == illegal).sum())
    if wrong:
        return f"is_legal_delivery disagrees with wides and noballs on {wrong:,} rows"
    shared = int(ball[ball.is_legal_delivery.astype(bool)].duplicated(["match_id", "innings", "scorecard_ball"]).sum())
    return f"{shared:,} legal deliveries share a scorecard_ball with another legal delivery" if shared else None


def balls_faced(ball: pd.DataFrame) -> str | None:
    """A striker's balls faced is the number of rows that are not wides, counted in the innings up to that row."""
    ordered = ball.sort_values(KEY)
    legal = (pd.to_numeric(ordered.wides, errors="coerce").fillna(0) == 0).astype(int)
    expected = legal.groupby([ordered.match_id, ordered.innings, ordered.striker], observed=True, dropna=False).cumsum()
    wrong = int((expected != ordered["striker balls faced"]).sum())
    return f"striker balls faced is not the count of non-wide rows on {wrong:,} rows" if wrong else None


def missing_references(child: pd.DataFrame, parent: pd.DataFrame, columns: list[str], what: str) -> str | None:
    child_keys = pd.MultiIndex.from_frame(child[columns].drop_duplicates())
    parent_keys = pd.MultiIndex.from_frame(parent[columns].drop_duplicates())
    count = int((~child_keys.isin(parent_keys)).sum())
    return f"{count:,} {what} have no match in the parent file" if count else None


def unknown_ids(ball: pd.DataFrame, players: pd.DataFrame) -> str | None:
    known = set(players.player_id.dropna())
    bad = int((~ball.striker_id.dropna().isin(known)).sum() + (~ball.bowler_id.dropna().isin(known)).sum())
    return f"{bad:,} striker or bowler ids are not in players.csv" if bad else None


def match_sets(ball: pd.DataFrame, matches: pd.DataFrame) -> str | None:
    only_ball, only_matches = set(ball.match_id) - set(matches.match_id), set(matches.match_id) - set(ball.match_id)
    if only_ball or only_matches:
        return f"matches differ between the ball file and matches.csv ({len(only_ball)} only in the ball file, {len(only_matches)} only in matches.csv)"
    return None


def coverage_rows(ball: pd.DataFrame, coverage: pd.DataFrame) -> str | None:
    rows = ball.groupby("match_id").size()
    given = coverage.set_index("match_id").rows
    if len(rows) != len(given) or not (rows.sort_index() == given.sort_index()).all():
        return "the row counts in coverage_report.csv differ from the ball file"
    return None


PAIRS = [("line", "ball_line"), ("length", "ball_length"), ("shot", "shot_played"), ("direction", "shot_direction")]


def predictions_clear_of_tracking(predictions: pd.DataFrame, tracking: pd.DataFrame) -> str | None:
    """A prediction exists only where Cricinfo has no value for that ball and field."""
    joined = predictions.merge(tracking, on=KEY, how="inner")
    clashes = sum(int((joined[p].notna() & joined[t].notna()).sum()) for p, t in PAIRS)
    return f"{clashes:,} predictions sit on a ball and field that Cricinfo already has" if clashes else None


def run_checks(out: Path) -> Report:
    report = Report()
    ball_path = out / "ball_by_ball_data.csv"
    if not ball_path.exists():
        report.record("", "ball_by_ball_data.csv is missing")
        return report
    available = pd.read_csv(ball_path, nrows=0).columns
    ball = pd.read_csv(ball_path, usecols=[c for c in BALL_COLUMNS if c in available],
                       dtype={"striker": "category", "striker_id": "category", "bowler_id": "category"})
    report.record("ball file: key is unique", duplicate_keys(ball, KEY, "the ball file"))
    report.record("ball file: deliveries are numbered 1 to n in every innings", delivery_numbers(ball))
    if {"over", "ball_in_over"} <= set(ball.columns):
        report.record("ball file: over and ball_in_over identify every delivery and agree with ball", over_and_position(ball))
    if {"wides", "noballs", "is_legal_delivery", "scorecard_ball"} <= set(ball.columns):
        report.record("ball file: is_legal_delivery matches wides and noballs, and legal deliveries have a unique scorecard_ball", legal_deliveries(ball))
    if {"wides", "striker", "striker balls faced"} <= set(ball.columns):
        report.record("ball file: balls faced is the count of non-wide rows in the innings", balls_faced(ball))
    missing_ids = int(ball.striker_id.isna().sum()) if "striker_id" in ball else 0
    if missing_ids:
        report.notes.append(f"{missing_ids:,} rows have no striker_id and {int(ball.bowler_id.isna().sum()):,} have no bowler_id, because the player is not in Cricsheet's register")

    files = {name: out / name for name in ("players.csv", "matches.csv", "coverage_report.csv", "cricinfo_tracking.csv", "cricinfo_text_predictions.csv")}
    if files["players.csv"].exists():
        players = pd.read_csv(files["players.csv"], usecols=["player_id"])
        report.record("players.csv: player_id is unique", duplicate_keys(players, ["player_id"], "players.csv"))
        report.record("every striker and bowler id is in players.csv", unknown_ids(ball, players))
    if files["matches.csv"].exists():
        matches = pd.read_csv(files["matches.csv"], usecols=["match_id"])
        report.record("matches.csv: match_id is unique", duplicate_keys(matches, ["match_id"], "matches.csv"))
        report.record("the same matches are in the ball file and matches.csv", match_sets(ball, matches))
    if files["coverage_report.csv"].exists():
        coverage = pd.read_csv(files["coverage_report.csv"], usecols=["match_id", "rows"])
        report.record("coverage_report.csv rows equal the ball file's rows per match", coverage_rows(ball, coverage))
    tracking = None
    if files["cricinfo_tracking.csv"].exists():
        tracking = pd.read_csv(files["cricinfo_tracking.csv"], usecols=KEY + [t for _, t in PAIRS], low_memory=False)
        report.record("tracking file: key is unique", duplicate_keys(tracking, KEY, "cricinfo_tracking.csv"))
        report.record("every tracking row is a delivery in the ball file", missing_references(tracking, ball, KEY, "tracking rows"))
    if files["cricinfo_text_predictions.csv"].exists():
        predictions = pd.read_csv(files["cricinfo_text_predictions.csv"], usecols=KEY + [p for p, _ in PAIRS])
        report.record("predictions file: key is unique", duplicate_keys(predictions, KEY, "cricinfo_text_predictions.csv"))
        report.record("every prediction is a delivery in the ball file", missing_references(predictions, ball, KEY, "prediction rows"))
        if tracking is not None:
            report.record("no prediction sits on a ball and field Cricinfo already has", predictions_clear_of_tracking(predictions, tracking))
    return report


def run(out: Path | None = None) -> int:
    from cricket_pipeline.config import data_dir

    report = run_checks(out or data_dir() / "output")
    for line in report.passed:
        print(f"ok       {line}")
    for line in report.notes:
        print(f"note     {line}")
    for line in report.problems:
        print(f"PROBLEM  {line}")
    print(f"{len(report.passed)} checks passed, {len(report.problems)} problems")
    return 1 if report.problems else 0
