"""DarkPatternClassifier: one interface over all trained models.

    clf = DarkPatternClassifier()            # loads the best available model
    clf.predict(["Only 2 left!", "Free delivery on all orders"])
    -> [("dark", 0.97), ("not_dark", 0.88)]

Which model? ``ml/results/comparison.json`` (written by ml/evaluate.py) ranks the models by F1;
we load the best one that exists on disk. If DistilBERT is not trained yet we fall back to the
MiniLM embeddings model, then to TF-IDF. Category prediction (which pattern) uses MiniLM or TF-IDF.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

from ml.common import LABELS, MODELS_DIR, RESULTS_DIR

MODEL_FILES = {
    "distilbert": MODELS_DIR / "distilbert",
    "minilm_lr": MODELS_DIR / "minilm_lr.joblib",
    "tfidf_lr": MODELS_DIR / "tfidf_lr.joblib",
}
DEFAULT_ORDER = ["distilbert", "minilm_lr", "tfidf_lr"]


def available_models() -> list[str]:
    return [name for name, path in MODEL_FILES.items() if path.exists()]


def ranked_models() -> list[str]:
    """Model names ordered by test F1 from comparison.json, else the default order."""
    path = RESULTS_DIR / "comparison.json"
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))["models"]
        order = [r["model"] for r in sorted(rows, key=lambda r: -r["f1"])]
        return order + [m for m in DEFAULT_ORDER if m not in order]
    return DEFAULT_ORDER


class DarkPatternClassifier:
    def __init__(self, model: str = "auto", batch_size: int = 64) -> None:
        self.batch_size = batch_size
        self.name: Optional[str] = None
        self._encoder = None  # sentence-transformers model (MiniLM)
        self._bundle: dict = {}
        self._category_bundle: Optional[dict] = None
        self._hf = None  # (tokenizer, model) for DistilBERT
        names = [model] if model != "auto" else [m for m in ranked_models() if m in available_models()]
        if names:
            self._load(names[0])
        self._load_category_model()

    @property
    def available(self) -> bool:
        return self.name is not None

    # ------------------------------------------------------------------ loading
    def _load(self, name: str) -> None:
        if name == "distilbert":
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            path = str(MODEL_FILES["distilbert"])
            self._hf = (AutoTokenizer.from_pretrained(path), AutoModelForSequenceClassification.from_pretrained(path).eval())
        else:
            self._bundle = joblib.load(MODEL_FILES[name])
            if name == "minilm_lr":
                self._encoder = self._get_encoder(self._bundle["encoder"])
        self.name = name

    def _load_category_model(self) -> None:
        for name in ("minilm_lr", "tfidf_lr"):
            if MODEL_FILES[name].exists():
                bundle = self._bundle if self.name == name else joblib.load(MODEL_FILES[name])
                if name == "minilm_lr" and self._encoder is None:
                    self._encoder = self._get_encoder(bundle["encoder"])
                self._category_bundle = {"name": name, **bundle}
                return

    @staticmethod
    def _get_encoder(model_name: str):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name, device="cpu")

    # ------------------------------------------------------------------ prediction
    def predict_proba(self, texts: list[str]) -> np.ndarray:
        """Probability that each text is a dark pattern (shape: len(texts))."""
        if not texts:
            return np.zeros(0)
        if not self.available:
            raise RuntimeError("No trained model found. Run the ML pipeline (see README).")
        if self.name == "distilbert":
            return self._distilbert_proba(texts)
        if self.name == "minilm_lr":
            x = self._encoder.encode(texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False)
            return self._bundle["binary"].predict_proba(x)[:, 1]
        return self._bundle["binary"].predict_proba(texts)[:, 1]

    def _distilbert_proba(self, texts: list[str]) -> np.ndarray:
        import torch

        tokenizer, model = self._hf
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), self.batch_size):
                enc = tokenizer(texts[i:i + self.batch_size], truncation=True, max_length=64, padding=True,
                                return_tensors="pt")
                out.append(torch.softmax(model(**enc).logits, dim=-1)[:, 1].numpy())
        return np.concatenate(out)

    def predict(self, texts: list[str]) -> list[tuple[str, float]]:
        """[(label, confidence)] where label is 'dark' or 'not_dark' and confidence is P(label)."""
        probs = self.predict_proba(texts)
        return [(LABELS[int(p >= 0.5)], float(p if p >= 0.5 else 1 - p)) for p in probs]

    def predict_category(self, texts: list[str]) -> list[Optional[str]]:
        """Pattern category (Urgency, Scarcity, Social Proof, Misdirection, ...) for dark texts."""
        if not texts or not self._category_bundle:
            return [None] * len(texts)
        clf = self._category_bundle["category"]
        if self._category_bundle["name"] == "minilm_lr":
            x = self._encoder.encode(texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False)
            return list(clf.predict(x))
        return list(clf.predict(texts))
