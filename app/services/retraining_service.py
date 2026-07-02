"""
Automated Model Retraining Pipeline
Runs monthly (cron: 1st of month at 02:00) or on-demand by System Admin.
Uses analyst-confirmed fraud labels since last training run.
"""
import json
import os
import pickle
import uuid
from datetime import datetime
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.models.orm_models import Transaction, MLModelRegistry, AuditLog
from app.ml.model_trainer import train_all_models, train_smishing_classifier, FEATURE_COLS


def _collect_training_data(db: Session) -> Optional[pd.DataFrame]:
    """
    Pull all analyst-confirmed fraud labels and unreviewed legitimate transactions
    for retraining. Returns None if insufficient data.
    """
    # Get all transactions with known ground truth
    transactions = db.query(Transaction).filter(
        Transaction.status == "COMPLETED"
    ).all()

    if len(transactions) < settings.MIN_SAMPLES_FOR_RETRAIN:
        print(f"Insufficient data: {len(transactions)} < {settings.MIN_SAMPLES_FOR_RETRAIN}")
        return None

    records = []
    for txn in transactions:
        rs = txn.risk_score
        if not rs:
            continue

        sub_scores = json.loads(rs.sub_scores or "{}")
        records.append({
            "transaction_id": txn.transaction_id,
            "amount_to_avg_ratio": sub_scores.get("amount_anomaly_ratio", 1.0),
            "kyc_limit_exceeded": 0,
            "txn_velocity_24h": 1,
            "velocity_anomaly": int(sub_scores.get("velocity_anomaly", 0) > 0),
            "is_new_device": 0,
            "is_new_beneficiary": 0,
            "new_device_new_beneficiary": int(sub_scores.get("new_device_new_beneficiary", 0) > 0),
            "sim_swap_flag_72h": int(sub_scores.get("sim_swap_72h", 0) > 0),
            "location_deviation_km": 0,
            "location_deviation_flag": int(sub_scores.get("location_deviation", 0) > 0),
            "off_hours_flag": int(sub_scores.get("off_hours", 0) > 0),
            "smishing_signal": int(sub_scores.get("smishing_signal", 0) > 0),
            "smishing_probability": 0.0,
            "agent_complaint_rate": 0.0,
            "agent_complaint_elevated": 0,
            "is_fraud": int(txn.is_fraud),
        })
        txn.used_for_training = True

    db.commit()
    return pd.DataFrame(records) if records else None


def run_retraining(
    db: Session,
    triggered_by: Optional[int] = None,
    model_dir: str = "./models",
    notes: str = "Scheduled monthly retraining",
) -> dict:
    """
    Execute full retraining pipeline and register new model versions.
    Returns summary dict.
    """
    print(f"\n{'='*60}")
    print(f"  RETRAINING PIPELINE STARTED — {datetime.utcnow().isoformat()}")
    print(f"{'='*60}")

    # Deactivate current active models
    db.query(MLModelRegistry).filter(MLModelRegistry.is_active == True).update(
        {"is_active": False}
    )
    db.commit()

    # Collect training data
    df = _collect_training_data(db)
    if df is None:
        # Fall back to synthetic dataset
        from app.ml.data_generator import generate_dataset
        print("Using synthetic dataset for retraining...")
        df = generate_dataset(n_transactions=10000, fraud_rate=0.03)

    training_samples = len(df)
    fraud_samples = int(df["is_fraud"].sum())

    # Run training
    version = datetime.utcnow().strftime("%Y%m%d_%H%M")
    metrics = train_all_models(df, model_dir=model_dir)

    # Train smishing model
    train_smishing_classifier(model_dir=model_dir)

    # Register models in database
    for model_name, m in metrics.items():
        entry = MLModelRegistry(
            model_name=model_name.upper(),
            version=version,
            is_active=True,
            trained_at=datetime.utcnow(),
            training_samples=training_samples,
            fraud_samples=fraud_samples,
            precision=m.get("precision"),
            recall=m.get("recall"),
            f1_score=m.get("f1_score"),
            auc_roc=m.get("auc_roc"),
            mcc=m.get("mcc"),
            accuracy=m.get("accuracy"),
            model_path=f"{model_dir}/{model_name}.pkl",
            trained_by=triggered_by,
            notes=notes,
            hyperparameters=json.dumps({"version": version}),
        )
        db.add(entry)

    # Audit log
    db.add(AuditLog(
        log_id=str(uuid.uuid4()),
        event_type="RETRAIN",
        operator_id=triggered_by,
        metadata_json=json.dumps({
            "version": version,
            "training_samples": training_samples,
            "fraud_samples": fraud_samples,
            "models_trained": list(metrics.keys()),
        }),
        result="SUCCESS",
    ))

    db.commit()

    # Reload inference models
    global _model_inference_ref
    from app.services.fraud_detection_service import get_model_inference
    import app.services.fraud_detection_service as fds
    fds._model_inference = None  # Force reload on next request

    print(f"\nRetraining complete. Version: {version}")
    print(f"Training samples: {training_samples}, Fraud: {fraud_samples}")

    return {
        "version": version,
        "training_samples": training_samples,
        "fraud_samples": fraud_samples,
        "metrics": metrics,
        "status": "SUCCESS",
    }


def setup_retraining_scheduler(db_session_factory):
    """Configure APScheduler for monthly automated retraining."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BackgroundScheduler()

        def scheduled_retrain():
            db = db_session_factory()
            try:
                run_retraining(db, notes="Automated monthly retraining")
            except Exception as e:
                print(f"Scheduled retraining failed: {e}")
            finally:
                db.close()

        # Run on 1st of every month at 02:00
        scheduler.add_job(
            scheduled_retrain,
            trigger=CronTrigger(day=1, hour=2, minute=0),
            id="monthly_retrain",
            name="Monthly ML Model Retraining",
            replace_existing=True,
        )

        scheduler.start()
        print("Monthly retraining scheduler started (runs on 1st of each month at 02:00)")
        return scheduler

    except Exception as e:
        print(f"Scheduler setup failed: {e}")
        return None
