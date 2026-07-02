"""
SQLAlchemy ORM Models — aligned with the CBU CS301 Group 20 OOAD Class Diagram.
Covers: Transaction, UserProfile, BehavioralProfile, DeviceSession, Agent,
SmishingSignal, RiskScore, FraudAlert, AuditLog, SimSwapEvent, FraudBlocklist,
MLModelRegistry, ComplianceReport.
"""
from datetime import datetime
from enum import Enum as PyEnum
import json

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum, JSON, Index, func
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# ─────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────

class TransactionType(str, PyEnum):
    P2P = "P2P"
    P2B = "P2B"
    CASHOUT = "CASHOUT"
    CASHIN = "CASHIN"
    BILLPAY = "BILLPAY"
    INTL_TRANSFER = "INTL_TRANSFER"


class NetworkOperator(str, PyEnum):
    MTN = "MTN"
    AIRTEL = "AIRTEL"
    ZAMTEL = "ZAMTEL"


class Channel(str, PyEnum):
    USSD = "USSD"
    APP = "APP"
    AGENT = "AGENT"
    API = "API"


class RiskLevel(str, PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, PyEnum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    ESCALATED = "ESCALATED"


class UserRole(str, PyEnum):
    MOBILE_USER = "MOBILE_USER"
    FRAUD_ANALYST = "FRAUD_ANALYST"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    OPERATOR_API = "OPERATOR_API"


class FraudType(str, PyEnum):
    SIM_SWAP = "SIM_SWAP"
    SMISHING = "SMISHING"
    AGENT_FRAUD = "AGENT_FRAUD"
    SOCIAL_ENGINEERING = "SOCIAL_ENGINEERING"
    ACCOUNT_TAKEOVER = "ACCOUNT_TAKEOVER"
    UNKNOWN = "UNKNOWN"


# ─────────────────────────────────────────────
# Core Domain Entities
# ─────────────────────────────────────────────

class UserProfile(Base):
    """Registered user identity. PII is hashed before storage."""
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    hashed_user_id = Column(String(64), unique=True, nullable=False, index=True)
    hashed_msisdn = Column(String(64), unique=True, nullable=False, index=True)
    operator = Column(Enum(NetworkOperator), nullable=False)
    kyc_tier = Column(Integer, default=1)  # 1=Basic, 2=Standard, 3=Enhanced
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Auth fields (for analyst/admin portal users)
    username = Column(String(100), unique=True, nullable=True)
    email = Column(String(200), unique=True, nullable=True)
    hashed_password = Column(String(256), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.MOBILE_USER)
    is_portal_user = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    behavioral_profile = relationship("BehavioralProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="sender_profile", foreign_keys="[Transaction.sender_profile_id]")
    fraud_alerts = relationship("FraudAlert", back_populates="user", foreign_keys="[FraudAlert.user_id]")
    audit_logs = relationship("AuditLog", back_populates="operator", foreign_keys="[AuditLog.operator_id]")

    __table_args__ = (
        Index("ix_user_operator", "operator"),
    )


class BehavioralProfile(Base):
    """Behavioural baseline — separated per SRP. Updated after each transaction."""
    __tablename__ = "behavioral_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_profiles.id"), unique=True, nullable=False)
    account_age_days = Column(Integer, default=0)
    avg_daily_txn_count = Column(Float, default=1.0)
    avg_30day_txn_amount = Column(Float, default=100.0)
    avg_daily_txn_amount = Column(Float, default=100.0)
    typical_active_hours_start = Column(Integer, default=7)   # 07:00
    typical_active_hours_end = Column(Integer, default=21)    # 21:00
    usual_province = Column(String(50), default="Lusaka")
    known_beneficiaries = Column(Text, default="[]")           # JSON list of hashed MSISDNs
    registered_devices = Column(Text, default="[]")            # JSON list of device fingerprints
    sim_swap_flag = Column(Boolean, default=False)
    sim_swap_timestamp = Column(DateTime, nullable=True)
    pin_change_flag = Column(Boolean, default=False)
    pin_change_timestamp = Column(DateTime, nullable=True)
    total_txn_count = Column(Integer, default=0)
    last_transaction_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("UserProfile", back_populates="behavioral_profile")

    def get_known_beneficiaries(self):
        return json.loads(self.known_beneficiaries or "[]")

    def get_registered_devices(self):
        return json.loads(self.registered_devices or "[]")


class Transaction(Base):
    """Central operational entity. Every fraud assessment starts here."""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String(36), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    sender_msisdn_hash = Column(String(64), nullable=False, index=True)
    receiver_msisdn_hash = Column(String(64), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    operator = Column(Enum(NetworkOperator), nullable=False)
    channel = Column(Enum(Channel), nullable=False)
    status = Column(String(20), default="COMPLETED")
    is_fraud = Column(Boolean, default=False, nullable=False)
    fraud_type = Column(Enum(FraudType), nullable=True)
    fraud_confirmed_by = Column(Integer, ForeignKey("user_profiles.id"), nullable=True)
    fraud_confirmed_at = Column(DateTime, nullable=True)
    is_flagged_for_review = Column(Boolean, default=False)
    analyst_override = Column(Boolean, nullable=True)   # None=no override, True=confirmed, False=cleared
    override_by = Column(Integer, ForeignKey("user_profiles.id"), nullable=True)
    override_at = Column(DateTime, nullable=True)
    override_note = Column(Text, nullable=True)
    sender_profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    used_for_training = Column(Boolean, default=False)

    # Relationships
    sender_profile = relationship("UserProfile", back_populates="transactions", foreign_keys=[sender_profile_id])
    risk_score = relationship("RiskScore", back_populates="transaction", uselist=False, cascade="all, delete-orphan")
    fraud_alerts = relationship("FraudAlert", back_populates="transaction")
    device_session = relationship("DeviceSession", back_populates="transaction", uselist=False)
    smishing_signals = relationship("SmishingSignal", back_populates="transaction")

    __table_args__ = (
        Index("ix_txn_timestamp_fraud", "timestamp", "is_fraud"),
        Index("ix_txn_sender", "sender_msisdn_hash"),
    )


class DeviceSession(Base):
    """Device and session context for APP/API channel transactions."""
    __tablename__ = "device_sessions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), unique=True)
    device_fingerprint = Column(String(128))
    device_type = Column(String(50))
    is_new_device = Column(Boolean, default=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    province = Column(String(50), nullable=True)
    location_deviation_km = Column(Float, default=0.0)
    session_duration_seconds = Column(Integer, default=0)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    transaction = relationship("Transaction", back_populates="device_session")


class Agent(Base):
    """Mobile money agent context for AGENT channel transactions."""
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(36), unique=True, nullable=False, index=True)
    operator = Column(Enum(NetworkOperator), nullable=False)
    province = Column(String(50))
    district = Column(String(50))
    agent_tier = Column(Integer, default=1)  # 1=Basic, 2=Premium, 3=Master
    complaint_count = Column(Integer, default=0)
    is_flagged = Column(Boolean, default=False)
    flagged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SmishingSignal(Base):
    """SMS-based fraud indicators linked to transactions."""
    __tablename__ = "smishing_signals"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    sender_short_code = Column(String(20))
    target_msisdn_hash = Column(String(64))
    message_hash = Column(String(64))
    smishing_probability = Column(Float, default=0.0)
    has_url = Column(Boolean, default=False)
    urgency_score = Column(Float, default=0.0)
    operator_impersonation = Column(Boolean, default=False)
    detected_at = Column(DateTime, default=datetime.utcnow)

    transaction = relationship("Transaction", back_populates="smishing_signals")


# ─────────────────────────────────────────────
# Risk Scoring and Alerting Layer
# ─────────────────────────────────────────────

class RiskScore(Base):
    """Final fraud evaluation outcome for each transaction."""
    __tablename__ = "risk_scores"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), unique=True)
    risk_score = Column(Integer, nullable=False)  # 0-100
    risk_level = Column(Enum(RiskLevel), nullable=False)
    fraud_probability = Column(Float, nullable=False)  # 0.0-1.0
    reason_codes = Column(Text, default="[]")  # JSON list
    sub_scores = Column(Text, default="{}")   # JSON breakdown
    ml_model_used = Column(String(50))
    automated_action = Column(String(50))     # ALLOW / REVIEW / BLOCK
    calculated_at = Column(DateTime, default=datetime.utcnow)
    processing_time_ms = Column(Integer, default=0)

    transaction = relationship("Transaction", back_populates="risk_score")
    fraud_alerts = relationship("FraudAlert", back_populates="risk_score")

    def get_reason_codes(self):
        return json.loads(self.reason_codes or "[]")

    def get_sub_scores(self):
        return json.loads(self.sub_scores or "{}")


class FraudAlert(Base):
    """Alert generated for HIGH/CRITICAL risk transactions."""
    __tablename__ = "fraud_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String(36), unique=True, nullable=False, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=True)
    risk_score_id = Column(Integer, ForeignKey("risk_scores.id"), nullable=True)
    alert_type = Column(String(50))  # AUTO_FLAGGED / MANUAL_FLAG / SYSTEM
    status = Column(Enum(AlertStatus), default=AlertStatus.OPEN)
    assigned_analyst_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    fraud_type = Column(Enum(FraudType), nullable=True)

    transaction = relationship("Transaction", back_populates="fraud_alerts")
    user = relationship("UserProfile", back_populates="fraud_alerts", foreign_keys=[user_id])
    risk_score = relationship("RiskScore", back_populates="fraud_alerts")
    assigned_analyst = relationship("UserProfile", foreign_keys=[assigned_analyst_id])
    audit_entries = relationship("AuditLog", back_populates="fraud_alert")

    __table_args__ = (
        Index("ix_alert_status", "status"),
        Index("ix_alert_created", "created_at"),
    )


class AuditLog(Base):
    """Event-level traceability for BoZ regulatory compliance."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(String(36), unique=True, nullable=False)
    event_type = Column(String(50), nullable=False)  # SCORE / FLAG / OVERRIDE / LOGIN / RETRAIN / EXPORT
    operator_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=True)
    fraud_alert_id = Column(Integer, ForeignKey("fraud_alerts.id"), nullable=True)
    transaction_ref = Column(String(36), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    metadata_json = Column(Text, default="{}")
    ip_address = Column(String(45), nullable=True)
    result = Column(String(20))  # SUCCESS / FAILURE

    operator = relationship("UserProfile", back_populates="audit_logs")
    fraud_alert = relationship("FraudAlert", back_populates="audit_entries")

    def get_metadata(self):
        return json.loads(self.metadata_json or "{}")


# ─────────────────────────────────────────────
# Reference and Support Data
# ─────────────────────────────────────────────

class SimSwapEvent(Base):
    """Records SIM swap events from operator feeds."""
    __tablename__ = "sim_swap_events"

    id = Column(Integer, primary_key=True, index=True)
    msisdn_hash = Column(String(64), nullable=False, index=True)
    operator = Column(Enum(NetworkOperator))
    swap_timestamp = Column(DateTime, nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow)
    is_verified = Column(Boolean, default=False)


class FraudBlocklist(Base):
    """Registry of known fraudulent MSISDNs (BoZ / operator reported)."""
    __tablename__ = "fraud_blocklist"

    id = Column(Integer, primary_key=True, index=True)
    msisdn_hash = Column(String(64), unique=True, nullable=False, index=True)
    added_by = Column(Integer, ForeignKey("user_profiles.id"), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    reason = Column(Text)
    source = Column(String(50))  # BOZ / OPERATOR / ANALYST
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)


class MLModelRegistry(Base):
    """Tracks ML model versions, training runs, and performance metrics."""
    __tablename__ = "ml_model_registry"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(50), nullable=False)  # RANDOM_FOREST / XGBOOST / LOGISTIC / SMISHING_NLP
    version = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=False)
    trained_at = Column(DateTime, default=datetime.utcnow)
    training_samples = Column(Integer)
    fraud_samples = Column(Integer)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    auc_roc = Column(Float, nullable=True)
    mcc = Column(Float, nullable=True)
    accuracy = Column(Float, nullable=True)
    model_path = Column(String(256))
    trained_by = Column(Integer, ForeignKey("user_profiles.id"), nullable=True)
    notes = Column(Text)
    hyperparameters = Column(Text, default="{}")

    __table_args__ = (
        Index("ix_model_active", "model_name", "is_active"),
    )


class ComplianceReport(Base):
    """BoZ regulatory compliance report export records."""
    __tablename__ = "compliance_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(String(36), unique=True, nullable=False)
    report_type = Column(String(50))  # MONTHLY_SUMMARY / INCIDENT / AUDIT_EXPORT
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    generated_by = Column(Integer, ForeignKey("user_profiles.id"))
    generated_at = Column(DateTime, default=datetime.utcnow)
    total_transactions = Column(Integer)
    total_flagged = Column(Integer)
    confirmed_fraud = Column(Integer)
    false_positives = Column(Integer)
    total_fraud_amount_zmw = Column(Float)
    report_path = Column(String(256))
    submitted_to_boz = Column(Boolean, default=False)
    submitted_at = Column(DateTime, nullable=True)
