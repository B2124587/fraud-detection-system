-- ============================================================
-- Zambia Mobile Money Fraud Detection System
-- MySQL Migration — CBU CS301 Group 20
-- Database: zambia_fraud
-- MySQL 8.0+ compatible
-- ============================================================

CREATE DATABASE IF NOT EXISTS zambia_fraud
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE zambia_fraud;

-- ─── User Profiles ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_profiles (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    hashed_user_id      VARCHAR(64)     NOT NULL UNIQUE,
    hashed_msisdn       VARCHAR(64)     NOT NULL UNIQUE,
    operator            ENUM('MTN','AIRTEL','ZAMTEL') NOT NULL,
    kyc_tier            TINYINT         NOT NULL DEFAULT 1,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- Portal auth fields (analysts / admins)
    username            VARCHAR(100)    UNIQUE,
    email               VARCHAR(200)    UNIQUE,
    hashed_password     VARCHAR(256),
    role                ENUM('MOBILE_USER','FRAUD_ANALYST','SYSTEM_ADMIN','OPERATOR_API')
                        NOT NULL DEFAULT 'MOBILE_USER',
    is_portal_user      BOOLEAN         NOT NULL DEFAULT FALSE,
    last_login          DATETIME,
    INDEX ix_user_operator (operator),
    INDEX ix_user_hashed_msisdn (hashed_msisdn)
) ENGINE=InnoDB;

-- ─── Behavioral Profiles ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS behavioral_profiles (
    id                          INT AUTO_INCREMENT PRIMARY KEY,
    user_id                     INT          NOT NULL UNIQUE,
    account_age_days            INT          NOT NULL DEFAULT 0,
    avg_daily_txn_count         FLOAT        NOT NULL DEFAULT 1.0,
    avg_30day_txn_amount        FLOAT        NOT NULL DEFAULT 100.0,
    avg_daily_txn_amount        FLOAT        NOT NULL DEFAULT 100.0,
    typical_active_hours_start  TINYINT      NOT NULL DEFAULT 7,
    typical_active_hours_end    TINYINT      NOT NULL DEFAULT 21,
    usual_province              VARCHAR(50)  NOT NULL DEFAULT 'Lusaka',
    known_beneficiaries         TEXT,     -- JSON array of hashed MSISDNs
    registered_devices          TEXT,     -- JSON array of device fingerprints
    sim_swap_flag               BOOLEAN      NOT NULL DEFAULT FALSE,
    sim_swap_timestamp          DATETIME,
    pin_change_flag             BOOLEAN      NOT NULL DEFAULT FALSE,
    pin_change_timestamp        DATETIME,
    total_txn_count             INT          NOT NULL DEFAULT 0,
    last_transaction_at         DATETIME,
    updated_at                  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ─── Transactions ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id          VARCHAR(36)     NOT NULL UNIQUE,
    timestamp               DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sender_msisdn_hash      VARCHAR(64)     NOT NULL,
    receiver_msisdn_hash    VARCHAR(64)     NOT NULL,
    amount                  DECIMAL(15,2)   NOT NULL,
    transaction_type        ENUM('P2P','P2B','CASHOUT','CASHIN','BILLPAY','INTL_TRANSFER') NOT NULL,
    operator                ENUM('MTN','AIRTEL','ZAMTEL') NOT NULL,
    channel                 ENUM('USSD','APP','AGENT','API') NOT NULL,
    status                  VARCHAR(20)     NOT NULL DEFAULT 'COMPLETED',
    is_fraud                BOOLEAN         NOT NULL DEFAULT FALSE,
    fraud_type              ENUM('SIM_SWAP','SMISHING','AGENT_FRAUD','SOCIAL_ENGINEERING','ACCOUNT_TAKEOVER','UNKNOWN'),
    fraud_confirmed_by      INT,
    fraud_confirmed_at      DATETIME,
    is_flagged_for_review   BOOLEAN         NOT NULL DEFAULT FALSE,
    analyst_override        BOOLEAN,
    override_by             INT,
    override_at             DATETIME,
    override_note           TEXT,
    sender_profile_id       INT,
    created_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    used_for_training       BOOLEAN         NOT NULL DEFAULT FALSE,
    FOREIGN KEY (fraud_confirmed_by) REFERENCES user_profiles(id) ON DELETE SET NULL,
    FOREIGN KEY (override_by)        REFERENCES user_profiles(id) ON DELETE SET NULL,
    FOREIGN KEY (sender_profile_id)  REFERENCES user_profiles(id) ON DELETE SET NULL,
    INDEX ix_txn_timestamp_fraud (timestamp, is_fraud),
    INDEX ix_txn_sender          (sender_msisdn_hash),
    INDEX ix_txn_flagged         (is_flagged_for_review)
) ENGINE=InnoDB;

-- ─── Device Sessions ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS device_sessions (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id          INT             NOT NULL UNIQUE,
    device_fingerprint      VARCHAR(128),
    device_type             VARCHAR(50),
    is_new_device           BOOLEAN         NOT NULL DEFAULT FALSE,
    latitude                DECIMAL(10,7),
    longitude               DECIMAL(10,7),
    province                VARCHAR(50),
    location_deviation_km   FLOAT           NOT NULL DEFAULT 0.0,
    session_duration_seconds INT            NOT NULL DEFAULT 0,
    ip_address              VARCHAR(45),
    created_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ─── Agents ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    agent_id        VARCHAR(36)     NOT NULL UNIQUE,
    operator        ENUM('MTN','AIRTEL','ZAMTEL') NOT NULL,
    province        VARCHAR(50),
    district        VARCHAR(50),
    agent_tier      TINYINT         NOT NULL DEFAULT 1,
    complaint_count INT             NOT NULL DEFAULT 0,
    is_flagged      BOOLEAN         NOT NULL DEFAULT FALSE,
    flagged_at      DATETIME,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_agent_operator (operator)
) ENGINE=InnoDB;

-- ─── Smishing Signals ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS smishing_signals (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id          INT,
    sender_short_code       VARCHAR(20),
    target_msisdn_hash      VARCHAR(64),
    message_hash            VARCHAR(64),
    smishing_probability    FLOAT           NOT NULL DEFAULT 0.0,
    has_url                 BOOLEAN         NOT NULL DEFAULT FALSE,
    urgency_score           FLOAT           NOT NULL DEFAULT 0.0,
    operator_impersonation  BOOLEAN         NOT NULL DEFAULT FALSE,
    detected_at             DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE SET NULL,
    INDEX ix_smishing_target (target_msisdn_hash)
) ENGINE=InnoDB;

-- ─── Risk Scores ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS risk_scores (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id      INT             NOT NULL UNIQUE,
    risk_score          TINYINT UNSIGNED NOT NULL,   -- 0–100
    risk_level          ENUM('LOW','MEDIUM','HIGH','CRITICAL') NOT NULL,
    fraud_probability   FLOAT           NOT NULL,
    reason_codes        TEXT,           -- JSON array
    sub_scores          TEXT,           -- JSON object
    ml_model_used       VARCHAR(50),
    automated_action    ENUM('ALLOW','REVIEW','BLOCK') NOT NULL DEFAULT 'ALLOW',
    calculated_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processing_time_ms  INT             NOT NULL DEFAULT 0,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
    INDEX ix_risk_level (risk_level)
) ENGINE=InnoDB;

-- ─── Fraud Alerts ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fraud_alerts (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    alert_id            VARCHAR(36)     NOT NULL UNIQUE,
    transaction_id      INT             NOT NULL,
    user_id             INT,
    risk_score_id       INT,
    alert_type          VARCHAR(50),    -- AUTO_FLAGGED / MANUAL_FLAG / SYSTEM
    status              ENUM('OPEN','UNDER_REVIEW','CONFIRMED_FRAUD','FALSE_POSITIVE','ESCALATED')
                        NOT NULL DEFAULT 'OPEN',
    assigned_analyst_id INT,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    resolved_at         DATETIME,
    resolution_notes    TEXT,
    fraud_type          ENUM('SIM_SWAP','SMISHING','AGENT_FRAUD','SOCIAL_ENGINEERING','ACCOUNT_TAKEOVER','UNKNOWN'),
    FOREIGN KEY (transaction_id)      REFERENCES transactions(id)   ON DELETE CASCADE,
    FOREIGN KEY (user_id)             REFERENCES user_profiles(id)  ON DELETE SET NULL,
    FOREIGN KEY (risk_score_id)       REFERENCES risk_scores(id)    ON DELETE SET NULL,
    FOREIGN KEY (assigned_analyst_id) REFERENCES user_profiles(id)  ON DELETE SET NULL,
    INDEX ix_alert_status  (status),
    INDEX ix_alert_created (created_at)
) ENGINE=InnoDB;

-- ─── Audit Logs ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    log_id          VARCHAR(36)     NOT NULL UNIQUE,
    event_type      VARCHAR(50)     NOT NULL,
    operator_id     INT,
    fraud_alert_id  INT,
    transaction_ref VARCHAR(36),
    timestamp       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json   TEXT,
    ip_address      VARCHAR(45),
    result          VARCHAR(20),
    FOREIGN KEY (operator_id)    REFERENCES user_profiles(id) ON DELETE SET NULL,
    FOREIGN KEY (fraud_alert_id) REFERENCES fraud_alerts(id)  ON DELETE SET NULL,
    INDEX ix_audit_timestamp  (timestamp),
    INDEX ix_audit_event_type (event_type)
) ENGINE=InnoDB;

-- ─── SIM Swap Events ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sim_swap_events (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    msisdn_hash     VARCHAR(64)     NOT NULL,
    operator        ENUM('MTN','AIRTEL','ZAMTEL'),
    swap_timestamp  DATETIME        NOT NULL,
    detected_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_verified     BOOLEAN         NOT NULL DEFAULT FALSE,
    INDEX ix_sim_swap_msisdn (msisdn_hash),
    INDEX ix_sim_swap_ts     (swap_timestamp)
) ENGINE=InnoDB;

-- ─── Fraud Blocklist ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fraud_blocklist (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    msisdn_hash VARCHAR(64)     NOT NULL UNIQUE,
    added_by    INT,
    added_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason      TEXT,
    source      VARCHAR(50),    -- BOZ / OPERATOR / ANALYST
    is_active   BOOLEAN         NOT NULL DEFAULT TRUE,
    expires_at  DATETIME,
    FOREIGN KEY (added_by) REFERENCES user_profiles(id) ON DELETE SET NULL,
    INDEX ix_blocklist_active (is_active)
) ENGINE=InnoDB;

-- ─── ML Model Registry ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS ml_model_registry (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    model_name          VARCHAR(50)     NOT NULL,
    version             VARCHAR(20)     NOT NULL,
    is_active           BOOLEAN         NOT NULL DEFAULT FALSE,
    trained_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    training_samples    INT,
    fraud_samples       INT,
    `precision`         FLOAT,
    recall              FLOAT,
    f1_score            FLOAT,
    auc_roc             FLOAT,
    mcc                 FLOAT,
    accuracy            FLOAT,
    model_path          VARCHAR(256),
    trained_by          INT,
    notes               TEXT,
    hyperparameters     TEXT,
    FOREIGN KEY (trained_by) REFERENCES user_profiles(id) ON DELETE SET NULL,
    INDEX ix_model_active (model_name, is_active)
) ENGINE=InnoDB;

-- ─── Compliance Reports ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS compliance_reports (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    report_id               VARCHAR(36)     NOT NULL UNIQUE,
    report_type             VARCHAR(50),
    period_start            DATETIME,
    period_end              DATETIME,
    generated_by            INT,
    generated_at            DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_transactions      INT,
    total_flagged           INT,
    confirmed_fraud         INT,
    false_positives         INT,
    total_fraud_amount_zmw  DECIMAL(15,2),
    report_path             VARCHAR(256),
    submitted_to_boz        BOOLEAN         NOT NULL DEFAULT FALSE,
    submitted_at            DATETIME,
    FOREIGN KEY (generated_by) REFERENCES user_profiles(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ─── Default seed users ───────────────────────────────────────
-- Passwords are bcrypt hashed; plaintext: Admin@GPS2024! and Analyst@2024!
INSERT IGNORE INTO user_profiles
    (hashed_user_id, hashed_msisdn, operator, username, email, hashed_password, role, is_portal_user)
VALUES
    ('admin_system',   'admin_msisdn',        'MTN', 'admin',    'admin@cbu.ac.zm',    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMqJqhKOh9xbQFG1R8bK5XHkPa', 'SYSTEM_ADMIN',   TRUE),
    ('analyst_001',    'analyst_msisdn_001',   'MTN', 'analyst1', 'analyst1@cbu.ac.zm', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMqJqhKOh9xbQFG1R8bK5XHkPa', 'FRAUD_ANALYST',  TRUE);

-- ─── Views for reporting ──────────────────────────────────────
CREATE OR REPLACE VIEW v_fraud_summary AS
SELECT
    DATE(t.timestamp)                       AS txn_date,
    t.operator,
    t.transaction_type,
    COUNT(t.id)                             AS total_transactions,
    SUM(t.is_fraud)                         AS fraud_count,
    ROUND(AVG(t.is_fraud) * 100, 2)         AS fraud_rate_pct,
    SUM(CASE WHEN t.is_fraud THEN t.amount ELSE 0 END) AS fraud_amount_zmw
FROM transactions t
GROUP BY DATE(t.timestamp), t.operator, t.transaction_type;

CREATE OR REPLACE VIEW v_open_alerts AS
SELECT
    fa.alert_id,
    fa.status,
    fa.created_at,
    fa.fraud_type,
    t.transaction_id,
    t.amount,
    t.transaction_type,
    t.channel,
    t.operator,
    rs.risk_score,
    rs.risk_level,
    rs.fraud_probability,
    rs.reason_codes,
    rs.automated_action
FROM fraud_alerts fa
JOIN transactions t  ON fa.transaction_id = t.id
LEFT JOIN risk_scores rs ON fa.risk_score_id = rs.id
WHERE fa.status IN ('OPEN', 'UNDER_REVIEW')
ORDER BY rs.risk_score DESC, fa.created_at ASC;

CREATE OR REPLACE VIEW v_model_performance AS
SELECT
    model_name,
    version,
    is_active,
    trained_at,
    training_samples,
    fraud_samples,
    ROUND(`precision` * 100, 2)  AS precision_pct,
    ROUND(recall * 100, 2)       AS recall_pct,
    ROUND(f1_score * 100, 2)     AS f1_pct,
    ROUND(auc_roc * 100, 2)      AS auc_roc_pct,
    ROUND(mcc * 100, 2)          AS mcc_pct
FROM ml_model_registry
ORDER BY trained_at DESC;
