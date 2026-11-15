"""Model 2: sentence-transformers MiniLM embeddings + Logistic Regression (runs on CPU).

all-MiniLM-L6-v2 maps any sentence to a 384-number vector where similar meanings are close
together ("only 2 left" ~ "few items remaining"), even with different words. A Logistic Regression
on top of these vectors is cheap to train and generalises better than word counts.

    python -m ml.train_embeddings
"""

from __future__ import annotations

import joblib
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from ml.common import EMBEDDING_MODEL, MODELS_DIR, SEED, load_split

C_GRID = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]


def embed(encoder: SentenceTransformer, texts: list[str]) -> np.ndarray:
    return encoder.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)


def fit_best(encoder: SentenceTransformer, task: str, label_col: str) -> tuple[LogisticRegression, float, float]:
    train, val = load_split(task, "train"), load_split(task, "val")
    x_train, x_val = embed(encoder, list(train["text"])), embed(encoder, list(val["text"]))
    best_c, best_f1 = C_GRID[0], -1.0
    for c in C_GRID:
        clf = LogisticRegression(C=c, max_iter=3000, class_weight="balanced", random_state=SEED)
        clf.fit(x_train, train[label_col])
        f1 = f1_score(val[label_col], clf.predict(x_val), average="macro")
        if f1 > best_f1:
            best_c, best_f1 = c, f1
    clf = LogisticRegression(C=best_c, max_iter=3000, class_weight="balanced", random_state=SEED)
    clf.fit(np.vstack([x_train, x_val]), list(train[label_col]) + list(val[label_col]))
    return clf, best_c, best_f1


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    encoder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    binary, c_bin, f1_bin = fit_best(encoder, "binary", "label")
    print(f"Binary   : best C={c_bin}, val macro-F1={f1_bin:.3f}")
    category, c_cat, f1_cat = fit_best(encoder, "category", "category")
    print(f"Category : best C={c_cat}, val macro-F1={f1_cat:.3f}")
    joblib.dump({"encoder": EMBEDDING_MODEL, "binary": binary, "category": category},
                MODELS_DIR / "minilm_lr.joblib")
    print(f"Saved {MODELS_DIR / 'minilm_lr.joblib'}")


if __name__ == "__main__":
    main()
