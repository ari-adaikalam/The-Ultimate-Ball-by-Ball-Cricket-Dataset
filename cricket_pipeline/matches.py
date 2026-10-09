"""Turn one Cricsheet match into dataset rows.

This is the notebook's process_match_file and process_info_file, ported so the
output is identical. Quirks of the original are kept on purpose (see the notes
on balls faced) so a rebuilt row matches what was published.
"""
import csv

import pandas as pd

from cricket_pipeline.config import Source

INFO_FIELDS = [
    "gender", "event", "match_number", "toss_winner", "toss_decision",
    "player_of_match", "winner", "winner_runs", "winner_wickets", "outcome",
]
NUMERIC_INFO_FIELDS = ("match_number", "winner_runs", "winner_wickets")

RAW_COLUMNS = [
    "match_id", "season", "start_date", "venue", "innings", "ball",
    "batting_team", "bowling_team", "striker", "non_striker", "bowler",
    "runs_off_bat", "extras", "wides", "noballs", "byes", "legbyes", "penalty",
    "wicket_type", "player_dismissed", "other_wicket_type", "other_player_dismissed",
]

ID_COLUMNS = ["striker_id", "bowler_id"]

# Column order of the dataset, for the part that comes from Cricsheet.
# 'player_of_match.1' is the second award line when a match has joint winners.
CRICSHEET_COLUMNS = [
    "match_id", "season", "start_date", "venue", "innings", "ball",
    "batting_team", "bowling_team", "striker", "striker_id", "non_striker", "bowler", "bowler_id",
    "runs_off_bat", "extras", "wides", "noballs", "byes", "legbyes", "penalty",
    "wicket_type", "player_dismissed", "other_wicket_type", "other_player_dismissed",
    "wicket", "striker balls faced", "total striker runs",
    "player out runs", "player out balls faced",
    "gender", "event", "match_number", "toss_winner", "toss_decision",
    "player_of_match", "player_of_match.1", "winner", "winner_runs",
    "winner_wickets", "outcome", "format", "type",
]

# What the old published dataset had, so verify can compare like with like
PUBLISHED_COLUMNS = [column for column in CRICSHEET_COLUMNS if column not in ID_COLUMNS]


def _clean(text: str) -> str:
    return text.strip().replace('"', "")


def _numeric_if_possible(value):
    """Keep a value as text if it is not a plain number, so nothing is silently dropped."""
    if value is None:
        return None
    number = pd.to_numeric(value, errors="coerce")
    return value if pd.isna(number) else float(number)


def parse_info(lines: list[str]) -> dict:
    """Pull the wanted fields out of a Cricsheet info file.

    Lines look like 'info,toss_winner,India'. The value can contain commas, so a
    line is split into at most three parts.
    """
    found: dict[str, list[str]] = {}
    for line in lines:
        parts = line.strip().split(",", 2)
        while len(parts) < 3:
            parts.append("")
        attribute = _clean(parts[1])
        if attribute in INFO_FIELDS:
            found.setdefault(attribute, []).append(_clean(parts[2]))

    info = {}
    for field in INFO_FIELDS:
        values = found.get(field, [])
        first = values[0] if values and values[0] != "" else None
        info[field] = _numeric_if_possible(first) if field in NUMERIC_INFO_FIELDS else first
    awards = found.get("player_of_match", [])
    info["player_of_match.1"] = awards[1] if len(awards) > 1 and awards[1] != "" else None
    return info


def parse_registry(lines: list[str]) -> dict[str, str]:
    """Map each player name in a match to their Cricsheet identifier.

    The csv module is used because a name containing a comma is quoted.
    """
    registry = {}
    for row in csv.reader(lines):
        if len(row) >= 5 and row[1] == "registry" and row[2] == "people":
            registry[row[3]] = row[4]
    return registry


def add_running_stats(balls: pd.DataFrame) -> pd.DataFrame:
    """Add wicket flag, balls faced and runs for the striker, and the same for a dismissed player.

    Balls faced counts every row for the striker, wides included, and it keeps
    counting across innings. That is how the published dataset was built, so it
    is kept. A dismissed non-striker (run out) gets the totals they had so far.
    """
    faced: dict = {}
    runs: dict = {}
    out_faced: dict = {}
    out_runs: dict = {}

    striker_faced, striker_runs, dismissed_runs, dismissed_faced = [], [], [], []
    for striker, scored, dismissed in zip(
        balls["striker"], balls["runs_off_bat"], balls["player_dismissed"]
    ):
        faced[striker] = faced.get(striker, 0) + 1
        runs[striker] = runs.get(striker, 0) + scored
        is_out = pd.notna(dismissed)
        if is_out:
            out_runs[dismissed] = runs.get(dismissed, 0)
            out_faced[dismissed] = faced.get(dismissed, 0)
        striker_faced.append(faced[striker])
        striker_runs.append(runs[striker])
        dismissed_runs.append(out_runs[dismissed] if is_out else None)
        dismissed_faced.append(out_faced[dismissed] if is_out else None)

    result = balls.copy()
    result["wicket"] = balls["player_dismissed"].notna().astype(int)
    result["striker balls faced"] = pd.Series(striker_faced, index=balls.index, dtype="float64")
    result["total striker runs"] = pd.Series(striker_runs, index=balls.index, dtype="float64")
    result["player out runs"] = pd.Series(dismissed_runs, index=balls.index, dtype="float64")
    result["player out balls faced"] = pd.Series(dismissed_faced, index=balls.index, dtype="float64")
    return result


def build_match_rows(balls: pd.DataFrame, info_lines: list[str], source: Source) -> pd.DataFrame:
    missing = [column for column in RAW_COLUMNS if column not in balls.columns]
    if missing:
        raise ValueError(f"Cricsheet match file is missing columns: {missing}")

    rows = add_running_stats(balls[RAW_COLUMNS])
    registry = parse_registry(info_lines)
    rows["striker_id"] = rows["striker"].map(registry)
    rows["bowler_id"] = rows["bowler"].map(registry)
    for field, value in parse_info(info_lines).items():
        rows[field] = value
    rows["format"] = source.format
    rows["type"] = source.type
    return rows[CRICSHEET_COLUMNS]
