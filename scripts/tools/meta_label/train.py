#!/usr/bin/env python3
"""Train meta-label classifier and save joblib bundle."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from scripts.core.meta_label.features import FEATURE_NAMES

try:
    import joblib
except ImportError:
    print("joblib required: pip install joblib")
    raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description="Train meta-label model")
    parser.add_argument("--input", default="data/meta_label/train.csv")
    parser.add_argument("--out-dir", default="models/meta_label")
    parser.add_argument("--test-size", type=float, default=0.2)
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Input not found: {args.input}")
        return 1

    if args.input.endswith(".parquet"):
        df = pd.read_parquet(args.input)
    else:
        df = pd.read_csv(args.input)
    if len(df) < 50:
        print(f"Need at least 50 rows, got {len(df)}")
        return 1

    missing = [c for c in FEATURE_NAMES if c not in df.columns]
    if missing:
        print(f"Missing feature columns: {missing}")
        return 1

    X = df[FEATURE_NAMES].astype(float)
    y = df["label_meta"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, shuffle=False
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = HistGradientBoostingClassifier(
        max_depth=5,
        learning_rate=0.08,
        max_iter=200,
        min_samples_leaf=20,
        class_weight="balanced",
        random_state=42,
    )
    model.fit(X_train_s, y_train)

    proba = model.predict_proba(X_test_s)[:, 1]
    preds = (proba >= 0.5).astype(int)
    metrics = {
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "roc_auc": float(roc_auc_score(y_test, proba)) if len(set(y_test)) > 1 else None,
        "report": classification_report(y_test, preds, output_dict=True),
    }

    os.makedirs(args.out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_path = os.path.join(args.out_dir, f"meta_label_{stamp}.joblib")
    bundle = {
        "model": model,
        "scaler": scaler,
        "feature_names": FEATURE_NAMES,
    }
    joblib.dump(bundle, model_path)

    metrics_path = os.path.join(args.out_dir, f"meta_label_{stamp}_metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"Model saved: {model_path}")
    print(f"Metrics: {metrics_path}")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
