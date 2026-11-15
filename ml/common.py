"""Shared paths and helpers for the ML pipeline."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"  # git-ignored
RAW_DIR = DATA_DIR / "raw"
MODELS_DIR = ML_DIR / "models"  # git-ignored
RESULTS_DIR = ML_DIR / "results"  # small, committed

SEED = 42
LABELS = ["not_dark", "dark"]  # index 0 / 1
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def clean_text(text: str) -> str:
    """Normalise whitespace and strip. We keep case and punctuation: '!!!' and CAPS are signals."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def load_split(task: str, split: str) -> pd.DataFrame:
    """Load ml/data/{task}_{split}.csv  (task = binary | category, split = train | val | test)."""
    path = DATA_DIR / f"{task}_{split}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python -m ml.prepare_data")
    return pd.read_csv(path, keep_default_na=False)


def save_json(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def set_seed(seed: int = SEED) -> None:
    np.random.seed(seed)
