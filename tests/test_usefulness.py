from cricket_pipeline.usefulness import is_useful, text_names_a_delivery


def test_text_that_names_a_line_length_shot_or_direction_counts():
    assert text_names_a_delivery("Full toss outside off, driven through extra cover")
    assert text_names_a_delivery("pushed to mid-wicket for a single")
    assert text_names_a_delivery("Yorker on middle stump, dug out")


def test_filler_text_does_not_count():
    assert not text_names_a_delivery("Good ball, no run")
    assert not text_names_a_delivery("Dot ball. Pressure building.")
    assert not text_names_a_delivery(None) and not text_names_a_delivery("")


def test_a_page_is_useful_if_any_ball_has_structured_data_or_naming_text():
    assert is_useful([{"structured": False, "text": "no run"}, {"structured": True, "text": ""}])
    assert is_useful([{"structured": False, "text": "cut away to point"}])
    assert not is_useful([{"structured": False, "text": "good ball"}, {"structured": False, "text": "no run"}])
    assert not is_useful([])
