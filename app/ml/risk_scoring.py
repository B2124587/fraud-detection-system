"""
Zambia Risk Scoring Engine
Composite risk score R in [0, 100] using weighted indicators per SDD Section 3.6.
Generates human-interpretable reason codes for BoZ compliance.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple
from app.ml.feature_engineering import FeatureVector


# ─── Risk indicator weights (per System Design Document Table 1) ───
RISK_WEIGHTS = {
    "sim_swap_72h":              25,
    "new_device_new_beneficiary": 20,
    "amount_anomaly":            15,
    "velocity_anomaly":          10,
    "smishing_signal":           10,
    "location_deviation":        10,
    "receiver_blocklist":         5,
    "off_hours":                  3,
    "agent_complaint":            2,
}

# Medium-tier partial scores
MEDIUM_SCORES = {
    "sim_swap_72h":              10,
    "new_device_new_beneficiary": 10,
    "amount_anomaly":             8,
    "velocity_anomaly":           5,
    "smishing_signal":            5,
    "location_deviation":         5,
    "receiver_blocklist":         0,
    "off_hours":                  1,
    "agent_complaint":            1,
}

REASON_CODE_MESSAGES = {
    "sim_swap_72h":              "SIM swap detected in past 72 hours — highest risk indicator",
    "new_device_new_beneficiary": "New device combined with new beneficiary — account-takeover pattern",
    "amount_anomaly":            "Transaction amount significantly exceeds 30-day average (>3x)",
    "velocity_anomaly":          "Transaction velocity anomaly: >5 transactions in past 24 hours",
    "smishing_signal":           "Smishing/social engineering signal detected within 30 minutes",
    "location_deviation":        "Geographic deviation >200km from usual transaction area",
    "receiver_blocklist":        "Receiver MSISDN appears on BoZ fraud blocklist",
    "off_hours":                 "Transaction outside user's typical active hours",
    "agent_complaint":           "Elevated complaint rate for this mobile money agent",
}


@dataclass
class RiskScoreResult:
    risk_score: int          # 0–100
    risk_level: str          # LOW / MEDIUM / HIGH / CRITICAL
    reason_codes: List[str]
    reason_messages: List[str]
    sub_scores: dict
    automated_action: str    # ALLOW / REVIEW / BLOCK
    fraud_probability: float # from ML model


def compute_risk_score(
    fv: FeatureVector,
    fraud_probability: float,
    ml_risk_level: Optional[str] = None,
) -> RiskScoreResult:
    """
    Compute composite risk score from FeatureVector and ML fraud probability.
    Returns a RiskScoreResult with score, level, reason codes, and recommended action.
    """
    sub_scores = {}
    reason_codes = []
    reason_messages = []

    def _add(key: str, condition: bool, medium_condition: bool = False):
        if condition:
            sub_scores[key] = RISK_WEIGHTS[key]
            reason_codes.append(key)
            reason_messages.append(REASON_CODE_MESSAGES[key])
        elif medium_condition:
            sub_scores[key] = MEDIUM_SCORES[key]
        else:
            sub_scores[key] = 0

    # 1. SIM swap (weight 25)
    _add("sim_swap_72h", fv.sim_swap_flag_72h)

    # 2. New device + new beneficiary (weight 20)
    _add("new_device_new_beneficiary", fv.new_device_new_beneficiary,
         medium_condition=fv.is_new_device or fv.is_new_beneficiary)

    # 3. Amount anomaly (weight 15) — >3x avg = HIGH, 1.5–3x = MEDIUM
    _add("amount_anomaly",
         condition=fv.amount_to_avg_ratio > 3.0,
         medium_condition=fv.amount_to_avg_ratio > 1.5)

    # 4. Velocity anomaly (weight 10) — >5 txns/24h = HIGH, 3–5 = MEDIUM
    _add("velocity_anomaly",
         condition=fv.txn_velocity_24h > 5,
         medium_condition=fv.txn_velocity_24h >= 3)

    # 5. Smishing (weight 10)
    _add("smishing_signal",
         condition=fv.smishing_signal_30min and fv.smishing_probability > 0.7,
         medium_condition=fv.smishing_signal_30min or fv.smishing_probability > 0.4)

    # 6. Location deviation (weight 10)
    _add("location_deviation",
         condition=fv.location_deviation_flag,
         medium_condition=fv.location_deviation_km > 100)

    # 7. Blocklist (weight 5)
    _add("receiver_blocklist", fv.receiver_on_blocklist)

    # 8. Off-hours (weight 3)
    _add("off_hours",
         condition=fv.off_hours_flag,
         medium_condition=False)

    # 9. Agent complaint (weight 2)
    _add("agent_complaint", fv.agent_complaint_elevated,
         medium_condition=fv.agent_complaint_rate > 0.15)

    # ─── Composite score ───
    indicator_score = sum(sub_scores.values())

    # Blend with ML probability (ML can boost or reduce)
    ml_score = int(fraud_probability * 100)
    # Weighted blend: 60% indicator-based, 40% ML
    blended_score = int(0.60 * indicator_score + 0.40 * ml_score)
    final_score = max(0, min(100, blended_score))

    # ─── Risk level tiers ───
    if final_score >= 60:
        risk_level = "CRITICAL" if final_score >= 80 else "HIGH"
    elif final_score >= 30:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    # ─── Automated action ───
    if risk_level in ("HIGH", "CRITICAL"):
        automated_action = "BLOCK"
    elif risk_level == "MEDIUM":
        automated_action = "REVIEW"
    else:
        automated_action = "ALLOW"

    return RiskScoreResult(
        risk_score=final_score,
        risk_level=risk_level,
        reason_codes=reason_codes,
        reason_messages=reason_messages,
        sub_scores=sub_scores,
        automated_action=automated_action,
        fraud_probability=round(fraud_probability, 4),
    )
