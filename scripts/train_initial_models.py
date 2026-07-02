#!/usr/bin/env python3
"""
Initial model training script.
Run once on first deployment before starting the API.
Generates a synthetic Zambian dataset and trains all models.
"""
import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ml.data_generator import generate_dataset
from app.ml.model_trainer import train_all_models, train_smishing_classifier

if __name__ == "__main__":
    print("=" * 60)
    print("  Zambia Fraud Detection — Initial Model Training")
    print("  CBU CS301 · Group 20")
    print("=" * 60)

    os.makedirs("./models", exist_ok=True)
    os.makedirs("./data", exist_ok=True)

    # Generate synthetic Zambian dataset (50k transactions, 3% fraud)
    df = generate_dataset(n_transactions=50000, fraud_rate=0.03)
    df.to_csv("./data/zambia_transactions_50k.csv", index=False)
    print(f"Dataset saved: {len(df)} records")

    # Train all classifiers
    metrics = train_all_models(df, model_dir="./models")

    # Train smishing NLP
    train_smishing_classifier(model_dir="./models")

    print("\n" + "=" * 60)
    print("  Training complete. Model performance summary:")
    print("=" * 60)
    targets = {"precision": 0.85, "recall": 0.80, "auc_roc": 0.90}
    for model_name, m in metrics.items():
        print(f"\n  {model_name.upper()}")
        for metric, target in targets.items():
            val = m.get(metric, 0)
            status = "✓" if val >= target else "✗"
            print(f"    {status} {metric:12s}: {val:.4f}  (target ≥ {target})")

    print("\n  Models saved to ./models/")
    print("  Ready to start API server.")
