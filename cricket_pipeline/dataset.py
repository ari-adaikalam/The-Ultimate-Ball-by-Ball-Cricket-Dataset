"""Read from the published dataset CSV."""
from pathlib import Path

import pandas as pd


def known_match_ids(path: Path) -> set[int]:
    """Match ids already in the built ball file. A first run has no file yet, so every match counts as new."""
    if not path.exists():
        return set()
    ids = pd.read_csv(path, usecols=["match_id"])["match_id"]
    return set(ids.dropna().astype(int))


def read_matches(path: Path, columns: list[str], match_ids: set[int]) -> pd.DataFrame:
    """Read only the rows of some matches. The file is several GB, so it is read in chunks."""
    kept = []
    # Everything is read as text so the caller decides how to compare values
    for chunk in pd.read_csv(path, usecols=columns, dtype=str, chunksize=500_000):
        kept.append(chunk[chunk["match_id"].astype(int).isin(match_ids)])
    return pd.concat(kept, ignore_index=True)
