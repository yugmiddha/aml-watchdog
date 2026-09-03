import sqlite3
import os
import json
from typing import List, Dict, Any, Optional

if os.environ.get('VERCEL') or not os.access(os.path.dirname(__file__), os.W_OK):
    DB_PATH = '/tmp/aml_compliance.db'
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), 'aml_compliance.db')

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

def get_connection():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    except Exception:
        pass
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=MEMORY;')
        conn.execute('PRAGMA synchronous=NORMAL;')
    except Exception:
        pass
    return conn

def init_db():
    conn = get_connection()
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print(f'Initialized AML SQLite Database at: {DB_PATH}')

def insert_transactions_bulk(transactions: List[Dict[str, Any]]):
    if not transactions:
        return
    conn = get_connection()
    cursor = conn.cursor()
    query = '''
    INSERT OR REPLACE INTO transactions (
        tx_id, date, time, timestamp, sender_account, receiver_account,
        amount, payment_currency, received_currency, sender_bank_location,
        receiver_bank_location, payment_type, is_laundering, laundering_type,
        risk_score, risk_tier, rule_violations
    ) VALUES (
        :tx_id, :date, :time, :timestamp, :sender_account, :receiver_account,
        :amount, :payment_currency, :received_currency, :sender_bank_location,
        :receiver_bank_location, :payment_type, :is_laundering, :laundering_type,
        :risk_score, :risk_tier, :rule_violations
    )
    '''
    cursor.executemany(query, transactions)
    conn.commit()
    conn.close()

def insert_alerts_bulk(alerts: List[Dict[str, Any]]):
    if not alerts:
        return
    conn = get_connection()
    cursor = conn.cursor()
    query = '''
    INSERT OR REPLACE INTO alerts (
        alert_id, tx_id, sender_account, receiver_account, amount,
        alert_type, severity, risk_score, status, rule_reason,
        ml_confidence, assigned_to, investigator_notes
    ) VALUES (
        :alert_id, :tx_id, :sender_account, :receiver_account, :amount,
        :alert_type, :severity, :risk_score, :status, :rule_reason,
        :ml_confidence, :assigned_to, :investigator_notes
    )
    '''
    cursor.executemany(query, alerts)
    conn.commit()
    conn.close()

def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    
    total_tx = cursor.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
    flagged_tx = cursor.execute('SELECT COUNT(*) FROM transactions WHERE risk_score >= 60 OR is_laundering = 1').fetchone()[0]
    total_volume = cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM transactions').fetchone()[0]
    flagged_volume = cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE risk_score >= 60 OR is_laundering = 1').fetchone()[0]
    
    alert_counts = cursor.execute('SELECT severity, COUNT(*) FROM alerts GROUP BY severity').fetchall()
    status_counts = cursor.execute('SELECT status, COUNT(*) FROM alerts GROUP BY status').fetchall()
    
    laundering_breakdown = cursor.execute('''
    SELECT laundering_type, COUNT(*), SUM(amount) 
    FROM transactions 
    WHERE is_laundering = 1 OR risk_score >= 70
    GROUP BY laundering_type 
    ORDER BY COUNT(*) DESC LIMIT 10
    ''').fetchall()
    
    tier_counts = cursor.execute('SELECT risk_tier, COUNT(*) FROM transactions GROUP BY risk_tier').fetchall()
    
    conn.close()
    
    return {
        'total_transactions': total_tx,
        'flagged_transactions': flagged_tx,
        'total_volume': round(total_volume, 2),
        'flagged_volume': round(flagged_volume, 2),
        'alerts_by_severity': {row[0]: row[1] for row in alert_counts},
        'alerts_by_status': {row[0]: row[1] for row in status_counts},
        'laundering_breakdown': [{'type': row[0] or 'Unknown', 'count': row[1], 'volume': round(row[2] or 0, 2)} for row in laundering_breakdown],
        'tier_distribution': {row[0]: row[1] for row in tier_counts}
    }

if __name__ == '__main__':
    init_db()
