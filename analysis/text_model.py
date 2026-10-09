"""Can a model read Cricinfo's commentary well enough to fill line, length, shot and direction?

Trains on balls where Cricinfo gave both the text and its own label, using the words of the commentary plus facts
that Cricsheet also has for every ball (runs, wicket, boundary, bowler style, batter hand). It only ever predicts
labels that appear in the JSON, so nothing new is invented. Two kinds of test, always on matches the model never saw:
  same era   a random 20 percent of matches
  other era  train on newer matches, test on older ones, because the older commentary may read differently
For each test the report gives the precision and how many balls are covered when only confident predictions are used.
"""
import re
import sys
import time

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from cricket_pipeline.align import readable
from cricket_pipeline.capture_queue import build_queue, load_raw, load_survey, raw_dir
from cricket_pipeline.directions import is_left_handed, zone_direction

CACHE = "data/calibration/text_model_balls_v2.pkl"
ARCHIVES = ["tests", "odis", "t20s", "ipl", "bbl", "wbb", "wpl", "cpl", "psl", "sat", "ilt", "hnd", "mlc", "lpl", "bpl"]
FIELDS = ["ball_line", "ball_length", "shot_played", "shot_direction"]
KEY = {"ball_line": "line", "ball_length": "length", "shot_played": "shot"}
MIN_CLASS = 300


def bowler_type(codes) -> str:
    code = (codes or [""])[0] if codes else ""
    return "spin" if code in ("ob", "lb", "lbg", "slo", "sla", "slc", "lbo", "ols") or code.startswith("sl") else "pace" if code else "unknown"


def build(stride: int) -> pd.DataFrame:
    queue = build_queue(load_survey())
    year = dict(zip(queue.match_id.astype(int), queue.year))
    archive = dict(zip(queue.match_id.astype(int), queue.archive))
    rows = []
    for path in sorted(raw_dir().glob("*.json.gz")):
        m = int(path.name.split(".")[0])
        if m % stride:
            continue
        raw = load_raw(m)
        if not raw or not raw.get("innings"):
            continue
        players = raw.get("players", {})
        for innings in raw["innings"]:
            ordered = sorted(innings["balls"], key=lambda x: (x.get("over_unique") if x.get("over_unique") is not None else x.get("over"), x.get("id")))
            texts = [(x.get("text") or "").strip().lower() for x in ordered]       # the text before and after belongs to something else
            for pos, b in enumerate(ordered):
                text = texts[pos]
                if not text:
                    continue
                batter, bowler = players.get(str(b.get("batter"))) or {}, players.get(str(b.get("bowler"))) or {}
                left = is_left_handed(batter.get("batting"))
                zone = b.get("wz") or 0
                row = {"match_id": m, "year": year.get(m, 0), "text": text, "prev": texts[pos - 1] if pos else "", "next": texts[pos + 1] if pos + 1 < len(texts) else "",
                       "archive": archive.get(m, ""), "over": float(b.get("over") or 0), "innings": int(b.get("innings") or 1), "bowler": b.get("bowler"), "runs": min(int(b.get("runs") or 0), 6), "extras": int(bool(b.get("wides") or b.get("noballs") or b.get("byes") or b.get("legbyes"))),
                       "four": int(bool(b.get("four"))), "six": int(bool(b.get("six"))), "wicket": int(bool(b.get("wicket"))), "bowler_type": bowler_type(bowler.get("bowling")),
                       "left": -1 if left is None else int(bool(left))}
                for f, k in KEY.items():
                    row[f] = readable(b.get(k))
                row["shot_direction"] = zone_direction(zone, bool(left)) if zone and left is not None and not (b.get("wx") == 0 and b.get("wy") == 0) else None
                rows.append(row)
    return pd.DataFrame(rows)


def context_matrix(df: pd.DataFrame) -> csr_matrix:
    """Fixed columns, so a category missing from the test set cannot change the shape."""
    parts = [df[["extras", "four", "six", "wicket"]].to_numpy(dtype=float)]
    over_bucket = (df.over // 5).clip(0, 9).astype(int)
    for values, series in ((range(7), df.runs.clip(0, 6)), (("pace", "spin", "unknown"), df.bowler_type), ((-1, 0, 1), df["left"]),
                           (ARCHIVES, df.archive), (range(10), over_bucket), (range(1, 5), df.innings.clip(1, 4))):
        parts.append(np.stack([(series == v).to_numpy(dtype=float) for v in values], axis=1))
    return csr_matrix(np.hstack(parts))


def curve(proba: np.ndarray, classes, truth: pd.Series) -> dict:
    guess = classes[proba.argmax(axis=1)]
    confidence = proba.max(axis=1)
    right = guess == truth.to_numpy()
    out = {"accuracy": right.mean(), "majority": truth.value_counts(normalize=True).iloc[0]}
    for target in (0.95, 0.9, 0.85, 0.8, 0.7):
        found = None
        for t in np.linspace(0.30, 0.995, 140):
            keep = confidence >= t
            if keep.sum() >= 200 and right[keep].mean() >= target:
                found = (t, keep.mean(), right[keep].mean())
                break
        out[target] = found
    return out


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, field: str):
    train = train[train[field].notna()]
    counts = train[field].value_counts()
    train = train[train[field].isin(counts[counts >= MIN_CLASS].index)]
    test = test[test[field].notna() & test[field].isin(train[field].unique())]
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=25, max_features=250_000, sublinear_tf=True, dtype=np.float32)
    near = TfidfVectorizer(ngram_range=(1, 1), min_df=50, max_features=30_000, sublinear_tf=True, dtype=np.float32)   # the words of the balls just before and after
    near.fit(pd.concat([train.prev, train.next]))
    xtr = hstack([vec.fit_transform(train.text), near.transform(train.prev) * 0.5, near.transform(train.next) * 0.5, context_matrix(train)]).tocsr()
    xte = hstack([vec.transform(test.text), near.transform(test.prev) * 0.5, near.transform(test.next) * 0.5, context_matrix(test)]).tocsr()
    clf = SGDClassifier(loss="log_loss", alpha=3e-7, max_iter=12, tol=None, random_state=0)
    clf.fit(xtr, train[field])
    return clf.predict_proba(xte), clf.classes_, test[field]


def report(name: str, field: str, train: pd.DataFrame, test: pd.DataFrame) -> None:
    started = time.time()
    proba, classes, truth = fit_predict(train, test, field)
    c = curve(proba, classes, truth)
    lines = [f"{name:34s} {field:15s} train {len(train):>8,} test {len(truth):>8,} | accuracy {100*c['accuracy']:.1f}% (always the commonest label: {100*c['majority']:.1f}%)"]
    for target in (0.95, 0.9, 0.85, 0.8, 0.7):
        f = c[target]
        lines.append(f"     for {int(target*100)}% precision: " + (f"fills {100*f[1]:.1f}% of balls with text (precision {100*f[2]:.1f}%, confidence {f[0]:.2f})" if f else "not reachable"))
    print("\n".join(lines) + f"\n     ({time.time()-started:.0f}s)", flush=True)


def main(stride: int = 4) -> None:
    try:
        df = pd.read_pickle(CACHE)
    except Exception:
        df = build(stride)
        df.to_pickle(CACHE)
    print(f"{len(df):,} balls with text from {df.match_id.nunique():,} matches", flush=True)
    test_ids = set(df.match_id.unique()[::5])
    same_train, same_test = df[~df.match_id.isin(test_ids)], df[df.match_id.isin(test_ids)]
    for field in FIELDS:
        report("same era (random 20% of matches)", field, same_train, same_test)
    old, new = df[df.year <= 2013], df[df.year >= 2014]
    mid, recent = df[(df.year >= 2014) & (df.year <= 2019)], df[df.year >= 2020]
    for field in ("shot_played", "shot_direction"):
        report("other era: train 2014+, test 2001-2013", field, new, old)
    for field in ("ball_line", "ball_length"):
        report("other era: train 2020+, test 2014-2019", field, recent, mid)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
