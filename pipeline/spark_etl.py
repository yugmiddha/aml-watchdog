import os
import pandas as pd
import numpy as np

def run_feature_engineering(input_csv_path: str, output_parquet_path: str, max_rows: int = 500000):
    print(f'[*] Extracting AML Big Data features from {input_csv_path} (limit={max_rows})...')
    
    # 1. Load data with Pandas
    df = pd.read_csv(input_csv_path, nrows=max_rows)
    print(f'[+] Loaded {len(df):,} rows. Engineering graph and behavioral features...')
    
    # 2. NumPy-accelerated feature calculations
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
    df['log_amount'] = np.log1p(df['Amount'])
    df['is_cross_border'] = (df['Sender_bank_location'] != df['Receiver_bank_location']).astype(np.int32)
    df['is_structuring_range'] = ((df['Amount'] >= 8500) & (df['Amount'] < 10000)).astype(np.int32)
    
    # 3. Pandas Groupby Account Velocity
    sender_stats = df.groupby('Sender_account')['Amount'].agg(['count', 'sum', 'mean', 'std']).reset_index()
    sender_stats.columns = ['Sender_account', 'sender_tx_count', 'sender_total_vol', 'sender_avg_vol', 'sender_vol_std']
    sender_stats['sender_vol_std'] = sender_stats['sender_vol_std'].fillna(0.0)
    
    receiver_stats = df.groupby('Receiver_account')['Amount'].agg(['count', 'sum', 'mean']).reset_index()
    receiver_stats.columns = ['Receiver_account', 'receiver_tx_count', 'receiver_total_vol', 'receiver_avg_vol']
    
    df = df.merge(sender_stats, on='Sender_account', how='left')
    df = df.merge(receiver_stats, on='Receiver_account', how='left')
    
    # Fill NAs
    df['sender_tx_count'] = df['sender_tx_count'].fillna(1).astype(np.int32)
    df['receiver_tx_count'] = df['receiver_tx_count'].fillna(1).astype(np.int32)
    df['sender_total_vol'] = df['sender_total_vol'].fillna(df['Amount'])
    df['receiver_total_vol'] = df['receiver_total_vol'].fillna(df['Amount'])
    df['sender_avg_vol'] = df['sender_avg_vol'].fillna(df['Amount'])
    df['receiver_avg_vol'] = df['receiver_avg_vol'].fillna(df['Amount'])
    
    # Graph Degree & Flow features
    df['fan_in_out_ratio'] = df['sender_tx_count'] / (df['receiver_tx_count'] + 1.0)
    df['amount_to_avg_ratio'] = df['Amount'] / (df['sender_avg_vol'] + 1e-5)
    
    # Payment Type One-Hot Encoding
    payment_dummies = pd.get_dummies(df['Payment_type'], prefix='pay_type', dtype=np.int32)
    df = pd.concat([df, payment_dummies], axis=1)
    
    os.makedirs(os.path.dirname(output_parquet_path), exist_ok=True)
    df.to_parquet(output_parquet_path, index=False)
    print(f'[+] Feature Engineering Complete! Saved {len(df):,} records to {output_parquet_path}')
    return df

if __name__ == '__main__':
    run_feature_engineering(
        'D:/fintech/AML/data/raw/SAML-D.csv',
        'D:/fintech/AML/data/processed/aml_features.parquet',
        max_rows=300000
    )
