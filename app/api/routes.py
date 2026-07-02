"""
FastAPI REST API — CBU CS301 Group 20 Fraud Detection System
Endpoints: /score, /flag/{txn_id}, /user/profile, /health,
           /alerts, /alerts/{id}/override, /dashboard/stats,
           /compliance/report, /audit-log, /models, /retrain,
           /auth/login, /blocklist, /smishing/classify
"""
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from io import StringIO

from app.config import settings
from app.models.database import get_db, create_tables
from app.models.orm_models import (
    UserProfile, BehavioralProfile, Transaction, FraudAlert,
    AuditLog, RiskScore, MLModelRegistry, FraudBlocklist,
    SimSwapEvent, AlertStatus, UserRole, NetworkOperator, FraudType
)
from app.services.auth_service import (
    authenticate_user, create_access_token, get_current_user,
    require_permission, hash_password
)
from app.services.fraud_detection_service import (
    score_transaction, manually_flag_transaction,
    override_fraud_decision, get_dashboard_stats
)
from app.services.compliance_service import generate_monthly_report, export_audit_log

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Zambia Mobile Money Fraud Detection REST API — CBU CS301 Group 20",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Startup ───
@app.on_event("startup")
async def startup_event():
    create_tables()
    _seed_default_users()
    _ensure_model_dir()
    print(f"{settings.APP_NAME} v{settings.VERSION} started.")


def _ensure_model_dir():
    import os
    os.makedirs("./models", exist_ok=True)
    os.makedirs("./reports", exist_ok=True)


def _seed_default_users():
    from app.models.database import SessionLocal
    db = SessionLocal()
    try:
        if not db.query(UserProfile).filter(UserProfile.username == "admin").first():
            admin = UserProfile(
                hashed_user_id="admin_system",
                hashed_msisdn="admin_msisdn",
                operator=NetworkOperator.MTN,
                username="admin",
                email="admin@cbu.ac.zm",
                hashed_password=hash_password("Admin@GPS2024!"),
                role=UserRole.SYSTEM_ADMIN,
                is_portal_user=True,
            )
            db.add(admin)

        if not db.query(UserProfile).filter(UserProfile.username == "analyst1").first():
            analyst = UserProfile(
                hashed_user_id="analyst_001",
                hashed_msisdn="analyst_msisdn_001",
                operator=NetworkOperator.MTN,
                username="analyst1",
                email="analyst1@cbu.ac.zm",
                hashed_password=hash_password("Analyst@2024!"),
                role=UserRole.FRAUD_ANALYST,
                is_portal_user=True,
            )
            db.add(analyst)
            db.add(BehavioralProfile(user=analyst))

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Seed warning: {e}")
    finally:
        db.close()


# ─── Pydantic Schemas ───

class LoginRequest(BaseModel):
    username: str
    password: str


class ScoreRequest(BaseModel):
    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender_msisdn: str
    receiver_msisdn: str
    amount: float = Field(gt=0)
    transaction_type: str = "P2P"
    operator: str = "MTN"
    channel: str = "USSD"
    timestamp: Optional[datetime] = None
    device_fingerprint: Optional[str] = None
    province: Optional[str] = None
    sms_text: Optional[str] = None
    agent_id: Optional[str] = None


class FlagRequest(BaseModel):
    fraud_type: Optional[str] = None
    note: Optional[str] = None


class OverrideRequest(BaseModel):
    is_fraud: bool
    fraud_type: Optional[str] = None
    note: Optional[str] = None


class BlocklistAddRequest(BaseModel):
    msisdn: str
    reason: str
    source: str = "ANALYST"


class SmishingRequest(BaseModel):
    sms_text: str


class ComplianceReportRequest(BaseModel):
    period_start: datetime
    period_end: datetime


class SimSwapRequest(BaseModel):
    msisdn: str
    operator: str = "MTN"
    swap_timestamp: Optional[datetime] = None


# ─── Auth Endpoints ───

@app.post("/auth/login", tags=["Auth"])
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "email": user.email,
        },
    }


@app.get("/auth/me", tags=["Auth"])
def get_me(current_user: UserProfile = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "email": current_user.email,
        "last_login": current_user.last_login,
    }


# ─── Core API Endpoints (per SDD Section 3.7.2) ───

@app.post("/score", tags=["Scoring"], summary="Submit transaction for risk scoring")
def score(
    body: ScoreRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    """SLA: < 2 seconds. Returns risk_score, risk_level, reason_codes, fraud_probability."""
    result = score_transaction(
        db=db,
        transaction_id=body.transaction_id,
        sender_msisdn=body.sender_msisdn,
        receiver_msisdn=body.receiver_msisdn,
        amount=body.amount,
        txn_type=body.transaction_type,
        operator=body.operator,
        channel=body.channel,
        timestamp=body.timestamp,
        device_fingerprint=body.device_fingerprint,
        province=body.province,
        sms_text=body.sms_text,
        agent_id=body.agent_id,
        requester_id=current_user.id,
        ip_address=request.client.host,
    )
    return result


@app.post("/flag/{txn_id}", tags=["Fraud Management"], summary="Manually flag a confirmed fraud transaction")
def flag_transaction(
    txn_id: str,
    body: FlagRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("flag_transaction")),
):
    """SLA: < 1 second. Feeds confirmed label into model retraining pipeline."""
    result = manually_flag_transaction(
        db=db,
        txn_id=txn_id,
        analyst_id=current_user.id,
        fraud_type=body.fraud_type,
        note=body.note,
        ip_address=request.client.host,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/user/profile", tags=["User"], summary="Get user behavioural profile and risk indicators")
def get_user_profile(
    msisdn: str = Query(..., description="Mobile number to look up"),
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    """SLA: < 1 second."""
    import hashlib
    msisdn_hash = hashlib.sha256(msisdn.encode()).hexdigest()[:32]
    profile = db.query(UserProfile).filter(UserProfile.hashed_msisdn == msisdn_hash).first()
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    bp = profile.behavioral_profile

    # Recent transactions count
    recent_txns = db.query(Transaction).filter(
        Transaction.sender_msisdn_hash == msisdn_hash,
        Transaction.timestamp >= datetime.utcnow() - timedelta(days=30),
    ).count()

    return {
        "user_id": profile.id,
        "operator": profile.operator,
        "kyc_tier": profile.kyc_tier,
        "behavioral": {
            "avg_30day_amount": bp.avg_30day_txn_amount if bp else None,
            "avg_daily_txn_count": bp.avg_daily_txn_count if bp else None,
            "usual_province": bp.usual_province if bp else None,
            "sim_swap_flag": bp.sim_swap_flag if bp else False,
            "sim_swap_timestamp": bp.sim_swap_timestamp if bp else None,
            "account_age_days": bp.account_age_days if bp else None,
            "total_txn_count": bp.total_txn_count if bp else 0,
            "last_transaction_at": bp.last_transaction_at if bp else None,
        },
        "recent_30day_txn_count": recent_txns,
    }


@app.get("/health", tags=["System"], summary="System health check")
def health_check(db: Session = Depends(get_db)):
    """SLA: < 200ms."""
    from app.services.fraud_detection_service import get_model_inference
    try:
        mi = get_model_inference()
        model_loaded = mi._rf is not None
    except Exception:
        model_loaded = False

    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if (db_ok and model_loaded) else "degraded",
        "database": "connected" if db_ok else "error",
        "ml_model": "loaded" if model_loaded else "not_loaded",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.VERSION,
    }


# ─── Alert Management ───

@app.get("/alerts", tags=["Alerts"])
def list_alerts(
    status: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("review_alerts")),
):
    query = db.query(FraudAlert).order_by(FraudAlert.created_at.desc())
    if status:
        query = query.filter(FraudAlert.status == status)

    total = query.count()
    alerts = query.offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for a in alerts:
        txn = a.transaction
        rs = txn.risk_score if txn else None
        items.append({
            "alert_id": a.alert_id,
            "status": a.status,
            "alert_type": a.alert_type,
            "created_at": a.created_at.isoformat(),
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            "fraud_type": a.fraud_type,
            "transaction": {
                "transaction_id": txn.transaction_id if txn else None,
                "amount": txn.amount if txn else None,
                "transaction_type": txn.transaction_type if txn else None,
                "channel": txn.channel if txn else None,
                "timestamp": txn.timestamp.isoformat() if txn else None,
            } if txn else None,
            "risk": {
                "risk_score": rs.risk_score if rs else None,
                "risk_level": rs.risk_level if rs else None,
                "fraud_probability": rs.fraud_probability if rs else None,
                "reason_codes": json.loads(rs.reason_codes) if rs else [],
                "automated_action": rs.automated_action if rs else None,
            } if rs else None,
        })

    return {"total": total, "page": page, "per_page": per_page, "items": items}


@app.post("/alerts/{alert_id}/override", tags=["Alerts"])
def override_alert(
    alert_id: str,
    body: OverrideRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("override_fraud")),
):
    alert = db.query(FraudAlert).filter(FraudAlert.alert_id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    txn = alert.transaction
    result = override_fraud_decision(
        db=db,
        txn_id=txn.transaction_id,
        analyst_id=current_user.id,
        is_fraud=body.is_fraud,
        fraud_type=body.fraud_type,
        note=body.note,
        ip_address=request.client.host,
    )
    return result


# ─── Dashboard ───

@app.get("/dashboard/stats", tags=["Dashboard"])
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("view_dashboard")),
):
    return get_dashboard_stats(db)


@app.get("/dashboard/recent-alerts", tags=["Dashboard"])
def recent_alerts(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("view_dashboard")),
):
    alerts = db.query(FraudAlert).order_by(
        FraudAlert.created_at.desc()
    ).limit(limit).all()

    return [
        {
            "alert_id": a.alert_id,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
            "amount": a.transaction.amount if a.transaction else None,
            "risk_score": a.risk_score.risk_score if a.risk_score else None,
            "risk_level": a.risk_score.risk_level if a.risk_score else None,
        }
        for a in alerts
    ]


@app.get("/dashboard/risk-trends", tags=["Dashboard"])
def risk_trends(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("view_analytics")),
):
    """Daily fraud alert counts for the past N days."""
    from sqlalchemy import func, cast, Date
    cutoff = datetime.utcnow() - timedelta(days=days)

    daily = db.query(
        func.date(FraudAlert.created_at).label("date"),
        func.count(FraudAlert.id).label("total"),
        func.sum(
            (FraudAlert.status == AlertStatus.CONFIRMED_FRAUD).cast(__import__("sqlalchemy").Integer)
        ).label("confirmed"),
    ).filter(
        FraudAlert.created_at >= cutoff
    ).group_by(
        func.date(FraudAlert.created_at)
    ).all()

    return [{"date": str(row.date), "total": row.total, "confirmed": row.confirmed or 0}
            for row in daily]


# ─── ML Models ───

@app.get("/models", tags=["Models"])
def list_models(
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user),
):
    models = db.query(MLModelRegistry).order_by(MLModelRegistry.trained_at.desc()).all()
    return [
        {
            "id": m.id,
            "model_name": m.model_name,
            "version": m.version,
            "is_active": m.is_active,
            "trained_at": m.trained_at.isoformat(),
            "training_samples": m.training_samples,
            "metrics": {
                "precision": m.precision,
                "recall": m.recall,
                "f1_score": m.f1_score,
                "auc_roc": m.auc_roc,
                "mcc": m.mcc,
                "accuracy": m.accuracy,
            },
        }
        for m in models
    ]


@app.post("/models/retrain", tags=["Models"])
def trigger_retrain(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("retrain_models")),
):
    from app.services.retraining_service import run_retraining
    result = run_retraining(db, triggered_by=current_user.id)
    return result


@app.get("/models/feature-importance", tags=["Models"])
def feature_importance(current_user: UserProfile = Depends(get_current_user)):
    from app.services.fraud_detection_service import get_model_inference
    mi = get_model_inference()
    return mi.get_feature_importance()


# ─── Compliance ───

@app.post("/compliance/report", tags=["Compliance"])
def create_compliance_report(
    body: ComplianceReportRequest,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("export_compliance")),
):
    result = generate_monthly_report(
        db=db,
        period_start=body.period_start,
        period_end=body.period_end,
        generated_by=current_user.id,
    )
    return result


@app.get("/compliance/audit-log", tags=["Compliance"])
def audit_log_export(
    start: datetime = Query(default_factory=lambda: datetime.utcnow() - timedelta(days=30)),
    end: datetime = Query(default_factory=datetime.utcnow),
    event_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("view_audit_log")),
):
    csv_content = export_audit_log(db, start, end, event_type)
    return StreamingResponse(
        StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit_log_{start.date()}_{end.date()}.csv"},
    )


@app.get("/audit-log", tags=["Compliance"])
def list_audit_log(
    page: int = 1,
    per_page: int = 50,
    event_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("view_audit_log")),
):
    query = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)
    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()
    return {
        "total": total,
        "items": [
            {
                "log_id": l.log_id,
                "event_type": l.event_type,
                "operator_id": l.operator_id,
                "transaction_ref": l.transaction_ref,
                "timestamp": l.timestamp.isoformat(),
                "result": l.result,
            }
            for l in logs
        ],
    }


# ─── Blocklist ───

@app.get("/blocklist", tags=["Reference Data"])
def list_blocklist(
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("manage_blocklist")),
):
    entries = db.query(FraudBlocklist).filter(FraudBlocklist.is_active == True).all()
    return [
        {"id": e.id, "source": e.source, "reason": e.reason, "added_at": e.added_at.isoformat()}
        for e in entries
    ]


@app.post("/blocklist", tags=["Reference Data"])
def add_to_blocklist(
    body: BlocklistAddRequest,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("manage_blocklist")),
):
    import hashlib
    msisdn_hash = hashlib.sha256(body.msisdn.encode()).hexdigest()[:32]
    existing = db.query(FraudBlocklist).filter(FraudBlocklist.msisdn_hash == msisdn_hash).first()
    if existing:
        raise HTTPException(status_code=409, detail="MSISDN already on blocklist")
    entry = FraudBlocklist(
        msisdn_hash=msisdn_hash,
        added_by=current_user.id,
        reason=body.reason,
        source=body.source,
    )
    db.add(entry)
    db.commit()
    return {"status": "added", "id": entry.id}


# ─── Smishing ───

@app.post("/smishing/classify", tags=["Smishing"])
def classify_sms(
    body: SmishingRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    from app.services.fraud_detection_service import get_model_inference
    mi = get_model_inference()
    prob = mi.predict_smishing(body.sms_text)
    return {
        "sms_text": body.sms_text[:100],
        "smishing_probability": round(prob, 4),
        "classification": "SMISHING" if prob > 0.5 else "LEGITIMATE",
        "confidence": "HIGH" if prob > 0.8 or prob < 0.2 else "MEDIUM",
    }


# ─── SIM Swap ───

@app.post("/sim-swap", tags=["Reference Data"])
def record_sim_swap(
    body: SimSwapRequest,
    db: Session = Depends(get_db),
    current_user: UserProfile = Depends(require_permission("manage_reference_data")),
):
    import hashlib
    msisdn_hash = hashlib.sha256(body.msisdn.encode()).hexdigest()[:32]
    event = SimSwapEvent(
        msisdn_hash=msisdn_hash,
        operator=body.operator,
        swap_timestamp=body.swap_timestamp or datetime.utcnow(),
    )
    db.add(event)

    # Update behavioral profile
    profile = db.query(UserProfile).filter(UserProfile.hashed_msisdn == msisdn_hash).first()
    if profile and profile.behavioral_profile:
        profile.behavioral_profile.sim_swap_flag = True
        profile.behavioral_profile.sim_swap_timestamp = body.swap_timestamp or datetime.utcnow()

    db.commit()
    return {"status": "recorded", "msisdn_hash": msisdn_hash}
