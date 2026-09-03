import math
from typing import Dict, Any, List, Tuple

HIGH_RISK_JURISDICTIONS = {'Panama', 'Cayman Islands', 'Cyprus', 'UAE', 'Bahamas', 'Seychelles', 'Bermuda', 'British Virgin Islands'}

class AMLRulesEngine:
    @staticmethod
    def check_structuring_smurfing(amount: float, payment_type: str) -> Tuple[bool, float, str]:
        if 8500 <= amount < 10000:
            confidence = 0.85 if 'cash' in payment_type.lower() or 'deposit' in payment_type.lower() else 0.70
            return True, confidence, f'Potential Structuring/Smurfing: Amount  is just below ,000 reporting threshold via {payment_type}'
        return False, 0.0, ''

    @staticmethod
    def check_cross_border_risk(sender_loc: str, receiver_loc: str, amount: float) -> Tuple[bool, float, str]:
        is_sender_hr = sender_loc in HIGH_RISK_JURISDICTIONS
        is_receiver_hr = receiver_loc in HIGH_RISK_JURISDICTIONS
        
        if is_sender_hr or is_receiver_hr:
            risk_loc = receiver_loc if is_receiver_hr else sender_loc
            conf = 0.80 if amount > 15000 else 0.60
            return True, conf, f'High-Risk Jurisdiction detected ({risk_loc}) on  transfer'
        
        if sender_loc != receiver_loc and amount > 25000:
            return True, 0.50, f'Substantial cross-border transfer from {sender_loc} to {receiver_loc} ()'
            
        return False, 0.0, ''

    @staticmethod
    def check_high_value_outlier(amount: float, payment_type: str) -> Tuple[bool, float, str]:
        if amount >= 50000:
            conf = 0.90 if amount >= 100000 else 0.75
            return True, conf, f'High-Value Anomaly: Single transaction of  exceeds standard risk threshold'
        return False, 0.0, ''

    @classmethod
    def evaluate_transaction(cls, tx: Dict[str, Any]) -> Dict[str, Any]:
        amount = float(tx.get('amount', 0.0))
        payment_type = str(tx.get('payment_type', ''))
        sender_loc = str(tx.get('sender_bank_location', ''))
        receiver_loc = str(tx.get('receiver_bank_location', ''))
        
        violations = []
        rule_scores = []
        
        r1, s1, msg1 = cls.check_structuring_smurfing(amount, payment_type)
        if r1:
            violations.append(msg1)
            rule_scores.append(s1)
            
        r2, s2, msg2 = cls.check_cross_border_risk(sender_loc, receiver_loc, amount)
        if r2:
            violations.append(msg2)
            rule_scores.append(s2)
            
        r3, s3, msg3 = cls.check_high_value_outlier(amount, payment_type)
        if r3:
            violations.append(msg3)
            rule_scores.append(s3)
                
        rule_risk = (max(rule_scores) * 100.0) if rule_scores else 0.0
        
        return {
            'rule_risk_score': round(rule_risk, 2),
            'violated_rules_count': len(violations),
            'rule_violations': violations,
            'is_rule_flagged': len(violations) > 0
        }
