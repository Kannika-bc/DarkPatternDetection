"""Download, clean, label and split the dark-pattern text datasets.

Datasets
* ec-darkpattern (Yada et al., 2022): 2,356 texts from e-commerce sites, balanced 50/50 dark / not
  dark, with the pattern category of each dark text. -> our BINARY task.
* "Dark Patterns at Scale" (Mathur et al., 2019): 1,818 dark-pattern strings from 11K shopping
  sites with category and type. Together with the dark rows of ec-darkpattern -> our CATEGORY task
  (which kind of dark pattern is it?).

Output (git-ignored): ml/data/{binary,category}_{train,val,test}.csv  (stratified 70/15/15, seed 42)

    python -m ml.prepare_data
"""

from __future__ import annotations

import urllib.request

import pandas as pd
from sklearn.model_selection import train_test_split

from ml.common import DATA_DIR, RAW_DIR, SEED, clean_text

SOURCES = {
    "ec_darkpattern.tsv": "https://raw.githubusercontent.com/yamanalab/ec-darkpattern/master/dataset/dataset.tsv",
    "princeton_dark_patterns.csv": "https://raw.githubusercontent.com/aruneshmathur/dark-patterns/master/data/final-dark-patterns/dark-patterns.csv",
}
MIN_CATEGORY_COUNT = 20  # categories rarer than this (e.g. Forced Action: 10 texts) are dropped


def download() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = RAW_DIR / name
        if not target.exists():
            print(f"Downloading {name} ...")
            urllib.request.urlretrieve(url, target)


def _dedupe(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    """Drop empty texts, exact duplicates, and texts that appear with conflicting labels."""
    df = df[df["text"].str.len() > 0].copy()
    df["key"] = df["text"].str.lower()
    conflicts = df.groupby("key")[label_col].nunique()
    df = df[~df["key"].isin(conflicts[conflicts > 1].index)]
    return df.drop_duplicates("key").drop(columns="key")


def _split(df: pd.DataFrame, label_col: str, name: str) -> None:
    train, rest = train_test_split(df, test_size=0.30, stratify=df[label_col], random_state=SEED)
    val, test = train_test_split(rest, test_size=0.50, stratify=rest[label_col], random_state=SEED)
    for split, part in (("train", train), ("val", val), ("test", test)):
        part.to_csv(DATA_DIR / f"{name}_{split}.csv", index=False)
    print(f"  {name}: train={len(train)} val={len(val)} test={len(test)}")


def build_binary() -> pd.DataFrame:
    ec = pd.read_csv(RAW_DIR / "ec_darkpattern.tsv", sep="\t", keep_default_na=False)
    df = pd.DataFrame({
        "text": ec["text"].map(clean_text),
        "label": ec["label"].astype(int),  # 1 = dark, 0 = not dark
        "category": ec["Pattern Category"].where(ec["label"].astype(int) == 1, ""),
        "source": "ec-darkpattern",
    })
    return _dedupe(df, "label")


def build_category() -> pd.DataFrame:
    ec = pd.read_csv(RAW_DIR / "ec_darkpattern.tsv", sep="\t", keep_default_na=False)
    ec = ec[ec["label"].astype(int) == 1]
    pr = pd.read_csv(RAW_DIR / "princeton_dark_patterns.csv", keep_default_na=False)
    df = pd.concat([
        pd.DataFrame({"text": ec["text"].map(clean_text), "category": ec["Pattern Category"], "source": "ec-darkpattern"}),
        pd.DataFrame({"text": pr["Pattern String"].map(clean_text), "category": pr["Pattern Category"], "source": "princeton"}),
    ])
    df = _dedupe(df, "category")
    counts = df["category"].value_counts()
    return df[df["category"].isin(counts[counts >= MIN_CATEGORY_COUNT].index)]


def main() -> None:
    download()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    binary = build_binary()
    print(f"\nBINARY task (dark vs not dark): {len(binary)} texts after cleaning")
    print(binary["label"].value_counts().rename({1: "dark", 0: "not_dark"}).to_string())
    print(f"  mean length: {binary['text'].str.len().mean():.0f} chars")
    _split(binary, "label", "binary")

    category = build_category()
    print(f"\nCATEGORY task (which pattern): {len(category)} dark texts after cleaning")
    print(category["category"].value_counts().to_string())
    _split(category, "category", "category")


if __name__ == "__main__":
    main()
