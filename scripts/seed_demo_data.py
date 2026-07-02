#!/usr/bin/env python3
"""
Seed script — populates the database with demo transactions,
alerts, and user profiles for dashboard demonstration.
Run after initial model training and DB migration.
"""
import sys, os, uuid, hashlib, json, random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import SessionLocal, create_tables
from app.models.orm_models import (
    UserProfile, BehavioralProfile, Transaction, RiskScore,
    FraudAlert, AuditLog, Agent, SimSwapEvent,
    NetworkOperator, UserRole, AlertStatus, FraudType
)
from app.services.auth_service import hash_password

def _h(v): return hashlib.sha256(v.encode()).hexdigest()[:32]

def seed():
    create_tables()
    db = SessionLocal()

    print("Seeding demo data...")

    # ─── Portal users ───
    users_data = [
        ("admin",    "Admin@GPS2024!",   UserRole.SYSTEM_ADMIN,  "admin@cbu.ac.zm"),
        ("analyst1", "Analyst@2024!",    UserRole.FRAUD_ANALYST, "analyst1@cbu.ac.zm"),
        ("analyst2", "Analyst@2024!",    UserRole.FRAUD_ANALYST, "analyst2@cbu.ac.zm"),
    ]
    portal_users = {}
    for username, pwd, role, email in users_data:
        existing = db.query(UserProfile).filter(UserProfile.username == username).first()
        if not existing:
            u = UserProfile(
                hashed_user_id=_h(username),
                hashed_msisdn=_h(f"msisdn_{username}"),
                operator=NetworkOperator.MTN,
                username=username, email=email,
                hashed_password=hash_password(pwd),
                role=role, is_portal_user=True,
            )
            db.add(u)
            db.flush()
            db.add(BehavioralProfile(user_id=u.id))
            portal_users[username] = u
        else:
            portal_users[username] = existing
    db.commit()
    print(f"  ✓ {len(users_data)} portal users")

    # ─── Mobile money user profiles ───
    msisdns = [f"+2609{random.randint(60000000,79999999)}" for _ in range(30)]
    mobile_users = []
    for msisdn in msisdns:
        existing = db.query(UserProfile).filter(
            UserProfile.hashed_msisdn == _h(msisdn)
        ).first()
        if not existing:
            op = random.choice(list(NetworkOperator))
            u = UserProfile(
                hashed_user_id=_h(f"user_{msisdn}"),
                hashed_msisdn=_h(msisdn),
                operator=op,
                kyc_tier=random.choice([1, 1, 2, 3]),
                role=UserRole.MOBILE_USER,
            )
            db.add(u)
            db.flush()
            bp = BehavioralProfile(
                user_id=u.id,
                account_age_days=random.randint(30, 730),
                avg_30day_txn_amount=round(random.uniform(100, 2000), 2),
                avg_daily_txn_count=round(random.uniform(1, 5), 1),
                usual_province=random.choice(["Lusaka","Copperbelt","Southern","Eastern"]),
                total_txn_count=random.randint(10, 500),
                known_beneficiaries=json.dumps([_h(f"ben_{i}_{msisdn}") for i in range(5)]),
                registered_devices=json.dumps([_h(f"dev_{i}_{msisdn}") for i in range(2)]),
            )
            db.add(bp)
            mobile_users.append((u, bp, msisdn))
        else:
            mobile_users.append((existing, existing.behavioral_profile, msisdn))
    db.commit()
    print(f"  ✓ {len(mobile_users)} mobile user profiles")

    # ─── Agents ───
    provinces = ["Lusaka","Copperbelt","Southern","Eastern"]
    for i in range(10):
        existing = db.query(Agent).filter(Agent.agent_id == f"AGT{i:04d}").first()
        if not existing:
            db.add(Agent(
                agent_id=f"AGT{i:04d}",
                operator=random.choice(list(NetworkOperator)),
                province=random.choice(provinces),
                district="Central",
                agent_tier=random.choice([1, 2]),
                complaint_count=random.randint(0, 15),
                is_flagged=random.random() > 0.85,
            ))
    db.commit()
    print("  ✓ 10 agents")

    # ─── Transactions + risk scores + alerts ───
    analyst = portal_users.get("analyst1")
    txn_count = 0
    alert_count = 0
    base_time = datetime.utcnow() - timedelta(days=30)

    scenarios = [
        # (is_fraud, risk_score, risk_level, action, reason_codes, fraud_type, alert_status)
        (True,  85, "CRITICAL", "BLOCK",  ["sim_swap_72h","new_device_new_beneficiary","amount_anomaly"], "SIM_SWAP",          AlertStatus.OPEN),
        (True,  78, "HIGH",     "BLOCK",  ["smishing_signal","amount_anomaly","velocity_anomaly"],          "SMISHING",          AlertStatus.UNDER_REVIEW),
        (True,  72, "HIGH",     "BLOCK",  ["agent_complaint","new_device_new_beneficiary"],                 "AGENT_FRAUD",       AlertStatus.CONFIRMED_FRAUD),
        (True,  65, "HIGH",     "BLOCK",  ["sim_swap_72h","location_deviation"],                            "SIM_SWAP",          AlertStatus.OPEN),
        (False, 45, "MEDIUM",   "REVIEW", ["amount_anomaly","off_hours"],                                   None,                AlertStatus.FALSE_POSITIVE),
        (True,  80, "CRITICAL", "BLOCK",  ["sim_swap_72h","smishing_signal","new_device_new_beneficiary"],  "ACCOUNT_TAKEOVER",  AlertStatus.OPEN),
        (False, 38, "MEDIUM",   "REVIEW", ["velocity_anomaly","off_hours"],                                 None,                AlertStatus.CONFIRMED_FRAUD),
        (True,  91, "CRITICAL", "BLOCK",  ["sim_swap_72h","amount_anomaly","receiver_blocklist"],           "SIM_SWAP",          AlertStatus.OPEN),
        (False, 22, "LOW",      "ALLOW",  [],                                                               None,                None),
        (False, 15, "LOW",      "ALLOW",  [],                                                               None,                None),
    ]

    for day_offset in range(30):
        ts_base = base_time + timedelta(days=day_offset)
        n_txns = random.randint(3, 8)
        for _ in range(n_txns):
            if not mobile_users:
                break
            sender_u, sender_bp, sender_msisdn = random.choice(mobile_users)
            receiver_u, _, receiver_msisdn = random.choice(mobile_users)
            if sender_msisdn == receiver_msisdn:
                continue

            scenario = random.choice(scenarios)
            is_fraud, risk_sc, risk_lv, action, reason_codes, fraud_type, alert_st = scenario
            amount = round(random.uniform(50, 8000), 2)
            ts = ts_base + timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))

            txn = Transaction(
                transaction_id=str(uuid.uuid4()),
                timestamp=ts,
                sender_msisdn_hash=_h(sender_msisdn),
                receiver_msisdn_hash=_h(receiver_msisdn),
                amount=amount,
                transaction_type=random.choice(["P2P","CASHOUT","CASHIN","P2B"]),
                operator=sender_u.operator,
                channel=random.choice(["USSD","APP","AGENT"]),
                status="COMPLETED",
                is_fraud=is_fraud,
                fraud_type=fraud_type,
                sender_profile_id=sender_u.id,
                is_flagged_for_review=risk_sc >= 30,
            )
            db.add(txn)
            db.flush()

            sub_scores = {rc: random.randint(5, 25) for rc in reason_codes}
            rs = RiskScore(
                transaction_id=txn.id,
                risk_score=risk_sc,
                risk_level=risk_lv,
                fraud_probability=round(risk_sc / 100 * random.uniform(0.85, 1.0), 4),
                reason_codes=json.dumps(reason_codes),
                sub_scores=json.dumps(sub_scores),
                ml_model_used="random_forest",
                automated_action=action,
                processing_time_ms=random.randint(45, 380),
            )
            db.add(rs)
            db.flush()
            txn_count += 1

            # Create alert for high-risk
            if alert_st and risk_sc >= 30:
                alert = FraudAlert(
                    alert_id=str(uuid.uuid4()),
                    transaction_id=txn.id,
                    user_id=sender_u.id,
                    risk_score_id=rs.id,
                    alert_type="AUTO_FLAGGED" if risk_sc >= 60 else "REVIEW",
                    status=alert_st,
                    assigned_analyst_id=analyst.id if analyst!= AlertStatus.OPEN else None,
                    created_at=ts,
                    fraud_type=fraud_type,
                    resolved_at=ts + timedelta(hours=random.randint(1,8)) if alert_st in (AlertStatus.CONFIRMED_FRAUD, AlertStatus.FALSE_POSITIVE) else None,
                    resolution_notes="Confirmed via analyst review" if alert_st == AlertStatus.CONFIRMED_FRAUD else (
                        "Legitimate transaction — false positive" if alert_st == AlertStatus.FALSE_POSITIVE else None
                    ),
                )
                db.add(alert)
                db.flush()
                alert_count += 1

                # Audit log entry
                db.add(AuditLog(
                    log_id=str(uuid.uuid4()),
                    event_type="SCORE",
                    operator_id=None,
                    transaction_ref=txn.transaction_id,
                    timestamp=ts,
                    metadata_json=json.dumps({"risk_score": risk_sc, "action": action}),
                    result="SUCCESS",
                ))

        db.commit()

    print(f"  ✓ {txn_count} transactions with risk scores")
    print(f"  ✓ {alert_count} fraud alerts")
    print("\nSeed complete. Login credentials:")
    print("  Admin:    admin    / Admin@GPS2024!")
    print("  Analyst:  analyst1 / Analyst@2024!")

if __name__ == "__main__":
    # fix reference to analyst_st (alias)
    # patch the scenario loop variable name collision
    seed()
