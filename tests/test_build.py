import pandas as pd
import pytest

from cricket_pipeline import build
from cricket_pipeline.capture_queue import save_raw
from cricket_pipeline.matches import CRICSHEET_COLUMNS


@pytest.fixture
def data_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_DATA_DIR", str(tmp_path))
    return tmp_path


def cricsheet_rows(match_id, balls=3, venue="Ground A", start="2024-05-01"):
    rows = []
    for ball in range(balls):
        row = {c: None for c in CRICSHEET_COLUMNS}
        row.update({
            "match_id": match_id, "season": "2024", "start_date": start, "venue": venue, "innings": 1, "ball": round(0.1 * (ball + 1), 1),
            "batting_team": "A", "bowling_team": "B", "striker": "V Kohli", "striker_id": "cs_kohli", "non_striker": "X", "bowler": "J Anderson",
            "bowler_id": "cs_anderson", "runs_off_bat": 1, "extras": 0, "wicket": 0, "gender": "male", "event": "Test League", "match_number": 4,
            "toss_winner": "A", "toss_decision": "bat", "winner": "A", "winner_runs": 12, "format": "T20", "type": "Fran(IPL)",
        })
        rows.append(row)
    return rows


def write_inputs(data_folder, matches):
    work = data_folder / "work"; work.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([r for m in matches for r in cricsheet_rows(*m)]).to_csv(work / "cricsheet_ipl.csv", index=False)
    players = data_folder / "players"; players.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"identifier": ["cs_kohli", "cs_anderson"], "name": ["V Kohli", "J Anderson"], "cricinfo_id": ["253802", "8608"]}).to_csv(players / "player_ids.csv", index=False)


def capture_for(match_id, balls=3):
    ball = lambda i: {"id": 10 + i, "innings": 1, "over": 0.1 * (i + 1), "over_unique": round(0.01 * (i + 1), 2), "batter": 1, "bowler": 2, "runs": 1,
                      "total_runs": 1, "line": "ON_THE_STUMPS", "length": "FULL", "shot": "FLICK", "control": 1, "wx": 240, "wy": 190, "wz": 3,
                      "timestamp": "2024-05-01T10:00:00.000Z", "win_probability": 40.5, "predicted_score": 150, "events": []}
    return {"match_id": match_id, "innings": [{"label": "A", "complete": True, "balls": [ball(i) for i in range(balls)]}],
            "players": {"1": {"objectId": 253802, "batting": ["rhb"]}, "2": {"objectId": 8608, "batting": ["lhb"]}}}


def test_iter_matches_keeps_a_match_whole_when_it_spans_two_chunks(data_folder, monkeypatch):
    write_inputs(data_folder, [(1, 3), (2, 3), (3, 2)])
    monkeypatch.setattr(build, "CHUNK_ROWS", 4)
    sizes = [(int(m.match_id.iloc[0]), len(m)) for m in build.iter_matches(data_folder / "work" / "cricsheet_ipl.csv")]
    assert sizes == [(1, 3), (2, 3), (3, 2)]


def test_build_writes_the_three_files_with_the_planned_columns(data_folder):
    write_inputs(data_folder, [(1, 3), (2, 3, "Ground B")])
    save_raw(1, capture_for(1))
    totals = build.build(archives=["ipl"])
    out = data_folder / "output"
    main = pd.read_csv(out / "ball_by_ball_data.csv")
    assert totals["rows"] == 6 and totals["matches"] == 2 and totals["captured"] == 1
    assert main.columns.tolist() == build.FINAL_COLUMNS and len(build.FINAL_COLUMNS) == 50
    assert "venue" not in main.columns and "winner" not in main.columns
    assert not set(build.CRICINFO_COLUMNS) & set(main.columns)          # the tracking lives only in its own file
    matches = pd.read_csv(out / "matches.csv")
    assert matches.match_id.tolist() == [1, 2] and matches.venue.tolist() == ["Ground A", "Ground B"] and matches.shape[1] == 38
    assert len(pd.read_csv(out / "players.csv")) == 2


def test_tracking_goes_to_its_own_file_for_the_captured_match_only(data_folder):
    write_inputs(data_folder, [(1, 3), (2, 3)])
    save_raw(1, capture_for(1))
    totals = build.build(archives=["ipl"])
    cricinfo = pd.read_csv(data_folder / "output" / "cricinfo_tracking.csv")
    assert cricinfo.columns.tolist() == build.CRICINFO_FILE_COLUMNS and totals["cricinfo_rows"] == 3
    assert set(cricinfo.match_id) == {1} and cricinfo.delivery_number.tolist() == [1, 2, 3]       # match 2 has no tracking, so no rows
    assert cricinfo.ball_line.tolist() == ["on the stumps"] * 3 and cricinfo.shot_direction.tolist() == ["mid wicket"] * 3


def test_delivery_number_counts_every_row_of_the_innings_and_joins_back(data_folder):
    write_inputs(data_folder, [(1, 3)])
    rows = pd.read_csv(data_folder / "work" / "cricsheet_ipl.csv")
    rows.loc[1, "ball"] = rows.loc[0, "ball"]                         # a repeated ball number, as an extra delivery gives
    rows.to_csv(data_folder / "work" / "cricsheet_ipl.csv", index=False)
    save_raw(1, capture_for(1))
    build.build(archives=["ipl"])
    out = data_folder / "output"
    main, cricinfo = pd.read_csv(out / "ball_by_ball_data.csv"), pd.read_csv(out / "cricinfo_tracking.csv")
    assert main.delivery_number.tolist() == [1, 2, 3]
    joined = main.merge(cricinfo, on=["match_id", "innings", "delivery_number"], how="left")
    assert len(joined) == len(main) and joined.ball_line.notna().all()   # no row doubled by the repeated ball number


def test_a_build_with_no_captures_still_writes_the_tracking_header(data_folder):
    write_inputs(data_folder, [(1, 3)])
    build.build(archives=["ipl"])
    cricinfo = pd.read_csv(data_folder / "output" / "cricinfo_tracking.csv")
    assert cricinfo.empty and cricinfo.columns.tolist() == build.CRICINFO_FILE_COLUMNS


def test_whole_numbers_are_written_without_a_trailing_point_zero(data_folder):
    write_inputs(data_folder, [(1, 3)])
    save_raw(1, capture_for(1))
    build.build(archives=["ipl"])
    line = open(data_folder / "output" / "cricinfo_tracking.csv").read().splitlines()[1]
    assert ",240,190,3," in line and ".0," not in line.replace("0.0,", "")  # wagon values are whole
    assert "12" in open(data_folder / "output" / "matches.csv").read() and "12.0" not in open(data_folder / "output" / "matches.csv").read()


def test_review_lists_matches_that_were_not_captured_and_skips_empty_ones(data_folder):
    write_inputs(data_folder, [(1, 3), (2, 3), (3, 3)])
    save_raw(1, capture_for(1))
    save_raw(2, {"match_id": 2, "innings": [], "no_commentary": True})
    build.build(archives=["ipl"])
    review = pd.read_csv(data_folder / "output" / "review.csv")
    assert review.match_id.tolist() == [3] and review.problem.tolist() == ["not captured yet"]
    coverage = pd.read_csv(data_folder / "output" / "coverage_report.csv")
    assert coverage.set_index("match_id").captured.to_dict() == {1: True, 2: False, 3: False}


def test_empty_matches_are_listed_in_their_own_file_and_stay_in_the_dataset(data_folder):
    write_inputs(data_folder, [(1, 3), (2, 3), (3, 3)])
    save_raw(1, capture_for(1))
    save_raw(2, {"match_id": 2, "innings": [], "no_commentary": True, "url": "https://example/2"})
    save_raw(3, {"match_id": 3, "innings": [], "no_useful_data": True, "url": "https://example/3"})
    totals = build.build(archives=["ipl"])
    empty = pd.read_csv(data_folder / "output" / "empty_matches.csv")
    assert empty.match_id.tolist() == [2, 3] and empty.rows.tolist() == [3, 3]
    assert empty.reason.str.contains("no commentary|nothing useful").all()
    assert totals["matches"] == 3 and totals["rows"] == 9      # skipped on Cricinfo, still in the dataset
    assert pd.read_csv(data_folder / "output" / "review.csv").empty


def write_json_work_files(data_folder):
    from cricket_pipeline import cricsheet_json as cj

    work = data_folder / "work"
    tables = {
        "facts": [{"match_id": 1, "team_1": "A", "team_2": "B", "city": "Leeds", "end_date": "2024-05-03", "scheduled_overs": 20.0, "balls_per_over": 6.0,
                   "match_type_number": 7.0, "collection": "ipl", "umpire_1": "U1"}, {"match_id": 2, "team_1": "A", "team_2": "B", "collection": "ipl"}],
        "wickets": [{"match_id": 1, "innings": 1.0, "delivery_number": 2.0, "wicket_number": 1.0, "player_dismissed": "X", "player_dismissed_id": "x", "wicket_type": "caught"}],
        "wicket_fielders": [{"match_id": 1, "innings": 1.0, "delivery_number": 2.0, "wicket_number": 1.0, "fielder_number": 1.0, "fielder": "F", "fielder_id": "f", "substitute": False}],
        "people": [{"match_id": 1, "role": "player", "person_number": 1.0, "team": "A", "person": "P", "person_id": "p"}],
        "innings": [{"match_id": 1, "innings": 1.0, "batting_team": "A", "target_runs": None, "is_super_over": False, "declared": False, "penalty_runs_pre": 0.0, "penalty_runs_post": 5.0}],
        "powerplays": [{"match_id": 1, "innings": 1.0, "powerplay_number": 1.0, "type": "mandatory", "start_over": 0.0, "start_ball_in_over": 1.0, "start_delivery_number": 1.0, "end_over": 5.0, "end_ball_in_over": 6.0, "end_delivery_number": 36.0, "start_listed": "0.1", "end_listed": "5.6"}],
        "reviews": [], "replacements": [],
        "notes": [{"match_id": 2, "collection": "ipl", "note": "1 deliveries spell the striker differently in the JSON and the CSV"}],
    }
    columns = {**cj.TABLE_COLUMNS, "notes": cj.NOTE_COLUMNS}
    for name, rows in tables.items():
        pd.DataFrame(rows, columns=columns[name]).to_csv(work / f"cricsheet_ipl_{name}.csv", index=False)


def test_the_tables_from_the_json_become_files_and_match_columns(data_folder):
    write_inputs(data_folder, [(1, 3), (2, 3, "Ground B")])
    write_json_work_files(data_folder)
    totals = build.build(archives=["ipl"])
    out = data_folder / "output"
    matches = pd.read_csv(out / "matches.csv")
    assert matches.loc[0, "city"] == "Leeds" and matches.loc[0, "scheduled_overs"] == 20 and matches.loc[0, "umpire_1"] == "U1" and pd.isna(matches.loc[1, "city"])
    assert totals["json_files"] == {"wickets.csv": 1, "wicket_fielders.csv": 1, "match_people.csv": 1, "innings.csv": 1, "powerplays.csv": 1, "reviews.csv": 0,
                                    "match_replacements.csv": 0, "match_missing.csv": 0, "miscounted_overs.csv": 0, "innings_absent_hurt.csv": 0, "match_dates.csv": 0,
                                    "player_external_ids.csv": 0}
    wickets = pd.read_csv(out / "wickets.csv")
    assert wickets.columns.tolist() == build.TABLE_COLUMNS["wickets"] and wickets.loc[0, "delivery_number"] == 2
    assert (out / "wickets.csv").read_text().splitlines()[1] == "1,1,2,1,X,x,caught"                   # whole numbers, not 1.0
    assert pd.read_csv(out / "innings.csv").loc[0, "penalty_runs_post"] == 5
    assert totals["json_notes"] == 1 and "spell the striker" in (out / "json_review.csv").read_text()
