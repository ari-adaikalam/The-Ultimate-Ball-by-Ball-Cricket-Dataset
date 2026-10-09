"""For every phrase in the meanings table whose label is not the one Cricinfo's JSON uses most often, what does the JSON use instead?

Balls where the phrase is the only label the text names (longest phrase wins). Listed when the table's label is not the most common JSON label for
the phrase, with the top three JSON labels. These are the phrases where cricket meaning and Cricinfo's tracking disagree.
"""
import re
import sys

import pandas as pd

import analysis.text_predictions as th
from analysis.phrase_meanings import SURE

FIELD = {"ball_length": "ball_length", "ball_line": "ball_line", "shot_direction": "shot_direction", "shot_played_new": "shot_label", "shot_played_old": "shot_label"}


def run(key, floor=150):
    col = FIELD[key]
    df = pd.read_pickle(th.OUT)
    d = df[df[col].notna() & (df.text.str.len() > 0) & (df.text.str.len() < 400)]
    d = d[d.year <= 2013] if key == "shot_played_old" else d[d.year > 2013] if key != "shot_direction" else d
    named = d.text.map(lambda t: th.named_labels(key, t))
    one = d[named.map(len) == 1].assign(label=named[named.map(len) == 1].map(lambda s: next(iter(s))))
    print(f"\n== {key}", flush=True)
    for label, phrases in SURE[key].items():
        if not label:
            continue
        for phrase in phrases:
            hit = one[(one.label == label) & one.text.str.contains(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", regex=True)]
            if len(hit) < floor:
                continue
            dist = hit[col].value_counts(normalize=True)
            if dist.index[0] != label:
                top = ", ".join(f"{k} {int(round(100 * v))}%" for k, v in dist.head(3).items())
                print(f"   {phrase:26s} table: {label:22s} JSON most often: {top}  ({len(hit):,} balls)", flush=True)


if __name__ == "__main__":
    for key in sys.argv[1:] or list(FIELD):
        run(key)
