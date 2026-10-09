# The text predictions file

`cricinfo_text_predictions.csv` gives a predicted line, length, shot and direction, each with a confidence, for balls that have commentary text but no Cricinfo tracking value. It is separate from `cricinfo_tracking.csv`, which holds only what Cricinfo recorded. Every row is an estimate. Nothing in the main files is filled in from it.

## How to read it

- **One row per ball**, joined on `match_id`, `innings` and `delivery_number`. A row exists if at least one of the four fields has a prediction, and the others can be empty.
- **Labels** are always Cricinfo's own: five for line, six for length, the shot names of the match's era (2001 to 2013 or 2014 on), and the eight direction names.
- **`*_confidence`** is the chance, from 0 to 1, that the label matches what Cricinfo would have recorded. It was calibrated on matches the model never saw. A prediction at 0.7 matched Cricinfo about 70% of the time.
- **`*_explicit`** is 1 when the commentary names that label outright and no other, using the phrases in [phrase_meanings.md](phrase_meanings.md). The label still comes from the model. An explicit prediction is right more often than the average prediction.
- **A cell is empty** where Cricinfo has a value, where the ball has no commentary text, or, for direction, where the model judges that the ball was not hit.
- **Line and length for 2001 to 2013** have confidences lowered by 2.2 and 5.6 points, because Cricinfo has no values there to test against.

## How it is built

1. Collect every captured ball that has text, a trusted pairing with Cricsheet and a missing field.
2. Train two models per field (shot per era). Both read the text, phrase cues, the runs, the extras, the dismissal and the bowler type. One also reads Cricinfo's other fields for the ball (shot, wagon point, control). It is trained on balls that have them.
3. Send each ball to the model that fits it: the one that reads the other fields if the ball has any, the text-only one if not. Most balls that need a prediction have none.
4. Calibrate each model's probabilities (isotonic regression) on a tenth of the matches, and check them on another tenth.
5. Write the label, the calibrated confidence and the explicit flag.

Direction has an extra class, "none", learned from tracked matches, so the model can decline a ball that was not hit. The diagram is on the architecture page: [architecture.md](architecture.md).

## The evidence in short

### Accuracy on matches the model never saw

| Field | Balls with other Cricinfo fields (shot, wagon point and so on) | Balls with commentary text only |
|---|---|---|
| Line | 65.2% | 62.9% |
| Length | 62.3% | 59.1% |
| Shot, 2001 to 2013 | 67.6% | 61.1% |
| Shot, 2014 on | 67.6% | 59.8% |
| Direction | 70.8% | 65.3% |

After recalibration the stated confidence is within 0.3 to 0.9 points of the observed agreement for every model, and within about 3 points on a competition held out of training.

### What I tried

| Idea | Result | Decision |
|---|---|---|
| Match the text against label words directly | agrees with Cricinfo 40 to 90%; only "reverse sweep" passes 90%. Where the text names exactly one label, the model beats it on the same balls (line 71.3% against 66.6%, length 60.3% against 54.2%) | not used for labels, only for the explicit flag |
| A learned text model with phrase cues | line about 65%, length about 62% | the base of the final model |
| Cricinfo's other fields as inputs (shot, wagon point, control, runs, dismissal) | the first change to move past the plateau | used where a ball has them |
| One shot model per era | a large gain, as the labels differ before 2014 | kept |
| More data (five times), other model families, a bigger network, a fine-tuned transformer | within a point of the boosting model, an ensemble adds 0.3 | not used, no gain worth the cost |
| Neighbouring balls, player history, separate wide and no-ball features | no gain | not used |
| Phrases as single tokens | +0.1 point | kept, it costs nothing |
| Merging neighbouring labels, a second label per prediction | merging would hide a label Cricinfo keeps separate | declined |
| A careful human reading the text | agrees with Cricinfo only 52 to 56% for line and length | shows the limit: wording and tracking differ |
| The IPL site's coded commentary | exists for 2008 on | not used, its terms need written authorisation |

For example, balls described as "back of a length" are recorded by Cricinfo as short of a good length 52% of the time and as good length 39%. The wording is ambiguous, so no reading of it can beat about 52%, and the model's confidence on those balls says so.

### Risks found and what I did

Some wordings look like a label but are not one. Each is listed in the phrase table with no label. The longest phrase wins, so the whole wording matches first and the single word inside it can never set a label.

| Risk | Measured | Fix (all implemented) |
|---|---|---|
| The word "cut" used of attempts or ball movement | a bare cut matches Cricinfo 65%, "can't cut" 20%, "cut off" 38% | "can't cut it", "cut off", "cuts away" and a few more are listed with no label, so the bare word does not count inside them. Precision rises to 69% |
| Words with another sense: "at this point", "match point", the square leg umpire | direction agreement 57 against 71% | each is listed with no label, so "point" in "at this point" is never read as the fielding zone and "square leg" in "square leg umpire" is never read as a direction |
| "The ball leaves him" (movement, not a leave) | 19 against 62% | "leaves him", "leaves the batter" and similar are listed with no label, so the word "leaves" there never counts as "left alone" |
| Surnames that are table words (Short, Fuller) | 29 against 40% where a player is called Short | a phrase starting with a player's name token is skipped |
| Negation ("not a yorker", "almost a yorker") | over the whole text it makes no difference, but a negator within 4 words before a phrase gives length 41 against 57% and shot 54 against 75% | such a phrase no longer counts for length and shot. Line and direction show no harm, so they are unchanged |
| An edged shot ("pulled, but it is an edge") | shot agreement 64 against 76%. Length, line and direction show no effect | a shot is never explicit when the text says edge or nick |
| Cricinfo records the same shot under another label | forward defence is "defended" 89%, glanced is "flick" 57 to 60%, hooks is "pull" 76% | from 2014 on the table follows the JSON label |
| A fielding position lands in another zone | cover point is cover 74%, gully is point 59%, short leg is mid wicket 64% | the table follows the JSON zone |
| Cricinfo's zones sit differently from the commentary | "wide outside off" is outside offstump 60%, "short and wide" is short of a good length 55% | phrases under 40% agreement, or with another label more often, left the table |
| A missing tracking field read as "left alone" | 96% of balls that need a 2014 on shot prediction have no tracking field, and 78% of those predictions said "left alone" | two models, chosen by whether the ball has other Cricinfo fields |

### Hand checks

I read 100 predictions (25 per field) against their commentary and graded each as supported, no information in the text, doubtful or contradicted. I did this three times: before the fixes, after them, and on a fresh sample from the final models.

| Field | First check | After the fixes | Final models |
|---|---|---|---|
| Line | 10, 9, 2, 4 | 10, 9, 2, 4 | 8, 10, 5, 2 |
| Length | 9, 13, 2, 1 | 9, 13, 2, 1 | 8, 13, 4, 0 |
| Shot | 9, 3, 0, 13 | 20, 2, 3, 0 | 21, 0, 2, 2 |
| Direction | 9, 14, 1, 1 | 19, 5, 0, 1 | 22, 1, 1, 1 |

The first check failed for shot and direction and led to the two-model design and the "none" class. The line and length rows of the first two checks were the same balls and their predictions did not change. Most line and length commentary says nothing about the line or length, so "no information" is the common grade there. A separate isolation check confirms that no prediction sits on a ball Cricinfo already has a value for and that every label is one of Cricinfo's.

## How the explicit flag is decided

[phrase_meanings.md](phrase_meanings.md) maps commentary wording to Cricinfo's JSON labels using cricket usage and Hawk-Eye length zones. Each phrase was measured against the JSON. A phrase is dropped when Cricinfo's JSON agrees with its label less than 40% of the time, or gives another label more often. A few wordings are listed with no label because they look like a label but are not one, a phrase right after a negator is skipped for length and shot, and a shot is never explicit when the text says the ball was edged.

## Keeping the phrase table up to date

Three scripts in `analysis/` maintain the table. `phrase_candidates.py` lists the most common wordings around a field's key words with how Cricinfo labelled those balls. `phrase_audit.py` measures, for every phrase in the table, how often the JSON agrees with its label. `phrase_audit2.py` lists the phrases where the JSON gives another label more often. After any change, run `python -m analysis.phrase_meanings` to regenerate [phrase_meanings.md](phrase_meanings.md), and `python -m analysis.text_predictions write` to rewrite the file with the new flags.

## Fixed phrase tokens

The phrase tokens a model reads are frozen in `analysis/unit_phrases.txt` and stored inside each saved model, so scoring always reads the text the way the model was trained.

## Limits

- Accuracy on held-out matches runs from 59% to 71% depending on the field, and the 2001 to 2013 line and length predictions cannot be tested directly.
- Commentary and Cricinfo's tracking disagree 25 to 45% of the time even where the text names a label outright, so no reading of the text can be much better than these figures.
- The 4,200 matches with no Cricinfo commentary have no predictions.
