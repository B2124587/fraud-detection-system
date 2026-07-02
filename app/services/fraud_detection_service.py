"""
FraudDetectionService — orchestrates transaction scoring, alert generation,
override workflow, and audit logging per OOAD Class Diagram.
"""
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.ml.feature_engineering import FeatureEngineeringService
from app.ml.risk_scoring import compute_risk_score
from app.ml.model_trainer import ModelInference
from app.models.orm_models import (
    Transaction, UserProfile, BehavioralProfile, DeviceSession,
    SmishingSignal, RiskScore, FraudAlert, AuditLog, FraudBlocklist,
    SimSwapEvent, RiskLevel, AlertStatus, FraudType
)

_model_inference: Optional[ModelInference] = None
_feature_service: Optional[FeatureEngineeringService] = None


def get_model_inference(model_dir: str = "./models") -> ModelInference:
    global _model_inference
    if _model_inference is None:
        _model_inference = ModelInference(model_dir=model_dir)
    return _model_inference


def get_feature_service(db: Session) -> FeatureEngineeringService:
    global _feature_service
    if _feature_service is None:
        # Load active blocklist into memory
        blocklist = db.query(FraudBlocklist).filter(
            FraudBlocklist.is_active == True
        ).all()
        blocklist_hashes = {b.msisdn_hash for b in blocklist}
        _feature_service = FeatureEngineeringService(blocklist_hashes=blocklist_hashes)
    return _feature_service


def _hash_value(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()[:32]


def _log_audit(
    db: Session,
    event_type: str,
    operator_id: Optional[int],
    transaction_ref: Optional[str] = None,
    fraud_alert_id: Optional[int] = None,
    metadata: dict = None,
    ip_address: str = None,
    result: str = "SUCCESS",
):
    db.add(AuditLog(
        log_id=str(uuid.uuid4()),
        event_type=event_type,
        operator_id=operator_id,
        fraud_alert_id=fraud_alert_id,
        transaction_ref=transaction_ref,
        metadata_json=json.dumps(metadata or {}),
        ip_address=ip_address,
        result=result,
    ))


def score_transaction(
    db: Session,
    transaction_id: str,
    sender_msisdn: str,
    receiver_msisdn: str,
    amount: float,
    txn_type: str,
    operator: str,
    channel: str,
    timestamp: Optional[datetime] = None,
    device_fingerprint: Optional[str] = None,
    province: Optional[str] = None,
    sms_text: Optional[str] = None,
    agent_id: Optional[str] = None,
    requester_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> dict:
    """
    Main scoring entry point. Returns risk_score, risk_level, reason_codes, fraud_probability.
    SLA target: < 2 seconds.
    """
    start_time = datetime.utcnow()
    if timestamp is None:
        timestamp = start_time

    sender_hash = _hash_value(sender_msisdn)
    receiver_hash = _hash_value(receiver_msisdn)

    # ─── Load sender profile ───
    profile = db.query(UserProfile).filter(
        UserProfile.hashed_msisdn == sender_hash
    ).first()

    bp = None
    if profile:
        bp = db.query(BehavioralProfile).filter(
            BehavioralProfile.user_id == profile.id
        ).first()

    # ─── Compute velocity (recent transactions in 1h / 24h) ───
    cutoff_1h = timestamp - timedelta(hours=1)
    cutoff_24h = timestamp - timedelta(hours=24)
    recent_1h = db.query(Transaction).filter(
        Transaction.sender_msisdn_hash == sender_hash,
        Transaction.timestamp >= cutoff_1h,
    ).count()
    recent_24h = db.query(Transaction).filter(
        Transaction.sender_msisdn_hash == sender_hash,
        Transaction.timestamp >= cutoff_24h,
    ).count()

    # ─── SIM swap check ───
    sim_swap_cutoff = timestamp - timedelta(hours=72)
    sim_swap = db.query(SimSwapEvent).filter(
        SimSwapEvent.msisdn_hash == sender_hash,
        SimSwapEvent.swap_timestamp >= sim_swap_cutoff,
    ).first()
    sim_swap_flag = sim_swap is not None or (bp and bp.sim_swap_flag)

    # ─── Smishing check ───
    smishing_prob = 0.0
    smishing_30min = False
    if sms_text:
        mi = get_model_inference()
        smishing_prob = mi.predict_smishing(sms_text)
        smishing_30min = smishing_prob > 0.5

    # ─── Agent complaint rate ───
    agent_complaint_rate = 0.0
    if agent_id:
        from app.models.orm_models import Agent
        agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
        if agent:
            agent_complaint_rate = min(agent.complaint_count / 100.0, 1.0)

    # ─── Feature engineering ───
    fe_service = get_feature_service(db)
    fv = fe_service.compute(
        transaction_id=transaction_id,
        amount=amount,
        timestamp=timestamp,
        sender_msisdn_hash=sender_hash,
        receiver_msisdn_hash=receiver_hash,
        channel=channel,
        kyc_tier=profile.kyc_tier if profile else 1,
        avg_30day_amount=bp.avg_30day_txn_amount if bp else 300.0,
        active_hours_start=bp.typical_active_hours_start if bp else 7,
        active_hours_end=bp.typical_active_hours_end if bp else 21,
        registered_devices=bp.get_registered_devices() if bp else [],
        known_beneficiaries=bp.get_known_beneficiaries() if bp else [],
        current_device_fp=_hash_value(device_fingerprint) if device_fingerprint else None,
        sim_swap_flag_72h=sim_swap_flag,
        pin_change_recent=bp.pin_change_flag if bp else False,
        location_deviation_km=0.0,
        usual_province=bp.usual_province if bp else "Lusaka",
        current_province=province or "Lusaka",
        recent_txn_timestamps_1h=[None] * recent_1h,
        recent_txn_timestamps_24h=[None] * recent_24h,
        smishing_signal_30min=smishing_30min,
        smishing_probability=smishing_prob,
        agent_complaint_rate=agent_complaint_rate,
    )

    # ─── ML inference ───
    mi = get_model_inference()
    fraud_prob, model_used = mi.predict_fraud_probability(fv.to_ml_array())

    # ─── Risk scoring ───
    result = compute_risk_score(fv, fraud_prob)

    processing_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

    # ─── Persist transaction ───
    txn = Transaction(
        transaction_id=transaction_id,
        timestamp=timestamp,
        sender_msisdn_hash=sender_hash,
        receiver_msisdn_hash=receiver_hash,
        amount=amount,
        transaction_type=txn_type,
        operator=operator,
        channel=channel,
        status="COMPLETED",
        sender_profile_id=profile.id if profile else None,
        is_flagged_for_review=result.automated_action in ("REVIEW", "BLOCK"),
    )
    db.add(txn)
    db.flush()

    # ─── Persist risk score ───
    rs = RiskScore(
        transaction_id=txn.id,
        risk_score=result.risk_score,
        risk_level=result.risk_level,
        fraud_probability=result.fraud_probability,
        reason_codes=json.dumps(result.reason_codes),
        sub_scores=json.dumps(result.sub_scores),
        ml_model_used=model_used,
        automated_action=result.automated_action,
        processing_time_ms=processing_ms,
    )
    db.add(rs)
    db.flush()

    # ─── Generate fraud alert if HIGH/CRITICAL ───
    alert_id = None
    if result.risk_level in ("HIGH", "CRITICAL"):
        alert = FraudAlert(
            alert_id=str(uuid.uuid4()),
            transaction_id=txn.id,
            user_id=profile.id if profile else None,
            risk_score_id=rs.id,
            alert_type="AUTO_FLAGGED",
            status=AlertStatus.OPEN,
        )
        db.add(alert)
        db.flush()
        alert_id = alert.alert_id

    # ─── Update behavioral profile ───
    if bp:
        bp.total_txn_count += 1
        bp.last_transaction_at = timestamp
        # Rolling average
        n = min(bp.total_txn_count, 30)
        bp.avg_30day_txn_amount = (bp.avg_30day_txn_amount * (n - 1) + amount) / n
        if device_fingerprint:
            devices = bp.get_registered_devices()
            dev_hash = _hash_value(device_fingerprint)
            if dev_hash not in devices:
                devices.append(dev_hash)
                bp.registered_devices = json.dumps(devices[-10:])  # keep last 10
        if receiver_hash not in bp.get_known_beneficiaries():
            bens = bp.get_known_beneficiaries()
            bens.append(receiver_hash)
            bp.known_beneficiaries = json.dumps(bens[-50:])  # keep last 50

    # ─── Audit log ───
    _log_audit(
        db, "SCORE", requester_id, transaction_id,
        metadata={
            "risk_score": result.risk_score,
            "risk_level": result.risk_level,
            "action": result.automated_action,
            "model": model_used,
            "processing_ms": processing_ms,
        },
        ip_address=ip_address,
    )

    db.commit()

    return {
        "transaction_id": transaction_id,
        "risk_score": result.risk_score,
        "risk_level": result.risk_level,
        "fraud_probability": result.fraud_probability,
        "reason_codes": result.reason_codes,
        "reason_messages": result.reason_messages,
        "sub_scores": result.sub_scores,
        "automated_action": result.automated_action,
        "model_used": model_used,
        "processing_time_ms": processing_ms,
        "alert_id": alert_id,
    }


def manually_flag_transaction(
    db: Session,
    txn_id: str,
    analyst_id: int,
    fraud_type: Optional[str] = None,
    note: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> dict:
    """Manually flag a confirmed fraud transaction for model retraining pipeline."""
    txn = db.query(Transaction).filter(Transaction.transaction_id == txn_id).first()
    if not txn:
        return {"error": "Transaction not found"}

    txn.is_fraud = True
    txn.fraud_confirmed_by = analyst_id
    txn.fraud_confirmed_at = datetime.utcnow()
    if fraud_type:
        txn.fraud_type = fraud_type
    txn.is_flagged_for_review = True

    # Create or update alert
    alert = db.query(FraudAlert).filter(FraudAlert.transaction_id == txn.id).first()
    if alert:
        alert.status = AlertStatus.CONFIRMED_FRAUD
        alert.resolved_at = datetime.utcnow()
        alert.resolution_notes = note
        alert.fraud_type = fraud_type
    else:
        alert = FraudAlert(
            alert_id=str(uuid.uuid4()),
            transaction_id=txn.id,
            alert_type="MANUAL_FLAG",
            status=AlertStatus.CONFIRMED_FRAUD,
            assigned_analyst_id=analyst_id,
            resolved_at=datetime.utcnow(),
            resolution_notes=note,
            fraud_type=fraud_type,
        )
        db.add(alert)

    _log_audit(
        db, "FLAG", analyst_id, txn_id,
        metadata={"fraud_type": fraud_type, "note": note},
        ip_address=ip_address,
    )

    db.commit()
    return {"transaction_id": txn_id, "status": "CONFIRMED_FRAUD", "alert_id": alert.alert_id if alert else None}


def override_fraud_decision(
    db: Session,
    txn_id: str,
    analyst_id: int,
    is_fraud: bool,
    fraud_type: Optional[str] = None,
    note: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> dict:
    """Override ML fraud decision — records in audit log per BoZ requirement."""
    txn = db.query(Transaction).filter(Transaction.transaction_id == txn_id).first()
    if not txn:
        return {"error": "Transaction not found"}

    txn.analyst_override = is_fraud
    txn.override_by = analyst_id
    txn.override_at = datetime.utcnow()
    txn.override_note = note
    txn.is_fraud = is_fraud
    if is_fraud and fraud_type:
        txn.fraud_type = fraud_type

    alert = db.query(FraudAlert).filter(FraudAlert.transaction_id == txn.id).first()
    if alert:
        alert.status = AlertStatus.CONFIRMED_FRAUD if is_fraud else AlertStatus.FALSE_POSITIVE
        alert.resolved_at = datetime.utcnow()
        alert.resolution_notes = note
        alert.assigned_analyst_id = analyst_id

    _log_audit(
        db, "OVERRIDE", analyst_id, txn_id,
        metadata={"decision": is_fraud, "fraud_type": fraud_type, "note": note},
        ip_address=ip_address,
    )

    db.commit()
    return {
        "transaction_id": txn_id,
        "override_decision": "FRAUD" if is_fraud else "LEGITIMATE",
        "overridden_by": analyst_id,
    }


def get_dashboard_stats(db: Session) -> dict:
    """Aggregate stats for the Fraud Analyst Dashboard."""
    from sqlalchemy import func

    total_txns = db.query(func.count(Transaction.id)).scalar()
    total_alerts = db.query(func.count(FraudAlert.id)).scalar()
    open_alerts = db.query(func.count(FraudAlert.id)).filter(
        FraudAlert.status == AlertStatus.OPEN
    ).scalar()
    confirmed_fraud = db.query(func.count(FraudAlert.id)).filter(
        FraudAlert.status == AlertStatus.CONFIRMED_FRAUD
    ).scalar()
    false_positives = db.query(func.count(FraudAlert.id)).filter(
        FraudAlert.status == AlertStatus.FALSE_POSITIVE
    ).scalar()

    fraud_amount = db.query(func.sum(Transaction.amount)).filter(
        Transaction.is_fraud == True
    ).scalar() or 0.0

    # Today's alerts
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    alerts_today = db.query(func.count(FraudAlert.id)).filter(
        FraudAlert.created_at >= today
    ).scalar()

    # Risk level distribution
    high_risk = db.query(func.count(RiskScore.id)).filter(
        RiskScore.risk_level.in_(["HIGH", "CRITICAL"])
    ).scalar()
    medium_risk = db.query(func.count(RiskScore.id)).filter(
        RiskScore.risk_level == "MEDIUM"
    ).scalar()

    return {
        "total_transactions": total_txns,
        "total_alerts": total_alerts,
        "open_alerts": open_alerts,
        "confirmed_fraud": confirmed_fraud,
        "false_positives": false_positives,
        "fraud_amount_zmw": round(fraud_amount, 2),
        "alerts_today": alerts_today,
        "high_risk_transactions": high_risk,
        "medium_risk_transactions": medium_risk,
        "precision": round(confirmed_fraud / max(confirmed_fraud + false_positives, 1), 4),
    }
