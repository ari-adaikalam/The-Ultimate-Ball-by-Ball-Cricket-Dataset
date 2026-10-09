import pandas as pd

from cricket_pipeline.align import CRICINFO_COLUMNS, events_text, cricinfo_frame, pair_match, readable

PROFILE_OF = {"cs_kohli": 253802, "cs_siraj": 940973}


def cricsheet(rows):
    base = {"innings": 1, "runs_off_bat": 0, "extras": 0, "striker_id": "cs_kohli", "bowler_id": "cs_siraj"}
    return pd.DataFrame([{**base, **row} for row in rows])


def raw_match(balls, players=None):
    players = players or {"1": {"objectId": 253802, "batting": ["rhb"]}, "2": {"objectId": 940973, "batting": ["rhb"]}}
    full = []
    for i, ball in enumerate(balls):
        full.append({"id": 100 + i, "innings": 1, "over": 0.1 + i / 10, "over_unique": round(0.01 * (i + 1), 2), "batter": 1, "bowler": 2,
                     "runs": 0, "total_runs": 0, "line": "OUTSIDE_OFFSTUMP", "length": "GOOD_LENGTH", "shot": "COVER_DRIVE", "control": 1,
                     "wx": 40, "wy": 220, "wz": 6, "timestamp": "2024-01-01T10:00:00.000Z", "win_probability": 55.5, "predicted_score": 160, "events": [], **ball})
    return {"innings": [{"label": "A", "balls": full}], "players": players}


def test_valid_pairs_get_the_cricinfo_columns():
    rows, report = pair_match(cricsheet([{}, {"runs_off_bat": 4}]), cricinfo_frame(raw_match([{}, {"runs": 4, "total_runs": 4}])), PROFILE_OF)
    assert report["paired"] == 2 and report["rejected"] == 0
    assert list(rows.columns[-len(CRICINFO_COLUMNS):]) == CRICINFO_COLUMNS
    assert rows.loc[0, "ball_line"] == "outside offstump" and rows.loc[0, "shot_played"] == "cover drive"
    assert rows.loc[0, "shot_control"] == "in control" and rows.loc[0, "wagon_zone"] == 6
    assert rows.loc[0, "shot_direction"] == "cover"          # zone 6 for a right-hander


def test_a_left_hander_is_mirrored_in_the_direction_and_angle():
    players = {"1": {"objectId": 253802, "batting": ["lhb"]}, "2": {"objectId": 940973, "batting": ["rhb"]}}
    rows, _ = pair_match(cricsheet([{}]), cricinfo_frame(raw_match([{}], players)), PROFILE_OF)
    assert rows.loc[0, "shot_direction"] == "mid wicket"      # the same raw zone 6 is the leg side for a left-hander
    right, _ = pair_match(cricsheet([{}]), cricinfo_frame(raw_match([{}])), PROFILE_OF)
    assert round(rows.loc[0, "wagon_angle"] + right.loc[0, "wagon_angle"], 1) == 360.0


def test_a_run_total_mismatch_leaves_the_cells_empty_instead_of_wrong():
    rows, report = pair_match(cricsheet([{"runs_off_bat": 6}]), cricinfo_frame(raw_match([{"runs": 1, "total_runs": 1}])), PROFILE_OF)
    assert report["paired"] == 0 and report["rejected"] == 1
    assert rows.loc[0, CRICINFO_COLUMNS].isna().all()


def test_a_wrong_bowler_is_rejected_but_an_unknown_player_is_not():
    wrong = {"1": {"objectId": 253802, "batting": ["rhb"]}, "2": {"objectId": 999, "batting": ["rhb"]}}
    _, report = pair_match(cricsheet([{}]), cricinfo_frame(raw_match([{}], wrong)), PROFILE_OF)
    assert report["rejected"] == 1
    _, report = pair_match(cricsheet([{}]), cricinfo_frame(raw_match([{}], wrong)), {"cs_kohli": 253802})   # bowler not in the crosswalk
    assert report["paired"] == 1


def test_an_innings_with_a_different_ball_count_is_not_trusted():
    rows, report = pair_match(cricsheet([{}, {}, {}]), cricinfo_frame(raw_match([{}, {}])), PROFILE_OF)
    assert report["innings_count_differs"] == [1] and report["paired"] == 0
    assert rows["ball_line"].isna().all()


def test_placeholder_wagon_values_stay_empty_but_the_rest_still_pairs():
    rows, report = pair_match(cricsheet([{}]), cricinfo_frame(raw_match([{"wx": 0, "wy": 0, "wz": 0}])), PROFILE_OF)
    assert report["paired"] == 1 and pd.isna(rows.loc[0, "wagon_zone"]) and rows.loc[0, "ball_line"] == "outside offstump"


def test_readable_values_and_events():
    assert readable("SHORT_OF_A_GOOD_LENGTH") == "short of a good length" and readable(None) is None
    assert events_text([{"type": "DRS_REVIEW", "isSuccessful": True}, {"type": "DROPPED_CATCH"}]) == "drs review (successful); dropped catch"
    assert events_text([]) is None


def test_super_over_innings_pair_by_their_own_innings_number():
    # Cricsheet and Cricinfo both number the Super Over innings 3 and 4, so the pairing needs no special case
    cs = pd.concat([cricsheet([{}, {}]), cricsheet([{"runs_off_bat": 4}]).assign(innings=3), cricsheet([{"runs_off_bat": 1}]).assign(innings=4)], ignore_index=True)
    raw = raw_match([{}, {}])
    raw["innings"].append({"label": "Super Over 1", "balls": [
        {"id": 500, "innings": 3, "over": 0.1, "over_unique": 0.01, "batter": 1, "bowler": 2, "runs": 4, "total_runs": 4, "line": None, "length": None, "shot": None,
         "control": None, "wx": 0, "wy": 0, "wz": 0, "timestamp": None, "win_probability": None, "predicted_score": None, "events": []},
        {"id": 501, "innings": 4, "over": 0.1, "over_unique": 0.01, "batter": 1, "bowler": 2, "runs": 1, "total_runs": 1, "line": None, "length": None, "shot": None,
         "control": None, "wx": 0, "wy": 0, "wz": 0, "timestamp": None, "win_probability": None, "predicted_score": None, "events": []}]})
    rows, report = pair_match(cs, cricinfo_frame(raw), PROFILE_OF)
    assert report["paired"] == 4 and report["rejected"] == 0 and report["innings_count_differs"] == []
    assert rows.loc[rows.innings >= 3, CRICINFO_COLUMNS].isna().all().all()     # a Super Over ball with no tracking stays empty, not guessed


def test_every_rejected_ball_is_listed_with_its_reason():
    wrong = {"1": {"objectId": 999, "batting": ["rhb"]}, "2": {"objectId": 940973, "batting": ["rhb"]}}
    _, report = pair_match(cricsheet([{"runs_off_bat": 4}, {}]), cricinfo_frame(raw_match([{"runs": 1, "total_runs": 1}, {}], wrong)), PROFILE_OF)
    assert report["rejected"] == 2 and len(report["rejected_rows"]) == 2
    assert "runs differ (cricsheet 4, cricinfo 1)" in report["rejected_rows"][0] and "striker differs" in report["rejected_rows"][0]
    assert "striker differs" in report["rejected_rows"][1] and "runs differ" not in report["rejected_rows"][1]


def test_a_super_over_ball_count_mismatch_flags_only_that_innings():
    # Like match 1485939, where Cricinfo has two balls and Cricsheet one in the third Super Over
    cs = pd.concat([cricsheet([{}]), cricsheet([{"runs_off_bat": 6}]).assign(innings=8)], ignore_index=True)
    raw = raw_match([{}])
    ball = {"id": 700, "innings": 8, "over": 0.1, "over_unique": 0.01, "batter": 1, "bowler": 2, "runs": 2, "total_runs": 2, "line": None, "length": None,
            "shot": None, "control": None, "wx": 0, "wy": 0, "wz": 0, "timestamp": None, "win_probability": None, "predicted_score": None, "events": []}
    raw["innings"].append({"label": "Super Over 3", "balls": [ball, {**ball, "id": 701, "over_unique": 0.02, "runs": 1, "total_runs": 1}]})
    rows, report = pair_match(cs, cricinfo_frame(raw), PROFILE_OF)
    assert report["innings_count_differs"] == [8] and report["paired"] == 1 and report["rejected"] == 1
    assert "innings ball count differs" in report["rejected_rows"][0]
    assert rows.loc[rows.innings == 1, "ball_line"].notna().all()


def test_an_cricinfo_innings_missing_from_cricsheet_is_flagged():
    raw = raw_match([{}])
    raw["innings"].append({"label": "Super Over 1", "balls": [{**raw["innings"][0]["balls"][0], "id": 900, "innings": 3}]})
    _, report = pair_match(cricsheet([{}]), cricinfo_frame(raw), PROFILE_OF)
    assert report["innings_count_differs"] == [3]


def two_over_match(cricinfo_overs):
    """Cricsheet holds overs 1 and 2 (6 balls each, over numbers 0.x and 1.x). Cricinfo holds the overs listed, with runs that tell the balls apart."""
    cs = cricsheet([{"ball": round(o + (b + 1) / 10, 1), "runs_off_bat": o + b % 2} for o in (0, 1) for b in range(6)])
    balls = []
    for number, count in cricinfo_overs:
        for b in range(count):
            balls.append({"over": number - 1 + (b + 1) / 10, "over_number": number, "runs": (number - 1) + b % 2, "total_runs": (number - 1) + b % 2})
    return cs, cricinfo_frame(raw_match(balls))


def test_an_over_missing_from_cricinfo_leaves_the_other_overs_paired():
    cs, cricinfo = two_over_match([(2, 6)])
    rows, report = pair_match(cs, cricinfo, PROFILE_OF)
    assert report["innings_count_differs"] == [1] and report["paired"] == 6 and report["rejected"] == 0
    assert rows.cricinfo_paired.tolist() == [False] * 6 + [True] * 6
    assert rows.loc[:5, "ball_line"].isna().all() and rows.loc[6:, "ball_line"].eq("outside offstump").all()
    assert rows.loc[6:, "cricinfo_ball_id"].tolist() == [100, 101, 102, 103, 104, 105] and rows.loc[:5, "cricinfo_ball_id"].isna().all()   # row 7 of the innings got Cricinfo's first ball


def test_an_over_with_a_different_number_of_deliveries_is_left_unpaired():
    cs, cricinfo = two_over_match([(1, 7), (2, 6)])
    rows, report = pair_match(cs, cricinfo, PROFILE_OF)
    assert report["paired"] == 6 and rows.cricinfo_paired.tolist() == [False] * 6 + [True] * 6
