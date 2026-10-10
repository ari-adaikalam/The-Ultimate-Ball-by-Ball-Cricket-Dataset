import json

import pandas as pd
import pytest

from cricket_pipeline.assemble import (
    IMAGE_PREFIX, MATCH_FILE_ONLY, MATCH_ON_EVERY_ROW, age_in_years, attach_players, load_profiles, matches_file, player_table, players_file,
    without_match_file_columns,
)


def write_profiles(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows))


def test_later_row_replaces_a_failed_one_and_failures_are_dropped(tmp_path):
    path = tmp_path / "profiles.jsonl"
    write_profiles(path, [
        {"cricinfo_id": 1, "status": 200, "error": "no __NEXT_DATA__"},
        {"cricinfo_id": 1, "status": 200, "full_name": "A Player", "country": "India"},
        {"cricinfo_id": 2, "status": 404},
    ])
    profiles = load_profiles(path)
    assert profiles["cricinfo_id"].tolist() == [1]
    assert profiles.loc[0, "full name"] == "A Player"


def test_lists_are_joined_and_image_gets_its_prefix(tmp_path):
    path = tmp_path / "profiles.jsonl"
    write_profiles(path, [{
        "cricinfo_id": 1, "status": 200, "full_name": "A", "batting_style": ["right-hand bat"],
        "bowling_style": ["right-arm medium", "legbreak"], "teams": ["India", "Delhi"],
        "playing_roles": [], "image_url": "/lsci/db/PICTURES/CMS/1/1.png",
    }])
    row = load_profiles(path).iloc[0]
    assert row["batting style"] == "right-hand bat"
    assert row["bowling style"] == "right-arm medium, legbreak"
    assert row["major teams"] == "India, Delhi"
    assert pd.isna(row["playing role"])
    assert row["image url"] == IMAGE_PREFIX + "/lsci/db/PICTURES/CMS/1/1.png"


def make_players():
    profiles = pd.DataFrame({"cricinfo_id": [10], "full name": ["Kohli"], "country": ["India"], "batting style": ["rhb"],
                             "bowling style": [None], "playing role": ["batter"], "major teams": ["India"], "image url": [None],
                             "birth_date": [pd.Timestamp("1988-11-05")], "gender": ["male"], "fielding style": [None],
                             "first international year": [2008], "last international year": [2026]})
    ids = pd.DataFrame({"identifier": ["aaa", "bbb"], "name": ["V Kohli", "A Nobody"], "cricinfo_id": ["10", None]})
    return player_table(profiles, ids)


def test_player_without_a_profile_gets_empty_columns():
    table = make_players()
    assert table.loc[table.identifier == "bbb", "full name"].isna().all()


def test_long_text_columns_stay_off_the_ball_rows_and_live_in_the_players_file():
    rows = pd.DataFrame({"striker_id": ["aaa"], "bowler_id": ["bbb"], "start_date": ["2024-01-01"]})
    result = attach_players(rows, make_players())
    for column in ("full name_striker", "major teams_bowler", "image url_striker"):
        assert column not in result.columns
    for column in ("country_striker", "batting style_striker", "bowling style_bowler", "playing role_bowler", "striker_age", "bowler_age"):
        assert column in result.columns
    file = players_file(make_players())
    assert file.columns.tolist() == ["player_id", "name", "cricinfo_id", "full name", "gender", "country", "batting style", "bowling style", "playing role",
                               "fielding style", "first international year", "last international year", "major teams", "image url"]
    assert file.loc[file.player_id == "aaa", "full name"].item() == "Kohli"
    assert len(file) == 2 and not any("birth" in c for c in file.columns)


def test_attach_keeps_row_order_and_count_and_labels_by_role():
    rows = pd.DataFrame({"striker_id": ["aaa", "bbb", "aaa"], "bowler_id": ["bbb", "aaa", None], "runs": [1, 2, 3], "start_date": ["2024-01-01"] * 3})
    result = attach_players(rows, make_players())
    assert result["runs"].tolist() == [1, 2, 3]
    assert result["country_striker"].fillna("-").tolist() == ["India", "-", "India"]
    assert result["country_bowler"].fillna("-").tolist() == ["-", "India", "-"]


def test_duplicate_identifier_is_an_error():
    profiles = pd.DataFrame({"cricinfo_id": [10], "full name": ["X"], "country": [None], "batting style": [None],
                             "bowling style": [None], "playing role": [None], "major teams": [None], "image url": [None],
                             "birth_date": [pd.NaT]})
    ids = pd.DataFrame({"identifier": ["aaa", "aaa"], "name": ["X", "X"], "cricinfo_id": ["10", "10"]})
    with pytest.raises(ValueError, match="twice"):
        player_table(profiles, ids)


def test_age_counts_whole_years_and_respects_the_birthday():
    born = pd.Series(pd.to_datetime(["1988-11-05"] * 3))
    played = pd.Series(["2024-11-04", "2024-11-05", "2025-01-01"])
    assert age_in_years(born, played).tolist() == [35, 36, 36]   # the day before the birthday, the birthday, after


def test_age_is_empty_when_a_date_is_missing():
    born = pd.Series(pd.to_datetime(["1990-01-01", None]))
    assert age_in_years(born, pd.Series(["2024-01-01", "2024-01-01"])).isna().tolist() == [False, True]


def test_attached_ages_are_there_but_the_birth_date_is_not():
    rows = pd.DataFrame({"striker_id": ["aaa"], "bowler_id": ["aaa"], "start_date": ["2024-11-05"]})
    result = attach_players(rows, make_players())
    assert result.loc[0, "striker_age"] == 36 and result.loc[0, "bowler_age"] == 36
    assert not any("birth" in column or "dob" in column for column in result.columns)


def test_loader_reads_cricinfo_birth_dates_and_ignores_impossible_ones(tmp_path):
    path = tmp_path / "profiles.jsonl"
    write_profiles(path, [
        {"cricinfo_id": 1, "status": 200, "full_name": "A", "dob": {"year": 1995, "month": 6, "date": 13}},
        {"cricinfo_id": 2, "status": 200, "full_name": "B", "dob": {"year": 1995, "month": 2, "date": 31}},
        {"cricinfo_id": 3, "status": 200, "full_name": "C"},
    ])
    profiles = load_profiles(path).set_index("cricinfo_id")
    assert profiles.loc[1, "birth_date"] == pd.Timestamp("1995-06-13")
    assert pd.isna(profiles.loc[2, "birth_date"]) and pd.isna(profiles.loc[3, "birth_date"])


def test_gender_career_years_and_styles_come_through(tmp_path):
    path = tmp_path / "profiles.jsonl"
    write_profiles(path, [
        {"cricinfo_id": 1, "status": 200, "full_name": "A", "gender": "M", "career_span": "2008 - 2026", "fielding_styles": ["wicketkeeper"]},
        {"cricinfo_id": 2, "status": 200, "full_name": "B", "gender": "F", "career_span": "2019", "fielding_styles": []},
        {"cricinfo_id": 3, "status": 200, "full_name": "C", "gender": None, "career_span": None, "fielding_styles": []},
    ])
    profiles = load_profiles(path).set_index("cricinfo_id")
    assert profiles.loc[1, "gender"] == "male" and profiles.loc[2, "gender"] == "female" and pd.isna(profiles.loc[3, "gender"])
    assert (profiles.loc[1, "first international year"], profiles.loc[1, "last international year"]) == (2008, 2026)
    assert (profiles.loc[2, "first international year"], profiles.loc[2, "last international year"]) == (2019, 2019)
    assert pd.isna(profiles.loc[3, "first international year"])
    assert profiles.loc[1, "fielding style"] == "wicketkeeper" and pd.isna(profiles.loc[2, "fielding style"])


def ball_rows(matches):
    rows = []
    for match_id, venue in matches:
        for ball in range(3):
            row = {"match_id": match_id, "ball": ball, "runs_off_bat": 1}
            row.update({c: "x" for c in MATCH_ON_EVERY_ROW})
            row.update({c: f"{c}-{match_id}" for c in MATCH_FILE_ONLY})
            row["venue"] = venue
            rows.append(row)
    return pd.DataFrame(rows)


def test_matches_file_has_one_row_per_match_with_every_match_level_column():
    rows = ball_rows([(2, "Lord's"), (1, "Eden Gardens")])
    file = matches_file(rows)
    assert file.match_id.tolist() == [1, 2]
    assert file.columns.tolist() == ["match_id", *MATCH_ON_EVERY_ROW, *MATCH_FILE_ONLY]
    assert file.loc[file.match_id == 1, "venue"].item() == "Eden Gardens"


def test_a_match_with_two_values_for_a_match_level_column_is_an_error():
    rows = ball_rows([(1, "A")])
    rows.loc[2, "venue"] = "B"
    with pytest.raises(ValueError, match="two different values"):
        matches_file(rows)


def test_ball_rows_lose_only_the_long_match_columns():
    result = without_match_file_columns(ball_rows([(1, "A")]))
    for column in MATCH_FILE_ONLY:
        assert column not in result.columns
    for column in ("match_id", "ball", "runs_off_bat", *MATCH_ON_EVERY_ROW):
        assert column in result.columns


def test_external_ids_come_from_the_register_without_cricinfo_for_the_people_in_the_dataset():
    from cricket_pipeline.assemble import external_ids_file

    register = pd.DataFrame({"identifier": ["a", "b", "c"], "key_cricbuzz": ["11", None, "33"], "key_opta": ["7.0", None, None], "key_opta_2": ["8", None, None],
                            "key_cricinfo": ["99", "98", "97"]})
    found = external_ids_file(register, {"a", "b"})
    assert found.values.tolist() == [["a", "cricbuzz", "11"], ["a", "opta", "7"], ["a", "opta", "8"]]
