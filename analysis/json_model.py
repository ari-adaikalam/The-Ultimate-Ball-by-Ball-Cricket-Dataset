"""Predict line and length from Cricinfo's other fields, from the text, and from both.

Cricinfo gives the shot (grouped into families that mean the same in both eras), the wagon wheel zone and point, the shot control, runs and
dismissal for most balls even where it gives no line or length. Cricsheet adds runs and wickets, and the bowler's type is known. This tests how much
those fields predict by themselves, how much the text predicts, and how much the two together predict, always on matches the models never saw.
Balls with no commentary text are scored separately, because there the text cannot help at all.
"""
import sys
import time

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import GroupKFold

from analysis.json_features import OUT
from analysis.text_model import MIN_CLASS, context_matrix
from analysis.text_model_sweep import fills
from analysis.text_model_sweep2 import EXTRA_CUES, cue_phrases

CATEGORICAL = ["shot_family", "zone_name", "dismissal", "bowler_type", "archive"]
NUMERIC = ["control", "reach", "angle", "wx", "wy", "runs", "four", "six", "wicket", "extras", "left", "innings", "over", "speed"]
ALPHA = {"ball_line": 3e-5, "ball_length": 1e-5}


def structured(df: pd.DataFrame, cats: dict) -> pd.DataFrame:
    x = df[NUMERIC].astype(float).copy()
    for c in CATEGORICAL:
        x[c] = pd.Categorical(df[c].fillna("none"), categories=cats[c])
    return x


def aligned(model, proba, classes):
    """The model's probabilities laid out on the full label list. A rare label can be missing from one fold."""
    out = np.zeros((proba.shape[0], len(classes)), dtype=np.float32)
    position = {c: i for i, c in enumerate(classes)}
    for j, c in enumerate(model.classes_):
        out[:, position[c]] = proba[:, j]
    return out


def text_probabilities(train, test, classes, field):
    cues = sorted(set(cue_phrases()) | set(EXTRA_CUES))
    def feats(fit, apply):
        words = TfidfVectorizer(ngram_range=(1, 2), min_df=25, max_features=250_000, sublinear_tf=True, dtype=np.float32)
        cv = CountVectorizer(vocabulary=cues, ngram_range=(1, 4), binary=True, dtype=np.float32, token_pattern=r"[a-z']+")
        a = hstack([words.fit_transform(fit.text), cv.transform(fit.text), context_matrix(fit)]).tocsr()
        return a, hstack([words.transform(apply.text), cv.transform(apply.text), context_matrix(apply)]).tocsr()
    oof = np.full((len(train), len(classes)), np.nan, dtype=np.float32)
    has = (train.text.str.len() > 0).to_numpy()
    idx = np.where(has)[0]
    for a, b in GroupKFold(n_splits=3).split(idx, groups=train.match_id.to_numpy()[idx]):
        fa, fb = train.iloc[idx[a]], train.iloc[idx[b]]
        xa, xb = feats(fa, fb)
        m = SGDClassifier(loss="log_loss", alpha=ALPHA[field], max_iter=12, tol=None, random_state=0).fit(xa, fa[field])
        oof[idx[b]] = aligned(m, m.predict_proba(xb), classes)
    htest = (test.text.str.len() > 0).to_numpy()
    xa, xb = feats(train[has], test[htest])
    m = SGDClassifier(loss="log_loss", alpha=ALPHA[field], max_iter=12, tol=None, random_state=0).fit(xa, train[has][field])
    p_test = np.full((len(test), len(classes)), np.nan, dtype=np.float32)
    p_test[htest] = aligned(m, m.predict_proba(xb), classes)
    return oof, p_test


def score(name, proba, classes, truth, mask=None):
    if mask is not None:
        proba, truth = proba[mask], truth[mask]
    r = fills(proba, classes, truth)
    return f"{name:34s} n {len(truth):>7,} acc {r['acc']:5.1f}% | fills at 90% {r['fill@90']:5.1f}%  80% {r['fill@80']:5.1f}%  70% {r['fill@70']:5.1f}%"


def main(fields, path=OUT) -> None:
    df = pd.read_pickle(path)
    cats = {c: sorted(df[c].fillna("none").unique()) for c in CATEGORICAL}
    test_ids = set(df.match_id.unique()[::5])
    for field in fields:
        t0 = time.time()
        part = df[df[field].notna()]
        keep = part[field].value_counts(); keep = keep[keep >= MIN_CLASS].index
        part = part[part[field].isin(keep)]
        train, test = part[~part.match_id.isin(test_ids)].reset_index(drop=True), part[part.match_id.isin(test_ids)].reset_index(drop=True)
        classes = np.array(sorted(keep))
        has_text = (test.text.str.len() > 0).to_numpy()
        print(f"\n=== {field}: train {len(train):,}, test {len(test):,} ({int(has_text.sum()):,} with text, {int((~has_text).sum()):,} without)", flush=True)
        xtr, xte = structured(train, cats), structured(test, cats)
        model = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, max_leaf_nodes=31, categorical_features="from_dtype", random_state=0)
        json_only = model.fit(xtr, train[field]).predict_proba(xte)
        print(score("Cricinfo fields only", json_only, classes, test[field], None), flush=True)
        print(score("   ...balls with text", json_only, classes, test[field], has_text), flush=True)
        print(score("   ...balls without text", json_only, classes, test[field], ~has_text), flush=True)
        oof, p_text = text_probabilities(train, test, classes, field)
        print(score("text only (balls with text)", np.nan_to_num(p_text, nan=1 / len(classes)), classes, test[field], has_text), flush=True)
        both_tr = pd.concat([xtr, pd.DataFrame(oof, columns=[f"p_{c}" for c in classes])], axis=1)
        both_te = pd.concat([xte, pd.DataFrame(p_text, columns=[f"p_{c}" for c in classes])], axis=1)
        combined = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, max_leaf_nodes=31, categorical_features="from_dtype", random_state=0).fit(both_tr, train[field]).predict_proba(both_te)
        print(score("text + Cricinfo fields", combined, classes, test[field], None), flush=True)
        print(score("   ...balls with text", combined, classes, test[field], has_text), flush=True)
        print(score("   ...balls without text", combined, classes, test[field], ~has_text), flush=True)
        print(f"   ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ball_line", "ball_length"], *([] if len(sys.argv) < 1 else []))
