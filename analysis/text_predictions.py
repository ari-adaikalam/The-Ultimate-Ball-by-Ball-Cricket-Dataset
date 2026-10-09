"""Predictions with a confidence for the balls that have commentary text but no Cricinfo tracking value.

Writes data/output/cricinfo_text_predictions.csv, one row per delivery, joined on match_id, innings and delivery_number, with line, length, shot and direction each
filled only where Cricinfo has no value for that ball and the commentary gives a reading. Labels are always Cricinfo's own. The confidence is the model's top
probability after an isotonic recalibration fitted on validation matches the model never trained on, and its error is checked on separate test matches.

Steps (each is its own command, so the heavy ones can run one at a time):
  targets            every captured ball that has text, a trusted pairing and a missing field -> data/calibration/prediction_targets.pkl
  fit <field>        train on the sample cache, calibrate, report, predict the targets -> data/calibration/predictions_<field>.pkl and a report
  drift              how much line and length confidence drops when the model moves to another era (sets the 2001 to 2013 discount)
  write              merge the per-field predictions into the CSV
"""
import os
import re
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import GroupKFold

import analysis.json_model3 as jm3
from analysis.calibration_check import table
from analysis.predictions_bundle import VERSION, Bundle
from analysis.json_features import OUT, ball_rows
from analysis.shot_families import family
from analysis.json_model import CATEGORICAL, aligned, text_probabilities
from analysis.phrase_meanings import SURE
from analysis.text_model import MIN_CLASS, context_matrix
from analysis.text_model_sweep2 import EXTRA_CUES, cue_phrases
from cricket_pipeline.align import cricinfo_frame, pair_match
from cricket_pipeline.build import iter_matches
from cricket_pipeline.capture_queue import load_raw, raw_dir
from cricket_pipeline.config import SOURCES, data_dir, work_dir

# PREDICTIONS_DIR and PREDICTIONS_STRIDE run the whole path on every N-th match into another folder, to test it before the long run
OUTDIR = Path(os.environ.get("PREDICTIONS_DIR", "data/calibration"))
STRIDE = int(os.environ.get("PREDICTIONS_STRIDE", "1"))
SMALL = "PREDICTIONS_DIR" in os.environ
IDS = {int(i) for i in os.environ["PREDICTIONS_IDS"].split(",")} if os.environ.get("PREDICTIONS_IDS") else None      # only these matches
TARGETS = OUTDIR / "prediction_targets.pkl"
FULL = "data/calibration/json_features_v5_s1.pkl"      # every captured match, the final fit trains on all of it
MODELS = OUTDIR / "models" if SMALL else Path("data/models")                            # one saved bundle per field and era
OLD_ERA_END = 2013
ERA_DISCOUNT = {"ball_line": 0.0216, "ball_length": 0.0563}     # calibration lost moving from 2020 on to 2014 to 2019, applied to 2001 to 2013
# field name in the ball table -> column in the predictions file. Shot has one model per era because its labels differ.
FIELDS = {"ball_line": "line", "ball_length": "length", "shot_played": "shot", "shot_direction": "direction"}
KEEP = ["match_id", "innings", "delivery_number", "year", "archive", "text", "over", "runs", "extras", "wides", "noballs", "byes", "legbyes", "four", "six", "wicket", "dismissal",
        "bowler_type", "left", "shot_family", "control", "zone_name", "wx", "wy", "reach", "angle", "speed", *FIELDS]


# Phrases that point to a label, from analysis/phrase_meanings.py (cricket meaning in Cricinfo's own labels). A prediction is flagged explicit when the
# commentary names that label and no other, so users can keep only the readings the text states outright. The longest phrase wins, so
# "short of a good length" is not also "good length".
PHRASES = SURE


_WORDS = {}


def _found(word: str, text: str, stem: bool = False):
    """Whole word matches of a phrase, so "covers the line" does not count as the direction cover. With stem, letters may follow ("pulled")."""
    key = (word, stem)
    if key not in _WORDS:
        _WORDS[key] = re.compile(r"(?<![a-z])" + re.escape(word) + (r"[a-z]*" if stem else r"(?![a-z])"))
    return _WORDS[key].finditer(text)


NEGATORS = {"not", "hardly", "barely", "almost", "nearly", "never", "no"}
NEGATION_FIELDS = {"ball_length", "shot_played_new", "shot_played_old"}      # measured on length and shot: a negator within 4 words before a phrase agrees 41 and 54% against 57 and 75%
EDGE = re.compile(r"(?<![a-z])(?:edge|edged|edges|nick|nicked|nicks)(?![a-z])")        # an edged shot did not go where the batter meant it: shot agreement 64 against 76%


def named_labels(field: str, text: str, names=frozenset()) -> set:
    """The labels the text names outright, keeping only the longest of any overlapping phrases.

    names holds the name tokens of the match's players. A phrase that starts with one of them is skipped, because it is
    probably a person (Short, Fuller), not a length. A phrase right after a negator ("not a yorker") is skipped for length and
    shot, and a shot is never named outright when the text says edge or nick."""
    text = text.replace("-", " ")                                   # fine-leg and fine leg are the same wording
    if field.startswith("shot_played") and EDGE.search(text):
        return set()
    spans = sorted(((m.start(), m.end(), label) for label, words in PHRASES[field].items() for w in words if w.split("-")[0].split()[0] not in names for m in _found(w.replace("-", " "), text)), key=lambda x: x[0] - x[1])
    kept = []
    for a, b, label in spans:
        if all(b <= k[0] or a >= k[1] for k in kept):
            kept.append((a, b, label))
    if field in NEGATION_FIELDS:
        kept = [(a, b, label) for a, b, label in kept
                if not any(t in NEGATORS or t.endswith("n't") for t in re.findall(r"[a-z']+", text[max(0, a - 40):a])[-4:])]
    return {label for _, _, label in kept if label}                 # the empty label holds phrases that only block a false match


NAME_FILE = Path("data/calibration/match_name_tokens.pkl")


def match_names() -> dict:
    """Name tokens (three letters or more) of the players of each captured match, cached because it reads every capture."""
    if NAME_FILE.exists():
        return joblib.load(NAME_FILE)
    out = {}
    for path in raw_dir().glob("*.json.gz"):
        raw = load_raw(int(path.name.split(".")[0]))
        out[int(path.name.split(".")[0])] = frozenset(t for p in ((raw or {}).get("players") or {}).values() for t in re.findall(r"[a-z']+", (p.get("name") or "").lower()) if len(t) >= 3)
    joblib.dump(out, NAME_FILE)
    return out


def shot_key(year) -> str:
    return "shot_played_old" if year <= OLD_ERA_END else "shot_played_new"


def explicit(field: str, labels, texts, years=None, names=None) -> list[int]:
    """1 where the text names the predicted label and no other label of the field. Shot uses its era's table, so years are needed for it."""
    out = []
    for i, (label, text) in enumerate(zip(labels, texts)):
        key = shot_key(years.iloc[i] if hasattr(years, "iloc") else years[i]) if field == "shot_played" else field
        who = (names.iloc[i] if hasattr(names, "iloc") else names[i]) if names is not None else frozenset()
        out.append(int(named_labels(key, text, frozenset(who) if isinstance(who, (set, frozenset)) else frozenset()) == {label}))
    return out


def targets() -> None:
    ids = pd.read_csv(data_dir() / "players" / "player_ids.csv", dtype=str)
    known = ids.dropna(subset=["cricinfo_id"])
    profile_of = dict(zip(known["identifier"], known["cricinfo_id"].astype(int)))
    parts, seen, t0 = [], 0, time.time()
    for source in SOURCES:
        for rows in iter_matches(work_dir() / f"cricsheet_{source.archive}.csv"):
            match_id = int(rows["match_id"].iloc[0])
            if match_id % STRIDE or (IDS is not None and match_id not in IDS):
                continue
            raw = load_raw(match_id)
            if not raw or not raw.get("innings") or raw.get("no_commentary"):
                continue
            rows = rows.assign(delivery_number=rows.groupby("innings").cumcount() + 1)
            paired, _ = pair_match(rows, cricinfo_frame(raw), profile_of)
            ok = paired[paired.cricinfo_paired]
            # The n-th captured ball is the n-th Cricsheet row only until an over is missing, so the pairing's own ball id decides the position
            place = dict(zip(ok.cricinfo_ball_id.astype(int), zip(ok.innings.astype(int), ok.delivery_number.astype(int))))
            balls = pd.DataFrame(ball_rows(match_id, raw, int(str(rows["start_date"].iloc[0])[:4]), source.archive))
            balls = balls[balls.ball_id.isin(place)].copy()
            balls["innings"] = balls.ball_id.map(lambda i: place[i][0])        # one column at a time, so a match with no paired ball is fine
            balls["delivery_number"] = balls.ball_id.map(lambda i: place[i][1])
            missing = balls[list(FIELDS)].isna().any(axis=1)
            balls = balls[(balls.text.str.len() > 0) & missing]
            if len(balls):
                parts.append(balls[KEEP])
            seen += 1
            if seen % 1000 == 0:
                print(f"{seen} matches, {sum(map(len, parts)):,} target balls ({time.time() - t0:.0f}s)", flush=True)
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=KEEP)
    out.to_pickle(TARGETS)
    print(f"{len(out):,} target balls from {out.match_id.nunique():,} matches saved to {TARGETS}")
    for f, name in FIELDS.items():
        print(f"  {name}: {int(out[f].isna().sum()):,} balls with text and no Cricinfo value")


# Cricinfo's own tracking fields. The model for balls without them must not look at these.
TRACK = {"shot_family", "zone_name", "control", "wx", "wy", "reach", "angle"}


def has_tracking(df: pd.DataFrame) -> pd.Series:
    """True for a ball with any Cricinfo tracking field. The balls that need predictions mostly have none, so they get their own model."""
    return (df.control > 0) | df.zone_name.notna() | df.wx.notna() | df.shot_family.notna()


def era_mask(df: pd.DataFrame, era: str | None) -> pd.Series:
    if era == "old":
        return df.year <= OLD_ERA_END
    if era == "new":
        return df.year > OLD_ERA_END
    return pd.Series(True, index=df.index)


UNITS = True                          # read known multi-word phrases as single tokens in the word model


UNITS_FILE = Path(__file__).parent / "unit_phrases.txt"


def unit_phrases() -> tuple:
    """The multi-word phrases read as single tokens, frozen in unit_phrases.txt. A model stores the list it was trained with, and changing the file means retraining."""
    return tuple(line for line in UNITS_FILE.read_text().splitlines() if line)


def _regex(units: tuple):
    ordered = sorted(units, key=len, reverse=True)
    return re.compile(r"(?<![a-z])(" + "|".join(re.escape(p) for p in ordered) + r")(?![a-z])")


def with_units(frame, units: tuple | None = None, force: bool = False):
    """The frame with a text_u column: the text with each known multi-word phrase joined into one token, longest first, so "short of a good length" is never read as "short" plus "good length"."""
    if "text_u" in frame.columns and not force:
        return frame
    rx = _regex(tuple(units) if units else unit_phrases())
    return frame.assign(text_u=frame.text.map(lambda t: rx.sub(lambda m: re.sub(r"[^a-z]+", "_", m.group(1)), t)))


def _words_text(frame):
    return frame.text_u if UNITS and "text_u" in frame.columns else frame.text


def _text_matrix(words, cues, frame):
    return hstack([words.transform(_words_text(frame)), cues.transform(frame.text), context_matrix(frame)]).tocsr()


def _fit_text(frame, classes, field, cue_words):
    """A text model on the rows that have text. Returns the fitted pieces."""
    rows = frame[frame.text.str.len() > 0]
    words = TfidfVectorizer(ngram_range=(1, 2), min_df=25, max_features=250_000, sublinear_tf=True, dtype=np.float32)
    cues = CountVectorizer(vocabulary=cue_words, ngram_range=(1, 4), binary=True, dtype=np.float32, token_pattern=r"[a-z']+")
    x = hstack([words.fit_transform(_words_text(rows)), cues.transform(rows.text), context_matrix(rows)]).tocsr()
    model = SGDClassifier(loss="log_loss", alpha=jm3.jm.ALPHA[field], max_iter=12, tol=None, random_state=0).fit(x, rows[field])
    return words, cues, model


def _text_probabilities(words, cues, model, frame, classes):
    """Text model probabilities for every row, empty where a row has no text."""
    out = np.full((len(frame), len(classes)), np.nan, dtype=np.float32)
    has = (frame.text.str.len() > 0).to_numpy()
    if has.any():
        sub = frame[has]
        out[has] = aligned(model, model.predict_proba(_text_matrix(words, cues, sub)), classes)
    return out


def train(field: str, era: str | None, train_frame, val, cats, classes, drop: set) -> Bundle:
    cue_words = sorted(set(cue_phrases()) | set(EXTRA_CUES))
    # out of fold text probabilities, so no ball is scored by a text model that saw its own match
    oof = np.full((len(train_frame), len(classes)), np.nan, dtype=np.float32)
    has = np.where((train_frame.text.str.len() > 0).to_numpy())[0]
    for a, b in GroupKFold(n_splits=3).split(has, groups=train_frame.match_id.to_numpy()[has]):
        words, cues, model = _fit_text(train_frame.iloc[has[a]], classes, field, cue_words)
        oof[has[b]] = _text_probabilities(words, cues, model, train_frame.iloc[has[b]], classes)
    words, cues, text_model = _fit_text(train_frame, classes, field, cue_words)
    cols = [f"p_{c}" for c in classes]
    a = pd.concat([jm3.make(train_frame, cats, drop), pd.DataFrame(oof, columns=cols)], axis=1)
    model = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, max_leaf_nodes=31, categorical_features="from_dtype", random_state=0).fit(a, train_frame[field])
    bundle = Bundle(field, era, classes, cats, drop, words, cues, text_model, model, None, units=unit_phrases())
    labels, probability = _predict(bundle, val)
    bundle.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(probability, (labels == val[field].to_numpy()).astype(float))
    return bundle


def _predict(bundle: Bundle, frame):
    """The top label and its raw probability for each row."""
    frame = with_units(frame.reset_index(drop=True), bundle.units, force=True)    # joined by position, so a sliced frame is renumbered. Read the text with the phrase tokens the model was trained with
    p_text = _text_probabilities(bundle.words, bundle.cues, bundle.text_model, frame, bundle.classes)
    x = pd.concat([jm3.make(frame, bundle.cats, bundle.drop), pd.DataFrame(p_text, columns=[f"p_{c}" for c in bundle.classes])], axis=1)
    proba = bundle.model.predict_proba(x)
    return bundle.classes[proba.argmax(axis=1)], proba.max(axis=1)


def score(bundle: Bundle, frame) -> pd.DataFrame:
    """Label and calibrated confidence for each row of frame."""
    labels, probability = _predict(bundle, frame)
    return pd.DataFrame({"label": labels, "confidence": bundle.iso.predict(probability).round(3)}, index=frame.index)


def routed(tg, bundles: dict) -> pd.DataFrame:
    """Score each target ball with the model for its regime: tracking fields present (T) or absent (N)."""
    track = has_tracking(tg).to_numpy()
    parts = []
    for regime, mask in (("T", track), ("N", ~track)):
        part = tg[mask]
        if len(part) and regime in bundles:
            scored = score(bundles[regime], part)
            parts.append(pd.DataFrame({"label": scored.label.to_numpy(), "confidence": scored.confidence.to_numpy(), "regime": regime}, index=part.index))
    return pd.concat(parts).loc[tg.index] if parts else pd.DataFrame(columns=["label", "confidence", "regime"])


def fit(field: str, era: str | None = None) -> None:
    df = pd.read_pickle(FULL)
    df = df[df.match_id % STRIDE == 0]
    df = with_units(df)
    if field == "shot_direction":
        df = df[df.match_id % 2 == 0]                         # the none class doubles the rows, so half the matches
        tracked = df.groupby("match_id").zone_name.transform(lambda z: z.notna().mean()) >= 0.5
        df = df.assign(shot_direction=df.shot_direction.where(df.shot_direction.notna() | ~tracked, "none"))   # a ball that was not hit in a tracked match has no direction
    cats = {c: sorted(df[c].fillna("none").unique()) for c in CATEGORICAL}
    ids = df.match_id.unique()
    test_ids, val_ids = set(ids[::10]), set(ids[3::10])      # a tenth each for calibration and for checking it, everything else trains
    part = df[df[field].notna() & era_mask(df, era)]
    keep = part[field].value_counts()
    keep = keep[keep >= MIN_CLASS].index
    part = part[part[field].isin(keep)]
    classes = np.array(sorted(keep))
    train_frame = part[~part.match_id.isin(test_ids | val_ids)].reset_index(drop=True)
    val = part[part.match_id.isin(val_ids)].reset_index(drop=True)
    test = part[part.match_id.isin(test_ids)].reset_index(drop=True)
    tg = pd.read_pickle(TARGETS)
    tg = tg[tg[field].isna() & era_mask(tg, era)].reset_index(drop=True)
    tag = f"{field}{'_' + era if era else ''}"
    needed = {"T": bool(has_tracking(tg).any()), "N": bool((~has_tracking(tg)).any())}
    print(f"\n=== {tag}: train {len(train_frame):,}, validation {len(val):,}, test {len(test):,}, targets {len(tg):,} (with tracking {int(has_tracking(tg).sum()):,})", flush=True)
    t0 = time.time()
    base_drop = jm3.DROP.get(field, set())
    bundles = {}
    MODELS.mkdir(parents=True, exist_ok=True)
    for regime, drop in (("T", base_drop), ("N", base_drop | TRACK)):
        if not needed[regime]:
            continue
        bundle = train(field, era, train_frame, val, cats, classes, drop)
        shown = score(bundle, test)
        hit = (shown.label.to_numpy() == test[field].to_numpy())
        rows, ece = table(shown.confidence.to_numpy(), hit)
        print(f"  [{regime}] test accuracy {100 * hit.mean():.1f}%, calibration error after recalibration {100 * ece:.2f} points", flush=True)
        print("   " + "\n   ".join(rows), flush=True)
        bundles[regime] = bundle
        joblib.dump(bundle, MODELS / f"predictions_{tag}_{regime}.joblib")
    scored = routed(tg, bundles)
    out = tg[["match_id", "innings", "delivery_number", "year"]].copy()
    out["label"], out["confidence"], out["regime"] = scored.label.to_numpy(), scored.confidence.to_numpy(), scored.regime.to_numpy()
    out["explicit"] = explicit(field, out["label"], tg["text"], tg["year"])
    if field == "shot_direction":
        out = out[out.label != "none"]                        # the model says this ball was not hit, so there is no direction to give
    out.to_pickle(OUTDIR / f"predictions_{tag}.pkl")
    print(f"  {len(out):,} predictions saved from {len(tg):,} balls, models saved ({time.time() - t0:.0f}s)", flush=True)
    print(f"  prediction label shares: {out.label.value_counts(normalize=True).head(3).round(3).to_dict()}", flush=True)


def drift() -> None:
    """Train and calibrate on 2020 and later, test on 2014 to 2019 (both eras have line and length). The largest shortfall is the old-era discount."""
    df = pd.read_pickle(OUT)
    cats = {c: sorted(df[c].fillna("none").unique()) for c in CATEGORICAL}
    ids = df.match_id.unique()
    test_ids, val_ids = set(ids[::5]), set(ids[2::5])
    for field in ("ball_line", "ball_length"):
        part = df[df[field].notna()]
        keep = part[field].value_counts()
        keep = keep[keep >= MIN_CLASS].index
        part = part[part[field].isin(keep)]
        classes = np.array(sorted(keep))
        late = part[part.year >= 2020]
        train = late[~late.match_id.isin(test_ids | val_ids)].reset_index(drop=True)
        val = late[late.match_id.isin(val_ids)].reset_index(drop=True)
        test = part[(part.year < 2020) & part.match_id.isin(test_ids | val_ids)].reset_index(drop=True)
        both = pd.concat([val, test], ignore_index=True)
        oof, p_text = text_probabilities(train, both, classes, field)
        cols = [f"p_{c}" for c in classes]
        a = pd.concat([jm3.make(train, cats, set()), pd.DataFrame(oof, columns=cols)], axis=1)
        b = pd.concat([jm3.make(both, cats, set()), pd.DataFrame(p_text, columns=cols)], axis=1)
        proba = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, max_leaf_nodes=31, categorical_features="from_dtype", random_state=0).fit(a, train[field]).predict_proba(b)
        pv, pt = proba[:len(val)], proba[len(val):]
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(pv.max(axis=1), (classes[pv.argmax(axis=1)] == val[field].to_numpy()).astype(float))
        conf, hit = iso.predict(pt.max(axis=1)), classes[pt.argmax(axis=1)] == test[field].to_numpy()
        rows, ece = table(conf, hit)
        gaps = [conf[(conf >= lo) & (conf < hi)].mean() - hit[(conf >= lo) & (conf < hi)].mean() for lo, hi in ((0, .4), (.4, .5), (.5, .6), (.6, .7), (.7, .8), (.8, .9), (.9, 1.01))
                if ((conf >= lo) & (conf < hi)).sum() >= 200]
        print(f"\n=== {field}: trained and calibrated on 2020 and later ({len(train):,} train), tested on 2014 to 2019 ({len(test):,} balls)", flush=True)
        print(f"  accuracy {100 * hit.mean():.1f}%, calibration error {100 * ece:.2f} points, largest shortfall {100 * max(gaps + [0]):.1f} points", flush=True)
        print("   " + "\n   ".join(rows), flush=True)
        print(f"DISCOUNT {field} {max(gaps + [0]):.4f}", flush=True)


def write(discount: dict) -> None:
    """Merge the per-field predictions into one wide CSV. Old-era line and length confidences are lowered by the measured drift shortfall."""
    frames = []
    names = match_names()
    texts = pd.read_pickle(TARGETS)[["match_id", "innings", "delivery_number", "text"]]      # the explicit flag is recomputed from the text, whichever version made the predictions
    for field, name in FIELDS.items():
        tags = [f"{field}_old", f"{field}_new"] if field == "shot_played" else [field]
        parts = []
        for tag in tags:
            p = pd.read_pickle(OUTDIR / f"predictions_{tag}.pkl")
            if field in discount:
                p.loc[p.year <= OLD_ERA_END, "confidence"] = (p.confidence - discount[field]).clip(lower=0).round(3)
            parts.append(p)
        p = pd.concat(parts, ignore_index=True).drop(columns="explicit").merge(texts, on=["match_id", "innings", "delivery_number"], how="left")
        p["explicit"] = explicit(field, p.label, p.text.fillna(""), p.year, p.match_id.map(names))
        p = p[["match_id", "innings", "delivery_number", "label", "confidence", "explicit"]]
        frames.append(p.rename(columns={"label": name, "confidence": f"{name}_confidence", "explicit": f"{name}_explicit"}).set_index(["match_id", "innings", "delivery_number"]))
    merged = pd.concat(frames, axis=1).reset_index().sort_values(["match_id", "innings", "delivery_number"])
    for name in FIELDS.values():
        merged[f"{name}_explicit"] = merged[f"{name}_explicit"].astype("Int64")      # 0 or 1, empty where there is no prediction
    out = (OUTDIR if SMALL else data_dir() / "output") / "cricinfo_text_predictions.csv"
    merged.to_csv(out, index=False)
    print(f"{len(merged):,} rows written to {out}")


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "targets":
        targets()
    elif command == "fit":
        fit(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif command == "drift":
        drift()
    elif command == "write":
        write({"ball_line": float(sys.argv[2]), "ball_length": float(sys.argv[3])} if len(sys.argv) > 3 else ERA_DISCOUNT)
