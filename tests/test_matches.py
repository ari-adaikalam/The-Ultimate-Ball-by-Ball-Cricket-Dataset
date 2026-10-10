import pandas as pd
import pytest

from cricket_pipeline.config import Source
from cricket_pipeline.matches import (
    CRICSHEET_COLUMNS,
    RAW_COLUMNS,
    add_ball_columns,
    add_running_stats,
    build_match_rows,
    parse_info,
    split_ball,
)

SOURCE = Source("ipl", "T20", "Fran(IPL)")


def make_balls(rows):
    """Build a ball-by-ball frame with only the columns a test cares about filled in."""
    frame = pd.DataFrame(rows)
    if "innings" not in frame.columns:
        frame["innings"] = 1
    for column in RAW_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame["runs_off_bat"] = frame["runs_off_bat"].astype(int)
    return frame[RAW_COLUMNS]


class TestParseInfo:
    def test_reads_wanted_fields_and_ignores_the_rest(self):
        info = parse_info([
            "version,2.0.0\n",
            "info,gender,male\n",
            "info,event,Indian Premier League\n",
            "info,toss_winner,Mumbai Indians\n",
            "info,venue,Wankhede Stadium\n",
        ])
        assert info["gender"] == "male"
        assert info["event"] == "Indian Premier League"
        assert info["toss_winner"] == "Mumbai Indians"
        assert "venue" not in info

    def test_value_with_commas_and_quotes_is_kept_whole(self):
        info = parse_info(['info,event,"Tour of England, Scotland and Wales"\n'])
        assert info["event"] == "Tour of England, Scotland and Wales"

    def test_joint_player_of_match_fills_the_second_column(self):
        info = parse_info([
            "info,player_of_match,A Kumar\n",
            "info,player_of_match,B Singh\n",
        ])
        assert info["player_of_match"] == "A Kumar"
        assert info["player_of_match_2"] == "B Singh"

    def test_single_player_of_match_leaves_second_column_empty(self):
        info = parse_info(["info,player_of_match,A Kumar\n"])
        assert info["player_of_match_2"] is None

    def test_missing_fields_are_none(self):
        info = parse_info(["info,gender,female\n"])
        assert info["winner"] is None
        assert info["outcome"] is None

    def test_numbers_become_floats_but_text_is_not_dropped(self):
        info = parse_info([
            "info,match_number,9\n",
            "info,winner_runs,36\n",
            "info,winner_wickets,Qualifier 1\n",
        ])
        assert info["match_number"] == 9.0
        assert info["winner_runs"] == 36.0
        assert info["winner_wickets"] == "Qualifier 1"


class TestRunningStats:
    def test_striker_totals_build_up_and_a_wide_is_not_a_ball_faced(self):
        balls = make_balls([
            {"striker": "A", "runs_off_bat": 4},
            {"striker": "A", "runs_off_bat": 0, "wides": 1},  # a wide is a row, but not a ball faced
            {"striker": "B", "runs_off_bat": 1},
            {"striker": "A", "runs_off_bat": 6},
        ])
        result = add_running_stats(balls)
        assert result["striker balls faced"].tolist() == [1, 1, 1, 2]
        assert result["total striker runs"].tolist() == [4, 4, 1, 10]

    def test_a_no_ball_and_byes_are_balls_faced(self):
        balls = make_balls([
            {"striker": "A", "runs_off_bat": 0, "noballs": 1},
            {"striker": "A", "runs_off_bat": 0, "byes": 2},
            {"striker": "A", "runs_off_bat": 0, "legbyes": 1},
        ])
        assert add_running_stats(balls)["striker balls faced"].tolist() == [1, 2, 3]

    def test_a_wide_first_ball_gives_a_batter_zero_balls_faced(self):
        balls = make_balls([{"striker": "A", "runs_off_bat": 0, "wides": 1}])
        assert add_running_stats(balls)["striker balls faced"].tolist() == [0]

    def test_totals_start_again_in_each_innings(self):
        balls = make_balls([
            {"innings": 1, "striker": "A", "runs_off_bat": 50},
            {"innings": 1, "striker": "A", "runs_off_bat": 0, "player_dismissed": "A"},
            {"innings": 3, "striker": "A", "runs_off_bat": 4},
            {"innings": 3, "striker": "A", "runs_off_bat": 0, "player_dismissed": "A"},
        ])
        result = add_running_stats(balls)
        assert result["striker balls faced"].tolist() == [1, 2, 1, 2]
        assert result["total striker runs"].tolist() == [50, 50, 4, 4]
        assert result.loc[1, "player out runs"] == 50 and result.loc[3, "player out runs"] == 4
        assert result.loc[3, "player out balls faced"] == 2

    def test_a_player_stumped_off_a_wide_keeps_the_balls_faced_so_far(self):
        balls = make_balls([
            {"striker": "A", "runs_off_bat": 1},
            {"striker": "A", "runs_off_bat": 0, "wides": 1, "player_dismissed": "A"},
        ])
        result = add_running_stats(balls)
        assert result.loc[1, "player out balls faced"] == 1

    def test_dismissed_striker_gets_their_totals_including_that_ball(self):
        balls = make_balls([
            {"striker": "A", "runs_off_bat": 2},
            {"striker": "A", "runs_off_bat": 0, "player_dismissed": "A"},
        ])
        result = add_running_stats(balls)
        assert result["wicket"].tolist() == [0, 1]
        assert result.loc[1, "player out runs"] == 2
        assert result.loc[1, "player out balls faced"] == 2

    def test_run_out_non_striker_gets_the_totals_they_had_so_far(self):
        balls = make_balls([
            {"striker": "A", "runs_off_bat": 3},
            {"striker": "B", "runs_off_bat": 1},
            {"striker": "B", "runs_off_bat": 0, "player_dismissed": "A"},
        ])
        result = add_running_stats(balls)
        assert result.loc[2, "player out runs"] == 3
        assert result.loc[2, "player out balls faced"] == 1

    def test_non_wicket_rows_have_no_dismissal_totals(self):
        balls = make_balls([
            {"striker": "A", "runs_off_bat": 1},
            {"striker": "A", "runs_off_bat": 0, "player_dismissed": "A"},
            {"striker": "B", "runs_off_bat": 2},
        ])
        result = add_running_stats(balls)
        assert pd.isna(result.loc[0, "player out runs"])
        assert pd.isna(result.loc[2, "player out runs"])

    def test_input_frame_is_not_changed(self):
        balls = make_balls([{"striker": "A", "runs_off_bat": 1}])
        add_running_stats(balls)
        assert "wicket" not in balls.columns


class TestBuildMatchRows:
    def balls(self):
        return make_balls([
            {"match_id": 1, "striker": "A", "runs_off_bat": 4, "ball": 0.1},
            {"match_id": 1, "striker": "A", "runs_off_bat": 0, "ball": 0.2, "player_dismissed": "A"},
        ])

    def test_columns_come_out_in_published_order(self):
        rows = build_match_rows(self.balls(), ["info,gender,male\n"], SOURCE)
        assert rows.columns.tolist() == CRICSHEET_COLUMNS

    def test_format_and_type_come_from_the_source(self):
        rows = build_match_rows(self.balls(), [], SOURCE)
        assert set(rows["format"]) == {"T20"}
        assert set(rows["type"]) == {"Fran(IPL)"}

    def test_match_info_is_repeated_on_every_row(self):
        rows = build_match_rows(self.balls(), ["info,toss_winner,Mumbai Indians\n"], SOURCE)
        assert rows["toss_winner"].tolist() == ["Mumbai Indians", "Mumbai Indians"]

    def test_missing_raw_column_is_an_error_not_a_silent_gap(self):
        balls = self.balls().drop(columns=["venue"])
        with pytest.raises(ValueError, match="venue"):
            build_match_rows(balls, [], SOURCE)


class TestRegistry:
    def test_names_map_to_identifiers_even_with_a_comma_in_the_name(self):
        from cricket_pipeline.matches import parse_registry

        registry = parse_registry([
            "info,registry,people,V Kohli,ba607b88\n",
            'info,registry,people,"Smith, J",1234abcd\n',
            "info,player,India,V Kohli\n",
        ])
        assert registry == {"V Kohli": "ba607b88", "Smith, J": "1234abcd"}

    def test_ids_are_added_for_striker_and_bowler(self):
        balls = make_balls([{"match_id": 1, "striker": "A", "bowler": "C", "runs_off_bat": 1}])
        rows = build_match_rows(
            balls,
            ["info,registry,people,A,aaaa1111\n", "info,registry,people,C,cccc3333\n"],
            SOURCE,
        )
        assert rows.loc[0, "striker_id"] == "aaaa1111"
        assert rows.loc[0, "bowler_id"] == "cccc3333"

    def test_player_missing_from_registry_gets_no_id_instead_of_an_error(self):
        balls = make_balls([{"match_id": 1, "striker": "A", "bowler": "C", "runs_off_bat": 1}])
        rows = build_match_rows(balls, [], SOURCE)
        assert pd.isna(rows.loc[0, "striker_id"])


class TestBallColumns:
    def test_the_over_and_position_come_from_the_text_so_the_tenth_ball_is_not_the_first(self):
        assert split_ball("4.1") == (4, 1)
        assert split_ball("4.10") == (4, 10)
        assert split_ball("0.11") == (0, 11)
        assert split_ball("14.6") == (14, 6)

    def test_an_unreadable_ball_gives_gaps_not_an_error(self):
        assert split_ball(None) == (None, None)
        assert split_ball("nan") == (None, None)

    def test_over_position_and_scorecard_ball_are_added_and_ball_stays_a_number(self):
        balls = make_balls([
            {"ball": "0.1", "actual_delivery": "0.1", "wides": 1, "runs_off_bat": 0},
            {"ball": "0.2", "actual_delivery": "0.1", "runs_off_bat": 0},
            {"ball": "0.9", "actual_delivery": "0.5", "runs_off_bat": 0},
            {"ball": "0.10", "actual_delivery": "0.5", "runs_off_bat": 0},
        ])
        result = add_ball_columns(balls)
        assert result["over"].tolist() == [0, 0, 0, 0]
        assert result["ball_in_over"].tolist() == [1, 2, 9, 10]
        assert result["scorecard_ball"].tolist() == [0.1, 0.1, 0.5, 0.5]
        assert result["ball"].tolist() == [0.1, 0.2, 0.9, 0.1]        # the number Cricsheet writes, which is why it is not a key

    def test_a_wide_and_a_no_ball_are_not_legal_and_byes_are(self):
        balls = make_balls([
            {"ball": "0.1", "actual_delivery": "0.1", "wides": 1, "runs_off_bat": 0},
            {"ball": "0.2", "actual_delivery": "0.1", "noballs": 1, "runs_off_bat": 0},
            {"ball": "0.3", "actual_delivery": "0.1", "byes": 2, "runs_off_bat": 0},
            {"ball": "0.4", "actual_delivery": "0.2", "legbyes": 1, "runs_off_bat": 0},
            {"ball": "0.5", "actual_delivery": "0.3", "runs_off_bat": 4},
        ])
        assert add_ball_columns(balls)["is_legal_delivery"].tolist() == [False, False, True, True, True]

    def test_every_delivery_of_an_innings_gets_a_different_over_and_position(self):
        text = ["0.1", "0.2", "0.9", "0.10", "0.11", "1.1", "1.2"]
        balls = make_balls([{"ball": t, "actual_delivery": "0.1", "runs_off_bat": 0} for t in text])
        result = add_ball_columns(balls)
        assert not result.duplicated(["over", "ball_in_over"]).any()


def test_non_boundary_is_true_only_where_cricsheet_marks_a_run_four_or_six_and_never_empty():
    balls = make_balls([{"ball": "0.1", "runs_off_bat": 4, "actual_delivery": "0.1"}, {"ball": "0.2", "runs_off_bat": 4, "actual_delivery": "0.2"}])
    balls["non_boundary"] = ["true", None]
    rows = build_match_rows(balls, ["info,gender,male\n"], SOURCE)
    assert rows["non_boundary"].tolist() == [True, False] and rows["non_boundary"].dtype == bool
    assert build_match_rows(balls.drop(columns="non_boundary"), ["info,gender,male\n"], SOURCE)["non_boundary"].tolist() == [False, False]       # an older file with no such column
