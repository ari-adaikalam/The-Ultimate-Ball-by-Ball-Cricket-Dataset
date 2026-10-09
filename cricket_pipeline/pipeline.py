"""Find matches the dataset does not have yet and build their Cricsheet rows."""
import zipfile
from pathlib import Path

import pandas as pd

from cricket_pipeline import cricsheet
from cricket_pipeline.config import SOURCES, Source
from cricket_pipeline.matches import build_match_rows


def fetch_archives(download: bool = True) -> None:
    for source in SOURCES:
        if download or not cricsheet.archive_path(source).exists():
            cricsheet.download(source)


def ids_by_source() -> dict[Source, set[int]]:
    found = {}
    for source in SOURCES:
        with zipfile.ZipFile(cricsheet.archive_path(source)) as archive:
            found[source] = cricsheet.match_ids(archive)
    return found


def find_new_matches(known: set[int]) -> dict[Source, list[int]]:
    """Match ids on Cricsheet that are not in the dataset, grouped by archive."""
    new = {}
    claimed: set[int] = set()
    for source, ids in ids_by_source().items():
        # A match should sit in one archive only. First archive wins if one ever appears in two.
        fresh = sorted(ids - known - claimed)
        claimed.update(fresh)
        new[source] = fresh
    return new


def build_rows(source: Source, match_ids: list[int]) -> tuple[pd.DataFrame, dict[int, str]]:
    """Build rows for the given matches. A match that fails is reported, not skipped quietly."""
    frames = []
    failures: dict[int, str] = {}
    with zipfile.ZipFile(cricsheet.archive_path(source)) as archive:
        for match_id in match_ids:
            try:
                balls, info_lines = cricsheet.read_match(archive, match_id)
                frames.append(build_match_rows(balls, info_lines, source))
            except Exception as error:  # one bad match must not stop the whole run
                failures[match_id] = f"{type(error).__name__}: {error}"
    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return rows, failures
