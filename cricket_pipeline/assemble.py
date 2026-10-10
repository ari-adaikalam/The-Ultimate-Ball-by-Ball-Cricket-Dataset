"""Turn saved Cricinfo profiles into player columns and join them to match rows by player id."""
import json
import re
from pathlib import Path

import pandas as pd

# Profile image paths from Cricinfo are relative to this prefix, as in the published dataset's images
IMAGE_PREFIX = "https://img1.hscicdn.com/image/upload/f_auto,t_ds_w_1280,q_80"

PLAYER_FIELDS = {
    "full_name": "full name",
    "country": "country",
    "batting_style": "batting style",
    "bowling_style": "bowling style",
    "playing_roles": "playing role",
    "teams": "major teams",
    "image_url": "image url",
    "gender": "gender",
    "fielding_styles": "fielding style",
}
GENDER = {"M": "male", "F": "female"}   # the same words the match rows use


# Short columns stay on every ball row. The three long text columns would roughly double the
# file, so they live once per player in players.csv and join on striker_id or bowler_id.
ON_EVERY_ROW = ["country", "batting style", "bowling style", "playing role"]
PLAYERS_FILE_ONLY = ["full name", "major teams", "image url", "gender", "fielding style", "first international year", "last international year"]


# Match-level columns: the same for every ball of a match. The short ones people filter on stay on every
# ball row. The long text ones are written once per match to matches.csv, keyed by match_id.
MATCH_ON_EVERY_ROW = ["season", "start_date", "gender", "event", "format", "type"]
MATCH_FILE_ONLY = [
    "venue", "match_number", "toss_winner", "toss_decision", "player_of_match", "player_of_match_2",
    "winner", "winner_runs", "winner_wickets", "outcome",
]


def _birth_date(value):
    """Cricinfo gives the date as {'year', 'month', 'date'}. Anything incomplete or impossible is a gap."""
    if not isinstance(value, dict):
        return pd.NaT
    try:
        return pd.Timestamp(year=int(value["year"]), month=int(value["month"]), day=int(value["date"]))
    except (KeyError, TypeError, ValueError):
        return pd.NaT


def _career_years(value):
    """Cricinfo writes the span as text like '2008 - 2026'. Returns (first, last) as numbers, or gaps."""
    match = re.match(r"\s*(\d{4})(?:\D+(\d{4}))?", value) if isinstance(value, str) else None
    if not match:
        return (pd.NA, pd.NA)
    first = int(match.group(1))
    return (first, int(match.group(2)) if match.group(2) else first)


def _joined(value) -> str | None:
    """Cricinfo gives lists for styles, roles and teams. A person can have more than one."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or None
    if value is None or pd.isna(value):
        return None
    return value or None


def empty_profiles() -> pd.DataFrame:
    """No profiles fetched yet: every player column is simply empty."""
    columns = ["cricinfo_id", *PLAYER_FIELDS.values(), "first international year", "last international year", "birth_date"]
    return pd.DataFrame({column: pd.Series(dtype="object") for column in columns}).astype({"cricinfo_id": "int64"})


def load_profiles(path: Path) -> pd.DataFrame:
    """One row per Cricinfo player id. A later row wins, so a retry replaces an earlier failure."""
    latest: dict[int, dict] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue        # a half written line from a stop, the profile is fetched again
            latest[int(row["cricinfo_id"])] = row
    good = [row for row in latest.values() if row.get("status") == 200 and not row.get("error")]
    profiles = pd.DataFrame(good)
    for field in PLAYER_FIELDS:
        if field not in profiles.columns:
            profiles[field] = None
        profiles[field] = profiles[field].map(_joined)
    profiles["image_url"] = profiles["image_url"].map(lambda p: IMAGE_PREFIX + p if isinstance(p, str) and p else None)
    profiles["gender"] = profiles["gender"].map(lambda g: GENDER.get(g))
    years = profiles["career_span"].map(_career_years) if "career_span" in profiles.columns else pd.Series([(pd.NA, pd.NA)] * len(profiles), index=profiles.index)
    profiles["first international year"] = years.map(lambda t: t[0]).astype("Int64")
    profiles["last international year"] = years.map(lambda t: t[1]).astype("Int64")
    # Used only to work out age at a match. The exact date never goes into the dataset.
    profiles["birth_date"] = profiles["dob"].map(_birth_date) if "dob" in profiles.columns else pd.NaT
    return profiles[["cricinfo_id", *PLAYER_FIELDS, "first international year", "last international year", "birth_date"]].rename(columns=PLAYER_FIELDS)


def player_table(profiles: pd.DataFrame, player_ids: pd.DataFrame) -> pd.DataFrame:
    """Profiles keyed by Cricsheet identifier. Players with no profile get empty columns."""
    ids = player_ids[["identifier", "name", "cricinfo_id"]].copy()
    ids["cricinfo_id"] = pd.to_numeric(ids["cricinfo_id"], errors="coerce")
    table = ids.merge(profiles, on="cricinfo_id", how="left")
    if table["identifier"].duplicated().any():
        raise ValueError("a Cricsheet identifier appears twice in the player table")
    return table


def age_in_years(birth_date: pd.Series, match_date: pd.Series) -> pd.Series:
    """Whole years of age on the first day of the match. Empty when either date is missing."""
    birth_date = pd.to_datetime(birth_date)        # an all-empty column arrives as plain objects
    match_date = pd.to_datetime(match_date)
    years = match_date.dt.year - birth_date.dt.year
    had_birthday = (match_date.dt.month > birth_date.dt.month) | (
        (match_date.dt.month == birth_date.dt.month) & (match_date.dt.day >= birth_date.dt.day)
    )
    return (years - (~had_birthday).astype(int)).astype("Int64")


def attach_players(rows: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Add the short player columns and the age at the match for striker and bowler.

    Keeps row order and never changes the row count. Long text columns and the birth date are
    left out on purpose: see ON_EVERY_ROW and players_file.
    """
    result = rows
    for role in ("striker", "bowler"):
        wanted = players[["identifier", "birth_date", *ON_EVERY_ROW]]
        renamed = wanted.rename(columns={"identifier": f"{role}_id", "birth_date": f"birth_date_{role}", **{c: f"{c}_{role}" for c in ON_EVERY_ROW}})
        result = result.merge(renamed, on=f"{role}_id", how="left")
        result[f"{role}_age"] = age_in_years(result[f"birth_date_{role}"], result["start_date"])
        # The exact birth date is dropped here on purpose, so it can never reach the published file
        result = result.drop(columns=[f"birth_date_{role}"])
    if len(result) != len(rows):
        raise ValueError("joining players changed the number of rows")
    return result


def players_file(players: pd.DataFrame) -> pd.DataFrame:
    """One row per player, joined to the ball rows on player_id (the same value as striker_id and bowler_id)."""
    # name is the short name used in the striker and bowler columns, so a row can be read at a glance
    columns = ["identifier", "name", "cricinfo_id", "full name", "gender", "country", "batting style", "bowling style", "playing role",
               "fielding style", "first international year", "last international year", "major teams", "image url"]
    file = players[columns].rename(columns={"identifier": "player_id"})
    file["cricinfo_id"] = file["cricinfo_id"].astype("Int64")
    return file.sort_values("player_id").reset_index(drop=True)


def matches_file(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per match with every match-level column, including the ones kept on the ball rows."""
    columns = ["match_id", *MATCH_ON_EVERY_ROW, *MATCH_FILE_ONLY]
    per_match = rows[columns].drop_duplicates()
    if per_match["match_id"].duplicated().any():
        raise ValueError("a match has two different values for a match-level column")
    return per_match.sort_values("match_id").reset_index(drop=True)


def without_match_file_columns(rows: pd.DataFrame) -> pd.DataFrame:
    """The ball rows as published: the long match-level columns live in matches.csv instead."""
    return rows.drop(columns=MATCH_FILE_ONLY)


def external_ids_file(register: pd.DataFrame, wanted: set[str]) -> pd.DataFrame:
    """One row per id a person has in another system, for the people in the dataset, from Cricsheet's register.

    The register has one column per system (key_cricbuzz, key_opta, and a second column such as key_pulse_2 when a person has two ids there).
    Cricinfo ids are left out on purpose: they live in players.csv only, so a release without Cricinfo removes them in one place.
    """
    people = register[register["identifier"].isin(wanted)]
    rows = []
    for column in register.columns:
        if not column.startswith("key_") or "cricinfo" in column:
            continue
        found = people[["identifier", column]].dropna()
        source = re.sub(r"_\d+$", "", column[len("key_"):])
        rows.append(pd.DataFrame({"player_id": found["identifier"], "source": source, "external_id": found[column].astype(str).str.replace(r"\.0$", "", regex=True)}))
    table = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["player_id", "source", "external_id"])
    return table.drop_duplicates().sort_values(["player_id", "source", "external_id"]).reset_index(drop=True)
