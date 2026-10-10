"""Rebuild known matches from Cricsheet and diff them against the published dataset."""
import random
import zipfile

import numpy as np
import pandas as pd

from cricket_pipeline import cricsheet, dataset
from cricket_pipeline.config import SOURCES, dataset_csv
from cricket_pipeline.matches import PUBLISHED_COLUMNS
from cricket_pipeline.pipeline import build_match, ids_by_source


def _column_differs(mine: pd.Series, theirs: pd.Series) -> int:
    """Count rows that differ. Numbers compare as numbers, everything else as text."""
    mine_num = pd.to_numeric(mine, errors="coerce")
    theirs_num = pd.to_numeric(theirs, errors="coerce")
    numeric = mine_num.notna().sum() == mine.notna().sum() and theirs_num.notna().sum() == theirs.notna().sum()
    if numeric:
        both_missing = mine_num.isna() & theirs_num.isna()
        close = np.isclose(mine_num.fillna(0), theirs_num.fillna(0), equal_nan=True)
        return int((~(both_missing | (close & mine_num.notna() & theirs_num.notna()))).sum())
    left = mine.astype("string").fillna("")
    right = theirs.astype("string").fillna("")
    return int((left != right).sum())


def run(sample: int, seed: int) -> int:
    known = dataset.known_match_ids(dataset_csv())
    by_source = ids_by_source()
    owner = {match_id: source for source, ids in by_source.items() for match_id in ids}
    candidates = sorted(known & owner.keys())
    chosen = set(random.Random(seed).sample(candidates, min(sample, len(candidates))))
    print(f"{len(known)} matches in dataset, {len(candidates)} also on Cricsheet, comparing {len(chosen)}")

    # The match-level columns moved to matches.csv, so the published rows are the ball file joined to it
    in_ball_file = set(pd.read_csv(dataset_csv(), nrows=0).columns)
    matches_path = dataset_csv().with_name("matches.csv")
    in_matches_file = set(pd.read_csv(matches_path, nrows=0).columns) if matches_path.exists() else set()
    columns = [c for c in PUBLISHED_COLUMNS if c in in_ball_file or c in in_matches_file]
    unpublished = [c for c in PUBLISHED_COLUMNS if c not in columns]
    if unpublished:
        print(f"not in any published file, skipped: {unpublished}")
    theirs_all = dataset.read_matches(dataset_csv(), [c for c in columns if c in in_ball_file], chosen)
    theirs_all["match_id"] = theirs_all["match_id"].astype(int)
    match_columns = [c for c in columns if c not in in_ball_file]
    if match_columns:
        info = pd.read_csv(matches_path, usecols=["match_id", *match_columns], dtype=str)
        info["match_id"] = info["match_id"].astype(int)
        theirs_all = theirs_all.merge(info, on="match_id", how="left")

    archives = {source: zipfile.ZipFile(cricsheet.archive_path(source)) for source in SOURCES}
    json_archives = {source: zipfile.ZipFile(cricsheet.json_archive_path(source)) for source in SOURCES}
    identical, row_count_diff, mismatches = 0, [], {}
    try:
        for match_id in sorted(chosen):
            source = owner[match_id]
            mine = build_match(archives[source], json_archives[source], match_id, source)[0][columns]
            theirs = theirs_all[theirs_all["match_id"] == match_id].reset_index(drop=True)
            if len(mine) != len(theirs):
                row_count_diff.append((match_id, len(mine), len(theirs)))
                continue
            wrong = {c: _column_differs(mine[c], theirs[c]) for c in columns}
            wrong = {c: n for c, n in wrong.items() if n}
            if wrong:
                for column, count in wrong.items():
                    mismatches.setdefault(column, []).append((match_id, count))
            else:
                identical += 1
    finally:
        for archive in [*archives.values(), *json_archives.values()]:
            archive.close()

    print(f"identical: {identical}")
    print(f"different row count: {len(row_count_diff)}  e.g. {row_count_diff[:5]} (id, mine, published)")
    for column, hits in mismatches.items():
        print(f"column differs: {column!r} in {len(hits)} matches, e.g. {hits[:3]} (id, rows)")
    return 0 if not (row_count_diff or mismatches) else 1
