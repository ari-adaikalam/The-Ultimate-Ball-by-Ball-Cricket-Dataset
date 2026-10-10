"""The numbers quoted in the README, computed from the built files in data/output.

Run: .venv/bin/python -m analysis.doc_figures
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from cricket_pipeline.config import data_dir

KEY = ["match_id", "innings", "delivery_number"]
COVERAGE_COLUMNS = ["ball_line", "ball_length", "shot_played", "wagon_x", "win_probability"]
ERAS = [(0, 2013, "2001 to 2013"), (2014, 2019, "2014 to 2019"), (2020, 3000, "2020 and later")]
COMPETITIONS = {
    "tests": "Tests", "odis": "ODIs", "t20s": "T20Is", "ipl": "IPL", "wpl": "WPL", "bbl": "BBL", "wbb": "WBBL", "cpl": "CPL",
    "psl": "PSL", "sat": "SA20", "ilt": "ILT20", "hnd": "The Hundred", "mlc": "MLC", "lpl": "LPL", "bpl": "BPL",
}


def row_count(path) -> int:
    return sum(len(chunk) for chunk in pd.read_csv(path, usecols=[0], chunksize=1_000_000))


def file_rows(out) -> dict:
    return {name: row_count(out / name) for name in ("ball_by_ball_data.csv", "cricinfo_tracking.csv", "cricinfo_text_predictions.csv", "players.csv", "matches.csv", "coverage_report.csv")}


def coverage_tables(out) -> tuple[list, list]:
    """Rows of the era and competition tables: (name, balls, line, length, shot, wagon, win probability) with whole-number percentages."""
    c = pd.read_csv(out / "coverage_report.csv")

    def table(groups):
        g = groups[["rows", *COVERAGE_COLUMNS]].sum()
        return g.assign(**{k: (100 * g[k] / g.rows).round(0).astype(int) for k in COVERAGE_COLUMNS})

    c["era"] = pd.cut(c.year, [-1, 2013, 2019, 3000], labels=[n for _, _, n in ERAS])
    eras = table(c.groupby("era", observed=True))
    comps = table(c.groupby("archive")).sort_values("rows", ascending=False)
    fmt = lambda name, r: (name, int(r.rows), *[int(r[k]) for k in COVERAGE_COLUMNS])
    return [fmt(n, r) for n, r in eras.iterrows()], [fmt(COMPETITIONS[a], r) for a, r in comps.iterrows()]


def tracking_figures(out) -> dict:
    balls = pd.read_csv(out / "ball_by_ball_data.csv", usecols=KEY + ["batting_team", "start_date", "runs_off_bat"])
    matches = pd.read_csv(out / "matches.csv", usecols=["match_id", "winner", "format", "venue"])
    tracking = pd.read_csv(out / "cricinfo_tracking.csv", usecols=KEY + ["win_probability", "wagon_x", "wagon_distance", "shot_played", "ball_timestamp"], low_memory=False)
    d = balls.merge(tracking, on=KEY).merge(matches, on="match_id")
    d["year"] = d.start_date.str[:4].astype(int)
    d["era"] = pd.cut(d.year, [-1, 2013, 2019, 3000], labels=["old", "mid", "new"])

    first = d[(d.innings == 1)].dropna(subset=["win_probability"]).sort_values(KEY).groupby("match_id").tail(1)
    first = first[first.winner.notna()]
    won = first[first.batting_team == first.winner].win_probability.mean()
    lost = first[first.batting_team != first.winner].win_probability.mean()

    w = d.dropna(subset=["wagon_distance"])
    boundary = w[w.runs_off_bat >= 4]
    beyond = {name: 100 * (boundary[(boundary.year >= lo) & (boundary.year <= hi)].wagon_distance >= 0.9).mean() for lo, hi, name in ERAS}
    shot_named = {name: 100 * d[(d.year >= lo) & (d.year <= hi)].shot_played.notna().mean() for lo, hi, name in ERAS}

    d["has_wagon"] = d.wagon_x.notna()
    sizes = d.groupby(["venue", "era"], observed=True).has_wagon.size().unstack()
    shared = sizes[(sizes["old"] >= 5000) & (sizes["new"] >= 5000)].index
    same = boundary[boundary.venue.isin(shared)]
    same_ground = {era: 100 * (g.wagon_distance >= 0.9).mean() for era, g in same.groupby("era", observed=True)}

    super_over = d[(d.format != "TEST") & (d.innings >= 3)]
    return {
        "first_innings_won": round(won), "first_innings_lost": round(lost),
        "boundary_beyond_old": round(beyond["2001 to 2013"]), "boundary_beyond_later": sorted({round(beyond["2014 to 2019"]), round(beyond["2020 and later"])}),
        "same_ground_old": round(same_ground["old"]), "same_ground_new": round(same_ground["new"]),
        "shot_named_low": round(min(shot_named.values())), "shot_named_high": round(max(shot_named.values())),
        "super_over_timestamps": int(super_over.ball_timestamp.notna().sum()),
    }


def _day(paths) -> str | None:
    paths = list(paths)
    if not paths:
        return None
    day = datetime.fromtimestamp(max(p.stat().st_mtime for p in paths), timezone.utc)
    return f"{day.day} {day:%B %Y}"


def snapshot_date() -> str | None:
    """How the Cricsheet downloads are dated, as the words that follow "built from Cricsheet's": one day when the CSV and JSON ones agree, both when they do not.

    The CSV downloads and the people register can be a day older than the JSON downloads, and the text says so.
    """
    folder = data_dir() / "cricsheet"
    csv_day = _day([*folder.glob("*_csv2.zip"), *folder.glob("people.csv")])
    json_day = _day(folder.glob("*_json.zip"))
    if csv_day and json_day and csv_day != json_day:
        return f"CSV downloads and the people register of {csv_day} and its JSON downloads of {json_day}"
    day = csv_day or json_day
    return f"downloads of {day}" if day else None


def spelling_matches(out) -> int | None:
    """Matches where Cricsheet's CSV and JSON files spell a name differently, from the build's review file."""
    path = out / "json_review.csv"
    if not path.exists():
        return None
    notes = pd.read_csv(path)
    return int(notes[notes.note.str.contains("spell")].match_id.nunique())


def figures(out=None) -> dict:
    out = out or data_dir() / "output"
    empty = pd.read_csv(out / "empty_matches.csv", usecols=["match_id"])
    era_rows, competition_rows = coverage_tables(out)
    return {"file_rows": file_rows(out), "empty_matches": len(empty), "eras": era_rows, "competitions": competition_rows,
            "snapshot": snapshot_date(), "spelling_matches": spelling_matches(out), **tracking_figures(out)}


def n(value: int) -> str:
    return f"{value:,}"


def percent_range(values) -> str:
    values = sorted(set(values))
    return f"{values[0]}%" if len(values) == 1 else f"{values[0]}% to {values[-1]}%"


def table_block(header: str, rows: list) -> str:
    lines = [f"| {header} | Balls | Line | Length | Shot | Wagon point | Win probability |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {name} | {n(balls)} | " + " | ".join(f"{v}%" for v in rest) + " |" for name, balls, *rest in rows]
    return "\n".join(lines)


def fill_readme(text: str, f: dict) -> str:
    """Put the computed figures into the README, in the tables and in the sentences that quote them."""
    rows = f["file_rows"]
    for name, count in rows.items():
        text = re.sub(rf"(\| `{re.escape(name)}` \| [^|]+\| )[\d,]+( \|)", lambda m: f"{m.group(1)}{n(count)}{m.group(2)}", text)
    text = re.sub(r"\| Era \|.*\n\|---.*\n(?:\|.*\n?)+", lambda m: table_block("Era", f["eras"]) + ("\n" if m.group(0).endswith("\n") else ""), text, count=1)
    text = re.sub(r"\| Competition \|.*\n\|---.*\n(?:\|.*\n?)+", lambda m: table_block("Competition", f["competitions"]) + ("\n" if m.group(0).endswith("\n") else ""), text, count=1)
    rounded = n(round(f["empty_matches"], -2))
    text = re.sub(r"About [\d,]+ matches, mostly", f"About {rounded} matches, mostly", text)
    text = re.sub(r"The [\d,]+ matches with no Cricinfo commentary", f"The {rounded} matches with no Cricinfo commentary", text)
    text = re.sub(r"Only \d+ have a timestamp", f"Only {f['super_over_timestamps']} have a timestamp", text)
    text = re.sub(r"averages \d+ when the side that batted first went on to win and \d+ when it lost", f"averages {f['first_innings_won']} when the side that batted first went on to win and {f['first_innings_lost']} when it lost", text)
    text = re.sub(r"\d+% of fours and sixes land beyond 0\.9 of the way to the boundary, against [\d% to]+ in later matches", f"{f['boundary_beyond_old']}% of fours and sixes land beyond 0.9 of the way to the boundary, against {percent_range(f['boundary_beyond_later'])} in later matches", text)
    text = re.sub(r"compared \(\d+% against \d+%\)", f"compared ({f['same_ground_old']}% against {f['same_ground_new']}%)", text)
    if f.get("snapshot"):
        text = re.sub(r"built from Cricsheet's [^.]+\.", f"built from Cricsheet's {f['snapshot']}.", text)
    if f.get("spelling_matches") is not None:
        text = re.sub(r"\((\d+) matches at the last count\)", f"({f['spelling_matches']} matches at the last count)", text)
    low, high = f["shot_named_low"], f["shot_named_high"]
    shot = f"Shot names are filled for {low}% of tracked balls in every era." if low == high else f"Shot names are filled for {low}% to {high}% of tracked balls, depending on the era."
    return re.sub(r"Shot names are filled for [^.]*\.", shot, text)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "readme":
        path = Path("docs/dataset_readme.md")
        old = path.read_text()
        new = fill_readme(old, figures())
        if "--check" in sys.argv:
            import difflib
            print("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), "README now", "README with new figures", n=0)) or "README figures are current")
        else:
            path.write_text(new)
            print("README figures written" if new != old else "README figures were already current")
    else:
        print(json.dumps(figures(), indent=1))
