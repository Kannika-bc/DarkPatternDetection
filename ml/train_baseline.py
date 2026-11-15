"""Model 1: TF-IDF + Logistic Regression (fast, explainable baseline).

TF-IDF turns each text into a sparse vector of word / word-pair weights (frequent in this text,
rare overall = high weight). Logistic Regression learns one weight per feature, so we can print the
words that push a text towards "dark".

    python -m ml.train_baseline
"""

from __future__ import annotations

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline

from ml.common import MODELS_DIR, SEED, load_split

C_GRID = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0]


def make_pipeline(c: float) -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1, lowercase=True)),
        ("lr", LogisticRegression(C=c, max_iter=2000, class_weight="balanced", random_state=SEED)),
    ])


def fit_best(task: str, label_col: str) -> tuple[Pipeline, float, float]:
    """Pick C on the validation set (macro F1), then refit on train+val."""
    train, val = load_split(task, "train"), load_split(task, "val")
    best_c, best_f1 = C_GRID[0], -1.0
    for c in C_GRID:
        model = make_pipeline(c).fit(train["text"], train[label_col])
        f1 = f1_score(val[label_col], model.predict(val["text"]), average="macro")
        if f1 > best_f1:
            best_c, best_f1 = c, f1
    full = make_pipeline(best_c).fit(list(train["text"]) + list(val["text"]),
                                     list(train[label_col]) + list(val[label_col]))
    return full, best_c, best_f1


def top_words(model: Pipeline, n: int = 15) -> list[str]:
    vocab = model.named_steps["tfidf"].get_feature_names_out()
    coefs = model.named_steps["lr"].coef_[0]
    return [vocab[i] for i in coefs.argsort()[::-1][:n]]


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    binary, c_bin, f1_bin = fit_best("binary", "label")
    print(f"Binary   : best C={c_bin}, val macro-F1={f1_bin:.3f}")
    print("  words most indicative of a dark pattern:", ", ".join(top_words(binary)))
    category, c_cat, f1_cat = fit_best("category", "category")
    print(f"Category : best C={c_cat}, val macro-F1={f1_cat:.3f}")
    joblib.dump({"binary": binary, "category": category}, MODELS_DIR / "tfidf_lr.joblib")
    print(f"Saved {MODELS_DIR / 'tfidf_lr.joblib'}")


if __name__ == "__main__":
    main()
