import copy

import pandas as pd
import pytest

from cricket_pipeline import cricsheet_json as cj

MATCH = {
    "info": {
        "teams": ["Team A", "Team B"], "dates": ["2020-01-01", "2020-01-03"], "city": "Leeds", "overs": 50, "balls_per_over": 6,
        "match_type_number": 99, "outcome": {"winner": "Team A", "method": "D/L", "eliminator": "Team B"},
        "officials": {"umpires": ["U One", "U Two", "U Three"], "tv_umpires": ["T One"], "match_referees": ["R One"], "reserve_umpires": ["V One", "V Two"]},
        "players": {"Team A": ["A1", "A2"], "Team B": ["B1", "B2"]},
        "registry": {"people": {"A1": "a1", "A2": "a2", "B1": "b1", "B2": "b2", "U One": "u1", "U Two": "u2", "U Three": "u3", "T One": "t1", "R One": "r1",
                                "V One": "v1", "V Two": "v2", "Imran Khan": "ik"}},
    },
    "innings": [
        {"team": "Team A", "powerplays": [{"from": 0.1, "to": 9.6, "type": "mandatory"}, {"from": 10.1, "to": 14.6, "type": "batting"}], "overs": [
            {"over": 0, "deliveries": [
                {"batter": "A1", "bowler": "B1", "non_striker": "A2", "runs": {"batter": 0, "extras": 0, "total": 0},
                 "wickets": [{"player_out": "A1", "kind": "caught", "fielders": [{"name": "B2"}, {"name": "B1", "substitute": True}]}],
                 "review": {"by": "Team A", "umpire": "U One", "batter": "A1", "decision": "struck down", "umpires_call": True}},
                {"batter": "A2", "bowler": "B1", "non_striker": "A1", "runs": {"batter": 4, "extras": 1, "total": 5}, "extras": {"wides": 1},
                 "wickets": [{"player_out": "A2", "kind": "run out", "fielders": [{"name": "B2"}]}, {"player_out": "A1", "kind": "retired out"}],
                 "replacements": {"match": [{"in": "A2", "out": "A1", "team": "Team A", "reason": "injury"}, {"in": "B2", "out": "B1", "team": "Team B", "reason": "injury"}]}},
            ]}]},
        {"team": "Team B", "target": {"runs": 120, "overs": 20}, "super_over": True, "penalty_runs": {"pre": 5}, "overs": [
            {"over": 0, "deliveries": [{"batter": "B1", "bowler": "Imran Khan", "non_striker": "B2", "runs": {"batter": 1, "extras": 0, "total": 1}}]}]},
    ],
}
NAMES = cj.Names(MATCH, {"Imran Khan (2)": "ik", "A1": "a1"})


def rows_for(match=MATCH):
    return pd.DataFrame([
        {"innings": 1, "striker": "A1", "bowler": "B1", "non_striker": "A2", "runs_off_bat": 0, "extras": 0, "player_dismissed": "A1", "wicket_type": "caught",
         "other_player_dismissed": None, "other_wicket_type": None},
        {"innings": 1, "striker": "A2", "bowler": "B1", "non_striker": "A1", "runs_off_bat": 4, "extras": 1, "player_dismissed": "A2", "wicket_type": "run out",
         "other_player_dismissed": "A1", "other_wicket_type": "retired out"},
        {"innings": 2, "striker": "B1", "bowler": "Imran Khan (2)", "non_striker": "B2", "runs_off_bat": 1, "extras": 0, "player_dismissed": None, "wicket_type": None,
         "other_player_dismissed": None, "other_wicket_type": None},
    ])


def test_deliveries_are_numbered_per_innings_in_source_order():
    assert [(i, n) for i, n, _ in cj.deliveries(MATCH)] == [(1, 1), (1, 2), (2, 1)]


def test_every_wicket_is_kept_with_its_position_and_its_fielders():
    wickets, fielders = cj.wicket_rows(MATCH, 5, NAMES)
    assert [(w["delivery_number"], w["wicket_number"], w["player_dismissed"], w["wicket_type"]) for w in wickets] == [
        (1, 1, "A1", "caught"), (2, 1, "A2", "run out"), (2, 2, "A1", "retired out")]
    assert [(f["delivery_number"], f["wicket_number"], f["fielder_number"], f["fielder"], f["substitute"]) for f in fielders] == [
        (1, 1, 1, "B2", False), (1, 1, 2, "B1", True), (2, 1, 1, "B2", False)]
    assert wickets[0]["player_dismissed_id"] == "a1" and fielders[1]["fielder_id"] == "b1"


def test_the_ball_columns_hold_the_first_listed_fielder_of_the_first_wicket():
    _, fielders = cj.wicket_rows(MATCH, 5, NAMES)
    first = cj.first_fielders(fielders)
    assert first[(1, 1)] == {"fielder_1": "B2", "fielder_1_id": "b2", "fielder_1_substitute": False}
    assert set(first) == {(1, 1), (1, 2)}


def test_names_are_written_the_way_the_ball_file_spells_them():
    assert NAMES.name("Imran Khan") == "Imran Khan (2)" and NAMES.id("Imran Khan") == "ik"
    assert NAMES.name("Somebody Else") == "Somebody Else" and NAMES.id("Somebody Else") is None
    assert NAMES.name(None) is None


def test_the_json_matches_the_rows_it_came_with():
    assert cj.check_against_rows(MATCH, rows_for()) == ([], [])


def test_a_different_striker_run_total_or_wicket_is_reported():
    rows = rows_for()
    rows.loc[0, "striker"] = "ZZ"
    assert cj.check_against_rows(MATCH, rows, {"ZZ": "zz", "A2": "a2", "B1": "b1", "B2": "b2", "Imran Khan (2)": "ik"})[0] != []
    rows = rows_for()
    rows.loc[1, "runs_off_bat"] = 6
    assert any("runs_off_bat" in p for p in cj.check_against_rows(MATCH, rows)[0])
    rows = rows_for()
    rows.loc[1, "other_wicket_type"] = "lbw"
    assert any("wickets differ" in p for p in cj.check_against_rows(MATCH, rows)[0])


def test_a_different_number_of_deliveries_or_innings_is_reported():
    assert "deliveries in the JSON" in cj.check_against_rows(MATCH, rows_for().iloc[:2].assign(innings=[1, 2]))[0][0]
    assert "innings in the JSON" in cj.check_against_rows(MATCH, rows_for().assign(innings=1))[0][0]


def test_match_facts_and_the_first_officials():
    facts = cj.facts(MATCH, "odis", NAMES)
    assert facts["team_1"] == "Team A" and facts["end_date"] == "2020-01-03" and facts["scheduled_overs"] == 50 and facts["collection"] == "odis"
    assert facts["result_method"] == "D/L" and facts["eliminator"] == "Team B" and facts["match_type_number"] == 99
    assert (facts["umpire_1"], facts["umpire_2"], facts["tv_umpire"], facts["match_referee"]) == ("U One", "U Two", "T One", "R One")


def test_a_match_without_officials_or_a_second_team_leaves_those_columns_empty():
    bare = copy.deepcopy(MATCH)
    bare["info"].pop("officials")
    bare["info"]["teams"] = ["Only"]
    facts = cj.facts(bare, "x", cj.Names(bare))
    assert facts["umpire_1"] is None and facts["team_2"] is None


def test_everyone_in_the_match_is_listed_in_source_order_with_a_role():
    rows = cj.people_rows(MATCH, 5, NAMES)
    players = [r for r in rows if r["role"] == "player"]
    assert [(r["person_number"], r["team"], r["person"]) for r in players] == [(1, "Team A", "A1"), (2, "Team A", "A2"), (3, "Team B", "B1"), (4, "Team B", "B2")]
    officials = [(r["role"], r["person_number"], r["person"], r["team"]) for r in rows if r["role"] != "player"]
    assert ("umpire", 3, "U Three", None) in officials and ("reserve_umpire", 2, "V Two", None) in officials and len(officials) == 7


def test_innings_carry_targets_flags_and_penalty_runs_with_false_and_zero_as_defaults():
    first, second = cj.innings_rows(MATCH, 5)
    assert (first["target_runs"], first["is_super_over"], first["declared"], first["penalty_runs_pre"], first["penalty_runs_post"]) == (None, False, False, 0, 0)
    assert (second["target_runs"], second["target_overs"], second["is_super_over"], second["penalty_runs_pre"]) == (120, 20, True, 5)


def test_powerplays_are_numbered_in_order():
    assert [(p["powerplay_number"], p["type"], p["start_scorecard_ball"], p["end_scorecard_ball"]) for p in cj.powerplay_rows(MATCH, 5)] == [
        (1, "mandatory", 0.1, 9.6), (2, "batting", 10.1, 14.6)]


def test_reviews_and_replacements():
    review = cj.review_rows(MATCH, 5, NAMES)
    assert len(review) == 1 and review[0]["delivery_number"] == 1 and review[0]["umpires_call"] is True and review[0]["umpire_id"] == "u1"
    replacements = cj.replacement_rows(MATCH, 5, NAMES)
    assert [(r["delivery_number"], r["replacement_number"], r["team"], r["player_in"]) for r in replacements] == [(2, 1, "Team A", "A2"), (2, 2, "Team B", "B2")]


def test_extras_gathers_every_table_and_refuses_an_unknown_innings_key():
    tables = cj.extras(MATCH, 5, "odis")
    assert set(tables) == set(cj.TABLE_COLUMNS) | {"notes"} and len(tables["wickets"]) == 3
    for name, rows in tables.items():
        if name != "notes":
            assert all(set(r) == set(cj.TABLE_COLUMNS[name]) for r in rows), name
    odd = copy.deepcopy(MATCH)
    odd["innings"][0]["forfeited"] = True
    with pytest.raises(ValueError, match="forfeited"):
        cj.extras(odd, 5, "odis")


def test_a_spelling_difference_with_no_id_is_a_note_and_a_different_id_is_a_problem():
    rows = rows_for()
    rows.loc[0, "striker"] = "Alan One"                    # the CSV spells A1 differently and its register does not know the name
    problems, notes = cj.check_against_rows(MATCH, rows)
    assert problems == [] and any("striker" in n for n in notes)
    same = {"Alan One": "a1", "A2": "a2", "B1": "b1", "B2": "b2", "Imran Khan (2)": "ik"}
    assert cj.check_against_rows(MATCH, rows, same) == ([], [])
    other = dict(same, **{"Alan One": "zz"})
    assert any("striker" in p for p in cj.check_against_rows(MATCH, rows, other)[0])


def test_a_substitute_fielder_with_no_name_is_kept_as_a_substitute():
    odd = copy.deepcopy(MATCH)
    odd["innings"][0]["overs"][0]["deliveries"][0]["wickets"][0]["fielders"] = [{"substitute": True}]
    _, fielders = cj.wicket_rows(odd, 5, NAMES)
    assert fielders[0]["fielder"] is None and fielders[0]["fielder_id"] is None and fielders[0]["substitute"] is True


MORE = copy.deepcopy(MATCH)
MORE["meta"] = {"created": "2023-03-06", "revision": 3, "data_version": "1.2.0"}
MORE["info"]["event"] = {"name": "Cup", "stage": "Final", "group": 2, "sub_name": "North"}
MORE["info"]["outcome"] = {"winner": "Team A", "by": {"innings": 1, "runs": 40}}
MORE["info"]["missing"] = ["player_of_match", "reviews", {"powerplays": {"1": ["batting"], "2": ["batting", "fielding"]}}]
MORE["info"]["bowl_out"] = [{"bowler": "A1", "outcome": "hit"}]
MORE["info"]["toss"] = {"decision": "bat", "winner": "Team A", "uncontested": True}
MORE["innings"][0]["miscounted_overs"] = {"0": {"balls": 7, "umpire": "U One"}, "3": {"balls": "5"}}
MORE["innings"][1]["absent_hurt"] = ["A2", "Nobody Known"]


def test_the_match_record_facts_and_the_event_are_kept():
    facts = cj.facts(MORE, "tests", NAMES)
    assert facts["won_by_innings"] is True and facts["cricsheet_created"] == "2023-03-06" and facts["cricsheet_revision"] == 3 and facts["cricsheet_data_version"] == "1.2.0"
    assert (facts["event_group"], facts["event_sub_name"], facts["event_stage"]) == ("2", "North", "Final")
    plain = cj.facts(MATCH, "tests", NAMES)
    assert plain["won_by_innings"] is False and plain["event_group"] is None and plain["cricsheet_revision"] is None


def test_what_cricsheet_says_is_missing_keeps_the_kind_and_the_innings():
    rows = cj.missing_rows(MORE, 5)
    assert [r["missing_number"] for r in rows] == [1, 2, 3, 4, 5]
    assert [(r["missing_type"], r["innings"], r["powerplay_type"]) for r in rows] == [
        ("player_of_match", None, None), ("reviews", None, None), ("powerplays", 1, "batting"), ("powerplays", 2, "batting"), ("powerplays", 2, "fielding")]
    odd = copy.deepcopy(MORE)
    odd["info"]["missing"] = [{"toss": {}}]
    with pytest.raises(ValueError, match="unknown kind of missing data"):
        cj.missing_rows(odd, 5)


def test_miscounted_overs_absent_hurt_and_dates():
    miscounted = cj.miscounted_rows(MORE, 5, NAMES)
    assert [(r["innings"], r["over"], r["balls"], r["umpire"], r["umpire_id"]) for r in miscounted] == [(1, 0, 7, "U One", "u1"), (1, 3, 5, None, None)]
    hurt = cj.absent_hurt_rows(MORE, 5, NAMES)
    assert [(r["innings"], r["player"], r["player_id"]) for r in hurt] == [(2, "A2", "a2"), (2, "Nobody Known", None)]
    assert [(r["date_number"], r["date"]) for r in cj.date_rows(MATCH, 5)] == [(1, "2020-01-01"), (2, "2020-01-03")]


def test_a_new_key_anywhere_in_the_json_is_refused_and_a_skipped_field_is_noted():
    assert cj.unexpected_keys(MORE) == []
    for place, key in (("info", "newthing"), ("innings", "forfeited"), ("delivery", "boundary_type")):
        odd = copy.deepcopy(MORE)
        {"info": odd["info"], "innings": odd["innings"][0], "delivery": odd["innings"][0]["overs"][0]["deliveries"][0]}[place][key] = 1
        assert cj.unexpected_keys(odd) == [f"{place}.{key}"]
    odd = copy.deepcopy(MORE)
    odd["info"]["event"]["colour"] = "red"
    assert cj.unexpected_keys(odd) == ["info.event.colour"]
    notes = [n["note"] for n in cj.unsupported_notes(MORE, 5, "tests")]
    assert any("bowl out" in n for n in notes) and any("uncontested toss" in n for n in notes) and not any("supersub" in n for n in notes)


def test_wickets_are_spelled_like_the_ball_rows_for_the_first_and_second_dismissal():
    wickets, _ = cj.wicket_rows(MATCH, 5, NAMES)
    rows = rows_for()
    rows.loc[0, "player_dismissed"] = "Alan One"
    rows.loc[1, "other_player_dismissed"] = "Alan One"
    fixed = cj.spell_like_the_ball_rows(wickets, rows)
    assert [w["player_dismissed"] for w in fixed] == ["Alan One", "A2", "Alan One"]
    assert [w["wicket_type"] for w in fixed] == [w["wicket_type"] for w in wickets]


def test_the_same_missing_powerplay_listed_twice_keeps_both_rows():
    twice = copy.deepcopy(MORE)
    twice["info"]["missing"] = [{"powerplays": {"1": ["fielding", "fielding"]}}]
    rows = cj.missing_rows(twice, 5)
    assert [(r["missing_number"], r["powerplay_type"]) for r in rows] == [(1, "fielding"), (2, "fielding")]
