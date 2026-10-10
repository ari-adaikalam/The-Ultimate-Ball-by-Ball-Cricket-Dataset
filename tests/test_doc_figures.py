import pandas as pd
import pytest

from analysis.doc_figures import availability, availability_block, fill_readme, percent_range

FIGURES = {
    "file_rows": {"ball_by_ball_data.csv": 1234567, "cricinfo_tracking.csv": 10, "cricinfo_text_predictions.csv": 20, "players.csv": 30, "matches.csv": 40, "coverage_report.csv": 40},
    "empty_matches": 4260,
    "eras": [("2001 to 2013", 1000, 0, 0, 90, 66, 7)],
    "competitions": [("Tests", 500, 53, 53, 98, 71, 0), ("IPL", 400, 68, 68, 100, 84, 100)],
    "first_innings_won": 65, "first_innings_lost": 40, "boundary_beyond_old": 87, "boundary_beyond_later": [99],
    "same_ground_old": 86, "same_ground_new": 99, "shot_named_low": 99, "shot_named_high": 99, "super_over_timestamps": 9,
    "snapshot": "downloads of 3 January 2027", "spelling_matches": 31,
    "availability": {"deliveries": 2000, "fields": [("Line", 800, 600, 1400), ("Length", 800, 600, 1400), ("Shot", 1500, 100, 1600), ("Direction", 1000, 50, 1050)]},
}

README = """| File | One row per | Rows |
|---|---|---|
| `ball_by_ball_data.csv` | ball | 5 |
| `players.csv` | player | 6 |

| Era | Balls | Line | Length | Shot | Wagon point | Win probability |
|---|---|---|---|---|---|---|
| old | 1 | 1% | 1% | 1% | 1% | 1% |

| Competition | Balls | Line | Length | Shot | Wagon point | Win probability |
|---|---|---|---|---|---|---|
| X | 1 | 1% | 1% | 1% | 1% | 1% |

- About 4,200 matches, mostly T20Is between associate teams.
- Only 7 have a timestamp, and none has win probability.
- 88% of fours and sixes land beyond 0.9 of the way to the boundary, against 98% to 100% in later matches. The gap stays when only grounds that appear in both periods are compared (88% against 100%). Shot names are filled for 95% to 99% of tracked balls, depending on the era.
- It averages 64 when the side that batted first went on to win and 39 when it lost.
- The 4,200 matches with no Cricinfo commentary have no tracking.

Both use the same denominator, all 1 deliveries in the ball file, and each delivery counts once.

| Field | Recorded | Predicted, no value recorded | Recorded or predicted |
|---|---|---|---|
| Line | 1.0% (1) | 1.0% (1) | 1.0% (1) |
| Length | 1.0% (1) | 1.0% (1) | 1.0% (1) |

These figures are for the snapshot.
The files are a snapshot built from Cricsheet's downloads of 9 October 2026. On Kaggle, more.
"""


def test_tables_and_sentences_take_the_new_figures():
    out = fill_readme(README, FIGURES)
    assert "| `ball_by_ball_data.csv` | ball | 1,234,567 |" in out
    assert "| `players.csv` | player | 30 |" in out
    assert "| 2001 to 2013 | 1,000 | 0% | 0% | 90% | 66% | 7% |" in out
    assert out.count("| Tests | 500 |") == 1 and "| IPL | 400 | 68% | 68% | 100% | 84% | 100% |" in out
    assert "| X |" not in out
    assert "About 4,300 matches, mostly" in out and "The 4,300 matches with no" in out
    assert "Only 9 have a timestamp" in out
    assert "averages 65 when the side that batted first went on to win and 40 when it lost" in out
    assert "87% of fours and sixes land beyond 0.9 of the way to the boundary, against 99% in later matches" in out
    assert "compared (86% against 99%)" in out
    assert "Shot names are filled for 99% of tracked balls in every era." in out
    assert "built from Cricsheet's downloads of 3 January 2027." in out
    assert "(31 matches at the last count)" in fill_readme("Names differ (12 matches at the last count).", FIGURES)
    two_days = fill_readme(README, {**FIGURES, "snapshot": "CSV downloads and the people register of 2 January 2027 and its JSON downloads of 3 January 2027"})
    assert "built from Cricsheet's CSV downloads and the people register of 2 January 2027 and its JSON downloads of 3 January 2027." in two_days


def test_filling_twice_changes_nothing():
    once = fill_readme(README, FIGURES)
    assert fill_readme(once, FIGURES) == once


def test_percent_range_collapses_equal_values():
    assert percent_range([100, 100]) == "100%"
    assert percent_range([100, 98]) == "98% to 100%"


def test_the_availability_table_and_its_denominator_take_the_new_figures():
    out = fill_readme(README, FIGURES)
    assert "all 2,000 deliveries in the ball file" in out
    assert "| Line | 40.0% (800) | 30.0% (600) | 70.0% (1,400) |" in out
    assert "| Shot | 75.0% (1,500) | 5.0% (100) | 80.0% (1,600) |" in out
    assert "| Direction | 50.0% (1,000) | 2.5% (50) | 52.5% (1,050) |" in out
    assert "| Length | 1.0%" not in out and "These figures are for the snapshot." in out
    assert availability_block(FIGURES["availability"]).count("\n") == 5


def tiny_files(tmp_path, tracking_rows, prediction_rows, ball_rows=5):
    keys = [(1, 1, n) for n in range(1, ball_rows + 1)]
    pd.DataFrame(keys, columns=["match_id", "innings", "delivery_number"]).to_csv(tmp_path / "ball_by_ball_data.csv", index=False)
    pd.DataFrame(tracking_rows, columns=["match_id", "innings", "delivery_number", "ball_line", "ball_length", "shot_played", "shot_direction"]).to_csv(tmp_path / "cricinfo_tracking.csv", index=False)
    pd.DataFrame(prediction_rows, columns=["match_id", "innings", "delivery_number", "line", "length", "shot", "direction"]).to_csv(tmp_path / "cricinfo_text_predictions.csv", index=False)


def test_availability_counts_each_delivery_once_over_all_deliveries_of_the_ball_file(tmp_path):
    """Five deliveries. Line is recorded on 1 and 2, predicted on 3 and 4 and missing on 5. A prediction with a confidence of nothing is counted too, since no cutoff is applied."""
    tiny_files(tmp_path, [(1, 1, 1, "full", "full", "drive", None), (1, 1, 2, "wide", None, None, "cover")],
               [(1, 1, 3, "wide", "short", None, None), (1, 1, 4, "full", None, "pull", None)])
    result = availability(tmp_path)
    assert result["deliveries"] == 5
    assert dict((row[0], row[1:]) for row in result["fields"]) == {"Line": (2, 2, 4), "Length": (1, 1, 2), "Shot": (1, 1, 2), "Direction": (1, 0, 1)}


def test_availability_stops_on_a_repeated_key_or_a_double_value(tmp_path):
    tiny_files(tmp_path, [(1, 1, 1, "full", None, None, None), (1, 1, 1, "wide", None, None, None)], [])
    with pytest.raises(ValueError, match="repeats a delivery key"):
        availability(tmp_path)
    tiny_files(tmp_path, [(1, 1, 1, "full", None, None, None)], [(1, 1, 1, "wide", None, None, None)])
    with pytest.raises(ValueError, match="recorded and a predicted"):
        availability(tmp_path)
