"""Write the published files from the Cricsheet rows, the Cricinfo captures and the player profiles.

Outputs, in data/output/:
  ball_by_ball_data.csv  the main file, one row per delivery, Cricsheet data and player columns
  cricinfo_tracking.csv      the Cricinfo tracking columns for the deliveries that have them, joined on match_id, innings and delivery_number
  players.csv            one row per player
  matches.csv            one row per match
  wickets.csv, wicket_fielders.csv, match_people.csv, innings.csv, powerplays.csv, reviews.csv, match_replacements.csv
                         what Cricsheet's JSON files add: every wicket and its fielders, the players and officials of each match, targets, powerplays,
                         DRS reviews and replacements
  coverage_report.csv    how much of each Cricinfo column is filled, by competition and year
  empty_matches.csv      matches left without Cricinfo columns because Cricinfo had nothing useful, with the page link to check by hand
  review.csv             matches whose Cricinfo data was missing, incomplete, or failed its checks
  json_review.csv        matches where Cricsheet's CSV and JSON spell a name differently, for reading by hand

Matches are handled one at a time, so memory stays small even for the biggest archive.
"""
import json
from pathlib import Path

import pandas as pd

from cricket_pipeline.align import CRICINFO_COLUMNS, cricinfo_frame, pair_match
from cricket_pipeline.assemble import (
    MATCH_ON_EVERY_ROW, attach_players, empty_profiles, external_ids_file, load_profiles, matches_file, player_table, players_file, without_match_file_columns,
)
from cricket_pipeline.capture_queue import load_raw
from cricket_pipeline.cricsheet_json import MATCH_FACT_COLUMNS, NOTE_COLUMNS, TABLE_COLUMNS
from cricket_pipeline.config import SOURCES, Source, data_dir, work_dir

CHUNK_ROWS = 250_000

# Cricsheet's own over.ball number is left out of the published ball file. The 10th delivery of an over (4.10) reads as the first (4.1),
# so over and ball_in_over replace it. The pipeline keeps it in the work files, where the Cricinfo pairing uses it.
FINAL_COLUMNS = [
    "match_id", "season", "start_date", "innings", "delivery_number", "over", "ball_in_over", "scorecard_ball", "is_legal_delivery", "batting_team", "bowling_team",
    "striker", "striker_id", "non_striker", "bowler", "bowler_id",
    "runs_off_bat", "extras", "wides", "noballs", "byes", "legbyes", "penalty",
    "wicket_type", "player_dismissed", "other_wicket_type", "other_player_dismissed", "wicket",
    "striker balls faced", "total striker runs", "player out runs", "player out balls faced",
    "gender", "event", "format", "type",
    "country_striker", "batting style_striker", "bowling style_striker", "playing role_striker", "striker_age",
    "country_bowler", "batting style_bowler", "bowling style_bowler", "playing role_bowler", "bowler_age",
    "fielder_1", "fielder_1_id", "fielder_1_substitute", "non_boundary",      # added at the end, so no earlier column moved
]
# The n-th delivery of the innings is the key to join the tracking file
CRICINFO_FILE_COLUMNS = ["match_id", "innings", "delivery_number", *CRICINFO_COLUMNS]
WHOLE_NUMBER_COLUMNS = [
    "wagon_x", "wagon_y", "wagon_zone", "predicted_score",
    "innings", "delivery_number", "over", "ball_in_over", "extras", "wides", "noballs", "byes", "legbyes", "penalty", "wicket",
    "striker balls faced", "total striker runs", "player out runs", "player out balls faced",
]
MATCH_WHOLE_NUMBER_COLUMNS = ["match_number", "winner_runs", "winner_wickets", "scheduled_overs", "balls_per_over", "match_type_number", "cricsheet_revision"]

# Files written from the JSON tables, and which of their columns are whole numbers
JSON_FILES = {
    "wickets": ("wickets.csv", ["innings", "delivery_number", "wicket_number"]),
    "wicket_fielders": ("wicket_fielders.csv", ["innings", "delivery_number", "wicket_number", "fielder_number"]),
    "people": ("match_people.csv", ["person_number"]),
    "innings": ("innings.csv", ["innings", "target_runs", "penalty_runs_pre", "penalty_runs_post"]),
    "powerplays": ("powerplays.csv", ["innings", "powerplay_number"]),
    "reviews": ("reviews.csv", ["innings", "delivery_number"]),
    "replacements": ("match_replacements.csv", ["innings", "delivery_number", "replacement_number"]),
    "missing": ("match_missing.csv", ["missing_number", "innings"]),
    "miscounted_overs": ("miscounted_overs.csv", ["innings", "over", "balls"]),
    "absent_hurt": ("innings_absent_hurt.csv", ["innings"]),
    "dates": ("match_dates.csv", ["date_number"]),
}
SORT_KEYS = {
    "wickets": ["match_id", "innings", "delivery_number", "wicket_number"],
    "wicket_fielders": ["match_id", "innings", "delivery_number", "wicket_number", "fielder_number"],
    "people": ["match_id", "role", "person_number"], "innings": ["match_id", "innings"], "powerplays": ["match_id", "innings", "powerplay_number"],
    "reviews": ["match_id", "innings", "delivery_number"], "replacements": ["match_id", "innings", "delivery_number", "replacement_number"],
    "missing": ["match_id", "missing_number"], "miscounted_overs": ["match_id", "innings", "over"],
    "absent_hurt": ["match_id", "innings", "player_id", "player"], "dates": ["match_id", "date_number"],
}


def output_dir() -> Path:
    path = data_dir() / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def iter_matches(path: Path):
    """Yield one DataFrame per match from a Cricsheet rows file, reading it in chunks.

    A match can be split across two chunks, so the last match of a chunk is held back until the next one.
    """
    held = None
    for chunk in pd.read_csv(path, chunksize=CHUNK_ROWS, dtype={"season": str}, low_memory=False):
        if held is not None:
            chunk = pd.concat([held, chunk], ignore_index=True)
        last = chunk["match_id"].iloc[-1]
        held = chunk[chunk["match_id"] == last]
        chunk = chunk[chunk["match_id"] != last]
        for _, match in chunk.groupby("match_id", sort=False):
            yield match
    if held is not None and len(held):
        yield held


def whole_if_possible(values: pd.Series) -> pd.Series:
    """Numbers that are all whole are written as 40 and not 40.0. Anything with a fraction is left alone."""
    numbers = pd.to_numeric(values, errors="coerce")
    return numbers.astype("Int64") if (numbers.dropna() % 1 == 0).all() else numbers


def tidy_numbers(rows: pd.DataFrame) -> pd.DataFrame:
    for column in WHOLE_NUMBER_COLUMNS:
        rows[column] = whole_if_possible(rows[column])
    rows["win_probability"] = pd.to_numeric(rows["win_probability"], errors="coerce")
    return rows


def profile_lookup(player_ids: pd.DataFrame) -> dict:
    known = player_ids.dropna(subset=["cricinfo_id"])
    return dict(zip(known["identifier"], known["cricinfo_id"].astype(int)))


def read_json_tables(wanted: list[Source]) -> dict[str, pd.DataFrame]:
    """The small tables ingest wrote from the JSON files, one set per Cricsheet collection, joined into one table each."""
    tables = {}
    for name, columns in {**TABLE_COLUMNS, "notes": NOTE_COLUMNS}.items():
        parts = []
        for source in wanted:
            path = work_dir() / f"cricsheet_{source.archive}_{name}.csv"
            if path.exists():
                parts.append(pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""]))
        tables[name] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=columns)
    return tables


def write_json_files(out: Path, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    rows = {}
    for name, (file_name, whole) in JSON_FILES.items():
        table = tables[name].copy()
        for column in ["match_id", *whole]:
            table[column] = pd.to_numeric(table[column]).astype("Int64")
        if "target_overs" in table:
            table["target_overs"] = pd.to_numeric(table["target_overs"])
        for column in ("start_ball", "end_ball"):
            if column in table:
                table[column] = pd.to_numeric(table[column])
        table.sort_values(SORT_KEYS[name]).reset_index(drop=True)[TABLE_COLUMNS[name]].to_csv(out / file_name, index=False)
        rows[file_name] = len(table)
    return rows


def build(archives: list[str] | None = None) -> dict:
    out = output_dir()
    ids = pd.read_csv(data_dir() / "players" / "player_ids.csv", dtype=str)
    profiles_path = data_dir() / "players" / "raw" / "profiles.jsonl"
    profiles = load_profiles(profiles_path) if profiles_path.exists() else empty_profiles()
    players = player_table(profiles, ids)
    profile_of = profile_lookup(ids)

    main_path = out / "ball_by_ball_data.csv"
    main_path.unlink(missing_ok=True)
    cricinfo_path = out / "cricinfo_tracking.csv"
    pd.DataFrame(columns=CRICINFO_FILE_COLUMNS).to_csv(cricinfo_path, index=False)    # header first, so the file exists even when nothing is tracked
    match_rows, coverage, review, empty = [], [], [], []
    totals = {"matches": 0, "rows": 0, "captured": 0, "cricinfo_rows": 0}
    wanted = [s for s in SOURCES if archives is None or s.archive in archives]
    for source in wanted:
        for rows in iter_matches(work_dir() / f"cricsheet_{source.archive}.csv"):
            match_id = int(rows["match_id"].iloc[0])
            rows = rows.assign(delivery_number=rows.groupby("innings").cumcount() + 1)
            raw = load_raw(match_id)
            report = {"rows": len(rows), "paired": 0, "rejected": 0, "innings_count_differs": [], "rejected_rows": []}
            if raw and raw.get("innings"):
                rows, report = pair_match(rows, cricinfo_frame(raw), profile_of)
                totals["captured"] += 1
            else:
                rows = rows.copy()
                for column in CRICINFO_COLUMNS:
                    rows[column] = None
            rows = tidy_numbers(attach_players(rows, players))
            match_rows.append(rows[["match_id", *MATCH_ON_EVERY_ROW, "venue", "match_number", "toss_winner", "toss_decision",
                                    "player_of_match", "player_of_match_2", "winner", "winner_runs", "winner_wickets", "outcome"]].iloc[[0]])
            coverage.append(_coverage_row(source, rows, raw))
            if raw and (raw.get("no_commentary") or raw.get("no_useful_data")):
                empty.append({"match_id": match_id, "archive": source.archive, "year": int(str(rows["start_date"].iloc[0])[:4]), "rows": len(rows),
                              "reason": "Cricinfo has no commentary" if raw.get("no_commentary") else "full capture found nothing useful" if raw.get("recaptured") else "nothing useful after a look at every innings",
                              "url": raw.get("url")})
            problem = _review_reason(raw, report)
            if problem:
                review.append({"match_id": match_id, "archive": source.archive, "problem": problem, **{k: report.get(k) for k in ("rows", "paired", "rejected", "innings_count_differs")},
                               "details": " | ".join(report.get("rejected_rows", [])[:20])})
            final = without_match_file_columns(rows)[FINAL_COLUMNS]
            final.to_csv(main_path, mode="a", header=not main_path.exists(), index=False)
            tracked = rows[CRICINFO_FILE_COLUMNS]
            tracked = tracked[tracked[CRICINFO_COLUMNS].notna().any(axis=1)]
            tracked.to_csv(cricinfo_path, mode="a", header=False, index=False)
            totals["cricinfo_rows"] += len(tracked)
            totals["matches"] += 1
            totals["rows"] += len(rows)

    matches = matches_file(pd.concat(match_rows, ignore_index=True)) if match_rows else pd.DataFrame()
    json_tables = read_json_tables(wanted)
    facts = json_tables["facts"]
    facts["match_id"] = pd.to_numeric(facts["match_id"]).astype("Int64")
    matches["match_id"] = matches["match_id"].astype("Int64")
    matches = matches.merge(facts[["match_id", *MATCH_FACT_COLUMNS]], on="match_id", how="left")
    for column in MATCH_WHOLE_NUMBER_COLUMNS:
        if column in matches.columns:
            matches[column] = whole_if_possible(matches[column])
    matches.to_csv(out / "matches.csv", index=False)
    totals["json_files"] = write_json_files(out, json_tables)
    register_path = data_dir() / "cricsheet" / "people.csv"
    register = pd.read_csv(register_path, dtype=str) if register_path.exists() else pd.DataFrame(columns=["identifier"])
    in_dataset = set(json_tables["people"]["person_id"].dropna()) | set(players["identifier"])
    external = external_ids_file(register, in_dataset)
    external.to_csv(out / "player_external_ids.csv", index=False)
    totals["json_files"]["player_external_ids.csv"] = len(external)
    json_tables["notes"].sort_values(["match_id", "note"]).to_csv(out / "json_review.csv", index=False)      # matches where Cricsheet's two formats differ in a spelling
    totals["json_notes"] = len(json_tables["notes"])
    players_file(players).to_csv(out / "players.csv", index=False)
    pd.DataFrame(coverage).to_csv(out / "coverage_report.csv", index=False)
    pd.DataFrame(review, columns=["match_id", "archive", "problem", "rows", "paired", "rejected", "innings_count_differs", "details"]).to_csv(out / "review.csv", index=False)
    pd.DataFrame(empty, columns=["match_id", "archive", "year", "rows", "reason", "url"]).to_csv(out / "empty_matches.csv", index=False)
    totals["review"] = len(review)
    return totals


def _coverage_row(source: Source, rows: pd.DataFrame, raw: dict | None) -> dict:
    row = {"archive": source.archive, "year": int(str(rows["start_date"].iloc[0])[:4]), "match_id": int(rows["match_id"].iloc[0]),
           "rows": len(rows), "captured": bool(raw and raw.get("innings")), "no_commentary": bool(raw and (raw.get("no_commentary") or raw.get("no_useful_data")))}
    for column in CRICINFO_COLUMNS:
        row[column] = int(rows[column].notna().sum())
    return row


def _review_reason(raw: dict | None, report: dict) -> str | None:
    if raw is None:
        return "not captured yet"
    if raw.get("no_commentary") or raw.get("no_useful_data"):
        return None                                    # nothing to capture is a normal outcome, not a problem
    if not raw.get("innings"):
        return "capture has no innings"
    if any(not i.get("complete", True) for i in raw["innings"]):
        return "capture incomplete (Cricinfo leaves overs out, repeat captures return the same balls)"
    if report.get("rejected") or report.get("innings_count_differs"):
        return "pairing checks failed"
    return None
