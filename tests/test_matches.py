import pandas as pd
import pytest

from cricket_pipeline.config import Source
from cricket_pipeline.matches import (
    CRICSHEET_COLUMNS,
    RAW_COLUMNS,
    add_running_stats,
    build_match_rows,
    parse_info,
)

SOURCE = Source("ipl", "T20", "Fran(IPL)")


def make_balls(rows):
    """Build a ball-by-ball frame with only the columns a test cares about filled in."""
    frame = pd.DataFrame(rows)
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
        assert info["player_of_match.1"] == "B Singh"

    def test_single_player_of_match_leaves_second_column_empty(self):
        info = parse_info(["info,player_of_match,A Kumar\n"])
        assert info["player_of_match.1"] is None

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
    def test_striker_totals_build_up_and_wides_count_as_balls_faced(self):
        balls = make_balls([
            {"striker": "A", "runs_off_bat": 4},
            {"striker": "A", "runs_off_bat": 0},  # a wide is a row too, and counts
            {"striker": "B", "runs_off_bat": 1},
            {"striker": "A", "runs_off_bat": 6},
        ])
        result = add_running_stats(balls)
        assert result["striker balls faced"].tolist() == [1, 2, 1, 3]
        assert result["total striker runs"].tolist() == [4, 4, 1, 10]

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
