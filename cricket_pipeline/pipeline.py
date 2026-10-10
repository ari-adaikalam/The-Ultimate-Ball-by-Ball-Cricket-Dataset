"""Find matches the dataset does not have yet and build their Cricsheet rows."""
import zipfile
from pathlib import Path

import pandas as pd

from cricket_pipeline import cricsheet, cricsheet_json
from cricket_pipeline.config import SOURCES, Source
from cricket_pipeline.matches import CRICSHEET_COLUMNS, add_fielder_columns, build_match_rows, parse_registry


def fetch_archives(download: bool = True) -> None:
    """The CSV archive gives the ball rows and the JSON archive of the same collection gives what the CSV leaves out."""
    for source in SOURCES:
        if download or not cricsheet.archive_path(source).exists():
            cricsheet.download(source)
        if download or not cricsheet.json_archive_path(source).exists():
            cricsheet.download(source, json=True)


def ids_by_source() -> dict[Source, set[int]]:
    found = {}
    for source in SOURCES:
        with zipfile.ZipFile(cricsheet.archive_path(source)) as archive:
            found[source] = cricsheet.match_ids(archive)
    return found


def find_new_matches(known: set[int]) -> dict[Source, list[int]]:
    """Match ids on Cricsheet that are not in the dataset, grouped by archive."""
    new, owner = {}, {}
    for source, ids in ids_by_source().items():
        for match_id in ids:
            owner.setdefault(match_id, []).append(source.archive)
        new[source] = sorted(ids - known)
    shared = {match_id: archives for match_id, archives in owner.items() if len(archives) > 1}
    if shared:
        # `collection` holds one value per match, so a match in two collections needs a decision and is not settled by order
        raise ValueError(f"{len(shared)} matches sit in more than one Cricsheet collection, for example {dict(list(shared.items())[:3])}")
    return new


def build_match(archive: zipfile.ZipFile, json_archive: zipfile.ZipFile, match_id: int, source: Source) -> tuple[pd.DataFrame, dict[str, list[dict]]]:
    """The ball rows of one match and the rows of every table the JSON adds. The JSON must describe the same deliveries as the CSV."""
    balls, info_lines = cricsheet.read_match(archive, match_id)
    match = cricsheet.read_json_match(json_archive, match_id)
    rows = build_match_rows(balls, info_lines, source)
    registry = parse_registry(info_lines)
    problems, notes = cricsheet_json.check_against_rows(match, rows, registry)
    if problems:
        raise ValueError("the JSON and the CSV disagree: " + "; ".join(problems))
    tables = cricsheet_json.extras(match, match_id, source.archive, registry)
    tables["notes"] += [{"match_id": match_id, "collection": source.archive, "note": note} for note in notes]
    tables["wickets"] = cricsheet_json.spell_like_the_ball_rows(tables["wickets"], rows)
    rows = add_fielder_columns(rows, cricsheet_json.first_fielders(tables["wicket_fielders"]))[CRICSHEET_COLUMNS]
    return rows, tables


def build_rows(source: Source, match_ids: list[int]) -> tuple[pd.DataFrame, dict[int, str], dict[str, pd.DataFrame]]:
    """Build rows for the given matches. A match that fails is reported, not skipped quietly."""
    frames = []
    failures: dict[int, str] = {}
    collected: dict[str, list[dict]] = {name: [] for name in cricsheet_json.TABLE_COLUMNS}
    collected["notes"] = []
    with zipfile.ZipFile(cricsheet.archive_path(source)) as archive, zipfile.ZipFile(cricsheet.json_archive_path(source)) as json_archive:
        for match_id in match_ids:
            try:
                rows, tables = build_match(archive, json_archive, match_id, source)
                frames.append(rows)
                for name, found in tables.items():
                    collected[name].extend(found)
            except Exception as error:  # one bad match must not stop the whole run
                failures[match_id] = f"{type(error).__name__}: {error}"
    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    columns = {**cricsheet_json.TABLE_COLUMNS, "notes": ["match_id", "collection", "note"]}
    tables = {name: pd.DataFrame(found, columns=columns[name]) for name, found in collected.items()}
    return rows, failures, tables
