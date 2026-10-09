import pytest

import math

from cricket_pipeline.directions import (
    CENTRE_X, CENTRE_Y, FIELD_CENTRE_X, FIELD_CENTRE_Y, FIELD_RADIUS, RING_CENTRE_Y, RING_HALF_HEIGHT, RING_HALF_WIDTH, ZONE_NAMES,
    batter_view_angle, boundary_fraction, has_wagon_data, inside_ring, is_left_handed, zone_direction, zone_from_xy,
)


@pytest.mark.parametrize("dx, dy, zone", [
    (10, -100, 1),    # just right of straight up
    (100, -10, 2),    # right, a little behind square
    (100, 10, 3),     # right, a little in front of square
    (10, 100, 4),     # just right of straight down
    (-10, 100, 5),    # just left of straight down
    (-100, 10, 6),
    (-100, -10, 7),
    (-10, -100, 8),
])
def test_zone_from_xy_runs_clockwise_from_straight_up(dx, dy, zone):
    assert zone_from_xy(CENTRE_X + dx, CENTRE_Y + dy) == zone


def test_real_ball_from_the_sample_lands_in_its_zone():
    # Siraj to Santner, a straight drive for six, Cricinfo gave zone 5
    assert zone_from_xy(145, 363) == 5


def test_right_hander_uses_the_names_as_they_are():
    assert zone_direction(6, left_handed=False) == "cover"
    assert zone_direction(3, left_handed=False) == "mid wicket"
    assert zone_direction(4, left_handed=False) == "mid on"
    assert zone_direction(5, left_handed=False) == "mid off"


def test_left_hander_is_mirrored():
    assert zone_direction(6, left_handed=True) == ZONE_NAMES[3]
    assert zone_direction(1, left_handed=True) == "third man"
    assert zone_direction(4, left_handed=True) == "mid off"


def test_unknown_hand_or_zone_gives_no_name_instead_of_a_guess():
    assert zone_direction(3, left_handed=None) is None
    assert zone_direction(0, left_handed=False) is None
    assert zone_direction(9, left_handed=True) is None


def test_hand_from_cricinfo_style_codes():
    assert is_left_handed(["lhb"]) is True
    assert is_left_handed(["rhb"]) is False
    assert is_left_handed([]) is None
    assert is_left_handed(None) is None


def test_placeholder_wagon_values_count_as_no_data():
    assert has_wagon_data(0, 0, 0) is False
    assert has_wagon_data(None, 100, 3) is False
    assert has_wagon_data(145, 363, 5) is True


def test_straight_down_the_ground_is_180_degrees_for_either_hand():
    assert round(batter_view_angle(CENTRE_X, CENTRE_Y + 100, left_handed=False)) == 180
    assert round(batter_view_angle(CENTRE_X, CENTRE_Y + 100, left_handed=True)) == 180


def test_left_hander_is_the_mirror_image_of_the_right_hander():
    right = batter_view_angle(CENTRE_X - 80, CENTRE_Y + 40, left_handed=False)   # off side for a right-hander
    left = batter_view_angle(CENTRE_X + 80, CENTRE_Y + 40, left_handed=True)     # the same shot, flipped
    assert round(right, 6) == round(left, 6)


def test_the_angle_always_agrees_with_the_zone_number():
    for x, y in [(50, 300), (300, 100), (181, 363), (20, 165), (340, 200), (180, 10)]:
        angle = batter_view_angle(x, y, left_handed=False)
        assert (math.ceil(round(angle, 9) / 45) - 1) % 8 + 1 == zone_from_xy(x, y)


def test_boundary_fraction_is_one_at_the_rope_and_zero_at_the_centre():
    assert boundary_fraction(FIELD_CENTRE_X, FIELD_CENTRE_Y) == 0
    assert round(boundary_fraction(FIELD_CENTRE_X + FIELD_RADIUS, FIELD_CENTRE_Y), 6) == 1


def test_ring_has_straight_sides_and_rounded_ends():
    straight = RING_HALF_HEIGHT - RING_HALF_WIDTH
    assert inside_ring(FIELD_CENTRE_X, RING_CENTRE_Y) is True
    assert inside_ring(FIELD_CENTRE_X + RING_HALF_WIDTH - 1, RING_CENTRE_Y) is True                  # on the straight side
    assert inside_ring(FIELD_CENTRE_X + RING_HALF_WIDTH + 1, RING_CENTRE_Y) is False                 # just past the side
    assert inside_ring(FIELD_CENTRE_X + RING_HALF_WIDTH - 1, RING_CENTRE_Y - straight) is True       # where the curve begins
    assert inside_ring(FIELD_CENTRE_X + RING_HALF_WIDTH - 1, RING_CENTRE_Y - RING_HALF_HEIGHT + 2) is False  # the rounded corner
    assert inside_ring(FIELD_CENTRE_X, RING_CENTRE_Y - RING_HALF_HEIGHT + 2) is True                 # the tip of the end


def test_a_ball_exactly_on_a_border_goes_to_the_earlier_zone():
    assert zone_from_xy(CENTRE_X, CENTRE_Y - 50) == 8        # straight behind the batter, the 8 and 1 border
    assert zone_from_xy(CENTRE_X, CENTRE_Y + 50) == 4        # straight down the ground, the 4 and 5 border
    assert zone_from_xy(CENTRE_X + 50, CENTRE_Y) == 2        # square on the right, the 2 and 3 border
    assert zone_from_xy(CENTRE_X - 50, CENTRE_Y) == 6        # square on the left, the 6 and 7 border


def test_exact_diagonals_are_borders_too():
    assert zone_from_xy(CENTRE_X + 30, CENTRE_Y - 30) == 1   # 45 degrees, border of 1 and 2
    assert zone_from_xy(CENTRE_X + 30, CENTRE_Y + 30) == 3   # 135 degrees, border of 3 and 4
    assert zone_from_xy(CENTRE_X - 30, CENTRE_Y + 30) == 5   # 225 degrees, border of 5 and 6
    assert zone_from_xy(CENTRE_X - 30, CENTRE_Y - 30) == 7   # 315 degrees, border of 7 and 8
