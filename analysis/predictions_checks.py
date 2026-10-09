"""Checks on data/output/cricinfo_text_predictions.csv before it is published.

  isolation   no prediction where cricinfo_tracking.csv has a value for the same ball and field, and every label is one Cricinfo already uses
  sample      100 predictions with their commentary text, for reading by hand (written to data/calibration/predictions_hand_check.csv, never published)
  summary     rows, share of rows by field, confidence bands and the explicit flag
"""
import os
import sys

import pandas as pd

from analysis.text_predictions import FIELDS, TARGETS
from cricket_pipeline.config import data_dir

KEY = ["match_id", "innings", "delivery_number"]
# predictions column -> tracking column
TRACKING = {"line": "ball_line", "length": "ball_length", "shot": "shot_played", "direction": "shot_direction"}


def load():
    out = data_dir() / "output"
    predictions = os.environ.get("PREDICTIONS_CSV") or out / "cricinfo_text_predictions.csv"
    return pd.read_csv(predictions), pd.read_csv(out / "cricinfo_tracking.csv", usecols=KEY + list(TRACKING.values()))


def isolation() -> int:
    predictions, tracking = load()
    both = predictions.merge(tracking, on=KEY, how="left")
    failures = 0
    for name, column in TRACKING.items():
        filled = predictions[name].notna()
        clash = int((both[name].notna() & both[column].notna()).sum())
        outside = sorted(set(predictions.loc[filled, name]) - set(tracking[column].dropna()))
        print(f"{name}: {int(filled.sum()):,} predictions, {clash} on a ball Cricinfo already tracks, {len(outside)} labels Cricinfo does not use {outside[:5]}")
        failures += clash + len(outside)
        conf = predictions[f"{name}_confidence"]
        bad = int(((conf < 0) | (conf > 1)).sum() + (conf.notna() != filled).sum())
        print(f"   confidence outside 0 to 1 or missing: {bad}")
        failures += bad
    print("PASS" if failures == 0 else f"FAIL ({failures} problems)")
    return 1 if failures else 0


def sample(count: int = 100) -> None:
    predictions, _ = load()
    targets = pd.read_pickle(TARGETS)[KEY + ["text", "year"]]
    rows = []
    for name in FIELDS.values():
        part = predictions[predictions[name].notna()].sample(count // 4, random_state=0)
        part = part.merge(targets, on=KEY, how="left")
        rows.append(pd.DataFrame({"field": name, "match_id": part.match_id, "innings": part.innings, "delivery_number": part.delivery_number, "year": part.year,
                                  "prediction": part[name], "confidence": part[f"{name}_confidence"], "explicit": part[f"{name}_explicit"], "text": part.text}))
    out = pd.concat(rows, ignore_index=True)
    out.to_csv("data/calibration/predictions_hand_check.csv", index=False)
    print(f"{len(out)} rows written to data/calibration/predictions_hand_check.csv")


def summary() -> None:
    predictions, _ = load()
    print(f"{len(predictions):,} rows, {predictions.match_id.nunique():,} matches")
    for name in FIELDS.values():
        filled = predictions[name].notna()
        conf = predictions.loc[filled, f"{name}_confidence"]
        bands = pd.cut(conf, [0, .4, .5, .6, .7, .8, .9, 1.0], include_lowest=True).value_counts(sort=False)
        print(f"{name}: {int(filled.sum()):,} predictions, explicit {100 * predictions.loc[filled, f'{name}_explicit'].mean():.1f}%, confidence bands {dict(bands)}")


if __name__ == "__main__":
    command = sys.argv[1]
    if command == "isolation":
        sys.exit(isolation())
    elif command == "sample":
        sample()
    elif command == "summary":
        summary()
