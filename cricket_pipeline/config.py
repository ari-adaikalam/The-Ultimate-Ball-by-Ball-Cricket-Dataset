"""Paths and the Cricsheet archives the dataset is built from."""
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CRICSHEET_URL = "https://cricsheet.org/downloads/{archive}_csv2.zip"
CRICSHEET_JSON_URL = "https://cricsheet.org/downloads/{archive}_json.zip"


@dataclass(frozen=True)
class Source:
    archive: str  # Cricsheet archive name, without the _csv2.zip suffix
    format: str
    type: str


# One archive per slice of the dataset. Using Cricsheet's own competition
# archives means no rule is needed to decide which matches belong.
SOURCES = (
    Source("tests", "TEST", "Intl"),
    Source("odis", "ODI", "Intl"),
    Source("t20s", "T20", "Intl"),
    Source("ipl", "T20", "Fran(IPL)"),
    Source("wpl", "T20", "Fran(WPL)"),
    # Added after checking Cricinfo has detailed commentary for these leagues. Every
    # match is kept, like the international ones, even where Cricinfo has no detail.
    # Cricsheet labels The Hundred as T20, so it is kept as T20 here too.
    Source("bbl", "T20", "Fran(BBL)"),
    Source("wbb", "T20", "Fran(WBBL)"),
    Source("cpl", "T20", "Fran(CPL)"),
    Source("psl", "T20", "Fran(PSL)"),
    Source("sat", "T20", "Fran(SA20)"),
    Source("ilt", "T20", "Fran(ILT20)"),
    Source("hnd", "T20", "Fran(Hundred)"),
    Source("mlc", "T20", "Fran(MLC)"),
    Source("lpl", "T20", "Fran(LPL)"),
    Source("bpl", "T20", "Fran(BPL)"),
)


def data_dir() -> Path:
    return Path(os.environ.get("CRICKET_DATA_DIR") or REPO_ROOT / "data")


def dataset_csv() -> Path:
    """The latest built ball file. `status` and `verify` use it as the list of matches the dataset already has."""
    return Path(os.environ.get("CRICKET_DATASET_CSV") or data_dir() / "output" / "ball_by_ball_data.csv")


def work_dir() -> Path:
    path = data_dir() / "work"
    path.mkdir(parents=True, exist_ok=True)
    return path
