"""Hand-written grouping of Cricinfo's shot labels into families that mean the same in both eras.

2001 to 2013 uses about 15 coarse labels ("off side drive on front foot"). 2014 onward uses about 40 fine ones ("cover drive").
Both are Cricinfo's own. The families only group them so that a model can learn "a pull goes with a short ball" once and use it
in either era. The families are never written to the dataset.
"""
FAMILY = {
    "defend": ["forward defence", "back defence", "defended", "push", "push shot", "vertical forward attack"],
    "leave": ["no shot", "left alone", "padded away", "drop and run"],
    "off_drive": ["off side drive on front foot", "off side drive on back foot", "cover drive", "square drive", "straight drive"],
    "on_drive": ["on side drive on front foot", "on side drive on back foot", "on drive"],
    "leg_work": ["leg glance", "flick", "paddle away", "paddle sweep"],
    "cut_guide": ["cut shot", "cut shot on back foot", "cut shot on front foot", "upper cut", "late cut", "steered", "dab"],
    "pull_hook": ["pull", "hook", "pull hook on back foot", "pull hook on front foot", "reverse pull"],
    "sweep": ["sweep", "sweep shot", "slog sweep", "reverse sweep", "reverse scoop", "ramp"],
    "slog": ["slog shot"],
}
LOOKUP = {label: family for family, labels in FAMILY.items() for label in labels}


def family(label):
    return LOOKUP.get(label) if isinstance(label, str) else None
