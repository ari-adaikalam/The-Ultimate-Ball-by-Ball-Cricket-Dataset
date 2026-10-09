from cricket_pipeline import dataset


def test_first_run_has_no_known_matches(tmp_path):
    assert dataset.known_match_ids(tmp_path / "ball_by_ball_data.csv") == set()


def test_known_matches_come_from_the_ball_file(tmp_path):
    path = tmp_path / "ball_by_ball_data.csv"
    path.write_text("match_id,innings\n11,1\n11,2\n12,1\n")
    assert dataset.known_match_ids(path) == {11, 12}
