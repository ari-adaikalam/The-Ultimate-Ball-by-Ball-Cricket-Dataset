# 🏏 The Ultimate Ball-by-Ball Cricket Dataset

![Cricket Dataset Banner](https://img1.hscicdn.com/image/upload/f_auto,t_ds_w_1280,q_80/lsci/db/PICTURES/CMS/325900/325966.jpg)

## Overview

Every delivery of every match that Cricsheet has for **Tests, ODIs, T20Is and twelve major T20 leagues** (IPL, WPL, BBL, WBBL, CPL, PSL, SA20, ILT20, The Hundred, MLC, LPL and BPL), as of the snapshot date below, in one dataset. Cricsheet has no matches before 2001, so the dataset starts there. Cricsheet supplies the facts of each ball: runs, extras, wickets and players. Cricinfo supplies how the ball was bowled and played, for the matches where it tracked it: line, length, shot, shot direction with the wagon wheel point behind it, win probability, predicted score and delivery timestamp.

The two sources sit in separate files and join on ids, so either one can be used alone. Every match in those Cricsheet collections is in the dataset. Where Cricinfo has nothing usable for a match, its Cricinfo cells stay empty.

## The Project Involves

- **Cricsheet**: the base. All 15 collections are downloaded and every match is rebuilt from them, including Cricsheet's corrections to old matches.
- **Playwright + Chrome**: captures each match's Cricinfo commentary page in a normal Chrome window, paced and resumable, with a shared cool-down when Cricinfo slows down.
- **Python + Pandas**: pairs, derives and writes every file, one match at a time so memory stays small.
- **Cricinfo's own per-ball record**: line, length, shot, wagon wheel point, timestamp, win probability and events are read from the page's data. Commentary text is not parsed for these.
- **pytest**: tests for the pairing, the wagon wheel maths and the build, plus coverage and review reports on every build.

## Dataset

👉 **[Access the Dataset on Kaggle](https://www.kaggle.com/datasets/ariadaikalam/the-ultimate-ball-by-ball-cricket-dataset)**

| File | One row per | Rows |
|---|---|---|
| `ball_by_ball_data.csv` | ball | 5,852,078 |
| `cricinfo_tracking.csv` | ball that Cricinfo tracked | 4,468,782 |
| `cricinfo_text_predictions.csv` | ball with a predicted label | 1,654,041 |
| `players.csv` | player | 9,374 |
| `matches.csv` | match | 14,585 |
| `coverage_report.csv` | match | 14,585 |

Twelve smaller files come from Cricsheet's JSON downloads and its people register: wickets, the fielders of each wicket, the people in each match, innings, powerplays, DRS reviews, replacements, what Cricsheet says is missing, miscounted overs, batters absent hurt, match dates and ids in other systems. All files and every column are in the [column reference](docs/columns.md).

Join the files on ids, never on names. The ball file holds only the short match and player columns. The Cricinfo tracking sits in its own file, one row per tracked ball, joined on `match_id`, `innings` and `delivery_number`. Bring in the rest like this:

```python
balls = pd.read_csv("ball_by_ball_data.csv")
tracking = pd.read_csv("cricinfo_tracking.csv")
matches = pd.read_csv("matches.csv")
players = pd.read_csv("players.csv")
balls = balls.merge(tracking, on=["match_id", "innings", "delivery_number"], how="left")
balls = balls.merge(matches[["match_id", "venue", "winner"]], on="match_id")
balls = balls.merge(players[["player_id", "full name"]], left_on="striker_id", right_on="player_id")
```

## Columns

Every column of every file, and what it means, is in the [column reference](docs/columns.md).

## Source Credit

- **Ball-by-ball & match metadata**: [Cricsheet](https://cricsheet.org/), released under the [Open Data Commons Attribution License 1.0](http://opendatacommons.org/licenses/by/1.0/)
- **Ball tracking, wagon wheel and win probability** (`cricinfo_tracking.csv`), **player profiles** (`players.csv`) **and the commentary the text predictions are made from** (`cricinfo_text_predictions.csv`): [Cricinfo](https://www.cricinfo.com/)

Cricinfo's commentary text is not included in the dataset.

The files are a snapshot built from Cricsheet's CSV downloads and the people register of 9 October 2026 and its JSON downloads of 10 October 2026. On Kaggle, `manifest.json` lists every archive and file with its SHA-256 checksum and row count, and `schema.json` gives the type, key, links, range and allowed values of every column.

---

## Why I Built This

I love cricket, and I wanted the data behind how each ball is bowled and played in one table. Cricsheet records what happened on every ball. It does not record where the ball pitched, which shot was played or where it went. Cricinfo tracks those for many matches, but they sit inside its match pages, one match at a time, with no table to download.

It is also a data engineering project. Getting from those pages to a table that lines up with Cricsheet's rows meant building the capture, the pairing and the checks myself, and testing each stage. The reasons behind each choice are in [docs/design_decisions.md](docs/design_decisions.md).

## How It Works

1. **Ingest**: download the 15 Cricsheet collections and rebuild every match.
2. **Capture**: read each match's Cricinfo commentary page over by over, Super Overs included. Matches with nothing useful on Cricinfo are noted and not scrolled.
3. **Pair**: attach each Cricinfo ball to its Cricsheet row only when the innings, position, total runs, striker and bowler all agree. A ball that fails any check stays empty and is listed in a review report.
4. **Derive**: compute the shot direction name, angle, distance to the boundary and in-ring flag from Cricinfo's wagon wheel point and the batter's hand. Left-handers are mirrored.
5. **Build**: write the 18 data files and the review reports.

The pipeline diagrams are in [docs/architecture.md](docs/architecture.md), and the reasons behind each choice are in [docs/design_decisions.md](docs/design_decisions.md).

## Build the Cricsheet Part Yourself

The Cricsheet files need no scraping. On a fresh clone this takes a few minutes (about one for the ingest and three for the build, plus the download):

```
pip install -e ".[dev]"
python -m cricket_pipeline ingest
python -m cricket_pipeline player-ids
python -m cricket_pipeline build
```

The files land in `data/output/`, with the Cricinfo columns left empty. The Cricinfo capture is a separate step (`python -m cricket_pipeline capture`) that drives a normal Chrome window, paces its requests and uses no stealth tools or proxies.

## Text Predictions

`cricinfo_text_predictions.csv` holds predicted line, length, shot and direction for balls that have commentary text but no Cricinfo tracking value, each with a confidence from 0 to 1. Every label is one of Cricinfo's own, nothing in the other files is filled in from it, and Cricinfo's commentary text is not published. On held-out matches the models score 59 to 71% depending on the field, so the confidence matters more than the label. How it was built and checked is in [docs/predictions_file.md](docs/predictions_file.md), the accuracy by label in [docs/predictions_per_class.md](docs/predictions_per_class.md), and the phrases behind the explicit flag in [docs/phrase_meanings.md](docs/phrase_meanings.md).

## Data Preview

Six deliveries from an IPL match in 2025, with the tracking file joined on. The first is the 7th delivery of its over, because an earlier wide in that over counts as a delivery, and a scorecard calls it 1.6. The two sweeps scored no runs and have no direction, which is how a shot that did not connect looks in the data.

| match_id | start_date | innings | delivery_number | over | ball_in_over | scorecard_ball | striker | bowler | runs_off_bat | extras | ball_length | ball_line | shot_played | shot_direction | win_probability |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1473487 | 2025-05-01 | 1 | 13 | 1 | 7 | 1.6 | RG Sharma | Fazalhaq Farooqi | 0 | 0 | yorker | on the stumps | defended | cover | 44.1 |
| 1473487 | 2025-05-01 | 1 | 14 | 2 | 1 | 2.1 | RD Rickelton | M Theekshana | 1 | 0 | short of a good length | on the stumps | cover drive | cover | 43.2 |
| 1473487 | 2025-05-01 | 1 | 15 | 2 | 2 | 2.2 | RG Sharma | M Theekshana | 1 | 0 | good length | outside offstump | push | mid off | 42.3 |
| 1473487 | 2025-05-01 | 1 | 16 | 2 | 3 | 2.3 | RD Rickelton | M Theekshana | 0 | 0 | good length | down leg | slog sweep |  | 39.4 |
| 1473487 | 2025-05-01 | 1 | 17 | 2 | 4 | 2.4 | RD Rickelton | M Theekshana | 0 | 0 | full | down leg | sweep shot |  | 37.6 |
| 1473487 | 2025-05-01 | 1 | 18 | 2 | 5 | 2.5 | RD Rickelton | M Theekshana | 1 | 0 | short of a good length | on the stumps | on drive | mid on | 35.8 |

## Results & Quality

Share of balls with each Cricinfo column filled, by era, from `coverage_report.csv`. These are values Cricinfo recorded, and the text predictions are not counted. The competition by competition figures and the share with predictions included are in [docs/results_and_quality.md](docs/results_and_quality.md).

| Era | Balls | Line | Length | Shot | Wagon point | Win probability |
|---|---|---|---|---|---|---|
| 2001 to 2013 | 1,662,343 | 0% | 0% | 91% | 66% | 7% |
| 2014 to 2019 | 1,470,104 | 68% | 68% | 73% | 60% | 13% |
| 2020 and later | 2,719,631 | 66% | 66% | 66% | 55% | 27% |

## Limitations / Scope

What the dataset leaves out, and where the Cricinfo fields are thin or less exact, is in [docs/limitations.md](docs/limitations.md).

## Citation

Ari Adaikalam. (2026). The Ultimate Ball-by-Ball Cricket Dataset [Dataset]. Kaggle. https://doi.org/10.34740/kaggle/ds/7579263

## License

Each part has its own source and terms.

| Part | Source | Terms |
|---|---|---|
| Pipeline code in this repository | Ari Adaikalam | MIT, see [LICENSE](LICENSE). It covers the code only |
| Ball and match data (`ball_by_ball_data.csv`, `matches.csv`, and the twelve files from Cricsheet's JSON downloads and people register) | Cricsheet | [Open Data Commons Attribution License 1.0](http://opendatacommons.org/licenses/by/1.0/). Any public use must credit Cricsheet and keep that licence notice |
| Tracking data (`cricinfo_tracking.csv`) | Cricinfo | Not covered by the other terms in this table. Shared for non-commercial use with credit to Cricinfo, and Cricinfo's terms apply to your use of it |
| Player profile columns (`players.csv`, and the player columns on ball rows) | Cricinfo | The same as the tracking data |
| Predicted labels (`cricinfo_text_predictions.csv`) | A model, from Cricinfo's commentary | The same as the tracking data |
| Commentary text | Cricinfo | Not included in the dataset |

If you hold rights to any of this and want it removed or changed, contact me through GitHub or Kaggle and I will act on it promptly.

## Contact

For any queries or contributions, feel free to reach out:

- **Ari Adaikalam**: [Email](mailto:ariadaikalam1234@gmail.com)
