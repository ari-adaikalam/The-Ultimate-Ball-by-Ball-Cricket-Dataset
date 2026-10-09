"""Pair each Cricinfo ball with its Cricsheet row, check the pairing, and build the Cricinfo columns.

Cricsheet is the base. Cricinfo's ball is attached only when it passes the checks, so a wrong
pairing leaves empty cells and never a wrong value. Both sources number every delivery,
extras included, so within an innings the n-th Cricinfo ball is the n-th Cricsheet row. Each pair
is then checked on total runs, and on the striker and bowler through their Cricinfo profile ids.
"""
import pandas as pd

from cricket_pipeline.directions import (
    batter_view_angle, boundary_fraction, has_wagon_data, inside_ring, is_left_handed, zone_direction, zone_from_xy,
)

CRICINFO_COLUMNS = [
    "ball_line", "ball_length", "shot_played", "shot_control", "wagon_x", "wagon_y", "wagon_zone", "wagon_angle",
    "wagon_distance", "wagon_in_ring", "shot_direction", "ball_timestamp", "win_probability", "predicted_score", "ball_events",
]
CONTROL = {1: "in control", 2: "not in control"}


def readable(code):
    """Cricinfo's own value, lower case with spaces: OUTSIDE_OFFSTUMP becomes outside offstump."""
    return code.lower().replace("_", " ") if isinstance(code, str) and code else None


def events_text(events) -> str | None:
    parts = []
    for event in events or []:
        label = event.get("type", "").lower().replace("_", " ")
        if "isSuccessful" in event and event["isSuccessful"] is not None:
            label += " (successful)" if event["isSuccessful"] else " (unsuccessful)"
        if label:
            parts.append(label)
    return "; ".join(parts) or None


def cricinfo_frame(raw: dict) -> pd.DataFrame:
    """All Cricinfo balls of a captured match in delivery order, with the batter's and bowler's Cricinfo profile ids."""
    balls = [ball for innings in raw["innings"] for ball in innings["balls"]]
    frame = pd.DataFrame(balls)
    if frame.empty:
        return frame
    players = raw.get("players", {})
    frame["batter_profile"] = frame["batter"].map(lambda i: (players.get(str(i)) or {}).get("objectId"))
    frame["bowler_profile"] = frame["bowler"].map(lambda i: (players.get(str(i)) or {}).get("objectId"))
    frame["batter_left"] = frame["batter"].map(lambda i: is_left_handed((players.get(str(i)) or {}).get("batting")))
    order = ["innings", "over_unique", "id"] if "over_unique" in frame.columns else ["innings", "over", "id"]
    frame = frame.sort_values(order).reset_index(drop=True)
    frame["seq"] = frame.groupby("innings").cumcount()
    return frame


def pair_by_over(rows: pd.DataFrame, cricinfo: pd.DataFrame, innings: int) -> pd.DataFrame:
    """For an innings whose ball counts differ, give each Cricinfo ball the position of its Cricsheet row, over by over.

    Cricinfo sometimes leaves whole overs out of its commentary (often every second over), so counting from the start of
    the innings would shift every ball after the first gap. An over is paired only when both sources hold the same number
    of deliveries in it. The other overs are dropped, and the run and player checks still apply to the ones that stay.
    """
    mine = cricinfo[cricinfo.innings == innings]
    over_of_row = rows.loc[rows.innings == innings, "ball"].astype(float).map(int)
    over_of_ball = (mine["over_number"].astype(float) - 1).where(mine["over_number"].notna(), mine["over"].astype(float).map(int)).astype(int) \
        if "over_number" in mine.columns else mine["over"].astype(float).map(int)
    positions = rows.loc[rows.innings == innings, "seq"].groupby(over_of_row).apply(list)
    keep, seq = [], {}
    for over, group in mine.groupby(over_of_ball, sort=False):
        wanted = positions.get(over, [])
        if len(group) == len(wanted):
            for index, position in zip(group.index, wanted):
                seq[index] = position
            keep += list(group.index)
    paired = cricinfo.loc[[i for i in cricinfo.index if cricinfo.at[i, "innings"] != innings or i in seq]].copy()
    paired.loc[list(seq), "seq"] = pd.Series(seq)
    return paired


def pair_match(cricsheet: pd.DataFrame, cricinfo: pd.DataFrame, profile_of: dict) -> tuple[pd.DataFrame, dict]:
    """Attach the Cricinfo columns to a match's Cricsheet rows.

    profile_of maps a Cricsheet player id to that player's Cricinfo profile id. Returns the rows with
    the Cricinfo columns added (empty where there is no valid pair) and a report of what happened.
    """
    rows = cricsheet.reset_index(drop=True).copy()
    rows["seq"] = rows.groupby("innings").cumcount()
    report = {"rows": len(rows), "cricinfo_balls": len(cricinfo), "paired": 0, "rejected": 0, "innings_count_differs": [], "rejected_rows": []}
    rows["cricinfo_paired"] = False
    rows["cricinfo_ball_id"] = None
    for column in CRICINFO_COLUMNS:
        rows[column] = None
    if cricinfo.empty:
        return rows.drop(columns="seq"), report

    for innings, group in rows.groupby("innings"):
        if len(group) != int((cricinfo.innings == innings).sum()):
            report["innings_count_differs"].append(int(innings))
    if "ball" in rows.columns and "over" in cricinfo.columns:
        for innings in [i for i in report["innings_count_differs"] if (cricinfo.innings == i).any()]:
            cricinfo = pair_by_over(rows, cricinfo, innings)
    merged = rows[["innings", "seq", "runs_off_bat", "extras", "striker_id", "bowler_id"]].merge(
        cricinfo, on=["innings", "seq"], how="left", suffixes=("", "_cricinfo"), indicator=True,
    )
    merged.index = rows.index

    # A Cricinfo innings that Cricsheet does not have at all is also a disagreement
    for innings in sorted(set(cricinfo.innings.astype(int)) - set(rows.innings.astype(int))):
        report["innings_count_differs"].append(innings)

    has_pair = merged["_merge"] == "both"
    cricsheet_total = merged["runs_off_bat"].fillna(0) + merged["extras"].fillna(0)
    runs_ok = has_pair & (merged["total_runs"].fillna(0) == cricsheet_total)
    # A player ID that cannot be mapped is unknown, not a mismatch
    striker_known = merged["striker_id"].map(profile_of).notna() & merged["batter_profile"].notna()
    bowler_known = merged["bowler_id"].map(profile_of).notna() & merged["bowler_profile"].notna()
    striker_ok = ~striker_known | (merged["striker_id"].map(profile_of) == merged["batter_profile"])
    bowler_ok = ~bowler_known | (merged["bowler_id"].map(profile_of) == merged["bowler_profile"])
    valid = runs_ok & striker_ok & bowler_ok
    # Without over numbers to go by, an innings with a different ball count is not trusted at all, because positions after the gap would shift
    if "ball" not in rows.columns or "over" not in cricinfo.columns:
        for innings in report["innings_count_differs"]:
            valid &= merged["innings"] != innings
    rows["cricinfo_paired"] = valid.to_numpy()       # lets the text predictions tell which Cricsheet rows a Cricinfo ball can be trusted for
    rows["cricinfo_ball_id"] = merged["id"].where(valid).to_numpy()   # which Cricinfo ball each row got, since position differs once overs are missing
    report["paired"] = int(valid.sum())
    report["rejected"] = int((has_pair & ~valid).sum())
    # Every rejected ball is listed with its reason, so a disagreement between the sources is never silent
    for i in merged.index[has_pair & ~valid]:
        reasons = []
        if merged.at[i, "innings"] in report["innings_count_differs"]:
            reasons.append("innings ball count differs")
        if not runs_ok[i]:
            reasons.append(f"runs differ (cricsheet {cricsheet_total[i]:g}, cricinfo {merged.at[i, 'total_runs']:g})")
        if not striker_ok[i]:
            reasons.append("striker differs")
        if not bowler_ok[i]:
            reasons.append("bowler differs")
        ball = rows.at[i, "ball"] if "ball" in rows.columns else rows.at[i, "seq"]
        report["rejected_rows"].append(f"innings {int(merged.at[i, 'innings'])} ball {ball}: {', '.join(reasons)}")

    for i in merged.index[valid]:
        ball = merged.loc[i]
        rows.at[i, "ball_line"] = readable(ball.get("line"))
        rows.at[i, "ball_length"] = readable(ball.get("length"))
        rows.at[i, "shot_played"] = readable(ball.get("shot"))
        rows.at[i, "shot_control"] = CONTROL.get(ball.get("control"))
        if has_wagon_data(ball.get("wx"), ball.get("wy"), ball.get("wz")):
            x, y, left = float(ball["wx"]), float(ball["wy"]), ball["batter_left"]
            rows.at[i, "wagon_x"], rows.at[i, "wagon_y"], rows.at[i, "wagon_zone"] = x, y, int(ball["wz"])
            rows.at[i, "wagon_distance"] = round(boundary_fraction(x, y), 3)
            rows.at[i, "wagon_in_ring"] = inside_ring(x, y)
            if pd.notna(left):
                rows.at[i, "wagon_angle"] = round(batter_view_angle(x, y, bool(left)), 1)
                rows.at[i, "shot_direction"] = zone_direction(zone_from_xy(x, y), bool(left))
        rows.at[i, "ball_timestamp"] = ball.get("timestamp") or None
        rows.at[i, "win_probability"] = ball.get("win_probability")
        rows.at[i, "predicted_score"] = ball.get("predicted_score")
        rows.at[i, "ball_events"] = events_text(ball.get("events"))
    return rows.drop(columns="seq"), report
