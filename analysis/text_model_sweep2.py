"""Second sweep: stronger regularisation, cue phrases and word stems.

The first sweep showed that line, length, shot and direction all improve as the regularisation grows, so this one
goes further. It also tests a block of cue phrases (the old prepare notebook's phrase lists plus extra ones such as
"pitched up" and "fuller") as extra features, and a light stemmer so that "fuller", "fullish" and "full" share a root.
The cues are only features. The label each one points to is learned from the data.
"""
import json
from pathlib import Path
import re
import sys
import time

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from analysis.text_model import CACHE, MIN_CLASS, context_matrix
from analysis.text_model_sweep import fills

EXTRA_CUES = [
    "pitched up", "fuller", "fullish", "full length", "good length", "back of a length", "back of length", "short of a length", "short of length", "length ball",
    "half volley", "half-volley", "yorker", "bouncer", "short ball", "full toss", "overpitched", "over-pitched", "bit short", "touch short", "banged in", "hit the deck",
    "on a length", "length delivery", "full and wide", "short and wide", "full on", "short and", "good line", "fuller length", "tad fuller", "bit fuller", "a touch fuller",
    "off stump", "middle stump", "leg stump", "outside off", "outside the off", "wide outside", "down the leg", "down leg", "leg side", "on the pads", "on the stumps",
    "middle and leg", "off and middle", "wide of off", "channel", "corridor", "on off", "on middle", "on leg", "wide", "angling in", "shaping away", "nipping back",
]


def cue_phrases() -> list[str]:
    """The phrases used as cue features, one per line in cue_phrases.txt."""
    return [line for line in (Path(__file__).parent / "cue_phrases.txt").read_text().splitlines() if line]


# shot has 40 classes and wants far less regularisation than the others
ALPHAS = {"shot_played": (1e-6, 3e-6, 1e-5), "shot_direction": (3e-6, 1e-5, 3e-5, 1e-4)}

SUFFIX = re.compile(r"(ing|ed|er|es|s|ish)$")


def stem(text: str) -> str:
    return " ".join(SUFFIX.sub("", w) if len(w) > 4 else w for w in re.findall(r"[a-z']+", text))


def main(fields) -> None:
    df = pd.read_pickle(CACHE)
    cues = sorted(set(cue_phrases()) | set(EXTRA_CUES))
    print(f"{len(cues)} cue phrases", flush=True)
    test_ids = set(df.match_id.unique()[::5])
    train_all, test_all = df[~df.match_id.isin(test_ids)], df[df.match_id.isin(test_ids)]
    for field in fields:
        train = train_all[train_all[field].notna()]
        counts = train[field].value_counts()
        train = train[train[field].isin(counts[counts >= MIN_CLASS].index)]
        test = test_all[test_all[field].notna() & test_all[field].isin(train[field].unique())]
        print(f"\n=== {field}: train {len(train):,}, test {len(test):,}, commonest label {100 * test[field].value_counts(normalize=True).iloc[0]:.1f}%", flush=True)
        words = TfidfVectorizer(ngram_range=(1, 2), min_df=25, max_features=250_000, sublinear_tf=True, dtype=np.float32)
        w_tr, w_te = words.fit_transform(train.text), words.transform(test.text)
        stems_tr, stems_te = train.text.map(stem), test.text.map(stem)
        sv = TfidfVectorizer(ngram_range=(1, 2), min_df=25, max_features=250_000, sublinear_tf=True, dtype=np.float32)
        s_tr, s_te = sv.fit_transform(stems_tr), sv.transform(stems_te)
        cv = CountVectorizer(vocabulary=cues, ngram_range=(1, 4), binary=True, dtype=np.float32, token_pattern=r"[a-z']+")
        c_tr, c_te = cv.transform(train.text), cv.transform(test.text)
        ctx_tr, ctx_te = context_matrix(train), context_matrix(test)
        variants = {"words": ([w_tr], [w_te]), "words + cues": ([w_tr, c_tr], [w_te, c_te]), "stems": ([s_tr], [s_te]),
                    "stems + cues": ([s_tr, c_tr], [s_te, c_te]), "words + stems + cues": ([w_tr, s_tr, c_tr], [w_te, s_te, c_te])}
        for name, (xtr, xte) in variants.items():
            for alpha in ALPHAS.get(field, (1e-5, 3e-5, 1e-4, 3e-4)):
                started = time.time()
                A, B = hstack(xtr + [ctx_tr]).tocsr(), hstack(xte + [ctx_te]).tocsr()
                model = SGDClassifier(loss="log_loss", alpha=alpha, max_iter=12, tol=None, random_state=0).fit(A, train[field])
                r = fills(model.predict_proba(B), model.classes_, test[field])
                print(f"  {name:22s} alpha {alpha:<7g} acc {r['acc']:5.1f}% | fills at 90% {r['fill@90']:5.1f}%  80% {r['fill@80']:5.1f}%  70% {r['fill@70']:5.1f}% | {time.time() - started:3.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["ball_line", "ball_length", "shot_played", "shot_direction"])
