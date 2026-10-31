# Column reference

Every file in the dataset and every column in it. The [README](../README.md) has the short version.

## The files

| File | One row per | Rows |
|---|---|---|
| `ball_by_ball_data.csv` | ball | 5,852,078 |
| `cricinfo_tracking.csv` | ball that Cricinfo tracked | 4,468,782 |
| `cricinfo_text_predictions.csv` | ball with a predicted label | 1,654,041 |
| `players.csv` | player | 9,374 |
| `matches.csv` | match | 14,585 |
| `wickets.csv` | wicket | 205,902 |
| `wicket_fielders.csv` | fielder of a wicket | 141,706 |
| `match_people.csv` | player or official in a match | 385,974 |
| `innings.csv` | innings | 30,745 |
| `powerplays.csv` | powerplay | 35,422 |
| `reviews.csv` | DRS review | 16,923 |
| `match_replacements.csv` | replacement in a match | 1,902 |
| `match_missing.csv` | item Cricsheet says is missing | 1,577 |
| `miscounted_overs.csv` | over the umpires miscounted | 395 |
| `innings_absent_hurt.csv` | batter absent hurt in an innings | 185 |
| `match_dates.csv` | date of a match | 17,683 |
| `player_external_ids.csv` | id of a person in another system | 5,653 |
| `coverage_report.csv` | match | 14,585 |

Eleven of the last twelve files come from Cricsheet's JSON downloads, which hold more than its CSV files: every wicket and who fielded it, the players and officials of each match, targets, powerplays, DRS reviews, replacements and what Cricsheet knows is missing. `player_external_ids.csv` comes from Cricsheet's people register. The ball file holds only the first fielder of a wicket, and `wickets.csv` and `wicket_fielders.csv` hold all of them.

## ball_by_ball_data.csv (50 columns)

**Ball and match position**

| Column | Meaning |
|---|---|
| `match_id` | Cricsheet match id |
| `season`, `start_date` | Season label as Cricsheet gives it, and the first day of the match |
| `innings` | The innings of the match, in the order they were batted. A Test has up to 4. A limited overs match has 1 and 2, and a Super Over adds 3 and 4, then 5 to 8 if it is tied again |
| `delivery_number` | Position of the delivery in its innings: 1 for the first, 2 for the next, and so on, with wides and no balls counted. With `match_id` and `innings` it identifies a delivery, and it joins `cricinfo_tracking.csv` |
| `over` | Over number, counted from 0, so 0 is the first over |
| `ball_in_over` | Position of the delivery in its over, counting every delivery, so it can pass 6 when the over has wides or no balls. With `over` it identifies a delivery within an innings. Cricsheet's own over.ball number is left out, because the 10th delivery of an over (4.10) reads the same as the first (4.1) |
| `scorecard_ball` | The ball as a scorecard numbers it, as over.ball. The legal deliveries are numbered 1, 2, 3 and so on in order (6 in a normal over), and a wide or no ball has the number of the legal ball that replaces it, so it is not unique. Among legal deliveries it is. This is Cricsheet's `actual_delivery` |
| `is_legal_delivery` | True unless the delivery is a wide or a no ball. Byes and leg byes are legal. The `wides` and `noballs` columns are blank when there is none, so use this and not a comparison with 0 |
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
| `runs_off_bat`, `extras` | Runs the batter scored off the bat, and runs from extras (wides, no balls, byes, leg byes and penalty added together). The team's runs on the ball are the two added. A no ball can still have runs off the bat |
| `wides`, `noballs`, `byes`, `legbyes`, `penalty` | The extras split out. `wides` includes any runs taken or a boundary on top of the wide's own run. `noballs` is the run for the no ball itself, normally 1, and runs off the bat on a no ball are in `runs_off_bat`. Byes and leg byes are not credited to the batter. Blank when there is none |
| `wicket` | 1 if a batter's innings ended on this ball, for any reason in `wicket_type`. That includes retired hurt and retired out, so filter on `wicket_type` to count only dismissals |
| `wicket_type`, `player_dismissed` | How the batter left the innings, and who it was. It can be the non striker, for example in a run out. `wicket_type` also holds retirements, which are not dismissals by the bowling side |
| `other_wicket_type`, `other_player_dismissed` | A second batter leaving the innings on the same ball, which is rare |
| `striker balls faced`, `total striker runs` | The striker's balls faced and runs off the bat so far in this innings, starting again at 0 in each innings. A wide is not a ball faced and a no ball is |
| `player out runs`, `player out balls faced` | The batter's runs and balls faced in this innings when their innings ended, on that ball. Blank on other balls |
| `non_boundary` | True for a four or six off the bat that was run and not hit to the boundary, which Cricsheet marks. A four or six with this False reached the boundary. Count boundaries with `runs_off_bat` of 4 or 6 and `non_boundary` False |
| `fielder_1`, `fielder_1_id`, `fielder_1_substitute` | The first listed fielder of the ball's first wicket: the catcher, the keeper on a stumping, or the first fielder named on a run out. Empty when no fielder is involved, or when Cricsheet records only that a substitute fielded. `wicket_fielders.csv` has every fielder |

## cricinfo_tracking.csv (18 columns)

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

## players.csv (14 columns)

`player_id` (the same value as `striker_id` and `bowler_id`), `name`, `cricinfo_id`, `full name`, `gender`, `country`, `batting style`, `bowling style`, `playing role`, `fielding style` (in practice only wicketkeeper), `first international year`, `last international year`, `major teams`, `image url`.

`image url` is a link to a picture on Cricinfo's servers. The pictures are not part of the dataset, and a link can stop working.

## cricinfo_text_predictions.csv (15 columns)

The first three columns are the key. For each of line, length, shot and direction there are three columns: the label (`line`, `length`, `shot`, `direction`), `<field>_confidence` (0 to 1) and `<field>_explicit` (1 if the commentary names the label outright, else 0). Shot labels follow the match's era: the coarser 2001 to 2013 names or the finer 2014 on names. Direction uses the same eight names as `shot_direction` in `cricinfo_tracking.csv`.

## matches.csv (38 columns)

`match_id`, `season`, `start_date`, `gender`, `event`, `format`, `type`, `venue`, `match_number`, `toss_winner`, `toss_decision`, `player_of_match`, `player_of_match_2`, `winner`, `winner_runs`, `winner_wickets`, `outcome`, then:

| Column | Meaning |
|---|---|
| `team_1`, `team_2` | The two teams, in Cricsheet's order. It does not mean the home team |
| `city`, `end_date` | City of the ground where Cricsheet has it, and the last day of the match |
| `scheduled_overs`, `balls_per_over` | Overs each innings was scheduled for (20 or 50, empty for Tests), and balls in an over (6, or 5 in some matches such as The Hundred) |
| `match_type_number` | The number of the match among all Tests, ODIs or T20Is, for internationals |
| `collection` | The Cricsheet collection: `tests`, `odis`, `t20s`, `ipl`, `wpl`, `bbl`, `wbb`, `cpl`, `psl`, `sat`, `ilt`, `hnd`, `mlc`, `lpl` or `bpl` |
| `result_method`, `eliminator` | The method that decided the result when one was used (D/L or Awarded), and the team that won the super over or bowl out that settled a tie |
| `umpire_1`, `umpire_2`, `tv_umpire`, `match_referee` | The first or common officials. `match_people.csv` has every official |
| `won_by_innings` | True if the match was won by an innings. `winner_runs` then holds the runs of the margin |
| `cricsheet_created`, `cricsheet_revision`, `cricsheet_data_version` | When Cricsheet created the match record, its revision number (which rises when the record is corrected), and the version of its data format. They let a correction be traced |
| `event_group`, `event_sub_name`, `event_stage` | The group (such as A or B), the sub-division and the stage (such as Final or Semi Final) of the event, where Cricsheet has them |

## The files from Cricsheet's JSON

Each of these is keyed so a row can be told apart. `wicket_number` is the position of the wicket in Cricsheet's list for a delivery: wicket 1 is `player_dismissed` and wicket 2 is `other_player_dismissed` in the ball file. Names are spelled as in the ball file.

| File | Key | Columns |
|---|---|---|
| `wickets.csv` | `match_id`, `innings`, `delivery_number`, `wicket_number` | `player_dismissed`, `player_dismissed_id`, `wicket_type`. Every wicket, including the second and later wickets the ball file cannot hold |
| `wicket_fielders.csv` | the wicket key and `fielder_number` | `fielder`, `fielder_id`, `substitute`. The fielders of each wicket. A fielder is empty when Cricsheet records only that a substitute fielded |
| `match_people.csv` | `match_id`, `role`, `person_number` | `team`, `person`, `person_id`. The roles are `player`, `umpire`, `tv_umpire`, `match_referee` and `reserve_umpire`. `team` is filled for players only. `person_id` joins to `players.csv` only for players who batted or bowled |
| `innings.csv` | `match_id`, `innings` | `batting_team`, `target_runs`, `target_overs`, `is_super_over`, `declared`, `penalty_runs_pre`, `penalty_runs_post`. Penalty runs awarded before or after an innings sit on no delivery, so add them to the innings total from the ball file |
| `powerplays.csv` | `match_id`, `innings`, `powerplay_number` | `type` (mandatory, batting or fielding), then for the start and the end of the powerplay the over, the position in the over and the `delivery_number` in the ball file (`start_over`, `start_ball_in_over`, `start_delivery_number`, `end_over`, `end_ball_in_over`, `end_delivery_number`), and the boundaries as Cricsheet lists them (`start_listed`, `end_listed`). A delivery is in the powerplay when its `delivery_number` lies from `start_delivery_number` to `end_delivery_number`. Cricsheet writes a boundary as over.position, so 5.11 is the 11th delivery of over 5, and a 10th delivery reads as .1. Where the listed boundary matches no single delivery the delivery number is empty (6 boundaries) |
| `reviews.csv` | `match_id`, `innings`, `delivery_number` | `review_by`, `umpire`, `umpire_id`, `batter`, `batter_id`, `decision`, `review_type`, `umpires_call` |
| `match_replacements.csv` | the delivery key and `replacement_number` | `kind`, `team`, `role`, `player_in`, `player_in_id`, `player_out`, `player_out_id`, `reason` |
| `match_missing.csv` | `match_id`, `missing_number` | `missing_type` (powerplays, reviews, player_of_match or umpires), `innings` and `powerplay_type` for powerplays. What Cricsheet says it does not have for a match, so a missing record is not read as "none happened". A powerplay type can be listed twice for an innings when two are missing |
| `miscounted_overs.csv` | `match_id`, `innings`, `over` | `balls`, `umpire`, `umpire_id`. Overs the umpires miscounted, with the legal balls the over really held (5 or 7, for example). It agrees with the ball file's legal balls in every case |
| `innings_absent_hurt.csv` | `match_id`, `innings`, `player` | `player_id`. Batters recorded as absent hurt, who are not the same as players who did not bat |
| `match_dates.csv` | `match_id`, `date_number` | `date`. Every date of a match as Cricsheet lists them, one row for each |
| `player_external_ids.csv` | `player_id`, `source`, `external_id` | A person's ids in other systems: bcci, bigbash, cricbuzz, cricheroes, crichq, cricingif, cricketarchive, cricketworld, nvplay, opta and pulse. Cricinfo ids are not in this file |
