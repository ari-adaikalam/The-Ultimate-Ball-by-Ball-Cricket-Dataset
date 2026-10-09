"""Sanity checks on the built dataset, read from data/output.

  win     Does win_probability behave like the batting side's chance of winning, in both innings?
  wagon   Do the wagon wheel values look right, and is the 2001 to 2013 data as good as the later data?

Run: .venv/bin/python -m analysis.dataset_checks win wagon
"""
import sys

import numpy as np
import pandas as pd

from cricket_pipeline.config import data_dir

KEY = ["match_id", "innings", "delivery_number"]
ERAS = [(0, 2013, "2001 to 2013"), (2014, 2019, "2014 to 2019"), (2020, 2100, "2020 on")]


def win() -> None:
    out = data_dir() / "output"
    balls = pd.read_csv(out / "ball_by_ball_data.csv", usecols=KEY + ["batting_team", "start_date"])
    tracking = pd.read_csv(out / "cricinfo_tracking.csv", usecols=KEY + ["win_probability"], low_memory=False)
    matches = pd.read_csv(out / "matches.csv", usecols=["match_id", "winner", "format"])
    d = balls.merge(tracking, on=KEY).dropna(subset=["win_probability"])
    d = d[d.innings.isin([1, 2])]
    last = d.sort_values(KEY).groupby(["match_id", "innings"]).tail(1).merge(matches, on="match_id")
    last = last[last.winner.notna()]
    last["batting_won"] = last.batting_team == last.winner
    print(f"matches with win probability and a winner: {last.match_id.nunique():,}")
    for innings in (1, 2):
        part = last[last.innings == innings]
        won, lost = part[part.batting_won].win_probability, part[~part.batting_won].win_probability
        print(f"innings {innings}: at the last tracked ball the batting side's win probability averages {won.mean():.0f} when it won and {lost.mean():.0f} when it lost "
              f"({len(won):,} and {len(lost):,} matches). Right side of 50 in {100 * (((part.win_probability > 50) == part.batting_won).mean()):.0f}% of matches")
    first = last[last.innings == 1].merge(d[d.innings == 1].groupby("match_id").size().rename("balls"), on="match_id")
    print(f"first innings: win probability at its end is above 50 for the side that batted first in {100 * (first.win_probability > 50).mean():.0f}% of matches")


def wagon() -> None:
    out = data_dir() / "output"
    balls = pd.read_csv(out / "ball_by_ball_data.csv", usecols=KEY + ["start_date", "runs_off_bat"])
    tracking = pd.read_csv(out / "cricinfo_tracking.csv", usecols=KEY + ["wagon_x", "wagon_zone", "wagon_distance", "wagon_in_ring", "shot_played", "shot_direction"], low_memory=False)
    d = balls.merge(tracking, on=KEY)
    d["year"] = d.start_date.str[:4].astype(int)
    print(f"{'era':14s} {'tracked':>9s} {'wagon filled':>13s} {'4s and 6s beyond 0.9':>21s} {'dots and 1s inside 0.9':>23s} {'shot named':>11s}")
    for lo, hi, name in ERAS:
        e = d[(d.year >= lo) & (d.year <= hi)]
        w = e.dropna(subset=["wagon_distance"])
        boundary = w[w.runs_off_bat >= 4]
        quiet = w[w.runs_off_bat <= 1]
        print(f"{name:14s} {len(e):9,d} {100 * e.wagon_x.notna().mean():12.0f}% {100 * (boundary.wagon_distance >= 0.9).mean():20.0f}% {100 * (quiet.wagon_distance < 0.9).mean():22.0f}% {100 * e.shot_played.notna().mean():10.0f}%")
    w = d.dropna(subset=["wagon_zone"])
    print("\nballs per zone share (should be roughly even sides, no zone empty):")
    print((w.groupby(pd.cut(w.year, [0, 2013, 2019, 2100], labels=[n for _, _, n in ERAS]), observed=True).wagon_zone.value_counts(normalize=True).unstack().round(3) * 100).to_string())


if __name__ == "__main__":
    for check in sys.argv[1:] or ["win", "wagon"]:
        {"win": win, "wagon": wagon}[check]()
