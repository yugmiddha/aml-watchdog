import os
import zipfile
import pandas as pd
import numpy as np
from database.db_manager import init_db, insert_transactions_bulk, insert_alerts_bulk
from models.risk_scorer import scorer

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
RAW_DIR = os.path.join(DATA_DIR, 'raw')
ZIP_PATH = r"D:\env\archive.zip"
CSV_PATH = os.path.join(RAW_DIR, 'SAML-D.csv')

def extract_raw_dataset():
    os.makedirs(RAW_DIR, exist_ok=True)
    if not os.path.exists(CSV_PATH):
        if os.path.exists(ZIP_PATH):
            print(f"[*] Extracting dataset from {ZIP_PATH} to {RAW_DIR}...")
            with zipfile.ZipFile(ZIP_PATH, 'r') as z:
                z.extractall(RAW_DIR)
            print("[+] Extraction complete.")
        else:
            print(f"[!] Warning: Zip file not found at {ZIP_PATH}")
    else:
        print(f"[+] Dataset already available at {CSV_PATH}")

def ingest_initial_batch_to_sqlite(sample_size: int = 25000):
    """
    Ingests a balanced initial slice of the 9.5M transaction dataset into SQLite
    along with rule/ML risk scores and alert generation for immediate dashboard use.
    """
    init_db()
    extract_raw_dataset()
    
    print(f"[*] Reading sample batch of {sample_size:,} records from SAML-D.csv...")
    
    # Read normal and laundering records to ensure rich demo data
    df_sample = pd.read_csv(CSV_PATH, nrows=sample_size)
    
    # Also grab laundering cases specifically to ensure rich alert cases
    df_laundering = []
    for chunk in pd.read_csv(CSV_PATH, chunksize=100000, nrows=1000000):
        launder_rows = chunk[chunk['Is_laundering'] == 1]
        if len(launder_rows) > 0:
            df_laundering.append(launder_rows)
        if len(df_laundering) >= 5:
            break
            
    if df_laundering:
        df_launder_combined = pd.concat(df_laundering).head(1500)
        df_sample = pd.concat([df_sample, df_launder_combined]).drop_duplicates(subset=['Sender_account', 'Receiver_account', 'Amount', 'Date', 'Time'])
        
    print(f"[+] Ingesting {len(df_sample):,} total transactions with AML Risk Scoring into SQLite...")
    
    tx_list = []
    alert_list = []
    
    for idx, row in df_sample.iterrows():
        tx_id = f"TX-{idx:08d}"
        amount = float(row['Amount'])
        is_laundering = int(row['Is_laundering'])
        laundering_type = str(row['Laundering_type']) if pd.notna(row['Laundering_type']) else "Normal"
        sender_loc = str(row['Sender_bank_location'])
        recv_loc = str(row['Receiver_bank_location'])
        pay_type = str(row['Payment_type'])
        
        tx_dict = {
            'tx_id': tx_id,
            'date': str(row['Date']),
            'time': str(row['Time']),
            'timestamp': f"{row['Date']}T{row['Time']}",
            'sender_account': str(row['Sender_account']),
            'receiver_account': str(row['Receiver_account']),
            'amount': amount,
            'payment_currency': str(row['Payment_currency']),
            'received_currency': str(row['Received_currency']),
            'sender_bank_location': sender_loc,
            'receiver_bank_location': recv_loc,
            'payment_type': pay_type,
            'is_laundering': is_laundering,
            'laundering_type': laundering_type
        }
        
        eval_res = scorer.calculate_risk(tx_dict)
        tx_dict['risk_score'] = eval_res['risk_score']
        tx_dict['risk_tier'] = eval_res['risk_tier']
        tx_dict['rule_violations'] = "; ".join(eval_res['rule_violations'])
        
        tx_list.append(tx_dict)
        
        # Trigger alert for high-risk or actual laundering cases
        if eval_res['risk_score'] >= 50.0 or is_laundering == 1:
            alert_id = f"ALT-{idx:06d}"
            alert_list.append({
                'alert_id': alert_id,
                'tx_id': tx_id,
                'sender_account': str(row['Sender_account']),
                'receiver_account': str(row['Receiver_account']),
                'amount': amount,
                'alert_type': laundering_type if is_laundering == 1 else "Heuristic Anomaly",
                'severity': eval_res['risk_tier'],
                'risk_score': eval_res['risk_score'],
                'status': 'NEW' if idx % 3 != 0 else 'UNDER_INVESTIGATION',
                'rule_reason': "; ".join(eval_res['explanation_reasons']),
                'ml_confidence': eval_res['ml_confidence'],
                'assigned_to': 'Senior Analyst' if idx % 3 == 0 else 'Unassigned',
                'investigator_notes': f"Flagged with risk score {eval_res['risk_score']}/100."
            })
            
    insert_transactions_bulk(tx_list)
    insert_alerts_bulk(alert_list)
    print(f"[+] Successfully loaded {len(tx_list):,} transactions and {len(alert_list):,} compliance alerts into SQLite database!")

if __name__ == '__main__':
    ingest_initial_batch_to_sqlite(sample_size=30000)
