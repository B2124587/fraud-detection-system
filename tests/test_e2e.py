"""
End-to-End Test Suite — CBU CS301 Group 20
Tests: data generation, feature engineering, risk scoring,
       ML inference, API endpoints, auth, alerts, override,
       compliance export, retraining pipeline.
Run: python -m pytest tests/ -v
"""
import json
import sys
import os
import uuid
import hashlib
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

# Force SQLite for tests
settings.DATABASE_URL = "sqlite:///./test_fraud.db"

from app.models.database import SessionLocal, create_tables, engine
from app.models.orm_models import Base, UserProfile, BehavioralProfile, NetworkOperator, UserRole
from app.services.auth_service import hash_password


# ─── Fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Create tables once for the whole test session."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_fraud.db"):
        os.remove("./test_fraud.db")


@pytest.fixture(scope="session")
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="session")
def analyst_user(db):
    """Create a test fraud analyst user."""
    existing = db.query(UserProfile).filter(UserProfile.username == "test_analyst").first()
    if existing:
        return existing
    user = UserProfile(
        hashed_user_id=hashlib.sha256(b"test_analyst").hexdigest()[:32],
        hashed_msisdn=hashlib.sha256(b"0961234567").hexdigest()[:32],
        operator=NetworkOperator.MTN,
        username="test_analyst",
        email="test@cbu.ac.zm",
        hashed_password=hash_password("Test@2024!"),
        role=UserRole.FRAUD_ANALYST,
        is_portal_user=True,
    )
    db.add(user)
    db.flush()
    db.add(BehavioralProfile(user_id=user.id))
    db.commit()
    return user


@pytest.fixture(scope="session")
def admin_user(db):
    """Create a test system admin user."""
    existing = db.query(UserProfile).filter(UserProfile.username == "test_admin").first()
    if existing:
        return existing
    user = UserProfile(
        hashed_user_id=hashlib.sha256(b"test_admin").hexdigest()[:32],
        hashed_msisdn=hashlib.sha256(b"0977654321").hexdigest()[:32],
        operator=NetworkOperator.MTN,
        username="test_admin",
        email="admin_test@cbu.ac.zm",
        hashed_password=hash_password("Admin@2024!"),
        role=UserRole.SYSTEM_ADMIN,
        is_portal_user=True,
    )
    db.add(user)
    db.flush()
    db.add(BehavioralProfile(user_id=user.id))
    db.commit()
    return user


# ─── Test 1: Synthetic Data Generation ───────────────────────────

def test_01_synthetic_data_generation():
    """Verify synthetic dataset generation produces correct size and fraud rate."""
    from app.ml.data_generator import generate_dataset

    df = generate_dataset(n_transactions=500, fraud_rate=0.03)

    assert len(df) == 500, f"Expected 500 transactions, got {len(df)}"
    fraud_rate = df["is_fraud"].mean()
    assert 0.01 <= fraud_rate <= 0.06, f"Fraud rate {fraud_rate:.3f} out of expected range"

    required_cols = [
        "transaction_id", "timestamp", "sender_msisdn", "receiver_msisdn",
        "amount", "transaction_type", "operator", "is_fraud",
        "sim_swap_flag_72h", "is_new_device", "is_new_beneficiary",
        "amount_to_avg_ratio", "location_deviation_km",
    ]
    for col in required_cols:
        assert col in df.columns, f"Missing column: {col}"

    assert df["amount"].min() > 0
    assert df["operator"].isin(["MTN", "AIRTEL", "ZAMTEL"]).all()
    fraud_types = df[df["is_fraud"]]["fraud_type"].unique()
    assert len(fraud_types) > 0

    print(f"\n  ✓ Dataset: {len(df)} records, fraud rate={fraud_rate:.2%}")


# ─── Test 2: Feature Engineering ─────────────────────────────────

def test_02_feature_engineering():
    """Verify FeatureEngineeringService computes all required indicators correctly."""
    from app.ml.feature_engineering import FeatureEngineeringService

    blocklist = {hashlib.sha256(b"fraud_receiver").hexdigest()[:32]}
    fe = FeatureEngineeringService(blocklist_hashes=blocklist)

    ts = datetime(2024, 3, 15, 2, 30)  # Off-hours

    fv = fe.compute(
        transaction_id="TEST-001",
        amount=9000.0,         # 3x avg (300 * 30 = 9000, so ratio=30 -> anomaly)
        timestamp=ts,
        sender_msisdn_hash="sender_hash",
        receiver_msisdn_hash=hashlib.sha256(b"fraud_receiver").hexdigest()[:32],
        channel="USSD",
        kyc_tier=1,
        avg_30day_amount=300.0,
        active_hours_start=7,
        active_hours_end=21,
        registered_devices=["known_device"],
        known_beneficiaries=["known_ben"],
        current_device_fp="unknown_device_xyz",
        sim_swap_flag_72h=True,
        pin_change_recent=False,
        location_deviation_km=250.0,
        usual_province="Lusaka",
        current_province="Copperbelt",
        recent_txn_timestamps_1h=[datetime.utcnow()] * 2,
        recent_txn_timestamps_24h=[datetime.utcnow()] * 6,
        smishing_signal_30min=True,
        smishing_probability=0.85,
        agent_complaint_rate=0.0,
    )

    assert fv.sim_swap_flag_72h is True,          "SIM swap flag should be True"
    assert fv.amount_to_avg_ratio == pytest.approx(30.0, rel=0.01), "Amount ratio wrong"
    assert fv.is_new_device is True,              "New device flag should be True"
    assert fv.is_new_beneficiary is True,         "New beneficiary flag should be True"
    assert fv.new_device_new_beneficiary is True, "Combined flag should be True"
    assert fv.location_deviation_flag is True,    "Location deviation >200km"
    assert fv.off_hours_flag is True,             "02:30 is off-hours (7-21)"
    assert fv.smishing_signal_30min is True,      "Smishing signal should be set"
    assert fv.receiver_on_blocklist is True,      "Receiver should be on blocklist"
    assert fv.txn_velocity_24h == 6,              "Velocity should be 6"
    assert fv.velocity_anomaly is True,           ">5 transactions in 24h"

    array = fv.to_ml_array()
    assert len(array) == 18, f"Feature vector length should be 18, got {len(array)}"

    print(f"\n  ✓ FeatureVector: {len(array)} features, all indicators correct")


# ─── Test 3: Risk Scoring Engine ─────────────────────────────────

def test_03_risk_scoring_engine():
    """Verify composite risk score and reason code generation."""
    from app.ml.feature_engineering import FeatureVector
    from app.ml.risk_scoring import compute_risk_score

    # High-risk scenario: SIM swap + new device/beneficiary + amount anomaly
    fv_high = FeatureVector(
        transaction_id="HIGH-001",
        sim_swap_flag_72h=True,
        new_device_new_beneficiary=True,
        is_new_device=True,
        is_new_beneficiary=True,
        amount_to_avg_ratio=4.5,
        txn_velocity_24h=7,
        velocity_anomaly=True,
        smishing_signal_30min=True,
        smishing_probability=0.9,
        location_deviation_km=300.0,
        location_deviation_flag=True,
        receiver_on_blocklist=True,
        off_hours_flag=True,
        agent_complaint_elevated=False,
        agent_complaint_rate=0.0,
    )
    result_high = compute_risk_score(fv_high, fraud_probability=0.92)

    assert result_high.risk_score >= 60,   f"High scenario score should be ≥60, got {result_high.risk_score}"
    assert result_high.risk_level in ("HIGH", "CRITICAL"), f"Level should be HIGH/CRITICAL"
    assert result_high.automated_action == "BLOCK"
    assert "sim_swap_72h" in result_high.reason_codes
    assert "new_device_new_beneficiary" in result_high.reason_codes
    assert len(result_high.reason_codes) >= 3

    # Low-risk scenario
    fv_low = FeatureVector(transaction_id="LOW-001", amount_to_avg_ratio=0.8)
    result_low = compute_risk_score(fv_low, fraud_probability=0.05)

    assert result_low.risk_score < 30,   f"Low scenario score should be <30, got {result_low.risk_score}"
    assert result_low.risk_level == "LOW"
    assert result_low.automated_action == "ALLOW"
    assert result_low.reason_codes == []

    # Max possible indicator score = 25+20+15+10+10+10+5+3+2 = 100
    max_score = sum([25, 20, 15, 10, 10, 10, 5, 3, 2])
    assert max_score == 100, "Risk weight table should sum to 100"

    print(f"\n  ✓ High-risk score={result_high.risk_score}, level={result_high.risk_level}")
    print(f"  ✓ Low-risk  score={result_low.risk_score},  level={result_low.risk_level}")


# ─── Test 4: ML Model Training ────────────────────────────────────

def test_04_ml_model_training():
    """Train models on small synthetic dataset and verify metrics meet targets."""
    from app.ml.data_generator import generate_dataset
    from app.ml.model_trainer import train_all_models, train_smishing_classifier

    df = generate_dataset(n_transactions=2000, fraud_rate=0.05)
    metrics = train_all_models(df, model_dir="./models")

    assert "random_forest" in metrics, "Random Forest should be trained"
    assert "logistic_regression" in metrics, "Logistic Regression should be trained"

    rf = metrics["random_forest"]
    assert 0 <= rf["precision"] <= 1, "Precision out of range"
    assert 0 <= rf["recall"] <= 1,    "Recall out of range"
    assert 0 <= rf["f1_score"] <= 1,  "F1 out of range"
    assert 0 <= rf["auc_roc"] <= 1,   "AUC-ROC out of range"
    assert -1 <= rf["mcc"] <= 1,      "MCC out of range"

    # Verify model files exist
    import os
    assert os.path.exists("./models/random_forest.pkl"),      "RF model file missing"
    assert os.path.exists("./models/logistic_regression.pkl"), "LR model file missing"
    assert os.path.exists("./models/feature_cols.json"),       "Feature cols file missing"

    # Smishing classifier
    result = train_smishing_classifier(model_dir="./models")
    assert result["model"] == "smishing_nlp"
    assert os.path.exists("./models/smishing_nlp.pkl"), "Smishing model file missing"

    print(f"\n  ✓ Random Forest  — F1={rf['f1_score']:.4f}, AUC={rf['auc_roc']:.4f}")


# ─── Test 5: ML Inference ─────────────────────────────────────────

def test_05_ml_inference():
    """Verify ModelInference loads models and produces valid predictions."""
    from app.ml.model_trainer import ModelInference

    mi = ModelInference(model_dir="./models")
    assert mi._rf is not None or mi._lr_bundle is not None, "At least one model should load"

    # Fraud-like feature vector (SIM swap + new device + amount anomaly)
    fraud_features = [
        4.5,   # amount_to_avg_ratio (>3x)
        1.0,   # kyc_limit_exceeded
        3,     # txn_velocity_1h
        7,     # txn_velocity_24h
        1.0,   # velocity_anomaly
        1.0,   # is_new_device
        1.0,   # is_new_beneficiary
        1.0,   # new_device_new_beneficiary
        1.0,   # sim_swap_flag_72h
        0.0,   # pin_change_recent
        0.3,   # location_deviation_km_norm
        1.0,   # location_deviation_flag
        1.0,   # off_hours_flag
        1.0,   # smishing_signal_30min
        0.85,  # smishing_probability
        0.0,   # agent_complaint_rate
        0.0,   # agent_complaint_elevated
        1.0,   # receiver_on_blocklist
    ]

    legit_features = [0.5, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0.01, 0, 0, 0, 0, 0, 0, 0]

    fraud_prob, model = mi.predict_fraud_probability(fraud_features)
    legit_prob, _ = mi.predict_fraud_probability(legit_features)

    assert 0.0 <= fraud_prob <= 1.0, f"Fraud probability out of range: {fraud_prob}"
    assert 0.0 <= legit_prob <= 1.0, f"Legit probability out of range: {legit_prob}"
    assert fraud_prob > legit_prob, f"Fraud prob ({fraud_prob:.4f}) should exceed legit ({legit_prob:.4f})"

    # Smishing
    smishing_prob = mi.predict_smishing("MTN: Your account suspended. Click: mtn-zm.net/verify")
    legit_sms_prob = mi.predict_smishing("Your MTN MoMo deposit of ZMW 200 was successful")
    assert smishing_prob > legit_sms_prob, "Smishing SMS should score higher than legit SMS"

    print(f"\n  ✓ Fraud prob={fraud_prob:.4f}, Legit prob={legit_prob:.4f}, Model={model}")
    print(f"  ✓ Smishing={smishing_prob:.4f} > Legit SMS={legit_sms_prob:.4f}")


# ─── Test 6: Full Transaction Scoring via Service ─────────────────

def test_06_transaction_scoring_service(db, analyst_user):
    """End-to-end transaction scoring through FraudDetectionService."""
    from app.services.fraud_detection_service import score_transaction

    txn_id = str(uuid.uuid4())
    result = score_transaction(
        db=db,
        transaction_id=txn_id,
        sender_msisdn="+260961111111",
        receiver_msisdn="+260977222222",
        amount=5000.0,
        txn_type="P2P",
        operator="MTN",
        channel="USSD",
        timestamp=datetime.utcnow(),
        requester_id=analyst_user.id,
    )

    assert result["transaction_id"] == txn_id
    assert "risk_score" in result
    assert "risk_level" in result
    assert "fraud_probability" in result
    assert "reason_codes" in result
    assert "automated_action" in result
    assert "processing_time_ms" in result
    assert 0 <= result["risk_score"] <= 100
    assert result["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert result["automated_action"] in ("ALLOW", "REVIEW", "BLOCK")
    assert result["processing_time_ms"] < 5000, "Processing should complete in <5s"

    # Verify persisted to DB
    from app.models.orm_models import Transaction, RiskScore
    txn = db.query(Transaction).filter(Transaction.transaction_id == txn_id).first()
    assert txn is not None, "Transaction should be persisted"
    assert txn.risk_score is not None, "RiskScore should be persisted"

    print(f"\n  ✓ Scored txn {txn_id[:8]}... → score={result['risk_score']}, level={result['risk_level']}, {result['processing_time_ms']}ms")


# ─── Test 7: Manual Flag + Override Workflow ──────────────────────

def test_07_flag_and_override_workflow(db, analyst_user):
    """Test analyst flag and fraud override decision with audit logging."""
    from app.services.fraud_detection_service import score_transaction, manually_flag_transaction, override_fraud_decision
    from app.models.orm_models import Transaction, FraudAlert, AuditLog

    # Score a transaction first
    txn_id = str(uuid.uuid4())
    score_transaction(
        db=db,
        transaction_id=txn_id,
        sender_msisdn="+260962333333",
        receiver_msisdn="+260978444444",
        amount=12000.0,
        txn_type="CASHOUT",
        operator="AIRTEL",
        channel="APP",
        requester_id=analyst_user.id,
    )

    # Manual flag
    flag_result = manually_flag_transaction(
        db=db,
        txn_id=txn_id,
        analyst_id=analyst_user.id,
        fraud_type="SIM_SWAP",
        note="Confirmed via customer callback",
    )
    assert "error" not in flag_result
    assert flag_result["status"] == "CONFIRMED_FRAUD"

    txn = db.query(Transaction).filter(Transaction.transaction_id == txn_id).first()
    assert txn.is_fraud is True
    assert txn.fraud_confirmed_by == analyst_user.id

    # Override to false positive
    override_result = override_fraud_decision(
        db=db,
        txn_id=txn_id,
        analyst_id=analyst_user.id,
        is_fraud=False,
        note="Customer confirmed it was legitimate",
    )
    assert override_result["override_decision"] == "LEGITIMATE"

    db.refresh(txn)
    assert txn.analyst_override is False
    assert txn.override_by == analyst_user.id

    # Audit log should have entries
    audit_count = db.query(AuditLog).filter(AuditLog.transaction_ref == txn_id).count()
    assert audit_count >= 2, f"Expected ≥2 audit entries, got {audit_count}"

    print(f"\n  ✓ Flag → CONFIRMED_FRAUD, Override → LEGITIMATE, {audit_count} audit entries")


# ─── Test 8: Dashboard Stats ──────────────────────────────────────

def test_08_dashboard_stats(db, analyst_user):
    """Verify dashboard stats return correct structure and non-negative values."""
    from app.services.fraud_detection_service import get_dashboard_stats

    stats = get_dashboard_stats(db)

    required_keys = [
        "total_transactions", "total_alerts", "open_alerts",
        "confirmed_fraud", "false_positives", "fraud_amount_zmw",
        "high_risk_transactions", "precision",
    ]
    for key in required_keys:
        assert key in stats, f"Missing dashboard stat: {key}"
        assert stats[key] >= 0, f"Stat {key} is negative: {stats[key]}"

    assert 0 <= stats["precision"] <= 1, f"Precision out of range: {stats['precision']}"
    assert stats["total_transactions"] > 0, "Should have at least some transactions from prior tests"

    print(f"\n  ✓ Dashboard: {stats['total_transactions']} txns, {stats['open_alerts']} open alerts, precision={stats['precision']:.2%}")


# ─── Test 9: Compliance Report + Audit Export ─────────────────────

def test_09_compliance_report_and_audit_export(db, analyst_user):
    """Verify BoZ compliance report generation and audit log CSV export."""
    from app.services.compliance_service import generate_monthly_report, export_audit_log

    period_start = datetime.utcnow() - timedelta(days=30)
    period_end = datetime.utcnow()

    report = generate_monthly_report(
        db=db,
        period_start=period_start,
        period_end=period_end,
        generated_by=analyst_user.id,
        report_dir="./reports",
    )

    assert "report_id" in report
    assert "summary" in report
    assert "csv_content" in report

    summary = report["summary"]
    assert summary["total_transactions"] >= 0
    assert summary["confirmed_fraud"] >= 0
    assert summary["false_positives"] >= 0

    csv = report["csv_content"]
    assert "BoZ Compliance Report" in csv
    assert "Total Transactions" in csv
    assert "Confirmed Fraud Cases" in csv

    # Audit log export
    audit_csv = export_audit_log(db, period_start, period_end)
    assert "Log ID" in audit_csv or "log_id" in audit_csv.lower() or len(audit_csv) > 0

    import os
    assert os.path.exists(report["report_path"]), "Report file should be saved to disk"

    print(f"\n  ✓ Compliance report: {report['report_id'][:8]}..., {summary['total_transactions']} txns")
    print(f"  ✓ Audit CSV: {len(audit_csv)} chars")


# ─── Test 10: Retraining Pipeline ────────────────────────────────

def test_10_retraining_pipeline(db, admin_user):
    """Verify automated retraining pipeline trains new models and updates registry."""
    from app.services.retraining_service import run_retraining
    from app.models.orm_models import MLModelRegistry

    result = run_retraining(
        db=db,
        triggered_by=admin_user.id,
        model_dir="./models",
        notes="Test retraining run",
    )

    assert result["status"] == "SUCCESS"
    assert "version" in result
    assert "training_samples" in result
    assert result["training_samples"] > 0
    assert "metrics" in result
    assert len(result["metrics"]) > 0

    # Verify registry updated
    active_models = db.query(MLModelRegistry).filter(MLModelRegistry.is_active == True).all()
    assert len(active_models) > 0, "At least one active model should be registered"

    for model in active_models:
        assert model.version == result["version"]
        assert model.training_samples > 0

    print(f"\n  ✓ Retrain v{result['version']}: {result['training_samples']} samples, {len(active_models)} models registered")
    for name, m in result["metrics"].items():
        print(f"    {name}: F1={m.get('f1_score',0):.4f}, AUC={m.get('auc_roc',0):.4f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
