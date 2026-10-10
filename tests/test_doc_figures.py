from analysis.doc_figures import fill_readme, percent_range

FIGURES = {
    "file_rows": {"ball_by_ball_data.csv": 1234567, "cricinfo_tracking.csv": 10, "cricinfo_text_predictions.csv": 20, "players.csv": 30, "matches.csv": 40, "coverage_report.csv": 40},
    "empty_matches": 4260,
    "eras": [("2001 to 2013", 1000, 0, 0, 90, 66, 7)],
    "competitions": [("Tests", 500, 53, 53, 98, 71, 0), ("IPL", 400, 68, 68, 100, 84, 100)],
    "first_innings_won": 65, "first_innings_lost": 40, "boundary_beyond_old": 87, "boundary_beyond_later": [99],
    "same_ground_old": 86, "same_ground_new": 99, "shot_named_low": 99, "shot_named_high": 99, "super_over_timestamps": 9,
    "snapshot": "downloads of 3 January 2027", "spelling_matches": 31,
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
