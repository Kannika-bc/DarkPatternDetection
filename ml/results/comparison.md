# ML model comparison

Binary task (dark vs not dark), ec-darkpattern held-out test set, n = 339 (stratified 15 %, seed 42). Positive class = dark.

| Rank | Model | Accuracy | Precision | Recall | F1 | ms / text (CPU) |
|---|---|---|---|---|---|---|
| 1 | DistilBERT fine-tuned (3 epochs) | 0.971 | 0.975 | 0.963 | 0.969 | 17.23 |
| 2 | TF-IDF (1-2 grams) + Logistic Regression | 0.950 | 0.993 | 0.902 | 0.946 | 0.02 |
| 3 | MiniLM-L6 sentence embeddings + Logistic Regression | 0.932 | 0.961 | 0.896 | 0.927 | 4.46 |

Confusion matrices: `confusion_distilbert.png`, `confusion_tfidf_lr.png`, `confusion_minilm_lr.png`

## Category task (which pattern, dark texts only)

| Model | Accuracy | Macro F1 |
|---|---|---|
| TF-IDF (1-2 grams) + Logistic Regression | 0.969 | 0.969 |
| MiniLM-L6 sentence embeddings + Logistic Regression | 0.975 | 0.978 |

**Best model:** DistilBERT fine-tuned (3 epochs) (used by `ml/predictor.py`).
