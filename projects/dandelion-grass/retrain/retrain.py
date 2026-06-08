"""
Standalone retraining script — can be called directly or triggered by Airflow.

Usage:
    python -m retrain.retrain
    python -m retrain.retrain --epochs 15 --lr 1e-4
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def main():
    parser = argparse.ArgumentParser(description="Retrain the Dandelion vs Grass model")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--patience", type=int, default=4)
    args = parser.parse_args()

    from src.train_optimized import train_one_run_optimized

    print(f"[retrain] Starting: epochs={args.epochs} lr={args.lr} batch={args.batch_size}")
    model_uri = train_one_run_optimized(
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        patience=args.patience,
    )
    print(f"[retrain] Done. Model saved to: {model_uri}")

    api_url = os.getenv("API_URL", "http://localhost:8000")
    try:
        import requests
        r = requests.post(f"{api_url}/admin/reload", params={"model_s3_uri": model_uri}, timeout=60)
        r.raise_for_status()
        print(f"[retrain] API reloaded with new model.")
    except Exception as e:
        print(f"[retrain] Warning: could not reload API: {e}")

    return model_uri


if __name__ == "__main__":
    main()
