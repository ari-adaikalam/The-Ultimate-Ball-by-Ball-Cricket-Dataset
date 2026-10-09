"""The most common wordings in the commentary around each field's key words, with how Cricinfo's JSON labelled those balls.

Candidates for the phrase meanings table. The labels shown are what Cricinfo's tracking recorded, as evidence for a reviewer, not the meaning.
The phrases come from the commentary itself, not from the old notebook.
"""
import re
import sys
from collections import Counter

import pandas as pd

import analysis.text_predictions as th

KEYS = {
    "ball_length": {"length", "full", "short", "yorker", "volley", "bouncer", "pitched", "toss", "slot", "fuller", "overpitched", "bounce"},
    "ball_line": {"off", "leg", "stump", "stumps", "middle", "wide", "down", "channel", "corridor", "straight", "pads", "outside"},
    "shot_direction": {"midwicket", "mid", "wicket", "long", "cover", "point", "square", "fine", "third", "slip", "gully", "sweeper", "corner", "ground", "deep", "extra", "backward", "keeper", "bowler", "silly"},
    "shot_played": {"drive", "driven", "drove", "driving", "pull", "pulled", "hook", "hooked", "flick", "flicked", "glance", "glanced", "sweep", "swept", "cut", "steered", "dab", "dabbed", "defended", "blocked", "push", "pushed",
                    "slog", "slogged", "ramp", "scoop", "scooped", "paddle", "paddled", "punch", "punched", "leave", "left", "poked", "slapped", "clipped", "whipped", "edged"},
}
TOKEN = re.compile(r"[a-z]+(?:-[a-z]+)?")


def main(field, top=45, floor=400):
    df = pd.read_pickle(th.OUT)
    d = df[((df.year > 2013) | (field == 'shot_direction')) & df[field].notna()]
    counts = Counter()
    seen = {}
    for text in d.text.sample(min(len(d), 300_000), random_state=0):
        words = TOKEN.findall(text)
        grams = set()
        for n in (2, 3, 4):
            for i in range(len(words) - n + 1):
                g = words[i:i + n]
                if KEYS[field] & set(g) and g[0] not in {"the", "a", "and", "of"} and g[-1] not in {"the", "a", "and", "of", "to"}:
                    grams.add(" ".join(g))
        counts.update(grams)
    rows = []
    for phrase, n in counts.most_common(400):
        if n < floor // 6:
            break
        hit = d.text.str.contains(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", regex=True)
        k = int(hit.sum())
        if k < floor:
            continue
        top2 = d.loc[hit, field].value_counts(normalize=True).head(3)
        rows.append((k, phrase, ", ".join(f"{a} {int(round(100 * b))}%" for a, b in top2.items())))
    for k, phrase, t in sorted(rows, reverse=True)[:top]:
        print(f"{k:7,d}  {phrase:34s} {t}")


if __name__ == "__main__":
    main(sys.argv[1])
