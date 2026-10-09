"""How often does Cricinfo's JSON agree with each phrase in the meanings table?

For each phrase, the balls where it is the only label the text names (longest phrase wins) and Cricinfo has a value for the field. Agreement is
the share where the JSON label is the one the table gives. The weakest phrases are candidates for the block list or for removal.
"""
import re
import sys

import pandas as pd

import analysis.text_predictions as th
from analysis.phrase_meanings import SURE

FIELD = {"ball_length": "ball_length", "ball_line": "ball_line", "shot_direction": "shot_direction", "shot_played_new": "shot_label", "shot_played_old": "shot_label"}


def run(key, floor=150, show=22):
    col = FIELD[key]
    df = pd.read_pickle(th.OUT)
    d = df[df[col].notna() & (df.text.str.len() > 0)]
    d = d[d.year <= 2013] if key == "shot_played_old" else d[d.year > 2013] if key != "shot_direction" else d
    d = d[d.text.str.len() < 400]
    named = d.text.map(lambda t: th.named_labels(key, t))
    one = d[named.map(len) == 1].assign(label=named[named.map(len) == 1].map(lambda s: next(iter(s))))
    rows = []
    for label, phrases in SURE[key].items():
        if not label:
            continue
        for phrase in phrases:
            hit = one[(one.label == label) & one.text.str.contains(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", regex=True)]
            if len(hit) >= floor:
                rows.append((float((hit[col] == label).mean()), phrase, label, len(hit)))
    allrows = sorted(rows)
    overall = float((one[col] == one.label).mean())
    print(f"\n== {key}: explicit balls {len(one):,}, agree with Cricinfo {100 * overall:.1f}%. Weakest phrases with {floor}+ balls:", flush=True)
    for share, phrase, label, n in allrows[:show]:
        print(f"   {100 * share:5.1f}%  {phrase:28s} -> {label:24s} ({n:,} balls)")


if __name__ == "__main__":
    for key in sys.argv[1:] or list(FIELD):
        run(key)
