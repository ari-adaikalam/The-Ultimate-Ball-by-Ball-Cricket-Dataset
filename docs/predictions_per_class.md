# Results by label

The accuracy in [predictions_file.md](predictions_file.md) is one number per model. This page splits it by Cricinfo label. All figures are on matches the models never saw. A model was trained on most matches, calibrated on a tenth and tested on another tenth.

- **Test balls** is how many held-out balls carry that Cricinfo label.
- **Precision** is, of the balls the model gave that label, the share where Cricinfo has it too.
- **Recall** is, of the balls Cricinfo gave that label, the share where the model found it.

Two models read each field. One also reads Cricinfo's other fields for the ball (shot, wagon point, control). The other reads the text alone, and it makes the predictions for the balls that have no other Cricinfo field.

### Line

#### Balls that have other Cricinfo fields

Accuracy 65.2% on 269,365 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| outside offstump | 141,328 | 68% | 83% |
| on the stumps | 91,499 | 62% | 57% |
| wide outside offstump | 18,683 | 61% | 10% |
| down leg | 16,836 | 52% | 26% |
| wide down leg | 1,019 | 16% | 3% |

How the balls of each Cricinfo label were labelled (each row adds to 100%, and the columns are the predictions):

| Cricinfo label | down leg | on the stumps | outside offstump | wide down leg | wide outside offstump |
|---|---|---|---|---|---|
| down leg | 26% | 53% | 20% | 0% | 0% |
| on the stumps | 3% | 57% | 40% | 0% | 0% |
| outside offstump | 0% | 16% | 83% | 0% | 1% |
| wide down leg | 60% | 26% | 9% | 3% | 2% |
| wide outside offstump | 0% | 4% | 86% | 0% | 10% |

#### Balls with commentary text only

Accuracy 62.9% on 269,365 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| outside offstump | 141,328 | 65% | 85% |
| on the stumps | 91,499 | 60% | 47% |
| wide outside offstump | 18,683 | 61% | 8% |
| down leg | 16,836 | 49% | 26% |
| wide down leg | 1,019 | 5% | 0% |

How the balls of each Cricinfo label were labelled (each row adds to 100%, and the columns are the predictions):

| Cricinfo label | down leg | on the stumps | outside offstump | wide down leg | wide outside offstump |
|---|---|---|---|---|---|
| down leg | 26% | 49% | 25% | 0% | 0% |
| on the stumps | 3% | 47% | 49% | 0% | 0% |
| outside offstump | 1% | 14% | 85% | 0% | 1% |
| wide down leg | 63% | 27% | 9% | 0% | 1% |
| wide outside offstump | 1% | 3% | 87% | 0% | 8% |


### Length

#### Balls that have other Cricinfo fields

Accuracy 62.3% on 269,428 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| good length | 126,153 | 62% | 78% |
| full | 60,125 | 61% | 46% |
| short of a good length | 57,735 | 60% | 47% |
| short | 14,883 | 70% | 55% |
| full toss | 6,529 | 78% | 64% |
| yorker | 4,003 | 58% | 43% |

How the balls of each Cricinfo label were labelled (each row adds to 100%, and the columns are the predictions):

| Cricinfo label | full | full toss | good length | short | short of a good length | yorker |
|---|---|---|---|---|---|---|
| full | 46% | 1% | 51% | 0% | 1% | 1% |
| full toss | 15% | 64% | 16% | 0% | 2% | 3% |
| good length | 12% | 0% | 78% | 0% | 9% | 0% |
| short | 0% | 0% | 7% | 55% | 38% | 0% |
| short of a good length | 2% | 0% | 45% | 5% | 47% | 0% |
| yorker | 31% | 4% | 20% | 0% | 2% | 43% |

#### Balls with commentary text only

Accuracy 59.1% on 269,428 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| good length | 126,153 | 59% | 79% |
| full | 60,125 | 59% | 38% |
| short of a good length | 57,735 | 56% | 40% |
| short | 14,883 | 67% | 52% |
| full toss | 6,529 | 78% | 64% |
| yorker | 4,003 | 54% | 43% |

How the balls of each Cricinfo label were labelled (each row adds to 100%, and the columns are the predictions):

| Cricinfo label | full | full toss | good length | short | short of a good length | yorker |
|---|---|---|---|---|---|---|
| full | 38% | 1% | 57% | 0% | 2% | 2% |
| full toss | 11% | 64% | 20% | 0% | 1% | 3% |
| good length | 11% | 0% | 79% | 0% | 10% | 0% |
| short | 0% | 0% | 14% | 52% | 33% | 0% |
| short of a good length | 2% | 0% | 52% | 6% | 40% | 0% |
| yorker | 29% | 4% | 24% | 0% | 1% | 43% |


### Shot, 2001 to 2013

#### Balls that have other Cricinfo fields

Accuracy 67.6% on 146,792 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| forward defence | 29,205 | 61% | 70% |
| leg glance | 26,248 | 78% | 81% |
| off side drive on front foot | 26,064 | 65% | 72% |
| no shot | 18,281 | 80% | 87% |
| back defence | 11,742 | 48% | 41% |
| cut shot on back foot | 8,722 | 63% | 65% |
| on side drive on front foot | 7,659 | 71% | 71% |
| off side drive on back foot | 7,148 | 49% | 16% |
| pull hook on back foot | 4,828 | 74% | 64% |
| sweep | 3,036 | 78% | 66% |
| cut shot on front foot | 1,155 | 15% | 1% |
| on side drive on back foot | 946 | 43% | 12% |
| pull hook on front foot | 684 | 17% | 2% |
| padded away | 348 | 59% | 59% |
| reverse sweep | 341 | 67% | 65% |
| vertical forward attack | 274 | 18% | 22% |
| push shot | 111 | 9% | 12% |

The most common mix-ups:

| Cricinfo label | Predicted | Balls | Share of that label |
|---|---|---|---|
| back defence | forward defence | 4,170 | 36% |
| off side drive on front foot | forward defence | 3,359 | 13% |
| forward defence | back defence | 2,780 | 10% |
| forward defence | off side drive on front foot | 2,631 | 9% |
| off side drive on back foot | off side drive on front foot | 2,554 | 36% |
| leg glance | forward defence | 1,546 | 6% |
| forward defence | leg glance | 1,518 | 5% |
| cut shot on back foot | off side drive on front foot | 1,354 | 16% |

#### Balls with commentary text only

Accuracy 61.1% on 146,792 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| forward defence | 29,205 | 56% | 68% |
| leg glance | 26,248 | 64% | 76% |
| off side drive on front foot | 26,064 | 61% | 63% |
| no shot | 18,281 | 71% | 80% |
| back defence | 11,742 | 45% | 35% |
| cut shot on back foot | 8,722 | 63% | 56% |
| on side drive on front foot | 7,659 | 60% | 47% |
| off side drive on back foot | 7,148 | 46% | 14% |
| pull hook on back foot | 4,828 | 74% | 61% |
| sweep | 3,036 | 77% | 59% |
| cut shot on front foot | 1,155 | 10% | 1% |
| on side drive on back foot | 946 | 30% | 9% |
| pull hook on front foot | 684 | 14% | 2% |
| padded away | 348 | 49% | 31% |
| reverse sweep | 341 | 76% | 71% |
| vertical forward attack | 274 | 16% | 9% |
| push shot | 111 | 9% | 3% |

The most common mix-ups:

| Cricinfo label | Predicted | Balls | Share of that label |
|---|---|---|---|
| back defence | forward defence | 4,338 | 37% |
| off side drive on front foot | forward defence | 4,134 | 16% |
| forward defence | back defence | 2,556 | 9% |
| forward defence | off side drive on front foot | 2,318 | 8% |
| forward defence | leg glance | 2,044 | 7% |
| leg glance | forward defence | 2,032 | 8% |
| off side drive on back foot | off side drive on front foot | 1,975 | 28% |
| off side drive on front foot | leg glance | 1,847 | 7% |


### Shot, 2014 on

#### Balls that have other Cricinfo fields

Accuracy 67.6% on 276,427 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| defended | 54,412 | 70% | 86% |
| flick | 38,184 | 67% | 78% |
| on drive | 34,871 | 72% | 77% |
| cover drive | 27,738 | 66% | 77% |
| left alone | 19,971 | 90% | 95% |
| cut shot | 19,026 | 61% | 62% |
| pull | 17,721 | 72% | 73% |
| push | 13,415 | 47% | 8% |
| slog shot | 7,797 | 44% | 34% |
| steered | 7,570 | 60% | 52% |
| square drive | 6,261 | 53% | 34% |
| sweep shot | 5,494 | 70% | 64% |
| leg glance | 5,298 | 47% | 22% |
| straight drive | 3,987 | 57% | 35% |
| slog sweep | 2,465 | 50% | 35% |
| dab | 2,119 | 24% | 11% |
| reverse sweep | 1,711 | 83% | 66% |
| forward defence | 1,254 | 19% | 2% |
| vertical forward attack | 1,200 | 32% | 17% |
| back defence | 728 | 8% | 1% |
| off side drive on front foot | 665 | 5% | 1% |
| hook | 620 | 21% | 17% |
| no shot | 606 | 25% | 12% |
| cut shot on back foot | 577 | 10% | 5% |
| paddle sweep | 528 | 22% | 21% |

The other 11 labels have 2,209 test balls in all.

The most common mix-ups:

| Cricinfo label | Predicted | Balls | Share of that label |
|---|---|---|---|
| push | defended | 5,518 | 41% |
| flick | defended | 3,074 | 8% |
| leg glance | flick | 3,000 | 57% |
| cut shot | cover drive | 2,915 | 15% |
| defended | flick | 2,776 | 5% |
| on drive | defended | 2,322 | 7% |
| cover drive | defended | 2,104 | 8% |
| push | on drive | 1,906 | 14% |

#### Balls with commentary text only

Accuracy 59.8% on 276,427 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| defended | 54,412 | 60% | 84% |
| flick | 38,184 | 60% | 69% |
| on drive | 34,871 | 56% | 64% |
| cover drive | 27,738 | 55% | 60% |
| left alone | 19,971 | 78% | 85% |
| cut shot | 19,026 | 60% | 55% |
| pull | 17,721 | 73% | 70% |
| push | 13,415 | 41% | 7% |
| slog shot | 7,797 | 43% | 29% |
| steered | 7,570 | 52% | 42% |
| square drive | 6,261 | 45% | 19% |
| sweep shot | 5,494 | 70% | 56% |
| leg glance | 5,298 | 43% | 15% |
| straight drive | 3,987 | 49% | 21% |
| slog sweep | 2,465 | 44% | 35% |
| dab | 2,119 | 17% | 2% |
| reverse sweep | 1,711 | 71% | 77% |
| forward defence | 1,254 | 15% | 1% |
| vertical forward attack | 1,200 | 0% | 0% |
| back defence | 728 | 8% | 1% |
| off side drive on front foot | 665 | 1% | 0% |
| hook | 620 | 21% | 6% |
| no shot | 606 | 3% | 1% |
| cut shot on back foot | 577 | 1% | 0% |
| paddle sweep | 528 | 19% | 7% |

The other 11 labels have 2,209 test balls in all.

The most common mix-ups:

| Cricinfo label | Predicted | Balls | Share of that label |
|---|---|---|---|
| push | defended | 5,967 | 44% |
| flick | defended | 4,248 | 11% |
| on drive | defended | 3,985 | 11% |
| cover drive | defended | 3,580 | 13% |
| on drive | flick | 3,235 | 9% |
| flick | on drive | 3,198 | 8% |
| leg glance | flick | 2,882 | 54% |
| defended | flick | 2,854 | 5% |


### Direction

#### Balls that have other Cricinfo fields

Accuracy 70.8% on 181,988 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| cover | 34,674 | 61% | 81% |
| none | 33,628 | 92% | 97% |
| mid wicket | 27,341 | 72% | 71% |
| mid off | 22,050 | 67% | 52% |
| mid on | 21,910 | 72% | 58% |
| point | 15,896 | 67% | 57% |
| square leg | 13,025 | 59% | 65% |
| third man | 7,531 | 68% | 61% |
| fine leg | 5,933 | 68% | 40% |

How the balls of each Cricinfo label were labelled (each row adds to 100%, and the columns are the predictions):

| Cricinfo label | cover | fine leg | mid off | mid on | mid wicket | none | point | square leg | third man |
|---|---|---|---|---|---|---|---|---|---|
| cover | 81% | 0% | 7% | 1% | 1% | 2% | 7% | 0% | 0% |
| fine leg | 1% | 40% | 0% | 1% | 10% | 6% | 0% | 37% | 5% |
| mid off | 34% | 0% | 52% | 11% | 1% | 2% | 0% | 0% | 0% |
| mid on | 13% | 0% | 13% | 58% | 14% | 2% | 0% | 0% | 0% |
| mid wicket | 6% | 0% | 1% | 7% | 71% | 1% | 0% | 12% | 0% |
| none | 1% | 0% | 0% | 0% | 1% | 97% | 0% | 0% | 0% |
| point | 30% | 0% | 0% | 0% | 1% | 2% | 57% | 0% | 8% |
| square leg | 1% | 6% | 0% | 0% | 25% | 2% | 0% | 65% | 1% |
| third man | 7% | 2% | 0% | 0% | 1% | 5% | 23% | 1% | 61% |

#### Balls with commentary text only

Accuracy 65.3% on 181,988 held-out balls.

| Cricinfo label | Test balls | Precision | Recall |
|---|---|---|---|
| cover | 34,674 | 56% | 74% |
| none | 33,628 | 85% | 94% |
| mid wicket | 27,341 | 63% | 66% |
| mid off | 22,050 | 63% | 49% |
| mid on | 21,910 | 67% | 48% |
| point | 15,896 | 65% | 50% |
| square leg | 13,025 | 51% | 58% |
| third man | 7,531 | 65% | 58% |
| fine leg | 5,933 | 68% | 40% |

How the balls of each Cricinfo label were labelled (each row adds to 100%, and the columns are the predictions):

| Cricinfo label | cover | fine leg | mid off | mid on | mid wicket | none | point | square leg | third man |
|---|---|---|---|---|---|---|---|---|---|
| cover | 74% | 0% | 7% | 2% | 3% | 4% | 7% | 2% | 0% |
| fine leg | 5% | 40% | 0% | 1% | 8% | 6% | 0% | 35% | 5% |
| mid off | 34% | 0% | 49% | 8% | 3% | 4% | 0% | 1% | 0% |
| mid on | 14% | 0% | 13% | 48% | 19% | 3% | 0% | 2% | 0% |
| mid wicket | 8% | 0% | 2% | 8% | 66% | 3% | 0% | 12% | 0% |
| none | 4% | 0% | 0% | 0% | 1% | 94% | 0% | 0% | 0% |
| point | 31% | 0% | 1% | 1% | 3% | 4% | 50% | 2% | 9% |
| square leg | 5% | 6% | 0% | 2% | 25% | 3% | 0% | 58% | 1% |
| third man | 9% | 2% | 0% | 0% | 4% | 6% | 17% | 4% | 58% |

