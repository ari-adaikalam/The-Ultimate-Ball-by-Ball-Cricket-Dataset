"""Do Cricinfo's other fields help predict the shot and the direction, on top of the text?

Same set-up as json_model.py. For the shot the shot and its family are left out, and for the direction the zone, point, reach and angle are left out,
because they would be the answer. The shot is modelled per era (its labels are a different set before 2014). Fields only, text only, text and fields.
"""
import sys
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from analysis.json_features import OUT
from analysis.json_model import CATEGORICAL, NUMERIC, score, text_probabilities
from analysis.text_model import MIN_CLASS
import analysis.json_model as jm

DROP = {"shot_played": {"shot_family"}, "shot_direction": {"zone_name", "wx", "wy", "reach", "angle"}}
jm.ALPHA.update({"shot_played": 3e-6, "shot_direction": 1e-5})


def make(df, cats, drop):
    cat_cols = [c for c in CATEGORICAL if c not in drop]
    x = df[[c for c in NUMERIC if c not in drop]].astype(float).copy()
    for c in cat_cols:
        x[c] = pd.Categorical(df[c].fillna("none"), categories=cats[c])
    return x


def run(field, part, cats, label, test_ids):
    drop = DROP[field]
    keep = part[field].value_counts(); keep = keep[keep >= MIN_CLASS].index
    part = part[part[field].isin(keep)]
    classes = np.array(sorted(keep))
    train, test = part[~part.match_id.isin(test_ids)].reset_index(drop=True), part[part.match_id.isin(test_ids)].reset_index(drop=True)
    has_text = (test.text.str.len() > 0).to_numpy()
    t0 = time.time()
    print(f"\n=== {field}, {label}: train {len(train):,}, test {len(test):,} ({int(has_text.sum()):,} with text)", flush=True)
    fit = lambda a, b: HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, max_leaf_nodes=31, categorical_features="from_dtype", random_state=0).fit(a, b)
    xtr, xte = make(train, cats, drop), make(test, cats, drop)
    p = fit(xtr, train[field]).predict_proba(xte)
    print(score("Cricinfo fields only", p, classes, test[field]), flush=True)
    oof, p_text = text_probabilities(train, test, classes, field)
    print(score("text only (balls with text)", np.nan_to_num(p_text, nan=1 / len(classes)), classes, test[field], has_text), flush=True)
    cols = [f"p_{c}" for c in classes]
    a = pd.concat([xtr, pd.DataFrame(oof, columns=cols)], axis=1)
    b = pd.concat([xte, pd.DataFrame(p_text, columns=cols)], axis=1)
    p = fit(a, train[field]).predict_proba(b)
    print(score("text + Cricinfo fields", p, classes, test[field]), flush=True)
    print(score("   ...balls with text", p, classes, test[field], has_text), flush=True)
    print(score("   ...balls without text", p, classes, test[field], ~has_text), flush=True)
    print(f"   ({time.time() - t0:.0f}s)", flush=True)


def main(only=None, path=OUT) -> None:
    df = pd.read_pickle(path)
    cats = {c: sorted(df[c].fillna("none").unique()) for c in CATEGORICAL}
    test_ids = set(df.match_id.unique()[::5])
    if only != "shot":
        run("shot_direction", df[df.shot_direction.notna()], cats, "all years", test_ids)
    run("shot_played", df.assign(shot_played=df.shot_label)[df.shot_label.notna() & (df.year <= 2013)], cats, "2001 to 2013", test_ids)
    run("shot_played", df.assign(shot_played=df.shot_label)[df.shot_label.notna() & (df.year >= 2014)], cats, "2014 and later", test_ids)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
