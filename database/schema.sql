-- Database Schema for AML Compliance System
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    bank_location TEXT,
    risk_rating REAL DEFAULT 0.0,
    flagged_tx_count INTEGER DEFAULT 0,
    total_inflow REAL DEFAULT 0.0,
    total_outflow REAL DEFAULT 0.0,
    account_status TEXT DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    tx_id TEXT PRIMARY KEY,
    date TEXT,
    time TEXT,
    timestamp TEXT,
    sender_account TEXT,
    receiver_account TEXT,
    amount REAL,
    payment_currency TEXT,
    received_currency TEXT,
    sender_bank_location TEXT,
    receiver_bank_location TEXT,
    payment_type TEXT,
    is_laundering INTEGER DEFAULT 0,
    laundering_type TEXT,
    risk_score REAL DEFAULT 0.0,
    risk_tier TEXT DEFAULT 'LOW',
    rule_violations TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    tx_id TEXT,
    sender_account TEXT,
    receiver_account TEXT,
    amount REAL,
    alert_type TEXT,
    severity TEXT,
    risk_score REAL,
    status TEXT DEFAULT 'NEW',
    rule_reason TEXT,
    ml_confidence REAL,
    assigned_to TEXT DEFAULT 'Unassigned',
    investigator_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sar_reports (
    sar_id TEXT PRIMARY KEY,
    alert_id TEXT,
    primary_account TEXT,
    counterparty_account TEXT,
    suspicious_amount REAL,
    laundering_typology TEXT,
    risk_score REAL,
    filing_status TEXT DEFAULT 'SUBMITTED',
    narrative TEXT,
    compliance_officer TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_metrics (
    metric_key TEXT PRIMARY KEY,
    metric_value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tx_sender ON transactions(sender_account);
CREATE INDEX IF NOT EXISTS idx_tx_receiver ON transactions(receiver_account);
CREATE INDEX IF NOT EXISTS idx_tx_risk_score ON transactions(risk_score);
CREATE INDEX IF NOT EXISTS idx_tx_is_laundering ON transactions(is_laundering);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
