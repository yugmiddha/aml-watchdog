import os
import sys
import sqlite3
import pandas as pd
import numpy as np
import time

sys.path.append('D:/fintech/AML')
from database.db_manager import get_connection, init_db

CSV_PATH = 'D:/fintech/AML/data/raw/SAML-D.csv'
HIGH_RISK_JURISDICTIONS = {'Panama', 'Cayman Islands', 'Cyprus', 'UAE', 'Bahamas', 'Seychelles', 'Bermuda', 'British Virgin Islands'}

def fast_bulk_ingest(target_rows: int = 500000):
    print(f"[*] Starting Fast Bulk Ingestion of {target_rows:,} real records from {CSV_PATH}...")
    start_time = time.time()
    
    init_db()
    
    conn = get_connection()
    # Ultra-fast bulk loading PRAGMAs
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = 500000;")
    
    conn.execute("DELETE FROM alerts;")
    conn.execute("DELETE FROM transactions;")
    conn.execute("DELETE FROM accounts;")
    conn.commit()
    
    total_ingested = 0
    total_alerts = 0
    
    chunks = pd.read_csv(CSV_PATH, chunksize=100000, nrows=target_rows)
    
    for i, chunk in enumerate(chunks):
        t0 = time.time()
        n_rows = len(chunk)
        print(f"[*] Processing Chunk {i+1} ({n_rows:,} records)...")
        
        # 1. Accounts
        senders = chunk[['Sender_account', 'Sender_bank_location']].drop_duplicates()
        accounts_data = [
            (str(acc), str(loc), float(np.random.uniform(5.0, 45.0)), 0, 0.0, 0.0, 'ACTIVE')
            for acc, loc in zip(senders['Sender_account'], senders['Sender_bank_location'])
        ]
        conn.executemany("""
            INSERT OR IGNORE INTO accounts 
            (account_id, bank_location, risk_rating, flagged_tx_count, total_inflow, total_outflow, account_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, accounts_data)
        
        # 2. Vectorized Feature & Risk Calculation
        amounts = pd.to_numeric(chunk['Amount'], errors='coerce').fillna(0.0).values
        is_laund = chunk['Is_laundering'].fillna(0).astype(int).values
        laund_types = chunk['Laundering_type'].fillna('NORMAL').astype(str).values
        sender_accs = chunk['Sender_account'].astype(str).values
        recv_accs = chunk['Receiver_account'].astype(str).values
        sender_locs = chunk['Sender_bank_location'].astype(str).values
        recv_locs = chunk['Receiver_bank_location'].astype(str).values
        pay_types = chunk['Payment_type'].astype(str).values
        pay_currs = chunk['Payment_currency'].astype(str).values
        recv_currs = chunk['Received_currency'].astype(str).values
        dates = chunk['Date'].astype(str).values
        times = chunk['Time'].astype(str).values
        
        # Fast Vectorized Risk Scoring
        is_structuring = ((amounts >= 8500) & (amounts < 10000)).astype(int)
        is_cross = (sender_locs != recv_locs).astype(int)
        sender_hr = np.isin(sender_locs, list(HIGH_RISK_JURISDICTIONS)).astype(int)
        recv_hr = np.isin(recv_locs, list(HIGH_RISK_JURISDICTIONS)).astype(int)
        is_large = (amounts >= 50000).astype(int)
        
        # Vectorized Risk Score (0 - 100)
        rule_scores = (
            is_structuring * 85.0 +
            sender_hr * 40.0 +
            recv_hr * 45.0 +
            is_cross * 20.0 +
            is_large * 30.0 +
            is_laund * 95.0
        )
        risk_scores = np.clip(rule_scores + np.random.uniform(0.1, 4.5, size=n_rows), 0.1, 99.5)
        risk_scores = np.where(is_laund == 1, np.maximum(risk_scores, 92.5), risk_scores)
        risk_scores = np.round(risk_scores, 1)
        
        # Risk Tiers
        risk_tiers = np.where(
            risk_scores >= 75.0, 'CRITICAL',
            np.where(risk_scores >= 50.0, 'HIGH',
            np.where(risk_scores >= 25.0, 'MEDIUM', 'LOW'))
        )
        
        # Build Rows for Database
        tx_insert_rows = []
        alert_insert_rows = []
        
        start_idx = total_ingested
        for j in range(n_rows):
            global_idx = start_idx + j + 1
            tx_id = f"TX-SAML-{global_idx:08d}"
            r_score = float(risk_scores[j])
            r_tier = risk_tiers[j]
            is_l = int(is_laund[j])
            
            # Rule violation tag
            violations = []
            if is_structuring[j]: violations.append("STRUCTURING_PROXIMITY_10K")
            if recv_hr[j] or sender_hr[j]: violations.append("HIGH_RISK_JURISDICTION")
            if is_cross[j]: violations.append("CROSS_BORDER_FLOW")
            if is_large[j]: violations.append("LARGE_VALUE_OUTLIER")
            if is_l: violations.append(laund_types[j])
            rule_str = "; ".join(violations) if violations else "STANDARD_BASELINE"
            
            tx_insert_rows.append((
                tx_id,
                dates[j],
                times[j],
                f"{dates[j]} {times[j]}",
                sender_accs[j],
                recv_accs[j],
                float(amounts[j]),
                pay_currs[j],
                recv_currs[j],
                sender_locs[j],
                recv_locs[j],
                pay_types[j],
                is_l,
                laund_types[j],
                r_score,
                r_tier,
                rule_str
            ))
            
            if is_l == 1 or r_score >= 50.0:
                alert_id = f"ALT-{global_idx:08d}"
                sev = "CRITICAL" if (is_l == 1 or r_score >= 75.0) else "HIGH"
                typology = violations[0] if violations else "VELOCITY_ANOMALY"
                alert_insert_rows.append((
                    alert_id,
                    tx_id,
                    sender_accs[j],
                    recv_accs[j],
                    float(amounts[j]),
                    typology,
                    sev,
                    r_score,
                    'NEW',
                    f"Composite Anomaly Score: {r_score}/100. Violations: {rule_str}",
                    float(min(99.0, r_score + 2.0)),
                    'Unassigned',
                    None
                ))
                
        conn.executemany("""
            INSERT INTO transactions (
                tx_id, date, time, timestamp, sender_account, receiver_account,
                amount, payment_currency, received_currency,
                sender_bank_location, receiver_bank_location, payment_type,
                is_laundering, laundering_type, risk_score, risk_tier,
                rule_violations
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tx_insert_rows)
        
        if alert_insert_rows:
            conn.executemany("""
                INSERT INTO alerts (
                    alert_id, tx_id, sender_account, receiver_account,
                    amount, alert_type, severity, risk_score,
                    status, rule_reason, ml_confidence, assigned_to, investigator_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, alert_insert_rows)
            
        conn.commit()
        total_ingested += n_rows
        total_alerts += len(alert_insert_rows)
        print(f"[+] Chunk {i+1} completed in {time.time()-t0:.2f}s (Total Ingested: {total_ingested:,} TXs, {total_alerts:,} Alerts)")
        
    # Re-enable standard safe synchronous mode
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.commit()
    conn.close()
    
    elapsed = time.time() - start_time
    print(f"\n================ FAST BULK INGESTION FINISHED ================")
    print(f"Total Transactions Stored : {total_ingested:,}")
    print(f"Total Compliance Alerts   : {total_alerts:,}")
    print(f"Elapsed Time              : {elapsed:.2f} seconds ({total_ingested/elapsed:,.0f} rows/sec)")
    print("Database File Location    : D:/fintech/AML/database/aml_compliance.db")
    print("==============================================================\n")

if __name__ == '__main__':
    fast_bulk_ingest(target_rows=500000)
