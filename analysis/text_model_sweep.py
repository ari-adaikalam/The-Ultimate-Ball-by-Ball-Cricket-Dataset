"""Compare models and settings for reading line, length, shot and direction from the commentary.

Same data and the same held-out matches as text_model.py. Each variant is scored by accuracy and by how many balls it
fills at 90, 80 and 70 percent precision (only the confident predictions). Prints one line per variant and field.
"""
import sys
import time

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.naive_bayes import ComplementNB
from sklearn.svm import LinearSVC

from analysis.text_model import CACHE, MIN_CLASS, context_matrix

TARGETS = (0.9, 0.8, 0.7)


def fills(proba, classes, truth):
    guess, conf = classes[proba.argmax(axis=1)], proba.max(axis=1)
    right = guess == truth.to_numpy()
    out = {"acc": 100 * right.mean()}
    for target in TARGETS:
        best = 0.0
        for t in np.linspace(0.25, 0.995, 150):
            keep = conf >= t
            if keep.sum() >= 200 and right[keep].mean() >= target:
                best = 100 * keep.mean()
                break
        out[f"fill@{int(target * 100)}"] = best
    return out


def softmax(scores):
    e = np.exp(scores - scores.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def main(fields) -> None:
    df = pd.read_pickle(CACHE)
    test_ids = set(df.match_id.unique()[::5])
    train_all, test_all = df[~df.match_id.isin(test_ids)], df[df.match_id.isin(test_ids)]
    for field in fields:
        train = train_all[train_all[field].notna()]
        counts = train[field].value_counts()
        train = train[train[field].isin(counts[counts >= MIN_CLASS].index)]
        test = test_all[test_all[field].notna() & test_all[field].isin(train[field].unique())]
        print(f"\n=== {field}: train {len(train):,}, test {len(test):,}, commonest label {100 * test[field].value_counts(normalize=True).iloc[0]:.1f}%", flush=True)
        near = TfidfVectorizer(ngram_range=(1, 1), min_df=50, max_features=30_000, sublinear_tf=True, dtype=np.float32).fit(pd.concat([train.prev, train.next]))
        blocks = {}
        for name, vec in {"words1-2": TfidfVectorizer(ngram_range=(1, 2), min_df=25, max_features=250_000, sublinear_tf=True, dtype=np.float32),
                          "words1-3": TfidfVectorizer(ngram_range=(1, 3), min_df=20, max_features=400_000, sublinear_tf=True, dtype=np.float32),
                          "chars3-5": TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=40, max_features=300_000, sublinear_tf=True, dtype=np.float32)}.items():
            blocks[name] = (vec.fit_transform(train.text), vec.transform(test.text))
        ctx_tr, ctx_te = context_matrix(train), context_matrix(test)
        near_tr = hstack([near.transform(train.prev) * 0.5, near.transform(train.next) * 0.5])
        near_te = hstack([near.transform(test.prev) * 0.5, near.transform(test.next) * 0.5])

        def matrices(*names, neighbours=True):
            xtr = [blocks[n][0] for n in names] + ([near_tr] if neighbours else []) + [ctx_tr]
            xte = [blocks[n][1] for n in names] + ([near_te] if neighbours else []) + [ctx_te]
            return hstack(xtr).tocsr(), hstack(xte).tocsr()

        variants = []
        for alpha in (1e-7, 3e-7, 1e-6, 3e-6, 1e-5):
            variants.append((f"SGD log, words1-2, alpha {alpha:g}", ("words1-2",), lambda a=alpha: SGDClassifier(loss="log_loss", alpha=a, max_iter=12, tol=None, random_state=0), "proba"))
        variants += [
            ("SGD log, words1-3, alpha 1e-6", ("words1-3",), lambda: SGDClassifier(loss="log_loss", alpha=1e-6, max_iter=12, tol=None, random_state=0), "proba"),
            ("SGD log, words1-2 + chars3-5, alpha 1e-6", ("words1-2", "chars3-5"), lambda: SGDClassifier(loss="log_loss", alpha=1e-6, max_iter=12, tol=None, random_state=0), "proba"),
            ("SGD modified huber, words1-2, alpha 1e-6", ("words1-2",), lambda: SGDClassifier(loss="modified_huber", alpha=1e-6, max_iter=12, tol=None, random_state=0), "proba"),
            ("LinearSVC, words1-2, C 0.3", ("words1-2",), lambda: LinearSVC(C=0.3), "scores"),
            ("Complement NB, words1-2", ("words1-2",), lambda: ComplementNB(alpha=0.3), "proba"),
        ]
        for name, feats, make, kind in variants:
            started = time.time()
            xtr, xte = matrices(*feats)
            model = make().fit(xtr, train[field])
            if kind == "scores":
                proba = softmax(model.decision_function(xte) * 3.0)
            else:
                proba = model.predict_proba(xte)
            r = fills(proba, model.classes_, test[field])
            print(f"  {name:44s} acc {r['acc']:5.1f}% | fills at 90% {r['fill@90']:5.1f}%  80% {r['fill@80']:5.1f}%  70% {r['fill@70']:5.1f}% | {time.time() - started:3.0f}s", flush=True)
        # without the neighbours, to see what they add
        xtr, xte = matrices("words1-2", neighbours=False)
        model = SGDClassifier(loss="log_loss", alpha=1e-6, max_iter=12, tol=None, random_state=0).fit(xtr, train[field])
        r = fills(model.predict_proba(xte), model.classes_, test[field])
        print(f"  {'SGD log alpha 1e-6, no neighbour text':44s} acc {r['acc']:5.1f}% | fills at 90% {r['fill@90']:5.1f}%  80% {r['fill@80']:5.1f}%  70% {r['fill@70']:5.1f}%", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ball_line", "ball_length", "shot_played", "shot_direction"])
