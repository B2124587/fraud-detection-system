"""
Feature Engineering Engine — CBU CS301 Group 20
Computes all 15 fraud-relevant features from raw transaction data.
Per System Design Document Section 3.4.2 and Section 5.
"""
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List

import numpy as np


@dataclass
class FeatureVector:
    """Encapsulates all engineered fraud indicators for a transaction."""
    transaction_id: str

    # Core amount features
    amount_to_avg_ratio: float = 0.0          # amount / 30-day avg — weight triggers at >3x
    kyc_limit_exceeded: bool = False           # amount > BoZ KYC tier limit

    # Velocity features
    txn_velocity_1h: int = 0                  # count of sender txns in last 1h
    txn_velocity_24h: int = 0                 # count of sender txns in last 24h
    velocity_anomaly: bool = False            # >5 txns in 24h

    # Identity / device signals
    is_new_device: bool = False               # device not in registered set
    is_new_beneficiary: bool = False          # receiver not in known set
    new_device_new_beneficiary: bool = False  # combined high-risk signal (weight 20)

    # SIM and account signals
    sim_swap_flag_72h: bool = False           # SIM swap in past 72h (weight 25)
    pin_change_recent: bool = False

    # Location
    location_deviation_km: float = 0.0
    location_deviation_flag: bool = False     # >200km (weight 10)

    # Time
    off_hours_flag: bool = False              # outside user's typical hours (weight 3)

    # SMS fraud signals
    smishing_signal_30min: bool = False       # smishing within 30min (weight 10)
    smishing_probability: float = 0.0

    # Agent channel
    agent_complaint_rate: float = 0.0
    agent_complaint_elevated: bool = False   # elevated rate (weight 2)

    # Blocklist
    receiver_on_blocklist: bool = False       # weight 5

    def to_ml_array(self) -> List[float]:
        """Return feature values as ordered list for ML model input."""
        return [
            self.amount_to_avg_ratio,
            float(self.kyc_limit_exceeded),
            float(self.txn_velocity_1h),
            float(self.txn_velocity_24h),
            float(self.velocity_anomaly),
            float(self.is_new_device),
            float(self.is_new_beneficiary),
            float(self.new_device_new_beneficiary),
            float(self.sim_swap_flag_72h or False),
            float(self.pin_change_recent or False),
            (self.location_deviation_km or 0.0) / 1000.0,  # normalised
            float(self.location_deviation_flag or False),
            float(self.off_hours_flag or False),
            float(self.smishing_signal_30min or False),
            float(self.smishing_probability or 0.0),
            float(self.agent_complaint_rate or 0.0),
            float(self.agent_complaint_elevated or False),
            float(self.receiver_on_blocklist or False),
        ]

    FEATURE_NAMES = [
        "amount_to_avg_ratio", "kyc_limit_exceeded",
        "txn_velocity_1h", "txn_velocity_24h", "velocity_anomaly",
        "is_new_device", "is_new_beneficiary", "new_device_new_beneficiary",
        "sim_swap_flag_72h", "pin_change_recent",
        "location_deviation_km_norm", "location_deviation_flag",
        "off_hours_flag", "smishing_signal_30min", "smishing_probability",
        "agent_complaint_rate", "agent_complaint_elevated",
        "receiver_on_blocklist",
    ]


# BoZ KYC tier single-transaction limits (ZMW)
KYC_LIMITS = {1: 500, 2: 5000, 3: 50000}


class FeatureEngineeringService:
    """
    Transforms raw transaction + context data into a FeatureVector.
    Used at inference time by the RiskScoringEngine.
    """

    def __init__(self, blocklist_hashes: Optional[set] = None):
        self.blocklist_hashes = blocklist_hashes or set()

    def compute(
        self,
        transaction_id: str,
        amount: float,
        timestamp: datetime,
        sender_msisdn_hash: str,
        receiver_msisdn_hash: str,
        channel: str,
        kyc_tier: int,
        avg_30day_amount: float,
        active_hours_start: int,
        active_hours_end: int,
        registered_devices: List[str],
        known_beneficiaries: List[str],
        current_device_fp: Optional[str],
        sim_swap_flag_72h: bool,
        pin_change_recent: bool,
        location_deviation_km: float,
        usual_province: str,
        current_province: str,
        recent_txn_timestamps_1h: List[datetime],
        recent_txn_timestamps_24h: List[datetime],
        smishing_signal_30min: bool = False,
        smishing_probability: float = 0.0,
        agent_complaint_rate: float = 0.0,
    ) -> FeatureVector:

        fv = FeatureVector(transaction_id=transaction_id)

        # 1. Amount-to-average ratio
        fv.amount_to_avg_ratio = amount / max(avg_30day_amount, 1.0)

        # 2. KYC limit exceeded
        kyc_limit = KYC_LIMITS.get(kyc_tier, 500)
        fv.kyc_limit_exceeded = amount > kyc_limit

        # 3. Transaction velocity
        fv.txn_velocity_1h = len(recent_txn_timestamps_1h)
        fv.txn_velocity_24h = len(recent_txn_timestamps_24h)
        fv.velocity_anomaly = fv.txn_velocity_24h > 5

        # 4. Device signals
        fv.is_new_device = (
            current_device_fp is not None
            and current_device_fp not in registered_devices
            and len(registered_devices) > 0
        )

        # 5. New beneficiary
        fv.is_new_beneficiary = receiver_msisdn_hash not in known_beneficiaries

        # 6. Combined new device + new beneficiary (account-takeover hallmark)
        fv.new_device_new_beneficiary = fv.is_new_device and fv.is_new_beneficiary

        # 7. SIM swap
        fv.sim_swap_flag_72h = sim_swap_flag_72h
        fv.pin_change_recent = pin_change_recent

        # 8. Location deviation
        fv.location_deviation_km = location_deviation_km
        fv.location_deviation_flag = location_deviation_km > 200

        # 9. Off-hours
        hour = timestamp.hour
        fv.off_hours_flag = not (active_hours_start <= hour <= active_hours_end)

        # 10. Smishing
        fv.smishing_signal_30min = smishing_signal_30min
        fv.smishing_probability = smishing_probability

        # 11. Agent complaint
        fv.agent_complaint_rate = agent_complaint_rate
        fv.agent_complaint_elevated = agent_complaint_rate > 0.3 and channel == "AGENT"

        # 12. Blocklist
        fv.receiver_on_blocklist = receiver_msisdn_hash in self.blocklist_hashes

        return fv

    def compute_from_dict(self, data: dict) -> FeatureVector:
        """Convenience method: compute from a flat dictionary (used for batch/CSV scoring)."""
        return FeatureVector(
            transaction_id=data.get("transaction_id", ""),
            amount_to_avg_ratio=float(data.get("amount_to_avg_ratio", 0)),
            kyc_limit_exceeded=bool(data.get("kyc_limit_exceeded", False)),
            txn_velocity_1h=int(data.get("txn_velocity_1h", 0)),
            txn_velocity_24h=int(data.get("txn_velocity_24h", 0)),
            velocity_anomaly=int(data.get("txn_velocity_24h", 0)) > 5,
            is_new_device=bool(data.get("is_new_device", False)),
            is_new_beneficiary=bool(data.get("is_new_beneficiary", False)),
            new_device_new_beneficiary=bool(data.get("is_new_device", False)) and bool(data.get("is_new_beneficiary", False)),
            sim_swap_flag_72h=bool(data.get("sim_swap_flag_72h", False)),
            pin_change_recent=False,
            location_deviation_km=float(data.get("location_deviation_km", 0)),
            location_deviation_flag=float(data.get("location_deviation_km", 0)) > 200,
            off_hours_flag=bool(data.get("off_hours_flag", False)),
            smishing_signal_30min=bool(data.get("smishing_signal", False)),
            smishing_probability=float(data.get("smishing_probability", 0)),
            agent_complaint_rate=float(data.get("agent_complaint_rate", 0)),
            agent_complaint_elevated=float(data.get("agent_complaint_rate", 0)) > 0.3,
            receiver_on_blocklist=False,
        )
