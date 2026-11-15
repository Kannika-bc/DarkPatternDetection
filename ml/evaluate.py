"""Compare every trained model on the SAME held-out test set.

Metrics: accuracy, precision, recall, F1 (dark = positive class), confusion matrix (PNG per model),
inference speed (ms per text). Writes ml/results/comparison.md and comparison.json.

    python -m ml.evaluate
"""

from __future__ import annotations

import time

import matplotlib

matplotlib.use("Agg")  # no window, just files
import matplotlib.pyplot as plt
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)

from ml.common import RESULTS_DIR, load_split, save_json
from ml.predictor import DarkPatternClassifier, available_models

DESCRIPTIONS = {
    "tfidf_lr": "TF-IDF (1-2 grams) + Logistic Regression",
    "minilm_lr": "MiniLM-L6 sentence embeddings + Logistic Regression",
    "distilbert": "DistilBERT fine-tuned (3 epochs)",
}


def evaluate_model(name: str, texts: list[str], y_true: list[int]) -> dict:
    clf = DarkPatternClassifier(model=name)
    clf.predict_proba(texts[:8])  # warm-up (loads lazy parts) so timing is fair
    t0 = time.perf_counter()
    probs = clf.predict_proba(texts)
    ms_per_text = (time.perf_counter() - t0) * 1000 / len(texts)
    y_pred = [int(p >= 0.5) for p in probs]

    cm = confusion_matrix(y_true, y_pred)
    disp = ConfusionMatrixDisplay(cm, display_labels=["not dark", "dark"])
    disp.plot(cmap="Blues", colorbar=False)
    plt.title(f"{name}  (test set, n={len(texts)})")
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / f"confusion_{name}.png", dpi=120)
    plt.close()

    return {
        "model": name, "description": DESCRIPTIONS.get(name, name),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred), 4),
        "recall": round(recall_score(y_true, y_pred), 4),
        "f1": round(f1_score(y_true, y_pred), 4),
        "ms_per_text": round(ms_per_text, 3),
        "confusion_matrix": cm.tolist(),
    }


def evaluate_category() -> list[dict]:
    """Macro-F1 of the category heads (TF-IDF and MiniLM) on the category test split."""
    import joblib

    from ml.common import MODELS_DIR
    from ml.predictor import MODEL_FILES

    test = load_split("category", "test")
    rows = []
    for name in ("tfidf_lr", "minilm_lr"):
        if not MODEL_FILES[name].exists():
            continue
        bundle = joblib.load(MODELS_DIR / MODEL_FILES[name].name)
        if name == "minilm_lr":
            from sentence_transformers import SentenceTransformer

            x = SentenceTransformer(bundle["encoder"], device="cpu").encode(list(test["text"]), normalize_embeddings=True)
        else:
            x = list(test["text"])
        pred = bundle["category"].predict(x)
        rows.append({"model": name, "accuracy": round(accuracy_score(test["category"], pred), 4),
                     "macro_f1": round(f1_score(test["category"], pred, average="macro"), 4)})
    return rows


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    test = load_split("binary", "test")
    texts, y_true = list(test["text"]), list(test["label"].astype(int))
    models = available_models()
    if not models:
        raise SystemExit("No trained models. Run ml.train_baseline / ml.train_embeddings first.")

    rows = []
    for name in models:
        print(f"Evaluating {name} ...")
        rows.append(evaluate_model(name, texts, y_true))
    rows.sort(key=lambda r: -r["f1"])
    cat_rows = evaluate_category()
    save_json({"test_size": len(texts), "models": rows, "category": cat_rows}, RESULTS_DIR / "comparison.json")

    lines = [
        "# ML model comparison", "",
        f"Binary task (dark vs not dark), ec-darkpattern held-out test set, n = {len(texts)} "
        "(stratified 15 %, seed 42). Positive class = dark.", "",
        "| Rank | Model | Accuracy | Precision | Recall | F1 | ms / text (CPU) |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['description']} | {r['accuracy']:.3f} | {r['precision']:.3f} | "
                     f"{r['recall']:.3f} | {r['f1']:.3f} | {r['ms_per_text']:.2f} |")
    lines += ["", "Confusion matrices: " + ", ".join(f"`confusion_{r['model']}.png`" for r in rows), ""]
    if cat_rows:
        lines += ["## Category task (which pattern, dark texts only)", "",
                  "| Model | Accuracy | Macro F1 |", "|---|---|---|"]
        lines += [f"| {DESCRIPTIONS[r['model']]} | {r['accuracy']:.3f} | {r['macro_f1']:.3f} |" for r in cat_rows]
        lines.append("")
    lines += [f"**Best model:** {rows[0]['description']} (used by `ml/predictor.py`)."]
    (RESULTS_DIR / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
