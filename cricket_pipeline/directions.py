"""Name the direction of a shot from Cricinfo's wagon wheel position.

Cricinfo draws the wheel on a 363 by 363 canvas. Fitted to 10,944 real balls from 62 matches,
the zone centre is at (180, 165) and the eight zones are equal 45 degree slices clockwise
from straight up. Up is behind the batter and down is straight down the ground. 99.94% of
those balls fell in exactly the zone Cricinfo gave (the other 6 sit within 0.04 degrees of a
border, which is rounding in Cricinfo's coordinates), so the zone number can be rebuilt from
the coordinates. Per-zone run totals rebuilt this way were compared with Cricinfo's own stats
page for 116 featured batters, 34 of them left-handers.

Names below are for a right-hand batter. A left-hander is a mirror image, so zone k
becomes zone 9 minus k. Finer names (deep midwicket, extra cover) would need distance
bands, but commentators' own naming is too inconsistent for that to be reliable (about
50% exact at best), so this module gives zone-level names only.
"""
import math

CENTRE_X = 180.0
CENTRE_Y = 165.0

# Cricinfo's own drawing of the wheel, read from the stats page (a 171 by 171 picture, scaled to the
# 363 by 363 data). Every spike starts at the batter's end of the pitch, above the field's
# centre, and the rope is the edge of the circle. The darker inner area is an oval.
# Checked against Cricinfo's per-zone run totals for a right-hander and a left-hander: they match.
_SCALE = 363 / 171
BATTER_X = 85.4 * _SCALE
BATTER_Y = 73.63 * _SCALE
FIELD_CENTRE_X = 85.35 * _SCALE
FIELD_CENTRE_Y = 85.35 * _SCALE
FIELD_RADIUS = 85 * _SCALE
# The inner shape is a rectangle with fully rounded ends (a semicircle at each end joined by straight
# sides), which is how the 30 yard fielding restriction is really drawn. Not an oval.
RING_CENTRE_Y = 85.58 * _SCALE
RING_HALF_WIDTH = 33.6909 * _SCALE
RING_HALF_HEIGHT = 45.0474 * _SCALE

# Zone number to the name used for a right-hand batter. The names are the standard eight-region
# wagon wheel (the standard eight region diagram, batter at the top, off side on the left), applied to Cricinfo's own
# zone numbers in order. Naming Cricinfo's equal 45 degree zones agreed with unambiguous commentary
# 75.3% of the time, and using the diagram's own uneven borders 74.9%, so the zone number decides.
ZONE_NAMES = {
    1: "fine leg",
    2: "square leg",
    3: "mid wicket",
    4: "mid on",
    5: "mid off",
    6: "cover",
    7: "point",
    8: "third man",
}


def has_wagon_data(x, y, zone) -> bool:
    """Cricinfo fills zone 0 and position (0, 0) when nothing was recorded, which was 18% of
    balls in the calibration sample. That is a gap, not a real shot, so it must stay empty."""
    if x is None or y is None or zone is None:
        return False
    return int(zone) in ZONE_NAMES and not (x == 0 and y == 0)


def zone_from_xy(x: float, y: float) -> int:
    """Zone 1 to 8 for a position on the wagon wheel canvas, the way Cricinfo assigns it.

    A ball exactly on a border belongs to the earlier zone, and straight behind the batter
    (the border between zone 8 and zone 1) counts as zone 8. That tie rule was the last thing
    needed to reproduce all 10,944 zones in the calibration data.
    """
    # Canvas y grows downward, so straight up is a negative y difference. Rounding keeps an
    # exact diagonal at exactly 45 degrees instead of 45.00000000000001.
    angle = round(math.degrees(math.atan2(x - CENTRE_X, CENTRE_Y - y)) % 360, 9)
    return (math.ceil(angle / 45) - 1) % 8 + 1


def is_left_handed(batting_styles) -> bool | None:
    """From Cricinfo's short style codes such as ['lhb']. None when the hand is unknown."""
    if not batting_styles:
        return None
    first = str(batting_styles[0] if isinstance(batting_styles, (list, tuple)) else batting_styles).lower()
    if first.startswith("l"):
        return True
    if first.startswith("r"):
        return False
    return None


def zone_direction(zone: int, left_handed: bool | None) -> str | None:
    """Zone-level direction name. Empty when the zone or the batter's hand is not known."""
    if zone not in ZONE_NAMES or left_handed is None:
        return None
    return ZONE_NAMES[9 - zone if left_handed else zone]


def batter_view_angle(x: float, y: float, left_handed: bool) -> float:
    """Direction of the shot in degrees, 0 straight behind the batter and clockwise.

    Measured from the same centre Cricinfo uses for its zones, so the angle and the zone number
    always agree (the zone is the angle divided by 45, a border ball going to the earlier zone).
    A left-hander is flipped about the pitch, so the angle always reads as if the batter were
    right-handed (off side on the left). Cricinfo stores one fixed frame for every batter, so this
    flip is mine to do.
    """
    mirrored_x = 2 * CENTRE_X - x if left_handed else x
    return math.degrees(math.atan2(mirrored_x - CENTRE_X, CENTRE_Y - y)) % 360


def boundary_fraction(x: float, y: float) -> float:
    """How far the ball went, from the field's centre, as a share of the way to the rope. 1 is the rope."""
    return math.hypot(x - FIELD_CENTRE_X, y - FIELD_CENTRE_Y) / FIELD_RADIUS


def inside_ring(x: float, y: float) -> bool:
    """Inside Cricinfo's drawn inner ring, the 30 yard fielding restriction shape."""
    dx = abs(x - FIELD_CENTRE_X)
    dy = abs(y - RING_CENTRE_Y)
    straight_half = RING_HALF_HEIGHT - RING_HALF_WIDTH   # the straight sides run this far from the centre
    if dx > RING_HALF_WIDTH:
        return False
    if dy <= straight_half:
        return True
    # In a rounded end: inside if within one half width of the centre of that semicircle
    return math.hypot(dx, dy - straight_half) <= RING_HALF_WIDTH
