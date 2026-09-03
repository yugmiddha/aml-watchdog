import os
import json
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, List

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'saved')
MODEL_PATH = os.path.join(MODEL_DIR, 'aml_xgb_model.joblib')
FEATURE_COLS_PATH = os.path.join(MODEL_DIR, 'feature_columns.json')
HIGH_RISK_JURISDICTIONS = {'Panama', 'Cayman Islands', 'Cyprus', 'UAE', 'Bahamas', 'Seychelles', 'Bermuda', 'British Virgin Islands'}

class AMLModelDetector:
    def __init__(self):
        self.model = None
        self.feature_cols = []
        self.load_model()
        
    def load_model(self):
        if os.path.exists(MODEL_PATH) and os.path.exists(FEATURE_COLS_PATH):
            try:
                self.model = joblib.load(MODEL_PATH)
                with open(FEATURE_COLS_PATH, 'r') as f:
                    self.feature_cols = json.load(f)
                print(f"[+] Loaded AML XGBoost Model ({len(self.feature_cols)} features).")
            except Exception as e:
                print(f"[!] Warning loading model: {e}")
                self.model = None
                
    def extract_features(self, tx: Dict[str, Any], context: Dict[str, Any] = None) -> pd.DataFrame:
        amount = float(tx.get('amount', 0.0))
        sender_loc = str(tx.get('sender_bank_location', 'US'))
        recv_loc = str(tx.get('receiver_bank_location', 'US'))
        pay_type = str(tx.get('payment_type', 'Wire Transfer'))
        pay_curr = str(tx.get('payment_currency', 'USD'))
        recv_curr = str(tx.get('received_currency', 'USD'))
        
        ctx = context or {}
        sender_tx_count = float(ctx.get('sender_tx_count', 1.0))
        sender_total_vol = float(ctx.get('sender_total_vol', amount))
        sender_avg_vol = float(ctx.get('sender_avg_vol', amount))
        sender_vol_std = float(ctx.get('sender_vol_std', 0.0))
        receiver_tx_count = float(ctx.get('receiver_tx_count', 1.0))
        receiver_total_vol = float(ctx.get('receiver_total_vol', amount))
        receiver_avg_vol = float(ctx.get('receiver_avg_vol', amount))
        
        log_amt = float(np.log1p(amount))
        sender_hr = 1 if sender_loc in HIGH_RISK_JURISDICTIONS else 0
        recv_hr = 1 if recv_loc in HIGH_RISK_JURISDICTIONS else 0
        is_cross = 1 if sender_loc != recv_loc else 0
        
        z_amt = (amount - sender_avg_vol) / (sender_vol_std + 1e-5) if sender_vol_std > 0 else 0.0
        z_amt = float(np.clip(z_amt, -5.0, 15.0))
        
        feat_dict = {
            'Amount': amount,
            'log_amount': log_amt,
            'log_amount_sq': log_amt ** 2,
            'is_structuring_range': 1 if (8500 <= amount < 10000) else 0,
            'dist_to_10k': abs(amount - 10000.0),
            'is_round_amount': 1 if (amount % 1000 == 0 or amount % 500 == 0) else 0,
            'is_cross_border': is_cross,
            'sender_high_risk': sender_hr,
            'receiver_high_risk': recv_hr,
            'corridor_risk_score': sender_hr * 2 + recv_hr * 3 + is_cross,
            'is_currency_mismatch': 1 if pay_curr != recv_curr else 0,
            'sender_tx_count': sender_tx_count,
            'sender_total_vol': sender_total_vol,
            'sender_avg_vol': sender_avg_vol,
            'sender_vol_std': sender_vol_std,
            'receiver_tx_count': receiver_tx_count,
            'receiver_total_vol': receiver_total_vol,
            'receiver_avg_vol': receiver_avg_vol,
            'fan_in_out_ratio': sender_tx_count / (receiver_tx_count + 1.0),
            'amount_to_avg_ratio': amount / (sender_avg_vol + 1e-5),
            'z_score_amount': z_amt
        }
        
        for col in self.feature_cols:
            if col.startswith('pay_type_'):
                expected_type = col.replace('pay_type_', '')
                feat_dict[col] = 1 if pay_type.lower() == expected_type.lower() else 0
                
        df_feat = pd.DataFrame([feat_dict])
        for col in self.feature_cols:
            if col not in df_feat.columns:
                df_feat[col] = 0.0
                
        return df_feat[self.feature_cols]

    def predict(self, tx: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        if self.model is None:
            self.load_model()
            
        if self.model is None:
            amt = float(tx.get('amount', 0.0))
            is_struct = 1.0 if 8500 <= amt < 10000 else 0.0
            is_cross = 1.0 if tx.get('sender_bank_location') != tx.get('receiver_bank_location') else 0.0
            prob = min(0.98, (is_struct * 0.75) + (is_cross * 0.20) + (0.15 if amt > 50000 else 0.02))
            return {'ml_probability': round(prob, 4), 'ml_predicted_class': int(prob >= 0.5), 'confidence': round(prob * 100, 2)}
            
        X = self.extract_features(tx, context)
        prob = float(self.model.predict_proba(X)[0, 1])
        pred_class = int(prob >= 0.5)
        
        return {
            'ml_probability': round(prob, 4),
            'ml_predicted_class': pred_class,
            'confidence': round(prob * 100, 2)
        }

detector = AMLModelDetector()
