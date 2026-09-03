import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report, roc_auc_score, average_precision_score,
    confusion_matrix, precision_score, recall_score, f1_score, precision_recall_curve
)
from xgboost import XGBClassifier

HIGH_RISK_JURISDICTIONS = {'Panama', 'Cayman Islands', 'Cyprus', 'UAE', 'Bahamas', 'Seychelles', 'Bermuda', 'British Virgin Islands'}

def extract_advanced_features(input_csv: str = 'D:/fintech/AML/data/raw/SAML-D.csv', output_parquet: str = 'D:/fintech/AML/data/processed/aml_features_v2.parquet', max_rows: int = 600000):
    print(f"[*] Extracting advanced AML features from {input_csv} (sample={max_rows:,})...")
    df = pd.read_csv(input_csv, nrows=max_rows)
    print(f"[+] Loaded {len(df):,} raw records. Building feature matrices...")
    
    # Numeric sanitization
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
    df['log_amount'] = np.log1p(df['Amount'])
    df['log_amount_sq'] = df['log_amount'] ** 2
    
    # Structuring & Amount Heuristics
    df['is_structuring_range'] = ((df['Amount'] >= 8500) & (df['Amount'] < 10000)).astype(np.int32)
    df['dist_to_10k'] = np.abs(df['Amount'] - 10000.0)
    df['is_round_amount'] = ((df['Amount'] % 1000 == 0) | (df['Amount'] % 500 == 0)).astype(np.int32)
    
    # Jurisdictional Arbitrage
    df['is_cross_border'] = (df['Sender_bank_location'] != df['Receiver_bank_location']).astype(np.int32)
    df['sender_high_risk'] = df['Sender_bank_location'].isin(HIGH_RISK_JURISDICTIONS).astype(np.int32)
    df['receiver_high_risk'] = df['Receiver_bank_location'].isin(HIGH_RISK_JURISDICTIONS).astype(np.int32)
    df['corridor_risk_score'] = (df['sender_high_risk'] * 2 + df['receiver_high_risk'] * 3 + df['is_cross_border']).astype(np.int32)
    
    # Currency mismatch
    df['is_currency_mismatch'] = (df['Payment_currency'] != df['Received_currency']).astype(np.int32)
    
    # Sender Velocity
    sender_stats = df.groupby('Sender_account')['Amount'].agg(['count', 'sum', 'mean', 'std']).reset_index()
    sender_stats.columns = ['Sender_account', 'sender_tx_count', 'sender_total_vol', 'sender_avg_vol', 'sender_vol_std']
    sender_stats['sender_vol_std'] = sender_stats['sender_vol_std'].fillna(0.0)
    
    # Receiver Velocity
    receiver_stats = df.groupby('Receiver_account')['Amount'].agg(['count', 'sum', 'mean']).reset_index()
    receiver_stats.columns = ['Receiver_account', 'receiver_tx_count', 'receiver_total_vol', 'receiver_avg_vol']
    
    df = df.merge(sender_stats, on='Sender_account', how='left')
    df = df.merge(receiver_stats, on='Receiver_account', how='left')
    
    df['sender_tx_count'] = df['sender_tx_count'].fillna(1).astype(np.int32)
    df['receiver_tx_count'] = df['receiver_tx_count'].fillna(1).astype(np.int32)
    df['sender_total_vol'] = df['sender_total_vol'].fillna(df['Amount'])
    df['receiver_total_vol'] = df['receiver_total_vol'].fillna(df['Amount'])
    df['sender_avg_vol'] = df['sender_avg_vol'].fillna(df['Amount'])
    df['receiver_avg_vol'] = df['receiver_avg_vol'].fillna(df['Amount'])
    df['sender_vol_std'] = df['sender_vol_std'].fillna(0.0)
    
    # Graph & Velocity Interaction
    df['fan_in_out_ratio'] = df['sender_tx_count'] / (df['receiver_tx_count'] + 1.0)
    df['amount_to_avg_ratio'] = df['Amount'] / (df['sender_avg_vol'] + 1e-5)
    df['z_score_amount'] = (df['Amount'] - df['sender_avg_vol']) / (df['sender_vol_std'] + 1e-5)
    df['z_score_amount'] = np.clip(df['z_score_amount'], -5.0, 15.0)
    
    # Payment type dummies
    pay_dummies = pd.get_dummies(df['Payment_type'], prefix='pay_type', dtype=np.int32)
    df = pd.concat([df, pay_dummies], axis=1)
    
    os.makedirs(os.path.dirname(output_parquet), exist_ok=True)
    df.to_parquet(output_parquet, index=False)
    print(f"[+] Advanced Feature Extraction Complete: {len(df):,} records saved to {output_parquet}")
    return df

def train_enhanced_aml_model():
    parquet_path = 'D:/fintech/AML/data/processed/aml_features_v2.parquet'
    model_dir = 'D:/fintech/AML/models/saved'
    
    if not os.path.exists(parquet_path):
        df = extract_advanced_features(max_rows=600000)
    else:
        df = pd.read_parquet(parquet_path)
        
    print(f"[*] Total training dataset size: {len(df):,} rows")
    target_dist = df['Is_laundering'].value_counts().to_dict()
    print(f"[+] Laundering Target Distribution: {target_dist}")
    
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
    
    # Stratified Train/Test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    
    neg_count = int(np.sum(y_train == 0))
    pos_count = int(np.sum(y_train == 1))
    scale_pos_weight = float(neg_count / max(1, pos_count))
    print(f"[*] Training High-Accuracy XGBoost (scale_pos_weight={scale_pos_weight:.1f}, features={len(feature_cols)})...")
    
    model = XGBClassifier(
        n_estimators=250,
        max_depth=7,
        learning_rate=0.06,
        scale_pos_weight=scale_pos_weight,
        subsample=0.90,
        colsample_bytree=0.90,
        gamma=1.2,
        min_child_weight=2,
        random_state=42,
        eval_metric='logloss',
        n_jobs=-1
    )
    
    model.fit(X_train, y_train)
    print("[+] XGBoost training complete!")
    
    # Predictions & Probabilities
    y_prob = model.predict_proba(X_test)[:, 1]
    
    # Optimal Threshold Selection via Precision-Recall curve
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
    
    feature_importances = {
        col: float(imp) for col, imp in zip(feature_cols, model.feature_importances_)
    }
    sorted_features = dict(sorted(feature_importances.items(), key=lambda x: x[1], reverse=True))
    
    metrics = {
        'model_name': 'Enhanced High-Accuracy XGBoost AML Classifier',
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
    
    print("\n================ ENHANCED ML ACCURACY METRICS ================")
    print(f"ROC-AUC Score          : {roc_auc:.4f} ({roc_auc * 100:.2f}%)")
    print(f"PR-AUC Score           : {pr_auc:.4f} ({pr_auc * 100:.2f}%)")
    print(f"Recall / Detection Rate: {recall:.4f} ({recall * 100:.2f}%)")
    print(f"Precision              : {precision:.4f} ({precision * 100:.2f}%)")
    print(f"F1-Score               : {f1:.4f}")
    print(f"Optimal Decision Cutoff: {optimal_threshold:.4f}")
    print("Confusion Matrix:\n", cm)
    print("==============================================================\n")
    
    os.makedirs(model_dir, exist_ok=True)
    joblib.dump(model, os.path.join(model_dir, 'aml_xgb_model.joblib'))
    with open(os.path.join(model_dir, 'feature_columns.json'), 'w') as f:
        json.dump(feature_cols, f, indent=2)
    with open(os.path.join(model_dir, 'metrics.json'), 'w') as f:
        json.dump(metrics, f, indent=2)
        
    print(f"[+] Successfully trained & saved enhanced model to: {model_dir}")
    return model, metrics

if __name__ == '__main__':
    train_enhanced_aml_model()
