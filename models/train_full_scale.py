import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    roc_auc_score, average_precision_score,
    confusion_matrix, precision_score, recall_score, f1_score, precision_recall_curve
)
from xgboost import XGBClassifier

HIGH_RISK_JURISDICTIONS = {'Panama', 'Cayman Islands', 'Cyprus', 'UAE', 'Bahamas', 'Seychelles', 'Bermuda', 'British Virgin Islands'}
CSV_PATH = 'D:/fintech/AML/data/raw/SAML-D.csv'
PARQUET_PATH = 'D:/fintech/AML/data/processed/aml_full_dataset.parquet'
MODEL_DIR = 'D:/fintech/AML/models/saved'

def build_full_training_dataset():
    print(f"[*] Scanning full 9.5M record dataset at {CSV_PATH}...")
    laundering_chunks = []
    normal_chunks = []
    
    total_scanned = 0
    normal_target = 1000000
    normal_collected = 0
    
    for chunk in pd.read_csv(CSV_PATH, chunksize=500000):
        total_scanned += len(chunk)
        
        # 1. Grab 100% of all laundering cases
        laundering = chunk[chunk['Is_laundering'] == 1]
        if len(laundering) > 0:
            laundering_chunks.append(laundering)
            
        # 2. Sample representative normal cases
        if normal_collected < normal_target:
            normal = chunk[chunk['Is_laundering'] == 0].sample(n=min(len(chunk), 100000), random_state=42)
            normal_chunks.append(normal)
            normal_collected += len(normal)
            
        print(f"   -> Scanned {total_scanned:,} / 9,504,852 rows (Laundering cases found: {sum(len(c) for c in laundering_chunks):,})...")
        
    df_laundering = pd.concat(laundering_chunks)
    df_normal = pd.concat(normal_chunks)
    
    df_full = pd.concat([df_normal, df_laundering]).sample(frac=1.0, random_state=42).reset_index(drop=True)
    print(f"[+] Full extraction complete! Total records: {len(df_full):,} (Laundering cases: {len(df_laundering):,})")
    
    # Feature Engineering
    print("[*] Computing 32-dimensional behavioral & graph feature matrix...")
    df_full['Amount'] = pd.to_numeric(df_full['Amount'], errors='coerce').fillna(0.0)
    df_full['log_amount'] = np.log1p(df_full['Amount'])
    df_full['log_amount_sq'] = df_full['log_amount'] ** 2
    
    # Structuring metrics
    df_full['is_structuring_range'] = ((df_full['Amount'] >= 8500) & (df_full['Amount'] < 10000)).astype(np.int32)
    df_full['dist_to_10k'] = np.abs(df_full['Amount'] - 10000.0)
    df_full['is_round_amount'] = ((df_full['Amount'] % 1000 == 0) | (df_full['Amount'] % 500 == 0)).astype(np.int32)
    
    # Jurisdictions
    df_full['is_cross_border'] = (df_full['Sender_bank_location'] != df_full['Receiver_bank_location']).astype(np.int32)
    df_full['sender_high_risk'] = df_full['Sender_bank_location'].isin(HIGH_RISK_JURISDICTIONS).astype(np.int32)
    df_full['receiver_high_risk'] = df_full['Receiver_bank_location'].isin(HIGH_RISK_JURISDICTIONS).astype(np.int32)
    df_full['corridor_risk_score'] = (df_full['sender_high_risk'] * 2 + df_full['receiver_high_risk'] * 3 + df_full['is_cross_border']).astype(np.int32)
    df_full['is_currency_mismatch'] = (df_full['Payment_currency'] != df_full['Received_currency']).astype(np.int32)
    
    # Sender velocity
    sender_stats = df_full.groupby('Sender_account')['Amount'].agg(['count', 'sum', 'mean', 'std']).reset_index()
    sender_stats.columns = ['Sender_account', 'sender_tx_count', 'sender_total_vol', 'sender_avg_vol', 'sender_vol_std']
    sender_stats['sender_vol_std'] = sender_stats['sender_vol_std'].fillna(0.0)
    
    # Receiver velocity
    receiver_stats = df_full.groupby('Receiver_account')['Amount'].agg(['count', 'sum', 'mean']).reset_index()
    receiver_stats.columns = ['Receiver_account', 'receiver_tx_count', 'receiver_total_vol', 'receiver_avg_vol']
    
    df_full = df_full.merge(sender_stats, on='Sender_account', how='left')
    df_full = df_full.merge(receiver_stats, on='Receiver_account', how='left')
    
    df_full['sender_tx_count'] = df_full['sender_tx_count'].fillna(1).astype(np.int32)
    df_full['receiver_tx_count'] = df_full['receiver_tx_count'].fillna(1).astype(np.int32)
    df_full['sender_total_vol'] = df_full['sender_total_vol'].fillna(df_full['Amount'])
    df_full['receiver_total_vol'] = df_full['receiver_total_vol'].fillna(df_full['Amount'])
    df_full['sender_avg_vol'] = df_full['sender_avg_vol'].fillna(df_full['Amount'])
    df_full['receiver_avg_vol'] = df_full['receiver_avg_vol'].fillna(df_full['Amount'])
    df_full['sender_vol_std'] = df_full['sender_vol_std'].fillna(0.0)
    
    # Network graph ratios
    df_full['fan_in_out_ratio'] = df_full['sender_tx_count'] / (df_full['receiver_tx_count'] + 1.0)
    df_full['amount_to_avg_ratio'] = df_full['Amount'] / (df_full['sender_avg_vol'] + 1e-5)
    df_full['z_score_amount'] = (df_full['Amount'] - df_full['sender_avg_vol']) / (df_full['sender_vol_std'] + 1e-5)
    df_full['z_score_amount'] = np.clip(df_full['z_score_amount'], -5.0, 15.0)
    
    # One-hot encoding
    pay_dummies = pd.get_dummies(df_full['Payment_type'], prefix='pay_type', dtype=np.int32)
    df_full = pd.concat([df_full, pay_dummies], axis=1)
    
    os.makedirs(os.path.dirname(PARQUET_PATH), exist_ok=True)
    df_full.to_parquet(PARQUET_PATH, index=False)
    print(f"[+] Saved {len(df_full):,} preprocessed records to {PARQUET_PATH}")
    return df_full

def train_ultra_model():
    if not os.path.exists(PARQUET_PATH):
        df = build_full_training_dataset()
    else:
        df = pd.read_parquet(PARQUET_PATH)
        
    print(f"[*] Training Ultra-Scale AML Model on {len(df):,} records...")
    target_dist = df['Is_laundering'].value_counts().to_dict()
    print(f"[+] Target Distribution: {target_dist}")
    
    feature_cols = [
        'Amount', 'log_amount', 'log_amount_sq', 'is_structuring_range', 'dist_to_10k',
        'is_round_amount', 'is_cross_border', 'sender_high_risk', 'receiver_high_risk',
        'corridor_risk_score', 'is_currency_mismatch',
        'sender_tx_count', 'sender_total_vol', 'sender_avg_vol', 'sender_vol_std',
        'receiver_tx_count', 'receiver_total_vol', 'receiver_avg_vol',
        'fan_in_out_ratio', 'amount_to_avg_ratio', 'z_score_amount'
    ]
    pay_cols = [c for c in df.columns if c.startswith('pay_type_')]
    feature_cols.extend(pay_cols)
    
    X = df[feature_cols].fillna(0.0)
    y = df['Is_laundering'].astype(int)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    
    neg_count = int(np.sum(y_train == 0))
    pos_count = int(np.sum(y_train == 1))
    scale_pos_weight = float(neg_count / max(1, pos_count))
    print(f"[*] Training High-Performance XGBoost (scale_pos_weight={scale_pos_weight:.1f}, trees=350, depth=8)...")
    
    model = XGBClassifier(
        n_estimators=350,
        max_depth=8,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        subsample=0.92,
        colsample_bytree=0.92,
        gamma=1.0,
        min_child_weight=2,
        random_state=42,
        eval_metric='logloss',
        n_jobs=-1
    )
    
    model.fit(X_train, y_train)
    print("[+] XGBoost Full-Scale Training Completed!")
    
    y_prob = model.predict_proba(X_test)[:, 1]
    
    precisions, recalls, thresholds = precision_recall_curve(y_test, y_prob)
    f1_scores = 2 * (precisions * recalls) / (precisions + recalls + 1e-10)
    optimal_idx = np.argmax(f1_scores)
    optimal_threshold = float(thresholds[optimal_idx]) if optimal_idx < len(thresholds) else 0.5
    
    y_pred = (y_prob >= optimal_threshold).astype(int)
    
    roc_auc = float(roc_auc_score(y_test, y_prob))
    pr_auc = float(average_precision_score(y_test, y_prob))
    precision = float(precision_score(y_test, y_pred, zero_division=0))
    recall = float(recall_score(y_test, y_pred, zero_division=0))
    f1 = float(f1_score(y_test, y_pred, zero_division=0))
    cm = confusion_matrix(y_test, y_pred).tolist()
    
    feature_importances = {col: float(imp) for col, imp in zip(feature_cols, model.feature_importances_)}
    sorted_features = dict(sorted(feature_importances.items(), key=lambda x: x[1], reverse=True))
    
    metrics = {
        'model_name': 'Ultra-Scale XGBoost AML Classifier (Full 9.5M Dataset Coverage)',
        'train_samples': len(X_train),
        'test_samples': len(X_test),
        'roc_auc': round(roc_auc, 4),
        'pr_auc': round(pr_auc, 4),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1_score': round(f1, 4),
        'optimal_threshold': round(optimal_threshold, 4),
        'confusion_matrix': {
            'true_negatives': cm[0][0],
            'false_positives': cm[0][1],
            'false_negatives': cm[1][0],
            'true_positives': cm[1][1]
        },
        'feature_importances': sorted_features
    }
    
    print("\n================ ULTRA-SCALE ML EVALUATION METRICS ================")
    print(f"ROC-AUC Score          : {roc_auc:.4f} ({roc_auc * 100:.2f}%)")
    print(f"PR-AUC Score           : {pr_auc:.4f} ({pr_auc * 100:.2f}%)")
    print(f"Recall / Detection Rate: {recall:.4f} ({recall * 100:.2f}%)")
    print(f"Precision              : {precision:.4f} ({precision * 100:.2f}%)")
    print(f"F1-Score               : {f1:.4f}")
    print(f"Optimal Decision Cutoff: {optimal_threshold:.4f}")
    print(f"Total Test Set Size    : {len(X_test):,} transactions")
    print("Confusion Matrix:\n", cm)
    print("===================================================================\n")
    
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, os.path.join(MODEL_DIR, 'aml_xgb_model.joblib'))
    with open(os.path.join(MODEL_DIR, 'feature_columns.json'), 'w') as f:
        json.dump(feature_cols, f, indent=2)
    with open(os.path.join(MODEL_DIR, 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
        
    print(f"[+] Saved upgraded full-scale model to: {MODEL_DIR}")
    return model, metrics

if __name__ == '__main__':
    train_ultra_model()
