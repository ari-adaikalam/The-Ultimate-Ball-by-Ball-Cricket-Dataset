# 🏏 The Ultimate Ball-by-Ball Cricket Dataset

![Cricket Dataset Banner](https://img1.hscicdn.com/image/upload/f_auto,t_ds_w_1280,q_80/lsci/db/PICTURES/CMS/325900/325966.jpg)

## Overview

Every ball of **Tests, ODIs, T20Is and twelve major T20 leagues** (IPL, WPL, BBL, WBBL, CPL, PSL, SA20, ILT20, The Hundred, MLC, LPL and BPL) in one dataset. Cricsheet supplies the facts of each ball: runs, extras, wickets and players. Cricinfo supplies how the ball was bowled and played, for the matches where it tracked it:

- **Ball Line** (e.g., outside offstump, on the stumps)
- **Ball Length** (e.g., full, good length, yorker)
- **Shot Played** (e.g., cover drive, sweep, pull)
- **Shot Direction** (e.g., mid wicket, third man) with the **wagon wheel coordinates** behind it
- **Win probability, predicted score and delivery timestamp** for every tracked ball

The two sources sit in separate files and join on ids, so either one can be used alone. Every match is in the dataset. Where Cricinfo has nothing usable for a match, its Cricinfo cells stay empty.

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
| `ball_by_ball_data.csv` | ball | 5,832,964 |
| `cricinfo_tracking.csv` | ball that Cricinfo tracked | 4,455,586 |
| `cricinfo_text_predictions.csv` | ball with a predicted label | 1,653,970 |
| `players.csv` | player | 9,344 |
| `matches.csv` | match | 14,520 |
| `coverage_report.csv` | match | 14,520 |

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

## Dataset Source

- **Ball-by-ball & match metadata**: [Cricsheet](https://cricsheet.org/), released under the [Open Data Commons Attribution License 1.0](http://opendatacommons.org/licenses/by/1.0/)
- **Ball tracking, wagon wheel and win probability** (`cricinfo_tracking.csv`), **player profiles** (`players.csv`) **and the commentary the text predictions are made from** (`cricinfo_text_predictions.csv`): [Cricinfo](https://www.cricinfo.com/)

Cricinfo's commentary text is not included in the dataset.

---

## Why I Built This

I love cricket, and I wanted the data behind how each ball is bowled and played in one table. Cricsheet records what happened on every ball. It does not record where the ball pitched, which shot was played or where it went. Cricinfo tracks those for many matches, but they sit inside its match pages, one match at a time, with no table to download.

It is also a data engineering project. Getting from those pages to a table that lines up with Cricsheet's rows meant building the capture, the pairing and the checks myself, and testing each stage. The reasons behind each choice are in [docs/design_decisions.md](docs/design_decisions.md).

## How It Works

1. **Ingest**: download the 15 Cricsheet collections and rebuild every match.
2. **Capture**: open each match's commentary page and load every over of every innings, Super Overs included. Matches with nothing useful on Cricinfo are noted and not scrolled.
3. **Pair**: attach each Cricinfo ball to its Cricsheet row. The innings, position, total runs, striker and bowler must all agree. A ball that fails any check stays empty and is listed in a review report. If Cricinfo left whole overs out, the overs it has are still paired, one over at a time.
4. **Derive**: compute the shot direction name, angle, distance to the boundary and in-ring flag from Cricinfo's wagon wheel point and the batter's hand, using Cricinfo's own zone layout. Left-handers are mirrored.
5. **Build**: write the five files, the coverage report and the review reports.

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

## Key Features

- **Two sources, two files**: the Cricsheet facts and the Cricinfo tracking are separate, so each can be used or removed on its own.
- **Joins on ids**: player and match ids join the files. Names are never a key.
- **Nothing guessed**: a missing Cricinfo value is an empty cell. No value is filled in from commentary text or from a model inside the main files.
- **Checked pairing**: every Cricinfo ball is verified against its Cricsheet row before it is attached.
- **Wagon wheel columns**: Cricinfo's raw point and zone are kept, with the angle, distance and ring flag derived from them.
- **Separate predictions**: balls with commentary but no tracking get predicted labels in their own file, each with a calibrated confidence. They never mix into the tracked data.
- **Coverage report**: for every match, how many balls have each Cricinfo column filled.

## Text Predictions

`cricinfo_text_predictions.csv` is a separate file of predictions for balls that have commentary text but no Cricinfo tracking value. It gives a predicted line, length, shot and direction, each with a confidence. Every label is one of Cricinfo's own. Nothing in the other files is filled in from it, and Cricinfo's commentary text is not published.

- **Confidence** is the chance that the label matches what Cricinfo would have recorded, calibrated on matches the model never saw. A prediction at 0.7 matched Cricinfo about 70% of the time.
- **Explicit** is 1 when the commentary names that label outright and no other, for example "full toss" or "back of a length" (which Cricinfo calls short of a good length). Those predictions are right more often.
- **Empty cells** mean Cricinfo already has a value, there is no commentary text, or, for direction, the model judges that the ball was not hit.

On held-out matches the models score 63 to 65% for line, 59 to 62% for length, 60 to 68% for shot and 65 to 71% for direction. Commentary and Cricinfo's tracking disagree often, even when the text is clear, so the confidence matters more than the label. Line and length for 2001 to 2013 have their confidences lowered by 2.2 and 5.6 points, because Cricinfo has no values there to test against.

```python
predictions = pd.read_csv("cricinfo_text_predictions.csv")
sure = predictions[(predictions.length_confidence >= 0.7) | (predictions.length_explicit == 1)]
balls = balls.merge(predictions, on=["match_id", "innings", "delivery_number"], how="left")
```

How it was built, what was tried and how it is checked: [docs/predictions_file.md](docs/predictions_file.md). The phrases behind the explicit flag: [docs/phrase_meanings.md](docs/phrase_meanings.md).

## Columns

### ball_by_ball_data.csv (43 columns)

**Ball and match position**

| Column | Meaning |
|---|---|
| `match_id` | Cricsheet match id |
| `season`, `start_date` | Season label as Cricsheet gives it, and the first day of the match |
| `innings` | 1 and 2 are the main innings. 3 and 4 (then 5 to 8) are Super Overs |
| `delivery_number` | 1 for the first delivery of the innings, 2 for the next, and so on. Wides and no balls count. Use it with `match_id` and `innings` to join `cricinfo_tracking.csv` |
| `ball` | Over and ball as over.ball, with overs counted from 0. The number repeats on extras, so it is not a key |
| `batting_team`, `bowling_team` | Team names |
| `gender`, `event`, `format`, `type` | Match labels. `event` is the competition name. `type` is Intl or Fran(league), for example Fran(IPL) |

**People**

| Column | Meaning |
|---|---|
| `striker`, `non_striker`, `bowler` | Names as Cricsheet writes them |
| `striker_id`, `bowler_id` | Cricsheet player ids. Use these to join to `players.csv` |
| `striker_age`, `bowler_age` | Age in whole years on the first day of the match. Dates of birth are not published |
| `country_striker`, `batting style_striker`, `bowling style_striker`, `playing role_striker` | From the Cricinfo profile. The same four for the bowler end in `_bowler` |

**Runs, extras and wickets (from Cricsheet)**

| Column | Meaning |
|---|---|
| `runs_off_bat`, `extras` | Runs scored by the bat and in extras on this ball |
| `wides`, `noballs`, `byes`, `legbyes`, `penalty` | The extras split out |
| `wicket` | 1 if a player was dismissed on this ball |
| `wicket_type`, `player_dismissed` | The dismissal and the player |
| `other_wicket_type`, `other_player_dismissed` | A second dismissal on the same ball, which is rare |
| `striker balls faced`, `total striker runs` | The striker's running balls and runs in the match. Every row counts as a ball faced, wides included |
| `player out runs`, `player out balls faced` | The dismissed player's runs and balls faced, on the ball they were out |

### cricinfo_tracking.csv (18 columns)

One row per ball that Cricinfo tracked, so a ball with no Cricinfo data has no row. A left join from the ball file leaves those balls empty. The first three columns are the key: `match_id`, `innings` and `delivery_number`. Within a column, an empty cell means Cricinfo had no value for that ball.

| Column | Meaning |
|---|---|
| `ball_length` | Where the ball pitched: full toss, yorker, full, good length, short of a good length, short |
| `ball_line` | outside offstump, wide outside offstump, on the stumps, down leg, wide down leg |
| `shot_played` | Cricinfo's shot name, for example cover drive, flick, defended, left alone |
| `shot_control` | in control or not in control |
| `wagon_x`, `wagon_y` | Cricinfo's wagon wheel point for where the ball went |
| `wagon_zone` | Cricinfo's zone number, 1 to 8 |
| `shot_direction` | The zone as a name: fine leg, square leg, mid wicket, mid on, mid off, cover, point, third man. Left-handers are mirrored, so cover is always the off side |
| `wagon_angle` | 0 to 360 degrees, 0 straight behind the batter, mirrored for left-handers |
| `wagon_distance` | Fraction of the way to the boundary from the centre. Can be above 1 |
| `wagon_in_ring` | True if the shot ended inside the 30 yard circle |
| `ball_timestamp` | Cricinfo's record time for the delivery, in UTC |
| `win_probability` | The batting side's chance of winning at that ball, 0 to 100, in both innings |
| `predicted_score` | Cricinfo's projected innings score at that ball |
| `ball_events` | Reviews, dropped catches and other events Cricinfo logged on the ball |

Cricinfo records no line, length, shot or wagon point for Super Over balls, so they have almost no rows here.

### players.csv (14 columns)

`player_id` (the same value as `striker_id` and `bowler_id`), `name`, `cricinfo_id`, `full name`, `gender`, `country`, `batting style`, `bowling style`, `playing role`, `fielding style` (in practice only wicketkeeper), `first international year`, `last international year`, `major teams`, `image url`.

### cricinfo_text_predictions.csv (15 columns)

The first three columns are the key. For each of line, length, shot and direction there are three columns: the label (`line`, `length`, `shot`, `direction`), `<field>_confidence` (0 to 1) and `<field>_explicit` (1 if the commentary names the label outright, else 0). Shot labels follow the match's era: the coarser 2001 to 2013 names or the finer 2014 on names. Direction uses the same eight names as `shot_direction` in `cricinfo_tracking.csv`.

### matches.csv (17 columns)

`match_id`, `season`, `start_date`, `gender`, `event`, `format`, `type`, `venue`, `match_number`, `toss_winner`, `toss_decision`, `player_of_match`, `player_of_match.1`, `winner`, `winner_runs`, `winner_wickets`, `outcome`.

## Data Preview

Six deliveries from an IPL match in 2025, with the tracking file joined on. The two sweeps scored no runs and have no direction, which is how a shot that did not connect looks in the data.

| match_id | start_date | innings | delivery_number | ball | striker | bowler | runs_off_bat | extras | ball_length | ball_line | shot_played | shot_direction | win_probability |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1473487 | 2025-05-01 | 1 | 13 | 1.7 | RG Sharma | Fazalhaq Farooqi | 0 | 0 | yorker | on the stumps | defended | cover | 44.1 |
| 1473487 | 2025-05-01 | 1 | 14 | 2.1 | RD Rickelton | M Theekshana | 1 | 0 | short of a good length | on the stumps | cover drive | cover | 43.2 |
| 1473487 | 2025-05-01 | 1 | 15 | 2.2 | RG Sharma | M Theekshana | 1 | 0 | good length | outside offstump | push | mid off | 42.3 |
| 1473487 | 2025-05-01 | 1 | 16 | 2.3 | RD Rickelton | M Theekshana | 0 | 0 | good length | down leg | slog sweep |  | 39.4 |
| 1473487 | 2025-05-01 | 1 | 17 | 2.4 | RD Rickelton | M Theekshana | 0 | 0 | full | down leg | sweep shot |  | 37.6 |
| 1473487 | 2025-05-01 | 1 | 18 | 2.5 | RD Rickelton | M Theekshana | 1 | 0 | short of a good length | on the stumps | on drive | mid on | 35.8 |

## Results & Quality

Share of balls with each Cricinfo column filled, from `coverage_report.csv`.

**By era**

| Era | Balls | Line | Length | Shot | Wagon point | Win probability |
|---|---|---|---|---|---|---|
| 2001 to 2013 | 1,662,343 | 0% | 0% | 91% | 66% | 7% |
| 2014 to 2019 | 1,470,104 | 68% | 68% | 73% | 60% | 13% |
| 2020 and later | 2,700,517 | 66% | 66% | 66% | 55% | 27% |

**By competition**

| Competition | Balls | Line | Length | Shot | Wagon point | Win probability |
|---|---|---|---|---|---|---|
| Tests | 1,769,426 | 53% | 53% | 98% | 71% | 0% |
| ODIs | 1,686,549 | 41% | 41% | 80% | 65% | 5% |
| T20Is | 1,296,050 | 26% | 26% | 32% | 27% | 16% |
| IPL | 295,732 | 68% | 68% | 100% | 84% | 100% |
| BBL | 153,250 | 71% | 71% | 71% | 60% | 99% |
| WBBL | 118,656 | 48% | 48% | 47% | 41% | 15% |
| BPL | 111,232 | 53% | 53% | 53% | 44% | 42% |
| CPL | 103,105 | 83% | 83% | 83% | 68% | 36% |
| PSL | 83,799 | 78% | 78% | 78% | 65% | 79% |
| The Hundred | 75,636 | 100% | 100% | 99% | 84% | 0% |
| LPL | 32,917 | 99% | 99% | 99% | 82% | 98% |
| ILT20 | 31,407 | 98% | 98% | 98% | 80% | 88% |
| SA20 | 29,020 | 100% | 100% | 99% | 83% | 96% |
| MLC | 25,529 | 100% | 100% | 99% | 83% | 96% |
| WPL | 20,656 | 99% | 99% | 99% | 85% | 72% |

Not every match has every Cricinfo field. Cricinfo did not record tracking for all matches, and coverage varies by competition and year.

- A ball has Cricinfo values only when it matched its Cricsheet ball on innings, position, runs and both players. Anything that failed is left empty. Matches with such disagreements are listed in `review.csv` in the project repo.
- Cricsheet corrects old matches, so rows can differ between versions of the dataset.

## Limitations / Scope

- Cricsheet has no matches before 2001, so the dataset starts there.
- About 4,200 matches, mostly T20Is between associate teams, have no Cricinfo tracking or commentary. They stay in the dataset with empty Cricinfo columns and are listed in `empty_matches.csv` in the project repo.
- Line and length exist from about 2014. Shot names before 2014 are coarser (for example "off side drive on front foot") than the ones after (for example "cover drive").
- Cricinfo leaves some overs out of its commentary. Balls in those overs have no row in `cricinfo_tracking.csv`.
- Super Over balls are in the main file and line up with Cricinfo's ball by ball, but Cricinfo has no line, length, shot or wagon point for them. Only 7 have a timestamp, and none has win probability.
- Wagon wheel points before 2014 are less exact: 88% of fours and sixes land beyond 0.9 of the way to the boundary, against 98% to 100% in later matches. The gap stays when only grounds that appear in both periods are compared (88% against 100%). Shot names are filled for 95% to 99% of tracked balls, depending on the era.
- `win_probability` is a prediction. At the end of the first innings it averages 64 when the side that batted first went on to win and 39 when it lost. In the second innings it ends at 100 or 0.
- The text predictions are estimates. Their accuracy is 59 to 71% depending on the field, and the 2001 to 2013 line and length predictions cannot be tested directly.
- The 4,200 matches with no Cricinfo commentary have no tracking and no predictions.

## License

The code is licensed under the MIT License, see the [LICENSE](LICENSE) file for details. The ball-by-ball and match data come from Cricsheet under the Open Data Commons Attribution License 1.0, so any public use of the dataset must credit Cricsheet and keep that licence notice.

`cricinfo_tracking.csv`, `cricinfo_text_predictions.csv` and the profile columns come from Cricinfo or are predicted from its commentary. That licence does not cover them. Use them for non-commercial work and credit Cricinfo.

## Contact

For any queries or contributions, feel free to reach out:

- **Ariharasudhan A**: [Email](mailto:ariadaikalam1234@gmail.com)
