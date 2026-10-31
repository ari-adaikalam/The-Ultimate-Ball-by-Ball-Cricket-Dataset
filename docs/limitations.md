# Limitations and scope

- Cricsheet has no matches before 2001, so the dataset starts there.
- The ball file records at most two wickets on a delivery. `wickets.csv` has all of them. One women's T20I has a ball with ten retired out wickets.
- Not every match has every extra. Officials are missing for 438 matches, the city for 792, and powerplays for the innings of Tests and Super Overs (which have none) and for 479 other innings, mostly ODIs before July 2005. `match_missing.csv` lists what Cricsheet itself says is missing, for 954 matches. DRS reviews exist only where DRS was used.
- Cricsheet's CSV and JSON files sometimes spell a player's name differently. Names in the new files follow the ball file, and ids are the safe way to join (31 matches at the last count).
- About 4,300 matches, mostly T20Is between associate teams, have no Cricinfo tracking or commentary. They stay in the dataset with empty Cricinfo columns and show a Cricinfo count of 0 for every field in `coverage_report.csv`.
- Line and length exist from about 2014. Shot names before 2014 are coarser (for example "off side drive on front foot") than the ones after (for example "cover drive").
- Cricinfo leaves some overs out of its commentary. Balls in those overs have no row in `cricinfo_tracking.csv`.
- Super Over balls are in the main file and line up with Cricinfo's ball by ball, but Cricinfo has no line, length, shot or wagon point for them. Only 7 have a timestamp, and none has win probability.
- Wagon wheel points before 2014 are less exact: 88% of fours and sixes land beyond 0.9 of the way to the boundary, against 98% to 100% in later matches. The gap stays when only grounds that appear in both periods are compared (88% against 100%). Shot names are filled for 95% to 99% of tracked balls, depending on the era.
- `win_probability` is a prediction. At the end of the first innings it averages 64 when the side that batted first went on to win and 39 when it lost. In the second innings it ends at 100 or 0.
- The text predictions are estimates. Their accuracy is 59 to 71% depending on the field, and the 2001 to 2013 line and length predictions cannot be tested directly.
- The 4,300 matches with no Cricinfo commentary have no tracking and no predictions.
