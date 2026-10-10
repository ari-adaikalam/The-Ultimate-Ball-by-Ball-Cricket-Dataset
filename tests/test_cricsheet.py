import io
import zipfile

import pytest

from cricket_pipeline import cricsheet, pipeline
from cricket_pipeline.config import Source

BALLS = (
    "match_id,season,start_date,venue,innings,ball,batting_team,bowling_team,striker,"
    "non_striker,bowler,runs_off_bat,extras,wides,noballs,byes,legbyes,penalty,"
    "wicket_type,player_dismissed,other_wicket_type,other_player_dismissed\n"
    "7,2007/08,2008-01-01,Ground,1,0.1,X,Y,A,B,C,1,0,,,,,,,,,\n"
)


def make_archive(match_ids):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("README.txt", "not a match")
        for match_id in match_ids:
            archive.writestr(f"{match_id}.csv", BALLS)
            archive.writestr(f"{match_id}_info.csv", "info,gender,male\n")
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


def test_match_ids_ignores_info_files_and_readme():
    assert cricsheet.match_ids(make_archive([7, 8])) == {7, 8}


def test_read_match_returns_rows_and_info_lines():
    balls, info_lines = cricsheet.read_match(make_archive([7]), 7)
    assert len(balls) == 1
    assert balls.loc[0, "season"] == "2007/08"  # kept as text, not parsed as a number
    assert info_lines == ["info,gender,male\n"]


def test_find_new_matches_skips_known_ids(monkeypatch):
    tests_source = Source("tests", "TEST", "Intl")
    odis_source = Source("odis", "ODI", "Intl")
    monkeypatch.setattr(pipeline, "ids_by_source", lambda: {tests_source: {1, 2, 3}, odis_source: {4}})
    new = pipeline.find_new_matches(known={1})
    assert new[tests_source] == [2, 3]
    assert new[odis_source] == [4]


def test_a_match_in_two_collections_stops_the_run_and_is_not_settled_by_order(monkeypatch):
    tests_source = Source("tests", "TEST", "Intl")
    odis_source = Source("odis", "ODI", "Intl")
    monkeypatch.setattr(pipeline, "ids_by_source", lambda: {tests_source: {1, 2, 3}, odis_source: {3, 4}})
    with pytest.raises(ValueError, match="more than one Cricsheet collection"):
        pipeline.find_new_matches(known={1})


def test_done_ids_keeps_final_answers_and_retries_blocks(tmp_path):
    import json

    from cricket_pipeline.scrape_players import done_ids

    path = tmp_path / "profiles.jsonl"
    rows = [
        {"cricinfo_id": 1, "status": 200, "fielding_styles": []},
        {"cricinfo_id": 2, "status": 404},  # the profile does not exist, so it is final
        {"cricinfo_id": 3, "status": 403},  # blocked, try again later
        {"cricinfo_id": 4, "status": 200, "error": "no __NEXT_DATA__"},
        {"cricinfo_id": 5, "status": 200},  # saved before gender, career span and styles were captured, so fetch again
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows))
    assert done_ids(path) == {1, 2}
