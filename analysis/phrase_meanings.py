"""What commentary wording means, in Cricinfo's own JSON labels.

Built from standard cricket usage and Hawk-Eye length zones (back of a length is the zone after good length, which Cricinfo calls short of a good
length). Only the JSON labels are used as targets. A phrase is listed under one label when its meaning is clear. A phrase that fits two labels stays
out, and the model decides from the context. SURE is what the explicit flag uses. UNSURE records phrases left out, with the reason.

Where Cricinfo's JSON plainly uses a different label for the same thing, the table follows the JSON. From 2014 on, forward and back defence mean
defended, glance means flick, hook means pull, late cut means cut shot and paddle sweep means sweep shot. Fielding positions follow the zone the JSON
puts the ball in: cover point is cover, gully is point, short leg and forward square leg are mid wicket, long leg is square leg.

For line, length and shot, a phrase is dropped when Cricinfo's JSON agrees with its label less than 40% of the time, or gives another label more
often (analysis/phrase_audit.py and phrase_audit2.py measure this). The empty label holds wording that looks like a label but is not one.
"""

SURE = {
    "ball_length": {
        "full toss": ["full toss", "low full toss", "high full toss", "beamer"],
        "yorker": ["yorker"],
        "full": ["full ball", "full delivery", "full and wide", "full and straight", "full on", "full outside", "full length",
                 "pitched up", "half volley", "half-volley", "overpitched", "over-pitched"],
        "good length": ["good length", "good length ball", "length ball", "length delivery", "on a length", "good-length", "length on", "length outside", "length at", "length just"],
        "short of a good length": ["short of a good length", "short of a length", "short of length", "back of a length", "back of length", "back-of-a-length"],
        "short": ["short ball", "short delivery", "bouncer", "bumper", "banged in short", "short pitched", "short-pitched", "dug in short"],
    },
    "ball_line": {
        "outside offstump": ["outside off", "outside off stump", "outside the off stump", "just outside off", "fourth stump", "fifth stump", "corridor of uncertainty", "in the channel"],
        "wide outside offstump": ["wide outside the off stump", "wide of the off stump", "a long way outside off"],
        "on the stumps": ["on the stumps", "on middle", "middle stump", "middle and leg", "middle and off", "on middle and leg", "on middle and off", "on leg stump", "leg stump",
                          "on the pads", "on leg"],
        "down leg": ["outside leg", "outside leg stump", "outside the leg stump"],
        "wide down leg": ["wide down leg", "wide down the leg side", "wide outside leg", "wide of leg stump"],
    },
    "shot_direction": {
        "cover": ["cover", "extra cover", "sweeper cover", "deep cover", "deep extra cover", "short cover", "over cover", "through cover", "cover point"],
        "point": ["point", "backward point", "deep point", "forward point", "deep backward point", "gully", "deep gully"],
        "third man": ["third man", "third-man", "fine third man", "deep third man", "short third man", "square third man", "past slips", "fly slip", "slip", "slips"],
        "fine leg": ["fine leg", "deep fine leg", "short fine leg", "square fine leg", "straight fine leg"],
        "square leg": ["square leg", "backward square leg", "deep square leg", "deep backward square leg", "deep backward square", "long leg"],
        "mid wicket": ["mid wicket", "midwicket", "mid-wicket", "deep midwicket", "deep mid wicket", "short mid wicket", "sweeper mid wicket", "over midwicket", "over mid wicket", "deep forward mid wicket", "cow corner", "forward square leg", "deep forward square leg", "short leg"],
        "mid on": ["mid on", "mid-on", "long on", "long-on", "straight mid on", "deep mid on", "short mid on", "silly mid on", "wide long on", "straight long on", "over long on", "over mid on"],
        "mid off": ["mid off", "mid-off", "long off", "long-off", "straight mid off", "deep mid off", "short mid off", "silly mid off", "wide long off", "straight long off", "over long off", "over mid off", "deep long off"],
        # Not a direction: the word point in other senses, and the umpire standing at square leg (agreement with Cricinfo 57 against 71 percent)
        "": ["at this point", "at that point", "at one point", "at the point", "match point", "point out", "good point", "to the point", "square leg umpire", "umpire at square leg"],
    },
    # 2014 and later, Cricinfo's fine shot names
    "shot_played_new": {
        "left alone": ["left alone", "leaves it", "leaves", "lets it go", "lets it pass", "shoulders arms", "leaves it alone"],
        "defended": ["defended", "defends", "blocked", "blocks", "forward defence", "forward defensive", "back defence", "back defensive"],
        "flick": ["flicked", "flicks", "flick", "glanced", "glances", "leg glance", "glance"],
        "pull": ["pulled", "pulls", "pull shot", "hooked", "hooks"],
        "cut shot": ["cut away", "cut shot", "cuts", "cut it", "cut", "square cut", "late cut", "late-cut"],
        "sweep shot": ["swept", "sweeps", "sweep shot", "paddle sweep", "paddle-sweep"],
        "slog sweep": ["slog sweep", "slog-sweep", "slog swept"],
        "reverse sweep": ["reverse sweep", "reverse swept", "reverse-sweep", "reverse sweeps"],
        "cover drive": ["cover drive", "driven through cover", "drives through cover", "drive through cover", "driven through the covers"],
        "on drive": ["on drive", "on-drive", "driven through mid on", "drive through mid on"],
        "ramp": ["ramp shot", "ramped", "scooped"],
        "padded away": ["padded away", "pads it away"],
        # Wording that looks like a cut but is not one. These phrases win over the bare cut and give no label.
        "": ["to cut it", "can't cut it", "cannot cut it", "couldn't cut it", "cut off", "cuts off", "cuts away", "cut away from", "cutting",
             "leaves him", "leaves her", "leaves them", "leaves the batter", "leaves the batsman", "leaves the right-hander", "leaves the left-hander", "leaves the bat", "leaves the pitch", "leaves the hand"],
    },
    # 2001 to 2013, Cricinfo's coarser shot names. Only wording that settles the label.
    "shot_played_old": {
        "no shot": ["left alone", "leaves it", "leaves", "lets it go", "lets it pass", "shoulders arms", "leaves it alone"],
        "forward defence": ["forward defence", "forward defensive"],
        "back defence": ["back defence", "back defensive"],
        "leg glance": ["glanced", "glances", "leg glance", "glance"],
        "sweep": ["swept", "sweeps", "sweep shot"],
        "reverse sweep": ["reverse sweep", "reverse swept", "reverse-sweep", "reverse sweeps"],
        "padded away": ["padded away", "pads it away"],
        "": ["leaves him", "leaves her", "leaves them", "leaves the batter", "leaves the batsman", "leaves the right-hander", "leaves the left-hander", "leaves the bat", "leaves the pitch", "leaves the hand"],
    },
}

# Wording whose cricket meaning is not clear, or that fits two labels. Each is (phrase, candidate labels, why it is unclear).
UNSURE = {
    "ball_length": [
        ("short and wide", ["short"], "dropped: Cricinfo agrees 17% (it says short of a good length 55%)"),
        ("short outside", ["short"], "dropped: Cricinfo agrees 29% (short of a good length 45%)"),
        ("short on", ["short"], "dropped: Cricinfo agrees 27% (short of a good length 48%)"),
        ("fullish", ["full"], "dropped: Cricinfo agrees 30% (good length 60%)"),
        ("fuller", ["full"], "dropped: Cricinfo says good length more often (good length 49%, full 44%)"),
        ("to short", ["short", "good length"], "often too short, a misuse"),
    ],
    "ball_line": [
        ("wide of off, wide of off stump", ["wide outside offstump"], "dropped: Cricinfo agrees 25 to 39% (outside offstump 55 to 67%)"),
        ("wide outside off, well outside off", ["wide outside offstump"], "dropped: Cricinfo agrees 33 to 34% (outside offstump 60 to 61%)"),
        ("on off stump, on the off stump, on off, off stump", ["on the stumps"], "dropped: Cricinfo agrees 31 to 39% (outside offstump 58 to 64%)"),
        ("wide down the leg, going down leg", ["wide down leg", "down leg"], "dropped: Cricinfo agrees 13% and 19% (on the stumps 58% and 66%)"),
        ("down leg, down the leg, down the leg side", ["down leg"], "dropped: Cricinfo says on the stumps more often (44 to 47%, down leg 40 to 43%)"),
        ("wide", ["wide outside offstump", "wide down leg"], "bare wide does not say which side"),
    ],
    "shot_direction": [
        ("down the ground", ["mid on", "mid off"], "straight, either side of the pitch"),
    ],
    "shot_played_new": [
        ("pushed, pushes", ["push"], "dropped: Cricinfo agrees 16 to 18% (defended 22 to 23%, on drive 22%)"),
        ("dabbed, dabs", ["dab"], "dropped: Cricinfo agrees 10% (steered 26%, defended 20 to 26%)"),
        ("steered, steers", ["steered"], "dropped: Cricinfo agrees 31 to 32%"),
        ("straight drive, driven straight, drives straight", ["straight drive"], "dropped: Cricinfo agrees 10 to 37% (on drive 38 to 49%)"),
        ("square drive, driven square, drives square", ["square drive"], "dropped: Cricinfo agrees 36%"),
        ("slogged, slogs", ["slog shot"], "dropped: Cricinfo agrees 36 to 39%"),
        ("upper cut, uppercut, upper-cut", ["upper cut"], "dropped: Cricinfo agrees 35 to 39%"),
        ("paddled", ["sweep shot"], "dropped: Cricinfo agrees 34%"),
        ("driven", ["cover drive", "on drive", "straight drive", "square drive"], "which drive depends on the direction"),
    ],
    "shot_played_old": [
        ("defended", ["forward defence", "back defence"], "front or back foot is not said"),
        ("blocked", ["forward defence", "back defence"], "same"),
        ("driven", ["off side drive on front foot", "off side drive on back foot", "on side drive on front foot", "on side drive on back foot"], "side and foot are not said"),
        ("pulled", ["pull hook on back foot", "pull hook on front foot"], "foot is not said, usually back"),
    ],
}


# Phrases kept with their cricket meaning although Cricinfo's JSON agrees with the label less than half the time, but with the label still the JSON's most
# common one (audit of 2026-10-09, analysis/phrase_audit.py, balls where the phrase is the only label the text names). The flag says the text states the label, not that Cricinfo agrees.
LOW_AGREEMENT = [
    ("Length", "full length, short delivery, full ball", "full or short", "46 to 47%", "JSON: good length or short of a good length"),
    ("Length", "yorker", "yorker", "46%", "JSON: full"),
]


def write_review(path="docs/phrase_meanings.md"):
    """The table as a page for review. Run: .venv/bin/python -m analysis.phrase_meanings"""
    titles = {"ball_length": "Length", "ball_line": "Line", "shot_direction": "Direction", "shot_played_new": "Shot, 2014 and later", "shot_played_old": "Shot, 2001 to 2013"}
    lines = ["# What commentary wording means", "",
             "Each phrase is listed under the one Cricinfo label it means in standard cricket usage. The `*_explicit` flag in `cricinfo_text_predictions.csv` is 1 only when the commentary "
             "names the predicted label and no other label of that field, using these phrases (the longest phrase wins). Labels are Cricinfo's own JSON labels. "
             "Meanings follow cricket usage and the Hawk-Eye length zones, in which back of a length is the zone after good length, which Cricinfo calls short of a good length. "
             "They are not a prediction of what Cricinfo's tracking recorded, which often differs: for example, balls described as back of a length were recorded as short of a good length about half the time.", ""]
    for key, title in titles.items():
        lines += [f"## {title}", "", "| Cricinfo label | Phrases that mean it |", "|---|---|"]
        lines += [f"| {label or 'no label (blocks a false match)'} | {', '.join(phrases)} |" for label, phrases in SURE[key].items()]
        lines += [""]
        if UNSURE.get(key):
            lines += ["Left out because they fit more than one label or the meaning is not clear. The model decides from the context.", "", "| Phrase | Could mean | Why it is unclear |", "|---|---|---|"]
            lines += [f"| {p} | {', '.join(c)} | {why} |" for p, c, why in UNSURE[key]]
            lines += [""]
    lines += ["## Kept with a low agreement", "",
              "These phrases keep their cricket meaning, but Cricinfo's JSON gave that label for fewer than half of the balls that use them. The flag says the text states the label, not that Cricinfo agrees. Measured on 2014 and later matches on 2026-10-09.", "",
              "| Field | Phrases | Label in the table | Agreement | What the JSON says instead |", "|---|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {d} | {e} |" for a, b, c, d, e in LOW_AGREEMENT]
    open(path, "w").write("\n".join(lines) + "\n")
    print(f"{path} written")


if __name__ == "__main__":
    write_review()
