"""Model 3: fine-tune DistilBERT for dark / not dark (Hugging Face Trainer).

DistilBERT is a smaller, faster BERT (66M parameters). Fine-tuning = we start from a model that
already understands English and train all its weights a little more on our labelled texts, with a
2-class classification head on top.

Runs on Colab (GPU, ~2 min) via ml/notebooks/train_distilbert.ipynb, or locally:
    python -m ml.train_distilbert            (CPU: ~15-30 min; NVIDIA GPU with CUDA torch: ~2 min)
Saves the model to ml/models/distilbert/ (git-ignored).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import accuracy_score, f1_score
from transformers import (AutoModelForSequenceClassification, AutoTokenizer, Trainer, TrainingArguments,
                          set_seed)

BASE_MODEL = "distilbert-base-uncased"
MAX_LEN = 64  # dark-pattern texts are short (median ~30 chars)


class TextDataset(torch.utils.data.Dataset):
    def __init__(self, df: pd.DataFrame, tokenizer) -> None:
        self.enc = tokenizer(list(df["text"]), truncation=True, max_length=MAX_LEN, padding="max_length")
        self.labels = list(df["label"].astype(int))

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, i: int) -> dict:
        item = {k: torch.tensor(v[i]) for k, v in self.enc.items()}
        item["labels"] = torch.tensor(self.labels[i])
        return item


def compute_metrics(eval_pred) -> dict:
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {"accuracy": accuracy_score(labels, preds), "f1": f1_score(labels, preds)}


def train(data_dir: Path, out_dir: Path, epochs: int = 3, seed: int = 42) -> None:
    set_seed(seed)
    train_df = pd.read_csv(data_dir / "binary_train.csv", keep_default_na=False)
    val_df = pd.read_csv(data_dir / "binary_val.csv", keep_default_na=False)
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL, num_labels=2, id2label={0: "not_dark", 1: "dark"}, label2id={"not_dark": 0, "dark": 1})
    args = TrainingArguments(
        output_dir=str(out_dir / "_checkpoints"), num_train_epochs=epochs, learning_rate=5e-5,
        per_device_train_batch_size=16, per_device_eval_batch_size=64, weight_decay=0.01,
        eval_strategy="epoch", save_strategy="no", logging_steps=50, seed=seed, report_to=[],
    )
    trainer = Trainer(model=model, args=args, train_dataset=TextDataset(train_df, tokenizer),
                      eval_dataset=TextDataset(val_df, tokenizer), compute_metrics=compute_metrics)
    trainer.train()
    print("Validation:", trainer.evaluate())
    out_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    print(f"Saved fine-tuned model to {out_dir}")


def main() -> None:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(root / "data"))
    parser.add_argument("--out-dir", default=str(root / "models" / "distilbert"))
    parser.add_argument("--epochs", type=int, default=3)
    a = parser.parse_args()
    train(Path(a.data_dir), Path(a.out_dir), a.epochs)


if __name__ == "__main__":
    main()
