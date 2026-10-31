# Results and quality

Share of balls with each Cricinfo column filled, from `coverage_report.csv`. These are values Cricinfo recorded. The text predictions in `cricinfo_text_predictions.csv` are not counted here, and the figures after these tables give the share with predictions included.

**By era**

| Era | Balls | Line | Length | Shot | Wagon point | Win probability |
|---|---|---|---|---|---|---|
| 2001 to 2013 | 1,662,343 | 0% | 0% | 91% | 66% | 7% |
| 2014 to 2019 | 1,470,104 | 68% | 68% | 73% | 60% | 13% |
| 2020 and later | 2,719,631 | 66% | 66% | 66% | 55% | 27% |

**By competition**

| Competition | Balls | Line | Length | Shot | Wagon point | Win probability |
|---|---|---|---|---|---|---|
| Tests | 1,769,426 | 53% | 53% | 98% | 71% | 0% |
| ODIs | 1,695,099 | 42% | 42% | 80% | 65% | 5% |
| T20Is | 1,306,002 | 26% | 26% | 32% | 27% | 16% |
| IPL | 295,732 | 68% | 68% | 100% | 84% | 100% |
| BBL | 153,250 | 71% | 71% | 71% | 60% | 99% |
| WBBL | 118,656 | 48% | 48% | 47% | 41% | 15% |
| BPL | 111,232 | 53% | 53% | 53% | 44% | 42% |
| CPL | 103,717 | 84% | 84% | 83% | 68% | 37% |
| PSL | 83,799 | 78% | 78% | 78% | 65% | 79% |
| The Hundred | 75,636 | 100% | 100% | 99% | 84% | 0% |
| LPL | 32,917 | 99% | 99% | 99% | 82% | 98% |
| ILT20 | 31,407 | 98% | 98% | 98% | 80% | 88% |
| SA20 | 29,020 | 100% | 100% | 99% | 83% | 96% |
| MLC | 25,529 | 100% | 100% | 99% | 83% | 96% |
| WPL | 20,656 | 99% | 99% | 99% | 85% | 72% |

**Recorded values and availability with predictions**

For line, length, shot and direction there are two figures. Both use the same denominator, all 5,852,078 deliveries in the ball file, and each delivery counts once. A delivery is identified by `match_id`, `innings` and `delivery_number`, and no key repeats in `ball_by_ball_data.csv`, `cricinfo_tracking.csv` or `cricinfo_text_predictions.csv`.

- **Recorded** is the share of deliveries that have a value for the field in `cricinfo_tracking.csv`.
- **Recorded or predicted** is the share that have a recorded value or a value in `cricinfo_text_predictions.csv`. A prediction is only made where no value is recorded, so no delivery is in both and the recorded and predicted-only shares add up to this figure.

| Field | Recorded | Predicted, no value recorded | Recorded or predicted |
|---|---|---|---|
| Line | 47.5% (2,780,332) | 27.9% (1,634,290) | 75.4% (4,414,622) |
| Length | 47.5% (2,780,911) | 27.9% (1,633,741) | 75.4% (4,414,652) |
| Shot | 74.9% (4,383,558) | 5.2% (306,455) | 80.1% (4,690,013) |
| Direction | 59.1% (3,458,016) | 4.8% (280,142) | 63.9% (3,738,158) |

These figures are for the snapshot described under Source Credit in the [README](../README.md). No confidence cutoff is applied: every prediction in the file is counted, whatever its confidence, and the confidences are in the file for anyone who wants to set their own. `coverage_report.csv` and the tables above count recorded values only, and predictions are never in them. The combined figure says how many deliveries have a label of either kind. It is not a measure of accuracy. How often a predicted label matches what Cricinfo records is what each prediction's confidence column estimates.

Not every match has every Cricinfo field. Cricinfo did not record tracking for all matches, and coverage varies by competition and year.

- A ball has Cricinfo values only when it matched its Cricsheet ball on innings, position, runs and both players. Anything that failed is left empty. The build writes the matches with such disagreements to a local report, `review.csv`, which is not published.
- Cricsheet corrects old matches, so rows can differ between versions of the dataset.
