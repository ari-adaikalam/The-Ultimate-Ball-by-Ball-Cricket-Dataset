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
    "striker balls faced", "runs_off_bat", "total striker runs", "player_dismissed", "player out runs", "player out balls faced",
    "wicket", "wicket_type", "other_player_dismissed", "other_wicket_type", "fielder_1", "fielder_1_id", "fielder_1_substitute", "non_boundary",
]

# The files Cricsheet's JSON adds, their keys, and the people roles and collections that are allowed
JSON_FILE_KEYS = {
    "wickets.csv": KEY + ["wicket_number"], "wicket_fielders.csv": KEY + ["wicket_number", "fielder_number"], "match_people.csv": ["match_id", "role", "person_number"],
    "innings.csv": ["match_id", "innings"], "powerplays.csv": ["match_id", "innings", "powerplay_number"], "reviews.csv": KEY,
    "match_replacements.csv": KEY + ["replacement_number"],
    "match_missing.csv": ["match_id", "missing_number"], "miscounted_overs.csv": ["match_id", "innings", "over"],
    "innings_absent_hurt.csv": ["match_id", "innings", "player"], "match_dates.csv": ["match_id", "date_number"],
    "player_external_ids.csv": ["player_id", "source", "external_id"],
}
MISSING_TYPES = {"powerplays", "reviews", "player_of_match", "umpires"}
EXTERNAL_SOURCES = {"bcci", "bigbash", "cricbuzz", "cricheroes", "crichq", "cricingif", "cricketarchive", "cricketworld", "nvplay", "opta", "pulse"}
ROLES = {"player", "umpire", "tv_umpire", "match_referee", "reserve_umpire"}
COLLECTIONS = {"tests", "odis", "t20s", "ipl", "wpl", "bbl", "wbb", "cpl", "psl", "sat", "ilt", "hnd", "mlc", "lpl", "bpl"}
FIELDING_KINDS = {"caught", "stumped", "run out"}


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


def running_totals(ball: pd.DataFrame) -> str | None:
    """Recompute the striker's runs and the dismissed player's runs and balls faced from the rows alone.

    The dismissed player's tally is the latest one that player had in the innings, and 0 for a batter who has not faced a ball.
    Rows with no dismissal carry no player out values."""
    ordered = ball.sort_values(KEY).reset_index(drop=True)
    keys = [ordered.match_id, ordered.innings, ordered.striker]
    runs = pd.to_numeric(ordered.runs_off_bat, errors="coerce").fillna(0)
    faced = (pd.to_numeric(ordered.wides, errors="coerce").fillna(0) == 0).astype(int)
    tally = pd.DataFrame({"match_id": ordered.match_id, "innings": ordered.innings, "player": ordered.striker.astype(str),
                          "delivery_number": ordered.delivery_number,
                          "runs": runs.groupby(keys, observed=True, dropna=False).cumsum(),
                          "faced": faced.groupby(keys, observed=True, dropna=False).cumsum()}).sort_values("delivery_number")
    problems = []
    wrong = int((tally.sort_index().runs != ordered["total striker runs"]).sum())
    if wrong:
        problems.append(f"total striker runs is not the running sum of runs_off_bat on {wrong:,} rows")
    out = ordered[ordered.player_dismissed.notna()]
    if len(out):
        asked = pd.DataFrame({"match_id": out.match_id, "innings": out.innings, "player": out.player_dismissed.astype(str),
                              "delivery_number": out.delivery_number, "out_runs": out["player out runs"], "out_faced": out["player out balls faced"]})
        joined = pd.merge_asof(asked.sort_values("delivery_number"), tally, on="delivery_number", by=["match_id", "innings", "player"])
        joined[["runs", "faced"]] = joined[["runs", "faced"]].fillna(0)
        wrong = int((joined.runs != joined.out_runs).sum())
        if wrong:
            problems.append(f"player out runs is not the dismissed player's runs on {wrong:,} dismissals")
        wrong = int((joined.faced != joined.out_faced).sum())
        if wrong:
            problems.append(f"player out balls faced is not the dismissed player's balls faced on {wrong:,} dismissals")
    stray = int(ball[ball.player_dismissed.isna()][["player out runs", "player out balls faced"]].notna().any(axis=1).sum())
    if stray:
        problems.append(f"{stray:,} rows with no dismissal carry a player out value")
    return "; ".join(problems) if problems else None


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


def _plain(series: pd.Series) -> pd.Series:
    return series.astype("string").str.replace(r"\s*\(\d+\)$", "", regex=True)


def wickets_agree_with_balls(ball: pd.DataFrame, wickets: pd.DataFrame) -> str | None:
    """wickets.csv holds every wicket. Its first and second wicket of a delivery are the ball file's first and second dismissal."""
    problems = []
    for number, who, kind in ((1, "player_dismissed", "wicket_type"), (2, "other_player_dismissed", "other_wicket_type")):
        on_ball = ball[ball[who].notna()][KEY + [who, kind]]
        in_file = wickets[wickets.wicket_number == number][KEY + ["player_dismissed", "wicket_type"]].rename(columns={"player_dismissed": "file_player", "wicket_type": "file_kind"})
        if len(on_ball) != len(in_file):
            problems.append(f"{len(on_ball):,} balls have a wicket {number} and wickets.csv has {len(in_file):,}")
            continue
        joined = on_ball.merge(in_file, on=KEY, how="left")
        wrong = int(((_plain(joined[who]) != _plain(joined["file_player"])) | (joined[kind] != joined["file_kind"])).sum())
        if wrong:
            problems.append(f"{wrong:,} wicket {number} rows differ from the ball file")
    return "; ".join(problems) if problems else None


def fielders_belong_to_wickets(wickets: pd.DataFrame, fielders: pd.DataFrame) -> str | None:
    wicket_key = KEY + ["wicket_number"]
    missing = missing_references(fielders, wickets, wicket_key, "fielder rows")
    if missing:
        return missing
    kinds = fielders.merge(wickets[wicket_key + ["wicket_type"]], on=wicket_key, how="left").wicket_type
    odd = int((~kinds.isin(FIELDING_KINDS)).sum())
    return f"{odd:,} fielders sit on a wicket that is not caught, stumped or run out" if odd else None


def ball_fielder_is_the_first_listed(ball: pd.DataFrame, fielders: pd.DataFrame) -> str | None:
    """fielder_1 on a ball is the first fielder of wicket 1 in wicket_fielders.csv, and empty when there is none."""
    first = fielders[(fielders.wicket_number == 1) & (fielders.fielder_number == 1)][KEY + ["fielder", "fielder_id", "substitute"]]
    joined = ball[KEY + ["fielder_1", "fielder_1_id", "fielder_1_substitute"]].merge(first, on=KEY, how="left")
    wrong = int((joined.fielder_1.astype("string").fillna("") != joined.fielder.astype("string").fillna("")).sum()
                + (joined.fielder_1_id.astype("string").fillna("") != joined.fielder_id.astype("string").fillna("")).sum())
    shown = int(ball.fielder_1_substitute.notna().sum())
    if shown != len(first):
        wrong += abs(shown - len(first))
    return f"fielder_1 on the ball file differs from wicket_fielders.csv on {wrong:,} cells" if wrong else None


def people_rules(people: pd.DataFrame) -> str | None:
    problems = []
    unknown = sorted(set(people.role) - ROLES)
    if unknown:
        problems.append(f"unknown roles {unknown}")
    players = people.role == "player"
    if people[players].team.isna().any():
        problems.append("a player has no team")
    if people[~players].team.notna().any():
        problems.append("an official has a team")
    return "; ".join(problems) if problems else None


def match_columns(matches: pd.DataFrame) -> str | None:
    problems = []
    if matches.collection.isna().any() or not set(matches.collection) <= COLLECTIONS:
        problems.append(f"collection is empty or unknown for {int((~matches.collection.isin(COLLECTIONS)).sum()):,} matches")
    if not set(matches.balls_per_over.dropna().astype(int)) <= {5, 6}:
        problems.append("balls_per_over is not 5 or 6")
    if (pd.to_datetime(matches.end_date) < pd.to_datetime(matches.start_date)).any():
        problems.append("a match ends before it starts")
    return "; ".join(problems) if problems else None


def non_boundary_only_on_fours_and_sixes(ball: pd.DataFrame) -> str | None:
    flagged = ball[ball.non_boundary.astype("string") == "True"]
    wrong = int((~flagged.runs_off_bat.isin([4, 6])).sum())
    unset = int(ball.non_boundary.isna().sum())
    problems = ([f"{wrong:,} balls marked non_boundary are not a four or a six"] if wrong else []) + ([f"non_boundary is empty on {unset:,} balls"] if unset else [])
    return "; ".join(problems) if problems else None


def missing_rules(missing: pd.DataFrame) -> str | None:
    unknown = sorted(set(missing.missing_type) - MISSING_TYPES)
    if unknown:
        return f"unknown kinds of missing data {unknown}"
    odd = int((missing[missing.missing_type == "powerplays"].innings.isna()).sum() + (missing[missing.missing_type != "powerplays"].innings.notna()).sum())
    return f"{odd:,} rows have an innings that does not fit their kind" if odd else None


def miscounted_agree_with_balls(ball: pd.DataFrame, miscounted: pd.DataFrame) -> str | None:
    """The balls Cricsheet says an over held are the legal deliveries the ball file has in that over."""
    legal = ball[ball.is_legal_delivery.astype("string") == "True"].groupby(["match_id", "innings", "over"]).size().rename("legal").reset_index()
    joined = miscounted.merge(legal, on=["match_id", "innings", "over"], how="left")
    wrong = int((joined.balls != joined.legal.fillna(0)).sum())
    return f"{wrong:,} of {len(miscounted):,} miscounted overs do not match the ball file's legal balls" if wrong else None


def dates_agree_with_matches(dates: pd.DataFrame, matches: pd.DataFrame) -> str | None:
    ordered = dates.sort_values(["match_id", "date_number"])
    first, last = ordered.groupby("match_id").date.first(), ordered.groupby("match_id").date.last()
    table = matches.set_index("match_id")
    missing = set(table.index) - set(first.index)
    wrong = int((first.reindex(table.index).astype("string") != table.start_date.astype("string")).sum() + (last.reindex(table.index).astype("string") != table.end_date.astype("string")).sum())
    return f"{len(missing):,} matches have no dates and {wrong:,} first or last dates differ from matches.csv" if missing or wrong else None


def powerplay_bounds_are_deliveries(ball: pd.DataFrame, powerplays: pd.DataFrame) -> str | None:
    """Every powerplay boundary that names a delivery names exactly the delivery it says: the ball file's over and position for that
    delivery number are the stated ones. There is no rounding and no share allowed to miss. A start never comes after its end."""
    deliveries = ball[["match_id", "innings", "delivery_number", "over", "ball_in_over"]]
    problems = []
    for side in ("start", "end"):
        named = powerplays[powerplays[f"{side}_delivery_number"].notna()]
        joined = named.merge(deliveries, left_on=["match_id", "innings", f"{side}_delivery_number"], right_on=["match_id", "innings", "delivery_number"], how="left")
        wrong = int(((joined.over != joined[f"{side}_over"]) | (joined.ball_in_over != joined[f"{side}_ball_in_over"])).sum())
        if wrong:
            problems.append(f"{wrong:,} powerplay {side}s are not at the over and position they state")
    both = powerplays.dropna(subset=["start_delivery_number", "end_delivery_number"])
    backwards = int((both.start_delivery_number > both.end_delivery_number).sum())
    if backwards:
        problems.append(f"{backwards:,} powerplays start after they end")
    return "; ".join(problems) if problems else None


def unresolved_powerplay_bounds(powerplays: pd.DataFrame) -> int:
    """Boundaries that match no single delivery. They keep their listed text and have no delivery number."""
    return int(powerplays.start_delivery_number.isna().sum() + powerplays.end_delivery_number.isna().sum())


def external_id_rules(external: pd.DataFrame) -> str | None:
    unknown = sorted(set(external.source) - EXTERNAL_SOURCES)
    return f"unknown sources {unknown}, and Cricinfo ids belong in players.csv only" if unknown else None


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
                       dtype={"striker": "category", "striker_id": "category", "bowler_id": "category", "player_dismissed": "category"})
    report.record("ball file: key is unique", duplicate_keys(ball, KEY, "the ball file"))
    report.record("ball file: deliveries are numbered 1 to n in every innings", delivery_numbers(ball))
    if {"over", "ball_in_over"} <= set(ball.columns):
        report.record("ball file: over and ball_in_over identify every delivery and agree with scorecard_ball", over_and_position(ball))
    if {"wides", "noballs", "is_legal_delivery", "scorecard_ball"} <= set(ball.columns):
        report.record("ball file: is_legal_delivery matches wides and noballs, and legal deliveries have a unique scorecard_ball", legal_deliveries(ball))
    if {"wides", "striker", "striker balls faced"} <= set(ball.columns):
        report.record("ball file: balls faced is the count of non-wide rows in the innings", balls_faced(ball))
    if {"wides", "striker", "runs_off_bat", "total striker runs", "player_dismissed", "player out runs", "player out balls faced"} <= set(ball.columns):
        report.record("ball file: the striker's runs and the dismissed player's runs and balls faced match a recount", running_totals(ball))
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
    json_files = {name: pd.read_csv(out / name, low_memory=False) for name in JSON_FILE_KEYS if (out / name).exists()}
    for name, frame in json_files.items():
        report.record(f"{name}: key is unique", duplicate_keys(frame, JSON_FILE_KEYS[name], name))
    if "wickets.csv" in json_files:
        report.record("every wicket is on a delivery of the ball file", missing_references(json_files["wickets.csv"], ball, KEY, "wickets"))
        report.record("wickets.csv agrees with the ball file's first and second dismissal", wickets_agree_with_balls(ball, json_files["wickets.csv"]))
        if "wicket_fielders.csv" in json_files:
            report.record("every fielder belongs to a wicket that is caught, stumped or run out", fielders_belong_to_wickets(json_files["wickets.csv"], json_files["wicket_fielders.csv"]))
            if {"fielder_1", "fielder_1_id", "fielder_1_substitute"} <= set(ball.columns):
                report.record("fielder_1 on the ball file is the first fielder of wicket 1", ball_fielder_is_the_first_listed(ball, json_files["wicket_fielders.csv"]))
    for name in ("reviews.csv", "match_replacements.csv"):
        if name in json_files:
            report.record(f"every row of {name} is a delivery in the ball file", missing_references(json_files[name], ball, KEY, f"{name} rows"))
    if "innings.csv" in json_files:
        in_ball = ball[["match_id", "innings"]].drop_duplicates()
        report.record("innings.csv has exactly the innings of the ball file", None if len(in_ball) == len(json_files["innings.csv"]) and not missing_references(in_ball, json_files["innings.csv"], ["match_id", "innings"], "innings") else "the innings in innings.csv and in the ball file differ")
        if "powerplays.csv" in json_files:
            report.record("every powerplay is in an innings of innings.csv", missing_references(json_files["powerplays.csv"], json_files["innings.csv"], ["match_id", "innings"], "powerplay rows"))
    if "non_boundary" in ball.columns:
        report.record("non_boundary is set only on fours and sixes and never empty", non_boundary_only_on_fours_and_sixes(ball))
    if "powerplays.csv" in json_files and {"over", "ball_in_over"} <= set(ball.columns):
        report.record("every powerplay boundary is exactly the delivery it names", powerplay_bounds_are_deliveries(ball, json_files["powerplays.csv"]))
        unresolved = unresolved_powerplay_bounds(json_files["powerplays.csv"])
        if unresolved:
            report.notes.append(f"{unresolved:,} powerplay boundaries match no single delivery, so they have no delivery number")
    if "match_missing.csv" in json_files:
        report.record("match_missing.csv: kinds are known and an innings is given for powerplays only", missing_rules(json_files["match_missing.csv"]))
    for name in ("miscounted_overs.csv", "innings_absent_hurt.csv"):
        if name in json_files and "innings.csv" in json_files:
            report.record(f"every row of {name} is an innings of innings.csv", missing_references(json_files[name], json_files["innings.csv"], ["match_id", "innings"], f"{name} rows"))
    if "miscounted_overs.csv" in json_files and {"is_legal_delivery", "over"} <= set(ball.columns):
        report.record("miscounted_overs.csv agrees with the legal balls of the ball file", miscounted_agree_with_balls(ball, json_files["miscounted_overs.csv"]))
    if "player_external_ids.csv" in json_files:
        report.record("player_external_ids.csv: known sources only, no Cricinfo ids", external_id_rules(json_files["player_external_ids.csv"]))
    if "match_people.csv" in json_files:
        report.record("match_people.csv: roles are known, players have a team and officials have none", people_rules(json_files["match_people.csv"]))
    if files["matches.csv"].exists() and "match_dates.csv" in json_files and "end_date" in pd.read_csv(files["matches.csv"], nrows=0).columns:
        report.record("match_dates.csv starts and ends where matches.csv says", dates_agree_with_matches(json_files["match_dates.csv"], pd.read_csv(files["matches.csv"], usecols=["match_id", "start_date", "end_date"])))
    if files["matches.csv"].exists() and "collection" in pd.read_csv(files["matches.csv"], nrows=0).columns:
        report.record("matches.csv: collection, balls_per_over and end_date make sense", match_columns(pd.read_csv(files["matches.csv"], usecols=["collection", "balls_per_over", "start_date", "end_date"])))
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
