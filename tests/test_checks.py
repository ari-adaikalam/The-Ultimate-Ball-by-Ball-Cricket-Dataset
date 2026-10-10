import pandas as pd

from cricket_pipeline import checks


def ball_frame(rows):
    columns = ["match_id", "innings", "delivery_number", "scorecard_ball", "over", "ball_in_over", "wides", "striker", "striker balls faced"]
    return pd.DataFrame(rows, columns=columns)


GOOD = [
    (1, 1, 1, 0.1, 0, 1, 1.0, "A", 0),
    (1, 1, 2, 0.2, 0, 2, None, "A", 1),
    (1, 1, 3, 0.3, 0, 3, None, "B", 1),
    (1, 2, 1, 0.1, 0, 1, None, "A", 1),
]


def test_a_repeated_key_is_a_problem():
    frame = ball_frame(GOOD)
    assert checks.duplicate_keys(frame, checks.KEY, "the ball file") is None
    frame.loc[1, "delivery_number"] = 1
    assert "not unique" in checks.duplicate_keys(frame, checks.KEY, "the ball file")


def test_deliveries_must_run_from_one_without_gaps():
    frame = ball_frame(GOOD)
    assert checks.delivery_numbers(frame) is None
    frame.loc[2, "delivery_number"] = 5
    assert "1 to n" in checks.delivery_numbers(frame)


def over_rows(positions, over=4, scorecard=4.1):
    return [(1, 1, i + 1, scorecard, over, p, None, "A", i + 1) for i, p in enumerate(positions)]


def test_the_tenth_delivery_of_an_over_is_told_from_the_first():
    assert checks.over_and_position(ball_frame(over_rows(range(1, 12)))) is None


def test_two_deliveries_with_the_same_over_and_position_are_a_problem():
    assert "share an over" in checks.over_and_position(ball_frame(over_rows([1, 2, 2])))


def test_the_position_must_count_on_by_one_inside_an_over_and_restart_in_the_next():
    assert "count 1, 2, 3" in checks.over_and_position(ball_frame(over_rows([1, 3])))
    rows = over_rows([1, 2]) + [(1, 1, 3, 5.1, 5, 3, None, "A", 3)]            # a new over that does not restart at 1
    assert "count 1, 2, 3" in checks.over_and_position(ball_frame(rows))
    rows = over_rows([1, 2]) + [(1, 1, 3, 5.1, 5, 1, None, "A", 3)]
    assert checks.over_and_position(ball_frame(rows)) is None


def test_over_may_not_go_backwards_and_must_agree_with_scorecard_ball():
    rows = over_rows([1]) + [(1, 1, 2, 3.1, 3, 1, None, "A", 2)]
    assert "backwards" in checks.over_and_position(ball_frame(rows))
    assert "scorecard_ball" in checks.over_and_position(ball_frame(over_rows([1, 2], over=4, scorecard=3.2)))


def test_balls_faced_does_not_count_wides_and_restarts_each_innings():
    assert checks.balls_faced(ball_frame(GOOD)) is None
    wrong = ball_frame(GOOD)
    wrong.loc[0, "striker balls faced"] = 1                 # counted the wide
    assert "non-wide" in checks.balls_faced(wrong)
    carried = ball_frame(GOOD)
    carried.loc[3, "striker balls faced"] = 3               # carried over from innings 1
    assert "non-wide" in checks.balls_faced(carried)


def totals_frame(rows):
    columns = ["match_id", "innings", "delivery_number", "striker", "wides", "runs_off_bat", "total striker runs", "player_dismissed",
               "player out runs", "player out balls faced"]
    return pd.DataFrame(rows, columns=columns)


TOTALS = [
    (1, 1, 1, "A", None, 4, 4, None, None, None),
    (1, 1, 2, "A", 1.0, 0, 4, None, None, None),
    (1, 1, 3, "B", None, 1, 1, None, None, None),
    (1, 1, 4, "B", None, 0, 1, "A", 4, 1),                  # the non striker is out, with the tally he had
    (1, 2, 1, "A", None, 6, 6, None, None, None),            # a new innings starts again at 0
]


def test_running_totals_agree_with_a_recount():
    assert checks.running_totals(totals_frame(TOTALS)) is None


def test_running_totals_catch_a_carried_or_wrong_figure():
    carried = totals_frame(TOTALS)
    carried.loc[4, "total striker runs"] = 10
    assert "total striker runs" in checks.running_totals(carried)
    wrong = totals_frame(TOTALS)
    wrong.loc[3, "player out runs"] = 5
    assert "player out runs" in checks.running_totals(wrong)
    wrong = totals_frame(TOTALS)
    wrong.loc[3, "player out balls faced"] = 2             # counted the wide
    assert "player out balls faced" in checks.running_totals(wrong)
    stray = totals_frame(TOTALS)
    stray.loc[0, "player out runs"] = 4
    assert "no dismissal" in checks.running_totals(stray)


def test_a_child_row_without_a_parent_is_a_problem():
    parent = pd.DataFrame({"match_id": [1], "innings": [1], "delivery_number": [1]})
    child = pd.DataFrame({"match_id": [1, 1], "innings": [1, 1], "delivery_number": [1, 9]})
    assert checks.missing_references(child, parent, checks.KEY, "tracking rows") == "1 tracking rows have no match in the parent file"
    assert checks.missing_references(child.iloc[:1], parent, checks.KEY, "tracking rows") is None


def test_unknown_player_ids_are_found_and_missing_ids_are_not_errors():
    ball = pd.DataFrame({"striker_id": ["a", None, "z"], "bowler_id": ["a", "a", "a"]})
    players = pd.DataFrame({"player_id": ["a"]})
    assert "1 striker or bowler ids" in checks.unknown_ids(ball, players)
    assert checks.unknown_ids(ball.iloc[:2], players) is None


def test_match_sets_and_coverage_rows_must_agree():
    ball = pd.DataFrame({"match_id": [1, 1, 2]})
    assert checks.match_sets(ball, pd.DataFrame({"match_id": [1, 2]})) is None
    assert "differ" in checks.match_sets(ball, pd.DataFrame({"match_id": [1, 3]}))
    assert checks.coverage_rows(ball, pd.DataFrame({"match_id": [1, 2], "rows": [2, 1]})) is None
    assert "differ" in checks.coverage_rows(ball, pd.DataFrame({"match_id": [1, 2], "rows": [2, 5]}))


def test_a_prediction_on_a_tracked_field_is_a_problem():
    key = {"match_id": [1], "innings": [1], "delivery_number": [1]}
    predictions = pd.DataFrame({**key, "line": ["on the stumps"], "length": [None], "shot": [None], "direction": [None]})
    tracking = pd.DataFrame({**key, "ball_line": [None], "ball_length": ["full"], "shot_played": [None], "shot_direction": [None]})
    assert checks.predictions_clear_of_tracking(predictions, tracking) is None       # different fields on the same ball is fine
    tracking["ball_line"] = ["outside offstump"]
    assert "1 predictions sit" in checks.predictions_clear_of_tracking(predictions, tracking)


def test_the_whole_run_passes_on_a_small_good_folder_and_fails_when_a_file_is_wrong(tmp_path):
    ball = ball_frame(GOOD).assign(striker_id=["a", "a", "b", "a"], bowler_id=["c", "c", "c", "c"])
    ball.to_csv(tmp_path / "ball_by_ball_data.csv", index=False)
    pd.DataFrame({"player_id": ["a", "b", "c"]}).to_csv(tmp_path / "players.csv", index=False)
    pd.DataFrame({"match_id": [1]}).to_csv(tmp_path / "matches.csv", index=False)
    pd.DataFrame({"match_id": [1], "rows": [4]}).to_csv(tmp_path / "coverage_report.csv", index=False)
    report = checks.run_checks(tmp_path)
    assert report.problems == [] and len(report.passed) >= 8
    pd.DataFrame({"match_id": [1], "rows": [9]}).to_csv(tmp_path / "coverage_report.csv", index=False)
    assert any("coverage_report" in p for p in checks.run_checks(tmp_path).problems)
    assert checks.run(tmp_path) == 1


def test_a_missing_ball_file_is_reported(tmp_path):
    assert checks.run_checks(tmp_path).problems == ["ball_by_ball_data.csv is missing"]


def legal_frame(rows):
    return pd.DataFrame(rows, columns=["match_id", "innings", "delivery_number", "scorecard_ball", "wides", "noballs", "is_legal_delivery"])


def test_the_legal_flag_must_match_wides_and_noballs_and_legal_balls_must_be_unique():
    rows = [(1, 1, 1, 0.1, 1.0, None, False), (1, 1, 2, 0.1, None, 1.0, False), (1, 1, 3, 0.1, None, None, True), (1, 1, 4, 0.2, None, None, True)]
    assert checks.legal_deliveries(legal_frame(rows)) is None
    wrong = [r[:6] + (True,) if r[0:3] == (1, 1, 1) else r for r in rows]                       # a wide marked legal
    assert "disagrees" in checks.legal_deliveries(legal_frame(wrong))
    shared = rows[:3] + [(1, 1, 4, 0.1, None, None, True)]                                       # two legal deliveries with the same scorecard_ball
    assert "share a scorecard_ball" in checks.legal_deliveries(legal_frame(shared))


def balls_with_wickets():
    columns = ["match_id", "innings", "delivery_number", "player_dismissed", "wicket_type", "other_player_dismissed", "other_wicket_type",
               "fielder_1", "fielder_1_id", "fielder_1_substitute"]
    return pd.DataFrame([
        (1, 1, 1, "A", "caught", None, None, "F", "f1", False),
        (1, 1, 2, "B (2)", "run out", "C", "retired out", "G", "g1", True),
        (1, 1, 3, None, None, None, None, None, None, None),
    ], columns=columns).astype({"fielder_1_substitute": "boolean"})


WICKETS = pd.DataFrame([
    (1, 1, 1, 1, "A", "a", "caught"), (1, 1, 2, 1, "B", "b", "run out"), (1, 1, 2, 2, "C", "c", "retired out"),
], columns=["match_id", "innings", "delivery_number", "wicket_number", "player_dismissed", "player_dismissed_id", "wicket_type"])
FIELDERS = pd.DataFrame([
    (1, 1, 1, 1, 1, "F", "f1", False), (1, 1, 2, 1, 1, "G", "g1", True), (1, 1, 2, 1, 2, "H", "h1", False),
], columns=["match_id", "innings", "delivery_number", "wicket_number", "fielder_number", "fielder", "fielder_id", "substitute"])


def test_wickets_agree_with_the_ball_file_ignoring_a_name_suffix():
    assert checks.wickets_agree_with_balls(balls_with_wickets(), WICKETS) is None


def test_a_wicket_that_differs_or_is_missing_is_reported():
    wrong = WICKETS.copy()
    wrong.loc[0, "wicket_type"] = "bowled"
    assert "differ" in checks.wickets_agree_with_balls(balls_with_wickets(), wrong)
    assert "wickets.csv has" in checks.wickets_agree_with_balls(balls_with_wickets(), WICKETS.iloc[:2])


def test_fielders_must_belong_to_a_caught_stumped_or_run_out_wicket():
    assert checks.fielders_belong_to_wickets(WICKETS, FIELDERS) is None
    bowled = WICKETS.copy()
    bowled.loc[0, "wicket_type"] = "bowled"
    assert "not caught, stumped or run out" in checks.fielders_belong_to_wickets(bowled, FIELDERS)
    orphan = FIELDERS.copy()
    orphan.loc[0, "wicket_number"] = 3
    assert "no match" in checks.fielders_belong_to_wickets(WICKETS, orphan)


def test_the_ball_fielder_is_the_first_listed_fielder_of_wicket_one():
    assert checks.ball_fielder_is_the_first_listed(balls_with_wickets(), FIELDERS) is None
    wrong = balls_with_wickets()
    wrong.loc[0, "fielder_1"] = "Z"
    assert "differs" in checks.ball_fielder_is_the_first_listed(wrong, FIELDERS)


def test_people_roles_and_teams():
    people = pd.DataFrame({"role": ["player", "umpire"], "team": ["T", None]})
    assert checks.people_rules(people) is None
    assert "unknown roles" in checks.people_rules(pd.DataFrame({"role": ["coach"], "team": [None]}))
    assert "no team" in checks.people_rules(pd.DataFrame({"role": ["player"], "team": [None]}))
    assert "official has a team" in checks.people_rules(pd.DataFrame({"role": ["umpire"], "team": ["T"]}))


def test_match_columns_are_sensible():
    good = pd.DataFrame({"collection": ["ipl", "tests"], "balls_per_over": [6, 5], "start_date": ["2020-01-01", "2020-01-02"], "end_date": ["2020-01-01", "2020-01-06"]})
    assert checks.match_columns(good) is None
    assert "collection" in checks.match_columns(good.assign(collection=["ipl", "nope"]))
    assert "balls_per_over" in checks.match_columns(good.assign(balls_per_over=[6, 7]))
    assert "ends before" in checks.match_columns(good.assign(end_date=["2019-12-31", "2020-01-06"]))


def test_non_boundary_is_only_on_fours_and_sixes_and_never_empty():
    frame = pd.DataFrame({"runs_off_bat": [4, 6, 2, 0], "non_boundary": [True, False, False, False]})
    assert checks.non_boundary_only_on_fours_and_sixes(frame) is None
    assert "not a four or a six" in checks.non_boundary_only_on_fours_and_sixes(frame.assign(non_boundary=[True, False, True, False]))
    assert "empty" in checks.non_boundary_only_on_fours_and_sixes(frame.assign(non_boundary=[True, None, False, False]))


def test_missing_data_kinds_and_innings():
    good = pd.DataFrame({"missing_type": ["reviews", "powerplays"], "innings": [None, 2]})
    assert checks.missing_rules(good) is None
    assert "unknown kinds" in checks.missing_rules(pd.DataFrame({"missing_type": ["toss"], "innings": [None]}))
    assert "does not fit" in checks.missing_rules(pd.DataFrame({"missing_type": ["reviews", "powerplays"], "innings": [1, None]}))


def test_miscounted_overs_must_match_the_legal_balls_of_the_ball_file():
    ball = pd.DataFrame({"match_id": 1, "innings": 1, "over": [0] * 7 + [1] * 6, "is_legal_delivery": True})
    assert checks.miscounted_agree_with_balls(ball, pd.DataFrame({"match_id": [1], "innings": [1], "over": [0], "balls": [7]})) is None
    assert "do not match" in checks.miscounted_agree_with_balls(ball, pd.DataFrame({"match_id": [1], "innings": [1], "over": [0], "balls": [6]}))


def test_dates_start_and_end_where_the_match_file_says():
    dates = pd.DataFrame({"match_id": [1, 1, 2], "date_number": [1, 2, 1], "date": ["2020-01-01", "2020-01-02", "2020-02-01"]})
    matches = pd.DataFrame({"match_id": [1, 2], "start_date": ["2020-01-01", "2020-02-01"], "end_date": ["2020-01-02", "2020-02-01"]})
    assert checks.dates_agree_with_matches(dates, matches) is None
    assert "differ" in checks.dates_agree_with_matches(dates, matches.assign(end_date=["2020-01-03", "2020-02-01"]))
    assert "no dates" in checks.dates_agree_with_matches(dates.iloc[:2], matches)


def test_external_ids_have_known_sources_and_no_cricinfo():
    assert checks.external_id_rules(pd.DataFrame({"source": ["opta", "pulse"]})) is None
    assert "Cricinfo" in checks.external_id_rules(pd.DataFrame({"source": ["opta", "cricinfo"]}))
