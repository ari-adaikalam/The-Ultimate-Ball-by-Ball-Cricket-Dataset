# Design decisions

Each decision with the reason I made it. The pipeline itself is in [architecture.md](architecture.md).

## Data

| Decision | Reason |
|---|---|
| Cricsheet and Cricinfo data sit in separate files, joined on ids | Either source can be used alone, and each file has one source and one licence note |
| Join on ids and `delivery_number`, never on names or on `ball` | Names collide, and Cricsheet's ball number repeats on extras. The n-th delivery of an innings is a stable key |
| A Cricinfo ball is attached only if innings, position, total runs, striker and bowler all agree | A wrong pairing must leave an empty cell, not a wrong value. Every rejection is listed in a review report |
| When an innings has missing overs, pair over by over | Cricinfo's own data leaves some overs out, often every second one. Pairing from the start of the innings would shift every ball after the first gap |
| Only Cricinfo's own labels, with no merging | The JSON keeps GOOD_LENGTH and SHORT_OF_A_GOOD_LENGTH apart (the second is 21% of tracked balls), so merging would throw detail away. Direction names are my names for Cricinfo's eight zone numbers |
| Raw wagon wheel values stay, with derived angle, distance and in-ring columns beside them | Derived values never replace what Cricinfo recorded |
| Players' age at the match in whole years, no date of birth | About 7% of players are under 19 |
| Every match is kept, with empty Cricinfo columns where it has nothing | Dropping matches would hide how much data there is. A coverage report shows it by competition and era |
| Nothing in the main or tracking files is guessed or filled from text | Predictions are in a separate file with their own confidence |

## Capture

| Decision | Reason |
|---|---|
| A normal Chrome driven over its debugging port, with paced requests, a shared cool-down, and no stealth tools or proxies | Plain HTTP and headless browsers are refused. The scraper has to behave like a patient reader and stop on any block |
| Resumable queues and a supervisor that restarts crashed or hung workers | A full capture takes days. Finished matches stay finished |
| A first look skips matches with nothing useful, and a full recapture later checked all of them | The first look was right for 99.6% of the 4,200 skipped matches, so the skip rule is safe and saves days |
| Retries stop after three attempts | Repeat captures of a match with holes return the same balls, so more tries cannot help |

## Predictions

| Decision | Reason |
|---|---|
| Predictions live in `cricinfo_text_predictions.csv`, never in the other files | A user can ignore them entirely, and the tracked data stays exactly what Cricinfo recorded |
| Confidence is calibrated on matches the model never saw | A prediction at 0.7 should be right about 70% of the time. Calibration error is under 1 point per model |
| Two models per field: one for balls that have some other Cricinfo tracking field, one that reads the text alone | Most balls that need a prediction have no tracking field at all. A single model read those missing fields as "left alone" and gave wrong shots |
| Direction has a "none" class | Balls the batter missed have no direction. The model can decline instead of inventing one |
| No confidence floor | Every reading is written with its confidence, and users filter for themselves |
| Line and length confidences for 2001 to 2013 are lowered by 2.2 and 5.6 points | Cricinfo has no values there to test against. The amount is the largest calibration loss seen when moving between eras |
| The explicit flag comes from a reviewed phrase table | It marks predictions the commentary states outright. The label still comes from the model, which is right more often than the text label alone |
| A phrase leaves the table when Cricinfo's JSON agrees with its label under 40% of the time, or gives another label more often | A flag that says "stated outright" should not mislead |
| No bigger transformer, no ensemble | Every alternative I tried landed within a point of the simple model, so the simple one stays |

The evidence behind these is summarised in [predictions_file.md](predictions_file.md).

## Licence and storage

| Decision | Reason |
|---|---|
| The dataset is licensed ODC-BY-1.0, matching Cricsheet, and the Cricinfo files are marked as not covered | The licence cannot grant rights over data it does not own. Cricinfo is credited wherever it is used |
| Files are written one match at a time and linked, not copied, for upload | Memory stays small, and the main file is about 2.4 GB |
