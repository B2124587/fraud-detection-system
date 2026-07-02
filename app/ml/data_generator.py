"""
Zambian Mobile Money Synthetic Dataset Generator
Calibrated to: MTN/Airtel/Zamtel prefix allocations, ZMW ranges,
provincial distributions, BoZ 2023 fraud typologies.
Target: 50,000 transactions at ~3% fraud prevalence.
"""
import hashlib
import json
import random
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

fake = Faker()
rng = np.random.default_rng(42)


# ─────────────────── Zambia reference data ───────────────────

PROVINCES = {
    "Lusaka": 0.32, "Copperbelt": 0.22, "Southern": 0.10,
    "Eastern": 0.09, "Northern": 0.07, "Western": 0.06,
    "Northwestern": 0.05, "Central": 0.05, "Luapula": 0.03, "Muchinga": 0.01,
}

PROVINCE_COORDS = {
    "Lusaka": (-15.42, 28.28), "Copperbelt": (-12.80, 28.25),
    "Southern": (-16.50, 26.90), "Eastern": (-13.50, 32.00),
    "Northern": (-9.50, 30.50), "Western": (-15.00, 23.00),
    "Northwestern": (-12.00, 24.50), "Central": (-14.50, 28.50),
    "Luapula": (-11.00, 29.00), "Muchinga": (-10.50, 32.00),
}

OPERATOR_PREFIXES = {
    "MTN": ["096", "076"],
    "AIRTEL": ["097", "077"],
    "ZAMTEL": ["095"],
}

TXN_TYPES = ["P2P", "P2B", "CASHOUT", "CASHIN", "BILLPAY", "INTL_TRANSFER"]
TXN_TYPE_WEIGHTS = [0.45, 0.20, 0.15, 0.10, 0.07, 0.03]

CHANNELS = ["USSD", "APP", "AGENT", "API"]
CHANNEL_WEIGHTS = [0.55, 0.25, 0.15, 0.05]

# ZMW amount distributions by transaction type
AMOUNT_PARAMS = {
    "P2P":           {"mean": 350,   "std": 600,   "min": 5,    "max": 15000},
    "P2B":           {"mean": 200,   "std": 300,   "min": 10,   "max": 8000},
    "CASHOUT":       {"mean": 500,   "std": 800,   "min": 20,   "max": 20000},
    "CASHIN":        {"mean": 600,   "std": 1000,  "min": 20,   "max": 25000},
    "BILLPAY":       {"mean": 180,   "std": 150,   "min": 10,   "max": 3000},
    "INTL_TRANSFER": {"mean": 2000,  "std": 3000,  "min": 100,  "max": 50000},
}

# Fraud type distribution (Zambian operator data)
FRAUD_TYPE_DIST = {
    "SIM_SWAP": 0.60,
    "SOCIAL_ENGINEERING": 0.20,
    "AGENT_FRAUD": 0.12,
    "UNKNOWN": 0.08,
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _generate_msisdn(operator: str) -> str:
    prefix = random.choice(OPERATOR_PREFIXES[operator])
    number = "".join([str(random.randint(0, 9)) for _ in range(7)])
    return f"+260{prefix}{number}"


def _sample_province() -> str:
    provinces = list(PROVINCES.keys())
    weights = list(PROVINCES.values())
    return random.choices(provinces, weights=weights)[0]


def _sample_amount(txn_type: str) -> float:
    p = AMOUNT_PARAMS[txn_type]
    amount = abs(rng.normal(p["mean"], p["std"]))
    return float(np.clip(amount, p["min"], p["max"]))


def _generate_timestamp(base_date: datetime, active_hours: tuple) -> datetime:
    """Generate a transaction timestamp biased toward active hours."""
    hour = random.choices(
        range(24),
        weights=[
            3 if active_hours[0] <= h <= active_hours[1] else 0.5
            for h in range(24)
        ]
    )[0]
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    day_offset = random.randint(0, 89)  # 90-day window
    return base_date + timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)


def generate_dataset(n_transactions: int = 50000, fraud_rate: float = 0.03) -> pd.DataFrame:
    """Generate synthetic Zambian mobile money transaction dataset."""
    print(f"Generating {n_transactions} transactions ({fraud_rate*100:.1f}% fraud rate)...")

    base_date = datetime(2024, 1, 1)
    n_fraud = int(n_transactions * fraud_rate)
    n_legit = n_transactions - n_fraud

    # Build user pool
    n_users = 5000
    users = []
    for _ in range(n_users):
        op = random.choices(["MTN", "AIRTEL", "ZAMTEL"], weights=[0.50, 0.40, 0.10])[0]
        province = _sample_province()
        users.append({
            "msisdn": _generate_msisdn(op),
            "operator": op,
            "province": province,
            "kyc_tier": random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0],
            "avg_30day_amount": abs(rng.normal(300, 200)) + 50,
            "active_hours": (random.randint(6, 9), random.randint(18, 22)),
            "registered_devices": [str(uuid.uuid4())[:8] for _ in range(random.randint(1, 3))],
            "known_beneficiaries": [str(uuid.uuid4())[:12] for _ in range(random.randint(2, 15))],
        })

    records = []

    # ─── Legitimate transactions ───
    for _ in range(n_legit):
        sender = random.choice(users)
        receiver = random.choice(users)
        while receiver["msisdn"] == sender["msisdn"]:
            receiver = random.choice(users)

        txn_type = random.choices(TXN_TYPES, weights=TXN_TYPE_WEIGHTS)[0]
        channel = random.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0]
        amount = _sample_amount(txn_type)
        ts = _generate_timestamp(base_date, sender["active_hours"])

        # Feature signals — all benign
        device_fp = random.choice(sender["registered_devices"])
        is_new_device = False
        is_new_beneficiary = receiver["msisdn"] not in sender["known_beneficiaries"]
        sim_swap_72h = False
        location_dev_km = abs(rng.normal(10, 15))
        off_hours = not (sender["active_hours"][0] <= ts.hour <= sender["active_hours"][1])
        txn_velocity_24h = random.randint(1, 4)
        amount_ratio = amount / max(sender["avg_30day_amount"], 1)
        smishing_signal = False
        agent_complaint_rate = 0.0

        records.append({
            "transaction_id": str(uuid.uuid4()),
            "timestamp": ts,
            "sender_msisdn": sender["msisdn"],
            "receiver_msisdn": receiver["msisdn"],
            "amount": round(amount, 2),
            "transaction_type": txn_type,
            "operator": sender["operator"],
            "channel": channel,
            "status": "COMPLETED",
            "province": sender["province"],
            "device_fingerprint": _hash(device_fp),
            "kyc_tier": sender["kyc_tier"],
            "is_new_device": is_new_device,
            "is_new_beneficiary": is_new_beneficiary,
            "sim_swap_flag_72h": sim_swap_72h,
            "location_deviation_km": round(location_dev_km, 1),
            "off_hours_flag": off_hours,
            "txn_velocity_24h": txn_velocity_24h,
            "amount_to_avg_ratio": round(amount_ratio, 3),
            "smishing_signal": smishing_signal,
            "agent_complaint_rate": agent_complaint_rate,
            "is_fraud": False,
            "fraud_type": None,
        })

    # ─── Fraudulent transactions ───
    fraud_type_list = random.choices(
        list(FRAUD_TYPE_DIST.keys()),
        weights=list(FRAUD_TYPE_DIST.values()),
        k=n_fraud
    )

    for fraud_type in fraud_type_list:
        sender = random.choice(users)
        receiver = random.choice(users)
        txn_type = random.choices(TXN_TYPES, weights=TXN_TYPE_WEIGHTS)[0]
        channel = random.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0]
        ts = _generate_timestamp(base_date, (0, 23))  # Fraud spans all hours

        # Inject fraud signals based on type
        if fraud_type == "SIM_SWAP":
            amount = _sample_amount(txn_type) * random.uniform(2, 8)
            sim_swap_72h = True
            is_new_device = True
            is_new_beneficiary = True
            location_dev_km = abs(rng.normal(250, 150))
            txn_velocity_24h = random.randint(5, 15)
            off_hours = random.random() > 0.4
            smishing_signal = random.random() > 0.5
            agent_complaint_rate = 0.0

        elif fraud_type == "SOCIAL_ENGINEERING":
            amount = _sample_amount(txn_type) * random.uniform(1.5, 5)
            sim_swap_72h = False
            is_new_device = random.random() > 0.5
            is_new_beneficiary = True
            location_dev_km = abs(rng.normal(50, 80))
            txn_velocity_24h = random.randint(1, 6)
            off_hours = random.random() > 0.3
            smishing_signal = True
            agent_complaint_rate = 0.0

        elif fraud_type == "AGENT_FRAUD":
            channel = "AGENT"
            amount = _sample_amount(txn_type) * random.uniform(1.2, 3)
            sim_swap_72h = False
            is_new_device = False
            is_new_beneficiary = random.random() > 0.4
            location_dev_km = abs(rng.normal(30, 50))
            txn_velocity_24h = random.randint(2, 8)
            off_hours = random.random() > 0.5
            smishing_signal = False
            agent_complaint_rate = round(random.uniform(0.3, 1.0), 2)

        else:  # UNKNOWN
            amount = _sample_amount(txn_type) * random.uniform(1.5, 4)
            sim_swap_72h = random.random() > 0.7
            is_new_device = random.random() > 0.5
            is_new_beneficiary = random.random() > 0.4
            location_dev_km = abs(rng.normal(100, 100))
            txn_velocity_24h = random.randint(3, 10)
            off_hours = random.random() > 0.4
            smishing_signal = random.random() > 0.6
            agent_complaint_rate = 0.0

        amount = float(np.clip(amount, 50, 75000))
        amount_ratio = amount / max(sender["avg_30day_amount"], 1)

        records.append({
            "transaction_id": str(uuid.uuid4()),
            "timestamp": ts,
            "sender_msisdn": sender["msisdn"],
            "receiver_msisdn": receiver["msisdn"],
            "amount": round(amount, 2),
            "transaction_type": txn_type,
            "operator": sender["operator"],
            "channel": channel,
            "status": "COMPLETED",
            "province": sender["province"],
            "device_fingerprint": _hash(str(uuid.uuid4())),
            "kyc_tier": sender["kyc_tier"],
            "is_new_device": is_new_device,
            "is_new_beneficiary": is_new_beneficiary,
            "sim_swap_flag_72h": sim_swap_72h,
            "location_deviation_km": round(location_dev_km, 1),
            "off_hours_flag": off_hours,
            "txn_velocity_24h": txn_velocity_24h,
            "amount_to_avg_ratio": round(amount_ratio, 3),
            "smishing_signal": smishing_signal,
            "agent_complaint_rate": agent_complaint_rate,
            "is_fraud": True,
            "fraud_type": fraud_type,
        })

    df = pd.DataFrame(records)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    print(f"Dataset generated: {len(df)} records, {df['is_fraud'].sum()} fraud ({df['is_fraud'].mean()*100:.2f}%)")
    return df


if __name__ == "__main__":
    df = generate_dataset(50000, 0.03)
    df.to_csv("data/zambia_transactions_50k.csv", index=False)
    print("Dataset saved to data/zambia_transactions_50k.csv")
