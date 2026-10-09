from analysis.phrase_meanings import SURE
from analysis.text_predictions import explicit, named_labels

VALID = {
    "ball_length": {"full toss", "yorker", "full", "good length", "short of a good length", "short"},
    "ball_line": {"outside offstump", "wide outside offstump", "on the stumps", "down leg", "wide down leg"},
    "shot_direction": {"cover", "mid wicket", "mid off", "mid on", "point", "square leg", "third man", "fine leg"},
}


def test_every_label_in_the_table_is_one_of_cricinfos_and_no_phrase_has_two_meanings():
    for field, labels in VALID.items():
        assert set(SURE[field]) - {""} <= labels, field          # the empty label holds phrases that only block a false match
    for key, table in SURE.items():
        seen = {}
        for label, phrases in table.items():
            for phrase in phrases:
                assert phrase == phrase.lower() and phrase not in seen, (key, phrase, seen.get(phrase))
                seen[phrase] = label


def test_the_longest_phrase_wins():
    assert named_labels("ball_length", "short of a good length, pushed") == {"short of a good length"}
    assert named_labels("ball_length", "a good length ball") == {"good length"}
    assert named_labels("ball_line", "wide outside the off stump, left alone") == {"wide outside offstump"}


def test_cricket_meanings_decided_by_ari():
    assert named_labels("ball_length", "back of a length outside off") == {"short of a good length"}
    assert named_labels("ball_line", "on the pads") == {"on the stumps"}
    assert named_labels("shot_direction", "edged past the slips") == {"third man"}
    assert named_labels("shot_direction", "swatted to cow corner") == {"mid wicket"}


def test_a_word_inside_a_longer_word_does_not_count():
    assert named_labels("shot_direction", "covers the line") == set()
    assert named_labels("shot_direction", "deep midwicket") == {"mid wicket"}


def test_text_naming_two_labels_is_not_explicit_for_either():
    assert named_labels("shot_direction", "between cover and mid off") == {"cover", "mid off"}
    assert explicit("shot_direction", ["cover", "mid off"], ["between cover and mid off"] * 2) == [0, 0]
    assert named_labels("shot_direction", "cover point") == {"cover"}                  # follows the JSON, which puts these balls in the cover zone


def test_explicit_is_one_only_for_the_label_the_text_names():
    texts = ["short of a good length, pushed"] * 2
    assert explicit("ball_length", ["short of a good length", "good length"], texts) == [1, 0]


def test_shot_uses_the_table_of_its_era():
    assert explicit("shot_played", ["pull"], ["pulled away to square leg"], [2020]) == [1]
    assert explicit("shot_played", ["cover drive"], ["driven through cover"], [2020]) == [1]
    assert explicit("shot_played", ["cover drive"], ["driven"], [2020]) == [0]                    # which drive is not said
    assert explicit("shot_played", ["pull"], ["pulled after a flick"], [2020]) == [0]             # two shots named
    assert explicit("shot_played", ["leg glance"], ["glanced fine"], [2008]) == [1]
    assert explicit("shot_played", ["forward defence"], ["defended"], [2008]) == [0]               # front or back foot is not said before 2014


def test_wording_that_looks_like_a_cut_but_is_not_one_is_blocked():
    assert named_labels("shot_played_new", "he can't cut it, beaten") == set()
    assert named_labels("shot_played_new", "the ball cuts away from the bat") == set()
    assert named_labels("shot_played_new", "fielder cut off the boundary") == set()
    assert named_labels("shot_played_new", "cut away to third man") == {"cut shot"}
    assert named_labels("shot_played_new", "a late cut, nicely done") == {"cut shot"}         # Cricinfo records late cuts as cut shot


def test_the_word_point_in_other_senses_and_the_square_leg_umpire_are_not_directions():
    assert named_labels("shot_direction", "at this point in the over") == set()
    assert named_labels("shot_direction", "match point for the bowler") == set()
    assert named_labels("shot_direction", "the square leg umpire checks") == set()
    assert named_labels("shot_direction", "dropped at point") == {"point"}


def test_leaves_used_of_the_ball_is_not_a_left_alone():
    assert named_labels("shot_played_new", "the ball leaves the batter") == set()
    assert named_labels("shot_played_new", "he leaves it alone") == {"left alone"}


def test_a_surname_that_is_also_a_table_word_is_not_read_as_a_length():
    assert named_labels("ball_length", "short ball, hit hard") == {"short"}
    assert named_labels("ball_length", "short ball, hit hard", frozenset({"short"})) == set()
    assert explicit("ball_length", ["short"], ["short delivery outside off"], names=[frozenset({"short"})]) == [0]
    assert explicit("ball_length", ["short"], ["short delivery outside off"], names=[set()]) == [1]


def test_where_cricinfo_uses_another_label_for_the_same_thing_the_table_follows_the_json():
    assert named_labels("shot_direction", "edged to gully") == {"point"}
    assert named_labels("shot_direction", "taken at short leg") == {"mid wicket"}
    assert named_labels("shot_direction", "fielded at long leg") == {"square leg"}
    assert named_labels("shot_played_new", "forward defence") == {"defended"}
    assert named_labels("shot_played_new", "glanced fine") == {"flick"}
    assert named_labels("shot_played_new", "hooked away") == {"pull"}
    assert named_labels("shot_played_new", "a late cut") == {"cut shot"}
    assert named_labels("shot_played_new", "a paddle sweep") == {"sweep shot"}
    assert named_labels("shot_played_old", "glanced fine") == {"leg glance"}            # the old era's own label is kept


def test_phrases_below_forty_percent_agreement_were_dropped_for_line_and_length():
    for field, gone in (("ball_line", ["on off stump", "off stump", "wide of off", "wide outside off", "well outside off", "wide down the leg", "going down leg"]),
                        ("ball_length", ["short and wide", "short on", "short outside", "fullish"])):
        assert not [p for phrases in SURE[field].values() for p in phrases if p in gone]
    assert named_labels("ball_line", "on off stump") == set()
    # dropped because Cricinfo records another label more often
    assert named_labels("ball_line", "down the leg side") == set() and named_labels("ball_length", "fuller outside off") == set()
    assert named_labels("ball_line", "outside leg stump") == {"down leg"}


def test_shot_phrases_below_forty_percent_agreement_were_dropped():
    gone = ["pushed", "pushes", "dabbed", "dabs", "steered", "steers", "slogged", "slogs", "uppercut", "upper cut", "paddled", "square drive", "straight drive", "driven straight"]
    assert not [p for phrases in SURE["shot_played_new"].values() for p in phrases if p in gone]
    assert named_labels("shot_played_new", "pushed back to the bowler") == set()


def test_a_hyphen_is_the_same_as_a_space():
    assert named_labels("shot_direction", "it runs away to fine-leg") == {"fine leg"}
    assert named_labels("shot_direction", "pushed to mid-on") == {"mid on"}
    assert named_labels("ball_length", "a short-pitched ball") == {"short"}


def test_a_negator_just_before_a_length_or_shot_phrase_blocks_it():
    assert named_labels("ball_length", "that is not a yorker, it is a full toss") == {"full toss"}
    assert named_labels("ball_length", "almost a yorker, but a full ball") == {"full"}
    assert named_labels("ball_length", "a yorker") == {"yorker"}
    assert named_labels("shot_played_new", "he does not pull this one") == set()
    assert named_labels("ball_length", "a good length ball, not much help for the batter") == {"good length"}      # the negator is after the phrase


def test_negation_does_not_block_line_or_direction():
    assert named_labels("shot_direction", "no, it goes to cover") == {"cover"}
    assert named_labels("ball_line", "not quite on the stumps, but outside off") == {"on the stumps", "outside offstump"}


def test_an_edged_shot_is_never_named_outright():
    assert named_labels("shot_played_new", "pulled, but it is an edge") == set()
    assert named_labels("shot_played_old", "a glance, or really a nick") == set()
    assert named_labels("shot_direction", "an edge through to third man") == {"third man"}
    assert named_labels("ball_length", "edged a good length ball") == {"good length"}


def test_a_player_name_token_blocks_only_the_phrases_that_start_with_it():
    assert named_labels("ball_length", "short ball, hit hard", frozenset({"short"})) == set()
    assert named_labels("ball_length", "a short ball", frozenset({"fuller"})) == {"short"}
