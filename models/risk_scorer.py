import json
from typing import Dict, Any
from models.rules_engine import AMLRulesEngine
from models.ml_detector import detector

class AMLRiskScorer:
    @staticmethod
    def calculate_risk(tx: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        rule_eval = AMLRulesEngine.evaluate_transaction(tx)
        rule_score = rule_eval['rule_risk_score']
        rule_violations = rule_eval['rule_violations']
        
        ml_eval = detector.predict(tx, context)
        ml_score = ml_eval['ml_probability'] * 100.0
        
        if rule_score >= 80:
            final_risk = 0.50 * rule_score + 0.50 * ml_score
        else:
            final_risk = 0.35 * rule_score + 0.65 * ml_score
            
        final_risk = min(100.0, max(0.0, final_risk))
        
        if final_risk >= 75.0:
            tier = 'CRITICAL'
        elif final_risk >= 50.0:
            tier = 'HIGH'
        elif final_risk >= 25.0:
            tier = 'MEDIUM'
        else:
            tier = 'LOW'
            
        requires_sar = final_risk >= 65.0 or len(rule_violations) >= 2 or tx.get('is_laundering') == 1
        
        reasons = []
        if rule_violations:
            reasons.extend(rule_violations)
        if ml_eval['ml_probability'] >= 0.5:
            conf_val = ml_eval['confidence']
            reasons.append(f"ML Model anomaly detection triggered (Confidence: {conf_val}%) based on account velocity & topology features")
        if not reasons:
            reasons.append("Standard behavioral baseline verified")
            
        return {
            'risk_score': round(final_risk, 1),
            'risk_tier': tier,
            'rule_score': round(rule_score, 1),
            'ml_score': round(ml_score, 1),
            'ml_confidence': ml_eval['confidence'],
            'requires_sar': requires_sar,
            'rule_violations': rule_violations,
            'explanation_reasons': reasons
        }

scorer = AMLRiskScorer()
