"""How honest is the model's stated confidence?

For the combined text-and-fields model, the stated confidence (the top probability) is compared with how often the label really matched Cricinfo's, band by band,
on matches the model never saw. An isotonic recalibration is fitted on a separate validation set of matches and judged on the test set. Reports the gap in
each band and the expected calibration error, before and after, for line, length and direction.
"""
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression

from analysis.json_features import OUT
from analysis.json_model import CATEGORICAL, structured, text_probabilities
from analysis.json_model3 import DROP, make
from analysis.text_model import MIN_CLASS

BANDS = [(0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]


def table(conf, hit):
    rows, ece = [], 0.0
    for lo, hi in BANDS:
        m = (conf >= lo) & (conf < hi)
        if m.sum() < 200:
            continue
        gap = hit[m].mean() - conf[m].mean()
        ece += m.mean() * abs(gap)
        rows.append(f"{lo:.1f}-{min(hi, 1.0):.1f}: stated {100 * conf[m].mean():4.1f}% observed {100 * hit[m].mean():4.1f}% ({100 * gap:+.1f}) n {int(m.sum()):,}")
    return rows, ece


def main(fields, path=OUT) -> None:
    df = pd.read_pickle(path)
    cats = {c: sorted(df[c].fillna("none").unique()) for c in CATEGORICAL}
    ids = df.match_id.unique()
    test_ids, val_ids = set(ids[::5]), set(ids[2::5])
    for field in fields:
        drop = DROP.get(field, set())
        part = df[df[field].notna()]
        keep = part[field].value_counts(); keep = keep[keep >= MIN_CLASS].index
        part = part[part[field].isin(keep)]
        classes = np.array(sorted(keep))
        train = part[~part.match_id.isin(test_ids | val_ids)].reset_index(drop=True)
        val = part[part.match_id.isin(val_ids)].reset_index(drop=True)
        test = part[part.match_id.isin(test_ids)].reset_index(drop=True)
        both = pd.concat([val, test], ignore_index=True)
        oof, p_text = text_probabilities(train, both, classes, field)
        cols = [f"p_{c}" for c in classes]
        a = pd.concat([make(train, cats, drop), pd.DataFrame(oof, columns=cols)], axis=1)
        b = pd.concat([make(both, cats, drop), pd.DataFrame(p_text, columns=cols)], axis=1)
        model = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, max_leaf_nodes=31, categorical_features="from_dtype", random_state=0).fit(a, train[field])
        proba = model.predict_proba(b)
        pv, pt = proba[:len(val)], proba[len(val):]
        conf_v, hit_v = pv.max(axis=1), classes[pv.argmax(axis=1)] == val[field].to_numpy()
        conf_t, hit_t = pt.max(axis=1), classes[pt.argmax(axis=1)] == test[field].to_numpy()
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(conf_v, hit_v.astype(float))
        rows, ece = table(conf_t, hit_t)
        rows2, ece2 = table(iso.predict(conf_t), hit_t)
        print(f"\n=== {field}: train {len(train):,}, validation {len(val):,}, test {len(test):,}", flush=True)
        print(f"  as the model states it, expected calibration error {100 * ece:.2f} points:", flush=True)
        print("   " + "\n   ".join(rows), flush=True)
        print(f"  after isotonic recalibration, error {100 * ece2:.2f} points:", flush=True)
        print("   " + "\n   ".join(rows2), flush=True)
        # per label: does the confidence mean the same thing for every label?
        guess = classes[pt.argmax(axis=1)]
        out = []
        for c in classes:
            m = (guess == c) & (iso.predict(conf_t) >= 0.7)
            if m.sum() >= 300:
                out.append(f"{c}: recalibrated mean {100 * iso.predict(conf_t)[m].mean():.1f}%, observed {100 * hit_t[m].mean():.1f}% (n {int(m.sum()):,})")
        print("  per label among the recalibrated >= 70% readings:\n   " + "\n   ".join(out), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ball_line", "ball_length", "shot_direction"])
