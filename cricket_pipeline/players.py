"""Work out which players need a Cricinfo profile."""
import pandas as pd

from cricket_pipeline import cricsheet
from cricket_pipeline.config import SOURCES, data_dir, work_dir

CRICINFO_ID_COLUMNS = ["key_cricinfo", "key_cricinfo_2", "key_cricinfo_3"]


def players_dir():
    path = data_dir() / "players"
    path.mkdir(parents=True, exist_ok=True)
    return path


def collect_player_ids() -> pd.DataFrame:
    """Every striker and bowler in the built matches, with their Cricinfo player id.

    Joined by Cricsheet identifier, never by name, because two real players can
    share a name.
    """
    seen = []
    for source in SOURCES:
        rows = pd.read_csv(
            work_dir() / f"cricsheet_{source.archive}.csv",
            usecols=["striker", "striker_id", "bowler", "bowler_id"],
        )
        seen.append(rows[["striker_id", "striker"]].set_axis(["identifier", "name"], axis=1))
        seen.append(rows[["bowler_id", "bowler"]].set_axis(["identifier", "name"], axis=1))
    players = pd.concat(seen).dropna(subset=["identifier"]).drop_duplicates("identifier")

    register = pd.read_csv(cricsheet.download_people(), dtype=str)
    # Some players have more than one Cricinfo id on record. The first listed one is used.
    register["cricinfo_id"] = register[CRICINFO_ID_COLUMNS].bfill(axis=1).iloc[:, 0]
    players = players.merge(register[["identifier", "cricinfo_id"]], on="identifier", how="left")
    return players.sort_values("identifier").reset_index(drop=True)


def write_player_ids() -> pd.DataFrame:
    players = collect_player_ids()
    players.to_csv(players_dir() / "player_ids.csv", index=False)
    return players
