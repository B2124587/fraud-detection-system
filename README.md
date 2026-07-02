# Zambia Mobile Money Fraud Detection System
### CBU CS301 — System Design · Group 20 · Supervisor: Mrs. Daka

| Member | Student ID |
|---|---|
| Liswaniso Ignitious | 23126744 |
| Bilonda Beyar | 23124587 |
| Chongo Vision | 23125282 |
| Phiri Betwell | 23125405 |

---

## System Overview

A production-ready machine learning fraud detection system for Zambian mobile money platforms (MTN MoMo, Airtel Money, Zamtel Kwacha). Implements the full OOAD class diagram from the CBU CS301 System Design Document with:

- **5-layer pipeline architecture** (Ingestion → Feature Engineering → ML Inference → Risk Scoring → Alert/Decision)
- **Composite risk scoring** (0–100) with 9 weighted Zambian fraud indicators
- **4 ML models**: Random Forest (primary), XGBoost (secondary), Logistic Regression (baseline), TF-IDF Naive Bayes Smishing NLP
- **React Fraud Analyst Dashboard** with alert review, override workflow, and compliance exports
- **Automated monthly retraining** pipeline triggered by analyst-confirmed fraud labels
- **BoZ compliance reporting** with full audit trail
- **MySQL** database — single, direct local connection (no Docker, no SQLite)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Client / External Layer             │
│  React Dashboard │ Operator API Client │ BoZ Portal  │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│               REST API Gateway (FastAPI)             │
│         Authentication & Access Control (JWT)        │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│            FraudDetectionService (Orchestration)     │
├────────────────┬──────────────────┬─────────────────┤
│ Feature Eng.   │   ML Inference   │  Risk Scoring   │
│ (15 features)  │ RF/XGB/LR/NLP   │ Engine (0-100)  │
└────────────────┴──────────────────┴─────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│          Alert & Compliance Layer                    │
│  FraudAlert │ AuditLog │ ComplianceReport            │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│                  MySQL Database                      │
│  Transactions │ Profiles │ Models │ Audit            │
└─────────────────────────────────────────────────────┘
```

---

## Quick Start (MySQL, Windows PowerShell)

This project connects directly to a MySQL server you already have running locally — no Docker, no SQLite. Tested against MySQL Community Server / MySQL Workbench's bundled server on Windows.

```powershell
# 0. Make sure MySQL Server is installed and running
#    (MySQL Installer for Windows, or via MySQL Workbench)
#    Confirm you can connect with: mysql -u root -p

# 1. Create the database and tables
mysql -u root -p < migrations\001_initial_schema.sql

# 2. Clone and set up a virtual environment
cd zambia-fraud-detection
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Configure your database connection
copy .env.example .env
# Edit .env and set DATABASE_URL to your MySQL credentials, e.g.:
# DATABASE_URL=mysql+pymysql://root:YOUR_MYSQL_PASSWORD@localhost:3306/zambia_fraud

# 4. Train models (generates 50k synthetic Zambian transactions)
python scripts\train_initial_models.py

# 5. (Optional) Seed demo data — users, alerts, sample transactions
python scripts\seed_demo_data.py

# 6. Start the API
python main.py
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)

# 7. Start the Dashboard (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

**Login credentials:**
| Role | Username | Password |
|---|---|---|
| System Admin | `admin` | `Admin@GPS2024!` |
| Fraud Analyst | `analyst1` | `Analyst@2024!` |

---

## REST API Endpoints

| Method | Path | Description | SLA |
|---|---|---|---|
| POST | `/auth/login` | JWT authentication | — |
| GET | `/auth/me` | Current user info | — |
| POST | `/score` | Score transaction for fraud risk | < 2s |
| POST | `/flag/{txn_id}` | Manually flag confirmed fraud | < 1s |
| GET | `/user/profile` | Behavioural profile by MSISDN | < 1s |
| GET | `/health` | System health check | < 200ms |
| GET | `/alerts` | List fraud alerts (paginated) | — |
| POST | `/alerts/{id}/override` | Analyst fraud override | — |
| GET | `/dashboard/stats` | Aggregate dashboard metrics | — |
| GET | `/dashboard/risk-trends` | Daily alert trend data | — |
| GET | `/models` | ML model registry | — |
| POST | `/models/retrain` | Trigger model retraining | — |
| POST | `/compliance/report` | Generate BoZ compliance report | — |
| GET | `/compliance/audit-log` | Export audit log CSV | — |
| GET | `/audit-log` | Paginated audit log | — |
| POST | `/blocklist` | Add MSISDN to fraud blocklist | — |
| POST | `/smishing/classify` | Classify SMS for smishing | — |
| POST | `/sim-swap` | Record SIM swap event | — |

Full interactive docs at: `http://localhost:8000/docs`

---

## Risk Scoring Model

Per CBU CS301 System Design Document Table 1:

| Risk Indicator | Weight | High/Critical |
|---|---|---|
| SIM swap in past 72h | 25 | Flagged |
| New device + new beneficiary | 20 | Both true |
| Amount anomaly (>3x 30-day avg) | 15 | Triggered |
| Transaction velocity anomaly (>5/24h) | 10 | Triggered |
| Preceded by smishing signal (30min) | 10 | Triggered |
| Location deviation >200km | 10 | Triggered |
| Receiver on fraud blocklist | 5 | Match |
| Off-hours activity | 3 | Triggered |
| Agent complaint rate elevated | 2 | Triggered |

**Thresholds:** LOW (0–29) · MEDIUM (30–59) · HIGH (60–79) · CRITICAL (80–100)

---

## ML Model Performance Targets

| Metric | Target |
|---|---|
| Precision | ≥ 85% |
| Recall | ≥ 80% |
| AUC-ROC | ≥ 0.90 |

---

## Running Tests

```bash
# Install test dependencies
pip install pytest

# Run all 10 end-to-end tests
python -m pytest tests/test_e2e.py -v
```

> Note: `tests/test_e2e.py` points at a disposable local SQLite file (`test_fraud.db`) purely so the test suite runs in isolation without touching your real MySQL database. The application itself always uses MySQL — see `DATABASE_URL` in `.env`.

```
# Tests cover:
#   1. Synthetic data generation (50k Zambian transactions)
#   2. Feature engineering (15 indicators)
#   3. Risk scoring engine (composite 0-100 score)
#   4. ML model training (RF + XGB + LR + NLP)
#   5. ML inference (fraud probability + smishing)
#   6. Transaction scoring service (end-to-end)
#   7. Manual flag + override workflow
#   8. Dashboard stats
#   9. Compliance report + audit export
#  10. Automated retraining pipeline
```

---

## OOAD Alignment

All 13 OOAD entities from the Class Diagram are implemented:

| Class | Implementation |
|---|---|
| `Transaction` | `app/models/orm_models.py:Transaction` |
| `UserProfile` | `app/models/orm_models.py:UserProfile` |
| `BehavioralProfile` | `app/models/orm_models.py:BehavioralProfile` |
| `DeviceSession` | `app/models/orm_models.py:DeviceSession` |
| `Agent` | `app/models/orm_models.py:Agent` |
| `SmishingSignal` | `app/models/orm_models.py:SmishingSignal` |
| `FeatureVector` | `app/ml/feature_engineering.py:FeatureVector` |
| `RiskScore` | `app/models/orm_models.py:RiskScore` |
| `MLModel` (abstract) | `app/ml/model_trainer.py:ModelInference` |
| `RiskScoringEngine` | `app/ml/risk_scoring.py:compute_risk_score` |
| `FraudDetectionService` | `app/services/fraud_detection_service.py` |
| `FraudAlert` | `app/models/orm_models.py:FraudAlert` |
| `AuditLog` | `app/models/orm_models.py:AuditLog` |

---

## Ethical Compliance

- No real customer data used — fully synthetic Zambian dataset
- All PII (MSISDNs, device IDs) SHA-256 hashed before storage
- Zambia Data Protection Act No. 3 of 2021 compliant
- ZICTA cybersecurity guideline compliant
- All analyst overrides logged with timestamp + operator ID for BoZ auditability
- Precision targets formalised to minimise false positives on legitimate transactions

---

## Project Structure

```
zambia-fraud-detection/
├── main.py                          # FastAPI entry point
├── requirements.txt
├── .env.example
├── app/
│   ├── config.py                    # Pydantic settings (MySQL DATABASE_URL)
│   ├── models/
│   │   ├── orm_models.py            # All 13 OOAD SQLAlchemy models
│   │   └── database.py              # MySQL engine + session management
│   ├── ml/
│   │   ├── data_generator.py        # Zambian synthetic dataset
│   │   ├── feature_engineering.py   # 15-feature FeatureVector
│   │   ├── risk_scoring.py          # Composite risk scoring engine
│   │   └── model_trainer.py         # RF/XGB/LR/NLP training + inference
│   ├── services/
│   │   ├── auth_service.py          # PyJWT + stdlib PBKDF2 hashing + RBAC
│   │   ├── fraud_detection_service.py # Core orchestration
│   │   ├── retraining_service.py    # Monthly retraining pipeline
│   │   └── compliance_service.py    # BoZ reporting
│   └── api/
│       └── routes.py                # All 18 REST endpoints
├── frontend/
│   ├── FraudDashboard.jsx           # React analyst dashboard
│   ├── main.jsx
│   ├── index.html
│   └── package.json
├── migrations/
│   └── 001_initial_schema.sql       # MySQL schema + views + seeds
├── scripts/
│   ├── train_initial_models.py      # First-run training
│   └── seed_demo_data.py            # Demo data seeder
└── tests/
    └── test_e2e.py                  # 10 end-to-end tests
```
#   f r a u d - d e t e c t i o n - s y s t e m  
 