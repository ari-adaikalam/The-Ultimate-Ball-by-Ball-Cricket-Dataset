"""Per-class results of the saved prediction models on the matches they never saw.

    .venv/bin/python -m analysis.predictions_report

Writes docs/predictions_per_class.md: for every field and model, the accuracy, then for each Cricinfo label how many test balls
carry it, how often the model is right when it says it (precision) and how often it finds it (recall), and for the small
fields the full confusion matrix. The held-out matches are chosen exactly as in text_predictions.fit, so the accuracy here
must equal the accuracy that fit printed. The run stops if it does not.
"""
import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import analysis.text_predictions as tp
from analysis.text_model import MIN_CLASS

REGIMES = {"T": "Balls that have other Cricinfo fields", "N": "Balls with commentary text only"}
FIELD_TITLES = {"ball_line": "Line", "ball_length": "Length", "shot_played": "Shot", "shot_direction": "Direction"}
ERA_TITLES = {"old": "2001 to 2013", "new": "2014 on"}
MATRIX_LIMIT = 10          # a confusion matrix is shown only for fields with this many labels or fewer
CLASS_ROWS = 25            # a per-class table lists at most this many labels, the biggest first
OUT = Path("docs/predictions_per_class.md")
LOGS = [Path("data/calibration/refit_A.log"), Path("data/calibration/refit_B.log")]      # what fit printed when it trained the saved models


def held_out(df: pd.DataFrame, field: str, era: str | None) -> pd.DataFrame:
    """The test matches of text_predictions.fit for one field and era, in the same way."""
    df = df[df.match_id % tp.STRIDE == 0]
    df = tp.with_units(df)
    if field == "shot_direction":
        df = df[df.match_id % 2 == 0]
        tracked = df.groupby("match_id").zone_name.transform(lambda z: z.notna().mean()) >= 0.5
        df = df.assign(shot_direction=df.shot_direction.where(df.shot_direction.notna() | ~tracked, "none"))
    ids = df.match_id.unique()
    test_ids = set(ids[::10])
    part = df[df[field].notna() & tp.era_mask(df, era)]
    keep = part[field].value_counts()
    keep = keep[keep >= MIN_CLASS].index
    part = part[part[field].isin(keep)]
    return part[part.match_id.isin(test_ids)].reset_index(drop=True)


def logged_accuracy() -> dict:
    """The test accuracy that fit printed for each tag and model, such as {("ball_line", "T"): 65.2}."""
    found, tag = {}, None
    for log in LOGS:
        if not log.exists():
            continue
        for line in log.read_text().splitlines():
            head = re.match(r"=== (\S+):", line)
            if head:
                tag = head.group(1)
            hit = re.match(r"\s*\[([TN])\] test accuracy ([\d.]+)%", line)
            if hit and tag:
                found[(tag, hit.group(1))] = float(hit.group(2))
    return found


def per_class(truth: np.ndarray, guess: np.ndarray, classes) -> pd.DataFrame:
    rows = []
    for c in classes:
        tp_ = int(((truth == c) & (guess == c)).sum())
        support, said = int((truth == c).sum()), int((guess == c).sum())
        rows.append({"label": c, "test_balls": support, "precision": tp_ / said if said else np.nan, "recall": tp_ / support if support else np.nan})
    return pd.DataFrame(rows).sort_values("test_balls", ascending=False).reset_index(drop=True)


def confusion(truth: np.ndarray, guess: np.ndarray, classes) -> pd.DataFrame:
    """Rows are the Cricinfo label, columns the prediction, cells the share of that row's balls."""
    table = pd.crosstab(pd.Series(truth, name="truth"), pd.Series(guess, name="guess")).reindex(index=classes, columns=classes, fill_value=0)
    return table.div(table.sum(axis=1).replace(0, np.nan), axis=0)


def top_mixups(truth: np.ndarray, guess: np.ndarray, n: int = 8) -> pd.DataFrame:
    wrong = pd.DataFrame({"truth": truth, "guess": guess})
    wrong = wrong[wrong.truth != wrong.guess]
    counts = wrong.value_counts().head(n).rename("balls").reset_index()
    totals = pd.Series(truth).value_counts()
    counts["share_of_label"] = counts.apply(lambda r: r.balls / totals[r.truth], axis=1)
    return counts


def pct(value) -> str:
    return "" if pd.isna(value) else f"{100 * value:.0f}%"


def markdown_table(frame: pd.DataFrame) -> str:
    lines = ["| " + " | ".join(frame.columns) + " |", "|" + "---|" * len(frame.columns)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in frame.itertuples(index=False)]
    return "\n".join(lines)


def section(title: str, accuracy: float, classes_table: pd.DataFrame, matrix: pd.DataFrame | None, mixups: pd.DataFrame, small: bool) -> str:
    out = [f"#### {title}", "", f"Accuracy {100 * accuracy:.1f}% on {int(classes_table.test_balls.sum()):,} held-out balls.", ""]
    shown = classes_table.head(CLASS_ROWS)
    table = pd.DataFrame({"Cricinfo label": shown.label, "Test balls": shown.test_balls.map("{:,}".format),
                          "Precision": shown.precision.map(pct), "Recall": shown.recall.map(pct)})
    out += [markdown_table(table), ""]
    if len(classes_table) > CLASS_ROWS:
        rest = classes_table.iloc[CLASS_ROWS:]
        out += [f"The other {len(rest)} labels have {int(rest.test_balls.sum()):,} test balls in all.", ""]
    if small and matrix is not None:
        grid = matrix.map(pct)
        grid.insert(0, "Cricinfo label", grid.index)
        out += ["How the balls of each Cricinfo label were labelled (each row adds to 100%, and the columns are the predictions):", "", markdown_table(grid.reset_index(drop=True)), ""]
    else:
        table = pd.DataFrame({"Cricinfo label": mixups.truth, "Predicted": mixups.guess, "Balls": mixups.balls.map("{:,}".format), "Share of that label": mixups.share_of_label.map(pct)})
        out += ["The most common mix-ups:", "", markdown_table(table), ""]
    return "\n".join(out)


def run() -> int:
    df = pd.read_pickle(tp.FULL)
    logged, sections, mismatches = logged_accuracy(), [], []
    for field, title in FIELD_TITLES.items():
        eras = ("old", "new") if field == "shot_played" else (None,)
        for era in eras:
            test = held_out(df, field, era)
            tag = f"{field}{'_' + era if era else ''}"
            heading = f"### {title}" + (f", {ERA_TITLES[era]}" if era else "")
            blocks = [heading, ""]
            for regime, regime_title in REGIMES.items():
                path = tp.MODELS / f"predictions_{tag}_{regime}.joblib"
                if not path.exists():
                    continue
                bundle = joblib.load(path)
                scored = tp.score(bundle, test)
                truth, guess = test[field].to_numpy(), scored.label.to_numpy()
                accuracy = float((truth == guess).mean())
                classes = list(bundle.classes)
                table = per_class(truth, guess, classes)
                small = len(classes) <= MATRIX_LIMIT
                blocks.append(section(regime_title, accuracy, table, confusion(truth, guess, classes) if small else None, top_mixups(truth, guess), small))
                expected = logged.get((tag, regime))
                note = "" if expected is None else ("  matches the training log" if abs(100 * accuracy - expected) <= 0.06 else f"  DIFFERS from the training log ({expected}%)")
                if expected is not None and abs(100 * accuracy - expected) > 0.06:
                    mismatches.append(f"{tag} {regime}: {100 * accuracy:.2f}% against {expected}%")
                print(f"{tag} {regime}: accuracy {100 * accuracy:.2f}% on {len(test):,} balls{note}", flush=True)
            sections.append("\n".join(blocks))
    intro = (
        "# Results by label\n\n"
        "The accuracy in [predictions_file.md](predictions_file.md) is one number per model. This page splits it by Cricinfo label. "
        "All figures are on matches the models never saw. A model was trained on most matches, calibrated on a tenth and tested on another tenth.\n\n"
        "- **Test balls** is how many held-out balls carry that Cricinfo label.\n"
        "- **Precision** is, of the balls the model gave that label, the share where Cricinfo has it too.\n"
        "- **Recall** is, of the balls Cricinfo gave that label, the share where the model found it.\n\n"
        "Two models read each field. One also reads Cricinfo's other fields for the ball (shot, wagon point, control). The other reads the text alone, "
        "and it makes the predictions for the balls that have no other Cricinfo field.\n"
    )
    if mismatches:
        print("The accuracy does not match what training printed, so nothing is written:", *mismatches, sep="\n  ")
        return 1
    OUT.write_text(intro + "\n" + "\n\n".join(sections) + "\n", encoding="utf-8")
    print(f"written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
