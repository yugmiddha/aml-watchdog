import os
import sys
import sqlite3
import pandas as pd
import numpy as np

sys.path.append('D:/fintech/AML')
from database.db_manager import get_connection, init_db
from models.risk_scorer import scorer

CSV_PATH = 'D:/fintech/AML/data/raw/SAML-D.csv'

def ingest_large_dataset(target_rows: int = 150000):
    print(f"[*] Scaling database storage to {target_rows:,} real transactions from {CSV_PATH}...")
    
    init_db()
    
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA cache_size = 100000;")
        
        # Clear existing data
        conn.execute("DELETE FROM alerts;")
        conn.execute("DELETE FROM transactions;")
        conn.execute("DELETE FROM accounts;")
        conn.commit()
    
    total_ingested = 0
    total_alerts = 0
    
    chunks = pd.read_csv(CSV_PATH, chunksize=50000, nrows=target_rows)
    
    for i, chunk in enumerate(chunks):
        print(f"[*] Processing Batch {i+1} ({len(chunk):,} records)...")
        
        # 1. Collect and aggregate accounts
        accounts_to_upsert = []
        senders = chunk[['Sender_account', 'Sender_bank_location']].drop_duplicates()
        for _, row in senders.iterrows():
            accounts_to_upsert.append((
                str(row['Sender_account']),
                str(row['Sender_bank_location']),
                float(np.random.uniform(5.0, 45.0)),
                0,
                0.0,
                0.0,
                'ACTIVE'
            ))
            
        with get_connection() as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO accounts 
                (account_id, bank_location, risk_rating, flagged_tx_count, total_inflow, total_outflow, account_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, accounts_to_upsert)
            conn.commit()
            
        # 2. Build transactions and compliance alerts
        tx_rows = []
        alert_rows = []
        
        for idx, row in chunk.iterrows():
            tx_id = f"TX-SAML-{idx+1:08d}"
            amt = float(row['Amount']) if pd.notnull(row['Amount']) else 0.0
            is_laundering = int(row['Is_laundering']) if pd.notnull(row['Is_laundering']) else 0
            laundering_type = str(row['Laundering_type']) if pd.notnull(row['Laundering_type']) else 'NORMAL'
            
            sender_acc = str(row['Sender_account'])
            receiver_acc = str(row['Receiver_account'])
            sender_loc = str(row['Sender_bank_location'])
            receiver_loc = str(row['Receiver_bank_location'])
            pay_type = str(row['Payment_type'])
            
            tx_dict = {
                'amount': amt,
                'sender_account': sender_acc,
                'receiver_account': receiver_acc,
                'payment_type': pay_type,
                'sender_bank_location': sender_loc,
                'receiver_bank_location': receiver_loc
            }
            
            risk_eval = scorer.calculate_risk(tx_dict)
            risk_score = risk_eval['risk_score']
            risk_tier = risk_eval['risk_tier']
            rule_flags = "; ".join(risk_eval['rule_violations'])
            ml_conf = float(risk_eval['ml_confidence'])
            
            date_str = str(row['Date'])
            time_str = str(row['Time'])
            timestamp_str = f"{date_str} {time_str}"
            
            tx_rows.append((
                tx_id,
                date_str,
                time_str,
                timestamp_str,
                sender_acc,
                receiver_acc,
                amt,
                str(row['Payment_currency']),
                str(row['Received_currency']),
                sender_loc,
                receiver_loc,
                pay_type,
                is_laundering,
                laundering_type,
                risk_score,
                risk_tier,
                rule_flags
            ))
            
            if is_laundering == 1 or risk_score >= 50.0:
                alert_id = f"ALT-{idx+1:08d}"
                sev = "CRITICAL" if (is_laundering == 1 or risk_score >= 75.0) else "HIGH"
                primary_typology = risk_eval['rule_violations'][0] if risk_eval['rule_violations'] else (laundering_type if laundering_type != 'NORMAL' else 'ANOMALOUS_VELOCITY')
                reasons = " | ".join(risk_eval['explanation_reasons'])
                
                alert_rows.append((
                    alert_id,
                    tx_id,
                    sender_acc,
                    receiver_acc,
                    amt,
                    primary_typology,
                    sev,
                    risk_score,
                    'NEW',
                    reasons,
                    ml_conf,
                    'Unassigned',
                    None
                ))
                
        with get_connection() as conn:
            conn.executemany("""
                INSERT INTO transactions (
                    tx_id, date, time, timestamp, sender_account, receiver_account,
                    amount, payment_currency, received_currency,
                    sender_bank_location, receiver_bank_location, payment_type,
                    is_laundering, laundering_type, risk_score, risk_tier,
                    rule_violations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tx_rows)
            
            if alert_rows:
                conn.executemany("""
                    INSERT INTO alerts (
                        alert_id, tx_id, sender_account, receiver_account,
                        amount, alert_type, severity, risk_score,
                        status, rule_reason, ml_confidence, assigned_to, investigator_notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, alert_rows)
                
            conn.commit()
            
        total_ingested += len(tx_rows)
        total_alerts += len(alert_rows)
        print(f"[+] Batch {i+1} committed: {total_ingested:,} transactions, {total_alerts:,} compliance alerts.")
        
    print(f"\n================ SCALE INGESTION COMPLETED ================")
    print(f"Total Transactions Stored : {total_ingested:,}")
    print(f"Total Compliance Alerts   : {total_alerts:,}")
    print("Database Location         : D:/fintech/AML/database/aml_compliance.db")
    print("===========================================================\n")

if __name__ == '__main__':
    ingest_large_dataset(target_rows=150000)
