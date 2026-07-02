"""
ML Model Training Pipeline — CBU CS301 Group 20
Trains: Random Forest (primary), XGBoost (secondary),
        Logistic Regression (baseline), Smishing NLP (supplementary).
Applies SMOTE for class imbalance. Evaluates with precision/recall/F1/AUC/MCC.
"""
import json
import os
import pickle
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score,
    matthews_corrcoef, accuracy_score, classification_report,
    confusion_matrix
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from imblearn.over_sampling import SMOTE

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

FEATURE_COLS = [
    "amount_to_avg_ratio",        # 0
    "kyc_limit_exceeded",         # 1
    "txn_velocity_1h",            # 2
    "txn_velocity_24h",           # 3
    "velocity_anomaly",           # 4
    "is_new_device",              # 5
    "is_new_beneficiary",         # 6
    "new_device_new_beneficiary", # 7
    "sim_swap_flag_72h",          # 8
    "pin_change_recent",          # 9
    "location_deviation_km_norm", # 10
    "location_deviation_flag",    # 11
    "off_hours_flag",             # 12
    "smishing_signal_30min",      # 13
    "smishing_probability",       # 14
    "agent_complaint_rate",       # 15
    "agent_complaint_elevated",   # 16
    "receiver_on_blocklist",      # 17
]


def _derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive all 18 feature columns from raw dataset."""
    df = df.copy()

    # velocity columns — generator uses txn_velocity_24h; add 1h if missing
    if "txn_velocity_1h" not in df.columns:
        df["txn_velocity_1h"] = (df.get("txn_velocity_24h", pd.Series(0, index=df.index)) / 4).astype(int)

    if "velocity_anomaly" not in df.columns:
        df["velocity_anomaly"] = (df.get("txn_velocity_24h", 0) > 5).astype(int)

    if "new_device_new_beneficiary" not in df.columns:
        df["new_device_new_beneficiary"] = (
            df.get("is_new_device", False).astype(bool) &
            df.get("is_new_beneficiary", False).astype(bool)
        ).astype(int)

    # Normalised location deviation
    if "location_deviation_km_norm" not in df.columns:
        df["location_deviation_km_norm"] = df.get("location_deviation_km", 0) / 1000.0

    if "location_deviation_flag" not in df.columns:
        df["location_deviation_flag"] = (df.get("location_deviation_km", 0) > 200).astype(int)

    # smishing columns — generator uses "smishing_signal"
    if "smishing_signal_30min" not in df.columns:
        df["smishing_signal_30min"] = df.get("smishing_signal", 0).astype(int)

    if "smishing_probability" not in df.columns:
        df["smishing_probability"] = df.get("smishing_signal", 0).astype(float) * 0.85

    if "agent_complaint_elevated" not in df.columns:
        df["agent_complaint_elevated"] = (df.get("agent_complaint_rate", 0) > 0.3).astype(int)

    if "kyc_limit_exceeded" not in df.columns:
        df["kyc_limit_exceeded"] = 0

    if "pin_change_recent" not in df.columns:
        df["pin_change_recent"] = 0

    if "receiver_on_blocklist" not in df.columns:
        df["receiver_on_blocklist"] = 0

    # Ensure boolean cols are int
    for col in ["is_new_device", "is_new_beneficiary", "sim_swap_flag_72h",
                "off_hours_flag", "smishing_signal_30min"]:
        if col in df.columns:
            df[col] = df[col].astype(int)

    return df


def evaluate_model(model, X_test, y_test, model_name: str) -> Dict[str, float]:
    """Evaluate model on held-out test set."""
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else y_pred

    metrics = {
        "accuracy":  round(accuracy_score(y_test, y_pred), 4),
        "precision": round(precision_score(y_test, y_pred, zero_division=0), 4),
        "recall":    round(recall_score(y_test, y_pred, zero_division=0), 4),
        "f1_score":  round(f1_score(y_test, y_pred, zero_division=0), 4),
        "auc_roc":   round(roc_auc_score(y_test, y_prob), 4),
        "mcc":       round(matthews_corrcoef(y_test, y_pred), 4),
    }

    print(f"\n{'='*50}")
    print(f"  {model_name} — Evaluation Results")
    print(f"{'='*50}")
    for k, v in metrics.items():
        print(f"  {k:12s}: {v:.4f}")
    print(f"\n{classification_report(y_test, y_pred, target_names=['Legitimate', 'Fraud'])}")
    cm = confusion_matrix(y_test, y_pred)
    print(f"Confusion Matrix:\n  TN={cm[0,0]}, FP={cm[0,1]}, FN={cm[1,0]}, TP={cm[1,1]}")

    return metrics


def train_all_models(
    df: pd.DataFrame,
    model_dir: str = "./models",
    random_state: int = 42,
) -> Dict[str, Any]:
    """
    Full training pipeline:
    1. Feature derivation
    2. Train/val/test split (70/15/15)
    3. SMOTE oversampling on training set
    4. Train RF, XGBoost, LogReg
    5. Evaluate all models
    6. Save best model as primary
    Returns dict of {model_name: metrics}
    """
    os.makedirs(model_dir, exist_ok=True)

    print(f"\nPreparing dataset: {len(df)} transactions...")
    df = _derive_features(df)

    # Ensure all feature columns exist
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0

    X = df[FEATURE_COLS].fillna(0).astype(float)
    y = df["is_fraud"].astype(int)

    print(f"Fraud prevalence: {y.mean()*100:.2f}%")

    # ─── Stratified split ───
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y, test_size=0.15, stratify=y, random_state=random_state
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp, test_size=0.15/0.85, stratify=y_temp, random_state=random_state
    )

    print(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")

    # ─── SMOTE on training set only ───
    print("Applying SMOTE oversampling to training set...")
    smote = SMOTE(random_state=random_state, sampling_strategy=0.5)
    X_train_sm, y_train_sm = smote.fit_resample(X_train, y_train)
    print(f"After SMOTE — Train: {len(X_train_sm)}, Fraud: {y_train_sm.sum()}")

    results = {}

    # ─── 1. Random Forest (Primary) ───
    print("\nTraining Random Forest (Primary)...")
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=15,
        min_samples_leaf=5,
        class_weight="balanced",
        n_jobs=-1,
        random_state=random_state,
    )
    rf.fit(X_train_sm, y_train_sm)
    rf_metrics = evaluate_model(rf, X_test, y_test, "Random Forest")
    results["random_forest"] = {"model": rf, "metrics": rf_metrics}

    with open(f"{model_dir}/random_forest.pkl", "wb") as f:
        pickle.dump(rf, f)
    print(f"Random Forest saved → {model_dir}/random_forest.pkl")

    # ─── 2. XGBoost (Secondary) ───
    if XGBOOST_AVAILABLE:
        print("\nTraining XGBoost (Secondary)...")
        scale_pos = int((y_train_sm == 0).sum() / max((y_train_sm == 1).sum(), 1))
        xgb_model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=8,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=scale_pos,
            eval_metric="aucpr",
            use_label_encoder=False,
            random_state=random_state,
            verbosity=0,
        )
        xgb_model.fit(
            X_train_sm, y_train_sm,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )
        xgb_metrics = evaluate_model(xgb_model, X_test, y_test, "XGBoost")
        results["xgboost"] = {"model": xgb_model, "metrics": xgb_metrics}

        with open(f"{model_dir}/xgboost.pkl", "wb") as f:
            pickle.dump(xgb_model, f)
        print(f"XGBoost saved → {model_dir}/xgboost.pkl")

    # ─── 3. Logistic Regression (Baseline) ───
    print("\nTraining Logistic Regression (Baseline)...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_sm)
    X_test_scaled = scaler.transform(X_test)

    lr = LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        C=1.0,
        random_state=random_state,
    )
    lr.fit(X_train_scaled, y_train_sm)
    lr_metrics = evaluate_model(lr, X_test_scaled, y_test, "Logistic Regression")
    results["logistic_regression"] = {"model": lr, "metrics": lr_metrics}

    with open(f"{model_dir}/logistic_regression.pkl", "wb") as f:
        pickle.dump({"model": lr, "scaler": scaler}, f)
    print(f"Logistic Regression saved → {model_dir}/logistic_regression.pkl")

    # ─── Save feature column list ───
    with open(f"{model_dir}/feature_cols.json", "w") as f:
        json.dump(FEATURE_COLS, f)

    # ─── Select primary model (best F1) ───
    best_name = max(
        [k for k in results],
        key=lambda k: results[k]["metrics"]["f1_score"]
    )
    print(f"\nBest model by F1: {best_name} (F1={results[best_name]['metrics']['f1_score']:.4f})")

    with open(f"{model_dir}/primary_model.json", "w") as f:
        json.dump({
            "model_name": best_name,
            "trained_at": datetime.utcnow().isoformat(),
            "metrics": results[best_name]["metrics"],
            "feature_cols": FEATURE_COLS,
        }, f, indent=2)

    return {k: v["metrics"] for k, v in results.items()}


def train_smishing_classifier(model_dir: str = "./models") -> dict:
    """
    Train TF-IDF + Naive Bayes smishing detector.
    Uses synthetic Zambian SMS examples.
    """
    print("\nTraining Smishing NLP Classifier...")

    # Zambian smishing examples (operator impersonation, urgency, URLs)
    smishing_samples = [
        "MTN: Your account is suspended. Verify now: bit.ly/mtn-zmb",
        "AIRTEL ALERT: Unusual login detected. Click to secure: airtel-zm.net/verify",
        "WIN 5000 ZMW! Claim your MTN MoMo reward: mtn-zm-prize.com",
        "ZAMTEL: Your SIM will be deactivated. Update KYC: zamtel-kyc.net",
        "URGENT: Your MoMo account has been compromised. Reset PIN at: zmb-momo.com",
        "You have won K10,000! Send PIN to 0969xxxxxx to claim",
        "Bank of Zambia: Verify your mobile account immediately: boz-verify.net",
        "MTN Zimbabwe promo: Send K50 to win K5000 back guarantee",
        "Your AIRTEL account needs verification. Reply with OTP code",
        "FINAL NOTICE: MoMo account blocked due to suspicious activity. Call 0977",
        "Congratulations! You've been selected. Send K20 airtime to activate reward",
        "ZICTA compliance check: Provide your NRC to avoid network suspension",
        "Airtel: Free data offer expires today! Click to activate: airtel-free.zm",
        "MTN: Your KYC is incomplete. Visit: mtn-zm-update.com/kyc or lose access",
        "Emergency: Your MoMo PIN was changed from unknown device. Reverse at momo-secure.zm",
    ]

    legitimate_samples = [
        "Your MTN MoMo transaction of ZMW 200 to 0976543210 was successful",
        "Airtel Money: You have received ZMW 500 from 0977123456",
        "ZAMTEL: Your recharge of ZMW 50 was successful. Balance: ZMW 65",
        "MTN: Your data bundle of 1GB has been activated",
        "MoMo PIN changed successfully on your request",
        "Transaction reference: TXN20240115001. Amount: ZMW 1000",
        "Your Airtel Money balance is ZMW 342.50",
        "MTN: Insufficient balance for this transaction",
        "Zamtel: Call charges for today: ZMW 12.30",
        "MoMo: You have requested to withdraw ZMW 800 from agent 001234",
        "Your Airtel money account has been credited ZMW 2000",
        "MTN data expires 15 Jan 2024. Recharge to extend.",
        "ZAMTEL: Network maintenance tonight 22:00-02:00. Apologies.",
        "Airtel: Your call to 0978 lasted 3 minutes. Cost: ZMW 1.50",
        "MoMo agent deposit of ZMW 5000 confirmed. Ref: DEP20240115",
    ]

    texts = smishing_samples + legitimate_samples
    labels = [1] * len(smishing_samples) + [0] * len(legitimate_samples)

    # TF-IDF + Naive Bayes pipeline
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=500)),
        ("clf", MultinomialNB(alpha=0.5)),
    ])

    pipeline.fit(texts, labels)

    with open(f"{model_dir}/smishing_nlp.pkl", "wb") as f:
        pickle.dump(pipeline, f)
    print(f"Smishing NLP saved → {model_dir}/smishing_nlp.pkl")

    return {"model": "smishing_nlp", "samples": len(texts)}


class ModelInference:
    """Loads trained models and runs inference."""

    def __init__(self, model_dir: str = "./models"):
        self.model_dir = model_dir
        self._rf = None
        self._xgb = None
        self._lr_bundle = None
        self._smishing = None
        self._feature_cols = FEATURE_COLS
        self._load_models()

    def _load_models(self):
        try:
            with open(f"{self.model_dir}/random_forest.pkl", "rb") as f:
                self._rf = pickle.load(f)
            print("Random Forest model loaded.")
        except FileNotFoundError:
            print("Warning: Random Forest model not found. Run training first.")

        try:
            with open(f"{self.model_dir}/xgboost.pkl", "rb") as f:
                self._xgb = pickle.load(f)
            print("XGBoost model loaded.")
        except FileNotFoundError:
            pass

        try:
            with open(f"{self.model_dir}/logistic_regression.pkl", "rb") as f:
                self._lr_bundle = pickle.load(f)
            print("Logistic Regression model loaded.")
        except FileNotFoundError:
            pass

        try:
            with open(f"{self.model_dir}/smishing_nlp.pkl", "rb") as f:
                self._smishing = pickle.load(f)
            print("Smishing NLP model loaded.")
        except FileNotFoundError:
            pass

    def predict_fraud_probability(self, feature_vector_array: list) -> Tuple[float, str]:
        """
        Returns (fraud_probability, model_used).
        Uses RF primary, falls back to XGB, then LR.
        """
        X = np.array(feature_vector_array).reshape(1, -1)

        if self._rf is not None:
            prob = self._rf.predict_proba(X)[0][1]
            return float(prob), "random_forest"

        if self._xgb is not None:
            prob = self._xgb.predict_proba(X)[0][1]
            return float(prob), "xgboost"

        if self._lr_bundle is not None:
            scaler = self._lr_bundle["scaler"]
            model = self._lr_bundle["model"]
            X_scaled = scaler.transform(X)
            prob = model.predict_proba(X_scaled)[0][1]
            return float(prob), "logistic_regression"

        # No model — use heuristic
        return self._heuristic_score(feature_vector_array)

    def _heuristic_score(self, features: list) -> Tuple[float, str]:
        """Fallback heuristic when no model is loaded."""
        # Map to feature names
        mapping = dict(zip(FEATURE_COLS, features))
        score = 0.0
        if mapping.get("sim_swap_flag_72h", 0): score += 0.35
        if mapping.get("new_device_new_beneficiary", 0): score += 0.25
        if mapping.get("amount_to_avg_ratio", 0) > 3: score += 0.15
        if mapping.get("velocity_anomaly", 0): score += 0.10
        if mapping.get("smishing_signal", 0): score += 0.10
        if mapping.get("location_deviation_flag", 0): score += 0.10
        return min(score, 0.99), "heuristic"

    def predict_smishing(self, sms_text: str) -> float:
        """Returns smishing probability for an SMS message."""
        if self._smishing is None:
            return 0.0
        try:
            prob = self._smishing.predict_proba([sms_text])[0][1]
            return float(prob)
        except Exception:
            return 0.0

    def get_feature_importance(self) -> dict:
        """Return feature importance from primary model."""
        if self._rf is not None:
            importances = self._rf.feature_importances_
            return dict(zip(self._feature_cols[:len(importances)], [round(float(x), 4) for x in importances]))
        return {}
