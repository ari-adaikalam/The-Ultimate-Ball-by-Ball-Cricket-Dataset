"""The saved model of one predictions field.

It lives in its own module, never run as a script, so that a saved model always records its class as analysis.predictions_bundle.Bundle
and can be loaded from any other module.
"""
from dataclasses import dataclass

import numpy as np

VERSION = "predictions-2"


@dataclass
class Bundle:
    """Everything needed to score new balls for one field without refitting, saved with joblib."""
    field: str
    era: str | None
    classes: np.ndarray
    cats: dict
    drop: set
    words: object
    cues: object
    text_model: object
    model: object
    iso: object
    version: str = VERSION
    units: tuple = ()          # the phrase tokens the text model was trained with, frozen so scoring reads text the same way
