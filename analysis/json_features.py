"""A ball table that keeps Cricinfo's other fields next to the text, to see whether they help predict line and length.

Cricinfo gives the shot played, the wagon wheel zone and point, the shot control and the dismissal for most balls in every era,
and a pull goes with a short ball and a leg-side flick with a ball on the pads. Cricsheet adds runs and wickets. Writes one row per ball with text.
"""
import re
import sys

import pandas as pd

from analysis.shot_families import family
from analysis.text_model import KEY, bowler_type
from cricket_pipeline.align import readable
from cricket_pipeline.capture_queue import build_queue, load_raw, load_survey, raw_dir
from cricket_pipeline.directions import batter_view_angle, boundary_fraction, has_wagon_data, is_left_handed, zone_direction

SPEED = re.compile(r"(\d{2,3}(?:\.\d)?)\s*(?:kph|km/h|kmph)")
OUT = "data/calibration/json_features_v5.pkl"


def ball_rows(m: int, raw: dict, year: int, archive: str) -> list[dict]:
    """One feature row per ball of a captured match, in delivery order (delivery_number counts within the innings)."""
    rows = []
    players = raw.get("players", {})
    for innings in raw["innings"]:
        ordered = sorted(innings["balls"], key=lambda x: (x.get("over_unique") if x.get("over_unique") is not None else x.get("over"), x.get("id")))
        for number, b in enumerate(ordered, 1):
            text = (b.get("text") or "").strip().lower()
            batter, bowler = players.get(str(b.get("batter"))) or {}, players.get(str(b.get("bowler"))) or {}
            left = is_left_handed(batter.get("batting"))
            has_wagon = has_wagon_data(b.get("wx"), b.get("wy"), b.get("wz"))
            shot = readable(b.get("shot"))
            speed = SPEED.search(text)
            row = {"match_id": m, "ball_id": b.get("id"), "year": year, "archive": archive, "text": text, "innings": int(b.get("innings") or 1), "delivery_number": number, "over": float(b.get("over") or 0),
                   "runs": min(int(b.get("runs") or 0), 6), "extras": int(bool(b.get("wides") or b.get("noballs") or b.get("byes") or b.get("legbyes"))), "wides": int(b.get("wides") or 0), "noballs": int(b.get("noballs") or 0), "byes": int(b.get("byes") or 0), "legbyes": int(b.get("legbyes") or 0),
                   "four": int(bool(b.get("four"))), "six": int(bool(b.get("six"))), "wicket": int(bool(b.get("wicket"))), "dismissal": b.get("dismissal_text") or "",
                   "bowler_type": bowler_type(bowler.get("bowling")), "bowler_id": bowler.get("objectId"), "batter_id": batter.get("objectId"), "left": -1 if left is None else int(bool(left)),
                   "shot_label": shot, "shot_family": family(shot), "control": b.get("control") or 0,
                   "zone_name": zone_direction(b.get("wz"), bool(left)) if has_wagon and left is not None else None,
                   "wx": float(b["wx"]) if has_wagon else None, "wy": float(b["wy"]) if has_wagon else None,
                   "reach": round(boundary_fraction(float(b["wx"]), float(b["wy"])), 3) if has_wagon else None,
                   "angle": round(batter_view_angle(float(b["wx"]), float(b["wy"]), bool(left)), 1) if has_wagon and left is not None else None,
                   "speed": float(speed.group(1)) if speed else None}
            for f, k in KEY.items():
                row[f] = readable(b.get(k))
            row["shot_direction"] = row["zone_name"]
            rows.append(row)
    return rows


def build(stride: int) -> pd.DataFrame:
    queue = build_queue(load_survey())
    year, archive = dict(zip(queue.match_id.astype(int), queue.year)), dict(zip(queue.match_id.astype(int), queue.archive))
    rows = []
    for path in sorted(raw_dir().glob("*.json.gz")):
        m = int(path.name.split(".")[0])
        if m % stride:
            continue
        raw = load_raw(m)
        if not raw or not raw.get("innings"):
            continue
        rows += ball_rows(m, raw, year.get(m, 0), archive.get(m, ""))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    stride = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    df = build(stride)
    out = OUT if stride == 4 else OUT.replace(".pkl", f"_s{stride}.pkl")
    df.to_pickle(out)
    print(f"{len(df):,} balls from {df.match_id.nunique():,} matches saved to {out}")
    print("with text:", int((df.text.str.len() > 0).sum()), "| shot family:", int(df.shot_family.notna().sum()), "| zone:", int(df.zone_name.notna().sum()), "| control:", int((df.control > 0).sum()))
