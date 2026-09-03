import os
import sys
import time
import sqlite3
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database.db_manager import get_connection, init_db
from models.risk_scorer import scorer
from models.ml_detector import detector

app = FastAPI(title="AML Watchdog Enterprise API", version="2.5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    try:
        os.makedirs(static_dir, exist_ok=True)
    except Exception:
        pass

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Fast In-Memory Stats Cache
_STATS_CACHE = {"data": None, "last_updated": 0}

def compute_stats():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions;")
        tot_tx, tot_vol = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions WHERE risk_score >= 50.0 OR is_laundering = 1;")
        flag_tx, flag_vol = cursor.fetchone()
        
        cursor.execute("SELECT status, COUNT(*) FROM alerts GROUP BY status;")
        alert_status = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute("SELECT alert_type, COUNT(*) FROM alerts GROUP BY alert_type ORDER BY COUNT(*) DESC LIMIT 8;")
        typology_breakdown = [{'type': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        cursor.execute("SELECT risk_tier, COUNT(*) FROM transactions GROUP BY risk_tier;")
        tier_dist = {row[0]: row[1] for row in cursor.fetchall()}
        
    return {
        "total_transactions": tot_tx,
        "total_volume": round(tot_vol, 2),
        "flagged_transactions": flag_tx,
        "flagged_volume": round(flag_vol, 2),
        "alerts_by_status": alert_status,
        "laundering_breakdown": typology_breakdown,
        "tier_distribution": tier_dist
    }

@app.on_event("startup")
def startup_event():
    init_db()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM transactions;")
            count = cursor.fetchone()[0]
            if count == 0:
                print("[*] Initializing compliance dataset for deployment...")
                from pipeline.transaction_generator import generate_scaled_transactions
                from database.db_manager import insert_transactions_bulk, insert_alerts_bulk
                df = generate_scaled_transactions(total_records=3000, laundering_ratio=0.18)
                txs = df.to_dict(orient="records")
                alerts_to_insert = []
                for t in txs:
                    res = scorer.calculate_risk(t)
                    t['risk_score'] = res['risk_score']
                    t['risk_tier'] = res['risk_tier']
                    t['rule_violations'] = ', '.join(res.get('rule_violations', []))
                    if res.get('is_alert') or res.get('risk_score', 0) >= 50.0:
                        alerts_to_insert.append({
                            'alert_id': f"ALT-{t['tx_id'][-6:]}",
                            'tx_id': t['tx_id'],
                            'sender_account': t['sender_account'],
                            'receiver_account': t['receiver_account'],
                            'amount': t['amount'],
                            'alert_type': res.get('typology', 'Structuring'),
                            'severity': res['risk_tier'],
                            'risk_score': res['risk_score'],
                            'status': 'UNASSIGNED',
                            'rule_reason': t['rule_violations'] or 'High risk score',
                            'ml_confidence': res.get('ml_score', 0.88),
                            'assigned_to': 'Compliance Pool',
                            'investigator_notes': ''
                        })
                insert_transactions_bulk(txs)
                insert_alerts_bulk(alerts_to_insert)
                cursor.execute("""
                    INSERT OR IGNORE INTO accounts (account_id, bank_location, risk_rating, flagged_tx_count, total_inflow, total_outflow, account_status)
                    SELECT sender_account, sender_bank_location, MAX(risk_score), COUNT(*), 0, SUM(amount), 'ACTIVE'
                    FROM transactions GROUP BY sender_account;
                """)
                conn.commit()
                print("[+] Initial compliance records seeded successfully!")
    except Exception as e:
        print(f"[!] Startup seeding note: {e}")

    global _STATS_CACHE
    _STATS_CACHE["data"] = compute_stats()
    _STATS_CACHE["last_updated"] = time.time()

@app.get("/favicon.ico")
def favicon():
    svg_icon = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#06b6d4">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>'''
    return Response(content=svg_icon, media_type="image/svg+xml")

@app.get("/")
def read_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/html")
    return {"message": "AML Surveillance System Running."}

@app.get("/api/stats")
def get_stats(force: bool = False):
    global _STATS_CACHE
    now = time.time()
    if force or not _STATS_CACHE["data"] or (now - _STATS_CACHE["last_updated"]) > 60:
        _STATS_CACHE["data"] = compute_stats()
        _STATS_CACHE["last_updated"] = now
    return _STATS_CACHE["data"]

@app.get("/api/alerts")
def get_alerts(severity: Optional[str] = None, status: Optional[str] = None, limit: int = 50):
    query = "SELECT alert_id, tx_id, sender_account, receiver_account, amount, alert_type, severity, risk_score, status, rule_reason, assigned_to FROM alerts WHERE 1=1"
    params = []
    if severity and severity != 'ALL':
        query += " AND severity = ?"
        params.append(severity)
    if status and status != 'ALL':
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY rowid DESC LIMIT ?"
    params.append(limit)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        alerts = [dict(row) for row in rows]
    return {"alerts": alerts, "count": len(alerts)}

class TriageRequest(BaseModel):
    status: str
    assigned_to: Optional[str] = "AML Analyst"
    investigator_notes: Optional[str] = ""

@app.post("/api/alerts/{alert_id}/triage")
def triage_alert(alert_id: str, req: TriageRequest):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE alerts
            SET status = ?, assigned_to = ?, investigator_notes = ?
            WHERE alert_id = ?
        """, (req.status, req.assigned_to, req.investigator_notes, alert_id))
        conn.commit()
    return {"status": "success", "alert_id": alert_id, "new_status": req.status}

@app.get("/api/transactions")
def get_transactions(search: Optional[str] = None, risk_tier: Optional[str] = None, limit: int = 50):
    query = "SELECT tx_id, date, time, timestamp, sender_account, receiver_account, amount, payment_currency, received_currency, sender_bank_location, receiver_bank_location, payment_type, is_laundering, laundering_type, risk_score, risk_tier FROM transactions WHERE 1=1"
    params = []
    if search:
        query += " AND (sender_account LIKE ? OR receiver_account LIKE ? OR tx_id LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    if risk_tier and risk_tier != 'ALL':
        query += " AND risk_tier = ?"
        params.append(risk_tier)
    query += " ORDER BY rowid DESC LIMIT ?"
    params.append(limit)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        txs = [dict(row) for row in cursor.fetchall()]
    return {"transactions": txs, "count": len(txs)}

@app.get("/api/network-graph/{account_id}")
def get_network_graph(account_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sender_account, receiver_account, amount, risk_score, payment_type
            FROM transactions
            WHERE sender_account = ? OR receiver_account = ?
            LIMIT 60
        """, (account_id, account_id))
        rows = cursor.fetchall()
        
    nodes = {account_id: {"id": account_id, "label": f"ACC ...{account_id[-4:]}", "color": "#ef4444", "size": 26}}
    edges = []
    
    for r in rows:
        s, rec, amt, score, ptype = r["sender_account"], r["receiver_account"], r["amount"], r["risk_score"], r["payment_type"]
        if s not in nodes:
            nodes[s] = {"id": s, "label": f"ACC ...{s[-4:]}", "color": "#3b82f6", "size": 18}
        if rec not in nodes:
            nodes[rec] = {"id": rec, "label": f"ACC ...{rec[-4:]}", "color": "#10b981" if score < 50 else "#f59e0b", "size": 18}
            
        edges.append({
            "from": s,
            "to": rec,
            "label": f"${amt:,.0f}",
            "color": "#ef4444" if score >= 75 else ("#f59e0b" if score >= 50 else "#64748b")
        })
        
    return {"nodes": list(nodes.values()), "edges": edges}

@app.get("/api/account/{account_id}/profile")
def get_account_profile(account_id: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN receiver_account = ? THEN amount ELSE 0 END), 0) as total_inflow,
                COALESCE(SUM(CASE WHEN sender_account = ? THEN amount ELSE 0 END), 0) as total_outflow,
                COUNT(*) as total_tx_count,
                MAX(risk_score) as max_risk
            FROM transactions
            WHERE sender_account = ? OR receiver_account = ?
        """, (account_id, account_id, account_id, account_id))
        inflow, outflow, count, max_risk = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE sender_account = ? OR receiver_account = ?", (account_id, account_id))
        alert_cnt = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT tx_id, date, time, sender_account, receiver_account, amount, payment_type, risk_score
            FROM transactions
            WHERE sender_account = ? OR receiver_account = ?
            ORDER BY rowid DESC LIMIT 15
        """, (account_id, account_id))
        recent = [dict(row) for row in cursor.fetchall()]
        
    risk_val = round(max_risk or 0.0, 1)
    tier = 'CRITICAL' if risk_val >= 75 else ('HIGH' if risk_val >= 50 else ('MEDIUM' if risk_val >= 25 else 'LOW'))
    
    return {
        "account_id": account_id,
        "total_inflow": round(inflow, 2),
        "total_outflow": round(outflow, 2),
        "transaction_count": count,
        "risk_rating": risk_val,
        "risk_tier": tier,
        "flagged_alerts_count": alert_cnt,
        "recent_transactions": recent
    }

@app.get("/api/accounts/list")
def list_entities_for_inspection(
    search: Optional[str] = "",
    risk_tier: Optional[str] = "ALL",
    location: Optional[str] = "ALL",
    sort_by: Optional[str] = "risk_desc",
    limit: int = 50,
    offset: int = 0
):
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT account_id, bank_location, risk_rating, flagged_tx_count, total_inflow, total_outflow, account_status FROM accounts WHERE 1=1"
        params = []
        
        if search:
            query += " AND account_id LIKE ?"
            params.append(f"%{search}%")
            
        if location and location != "ALL":
            query += " AND bank_location = ?"
            params.append(location)
            
        if risk_tier == "CRITICAL":
            query += " AND risk_rating >= 75"
        elif risk_tier == "HIGH":
            query += " AND risk_rating >= 50 AND risk_rating < 75"
        elif risk_tier == "MEDIUM":
            query += " AND risk_rating >= 25 AND risk_rating < 50"
        elif risk_tier == "LOW":
            query += " AND risk_rating < 25"
            
        # Sorting
        if sort_by == "risk_asc":
            order_clause = "risk_rating ASC, flagged_tx_count ASC"
        elif sort_by == "inflow_desc":
            order_clause = "total_inflow DESC, risk_rating DESC"
        elif sort_by == "outflow_desc":
            order_clause = "total_outflow DESC, risk_rating DESC"
        elif sort_by == "alerts_desc":
            order_clause = "flagged_tx_count DESC, risk_rating DESC"
        elif sort_by == "id_asc":
            order_clause = "account_id ASC"
        else: # risk_desc default
            order_clause = "risk_rating DESC, flagged_tx_count DESC"
            
        query += f" ORDER BY {order_clause} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        entities = []
        for r in rows:
            rv = round(float(r[2] or 0.0), 1)
            t = 'CRITICAL' if rv >= 75 else ('HIGH' if rv >= 50 else ('MEDIUM' if rv >= 25 else 'LOW'))
            entities.append({
                "account_id": r[0],
                "bank_location": r[1] or "US",
                "risk_rating": rv,
                "risk_tier": t,
                "flagged_alerts": r[3] or 0,
                "total_inflow": round(float(r[4] or 0.0), 2),
                "total_outflow": round(float(r[5] or 0.0), 2),
                "account_status": r[6] or "ACTIVE"
            })
            
        # Count total
        count_q = "SELECT COUNT(*) FROM accounts WHERE 1=1"
        c_params = []
        if search:
            count_q += " AND account_id LIKE ?"
            c_params.append(f"%{search}%")
        if location and location != "ALL":
            count_q += " AND bank_location = ?"
            c_params.append(location)
        if risk_tier == "CRITICAL":
            count_q += " AND risk_rating >= 75"
        elif risk_tier == "HIGH":
            count_q += " AND risk_rating >= 50 AND risk_rating < 75"
        elif risk_tier == "MEDIUM":
            count_q += " AND risk_rating >= 25 AND risk_rating < 50"
        elif risk_tier == "LOW":
            count_q += " AND risk_rating < 25"
            
        cursor.execute(count_q, tuple(c_params))
        total_count = cursor.fetchone()[0]
        
    return {
        "status": "success",
        "total": total_count,
        "count": len(entities),
        "offset": offset,
        "limit": limit,
        "entities": entities
    }

@app.get("/api/export/entities")
def export_all_entities_csv(
    search: Optional[str] = "",
    risk_tier: Optional[str] = "ALL",
    location: Optional[str] = "ALL"
):
    def iter_entities():
        yield "account_id,bank_location,risk_rating,risk_tier,flagged_alerts,total_inflow,total_outflow,account_status\n"
        with get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT account_id, bank_location, risk_rating, flagged_tx_count, total_inflow, total_outflow, account_status FROM accounts WHERE 1=1"
            params = []
            if search:
                query += " AND account_id LIKE ?"
                params.append(f"%{search}%")
            if location and location != "ALL":
                query += " AND bank_location = ?"
                params.append(location)
            if risk_tier == "CRITICAL":
                query += " AND risk_rating >= 75"
            elif risk_tier == "HIGH":
                query += " AND risk_rating >= 50 AND risk_rating < 75"
            elif risk_tier == "MEDIUM":
                query += " AND risk_rating >= 25 AND risk_rating < 50"
            elif risk_tier == "LOW":
                query += " AND risk_rating < 25"
            query += " ORDER BY risk_rating DESC, flagged_tx_count DESC"
            
            cursor.execute(query, tuple(params))
            while True:
                batch = cursor.fetchmany(1000)
                if not batch:
                    break
                for r in batch:
                    rv = round(float(r[2] or 0.0), 1)
                    t = 'CRITICAL' if rv >= 75 else ('HIGH' if rv >= 50 else ('MEDIUM' if rv >= 25 else 'LOW'))
                    yield f"{r[0]},{r[1] or 'US'},{rv},{t},{r[3] or 0},{round(float(r[4] or 0.0), 2)},{round(float(r[5] or 0.0), 2)},{r[6] or 'ACTIVE'}\n"

    return StreamingResponse(
        iter_entities(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=aml_all_entities_{int(time.time())}.csv"}
    )

class PredictionRequest(BaseModel):
    amount: float
    sender_account: str
    receiver_account: str
    sender_bank_location: str
    receiver_bank_location: str
    payment_type: str

@app.post("/api/predict")
def predict_transaction(req: PredictionRequest):
    tx_dict = req.dict()
    eval_res = scorer.calculate_risk(tx_dict)
    return {"transaction": tx_dict, "evaluation": eval_res}

@app.post("/api/simulate-stream")
def simulate_stream(batch_size: int = 10):
    import random
    cities = ['US', 'UK', 'Panama', 'Cayman Islands', 'UAE', 'Germany', 'Canada', 'Cyprus']
    methods = ['Cash Deposit', 'Wire Transfer', 'Cross-border', 'ACH', 'Credit Card']
    
    new_txs = []
    new_alerts = []
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions;")
        cur_count = cursor.fetchone()[0]
        
        for i in range(batch_size):
            tx_num = cur_count + i + 1
            tx_id = f"TX-SIM-{tx_num:08d}"
            
            is_attack = random.random() < 0.35
            if is_attack:
                amt = float(random.choice([9850.0, 9900.0, 85000.0, 120000.0, 55000.0]))
                s_loc = random.choice(['US', 'UK'])
                r_loc = random.choice(['Panama', 'Cayman Islands', 'Cyprus', 'UAE'])
                ptype = random.choice(['Cash Deposit', 'Cross-border', 'Wire Transfer'])
            else:
                amt = float(round(random.uniform(25.0, 1500.0), 2))
                s_loc = random.choice(['US', 'UK', 'Germany', 'Canada'])
                r_loc = s_loc
                ptype = random.choice(['Credit Card', 'ACH', 'Wire Transfer'])
                
            s_acc = str(random.randint(1000000000, 9999999999))
            r_acc = str(random.randint(1000000000, 9999999999))
            
            eval_res = scorer.calculate_risk({
                'amount': amt,
                'sender_account': s_acc,
                'receiver_account': r_acc,
                'payment_type': ptype,
                'sender_bank_location': s_loc,
                'receiver_bank_location': r_loc
            })
            
            r_score = eval_res['risk_score']
            r_tier = eval_res['risk_tier']
            violations = "; ".join(eval_res['rule_violations']) if eval_res['rule_violations'] else "STANDARD_BASELINE"
            
            new_txs.append((
                tx_id, "2026/08/28", "12:00:00", "2026/08/28 12:00:00",
                s_acc, r_acc, amt, "USD", "USD", s_loc, r_loc, ptype,
                1 if is_attack else 0, "SIMULATED_ATTACK" if is_attack else "NORMAL",
                r_score, r_tier, violations
            ))
            
            if r_score >= 50.0 or is_attack:
                alert_id = f"ALT-SIM-{tx_num:08d}"
                sev = "CRITICAL" if r_score >= 75.0 else "HIGH"
                typology = eval_res['rule_violations'][0] if eval_res['rule_violations'] else "STREAM_ANOMALY"
                new_alerts.append((
                    alert_id, tx_id, s_acc, r_acc, amt, typology, sev, r_score,
                    'NEW', " | ".join(eval_res['explanation_reasons']),
                    float(eval_res['ml_confidence']), 'Unassigned', None
                ))
                
        cursor.executemany("""
            INSERT INTO transactions (
                tx_id, date, time, timestamp, sender_account, receiver_account,
                amount, payment_currency, received_currency,
                sender_bank_location, receiver_bank_location, payment_type,
                is_laundering, laundering_type, risk_score, risk_tier,
                rule_violations
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, new_txs)
        
        if new_alerts:
            cursor.executemany("""
                INSERT INTO alerts (
                    alert_id, tx_id, sender_account, receiver_account,
                    amount, alert_type, severity, risk_score,
                    status, rule_reason, ml_confidence, assigned_to, investigator_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, new_alerts)
            
        conn.commit()
        
    global _STATS_CACHE
    _STATS_CACHE["data"] = compute_stats()
    _STATS_CACHE["last_updated"] = time.time()
    return {"status": "success", "injected_transactions": len(new_txs), "alerts_triggered": len(new_alerts)}

class SARRequest(BaseModel):
    alert_id: str
    primary_account: str
    counterparty_account: str
    suspicious_amount: float
    laundering_typology: str
    risk_score: float
    narrative: str
    compliance_officer: str

@app.post("/api/sar/generate")
def generate_sar(sar: SARRequest):
    sar_id = f"SAR-{int(time.time())}"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sar_reports (
                sar_id, alert_id, primary_account, counterparty_account,
                suspicious_amount, laundering_typology, risk_score,
                filing_status, narrative, compliance_officer
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'SUBMITTED', ?, ?)
        """, (sar_id, sar.alert_id, sar.primary_account, sar.counterparty_account,
              sar.suspicious_amount, sar.laundering_typology, sar.risk_score,
              sar.narrative, sar.compliance_officer))
        
        cursor.execute("UPDATE alerts SET status = 'SAR_FILED' WHERE alert_id = ?", (sar.alert_id,))
        conn.commit()
    return {"status": "success", "sar_id": sar_id, "message": "SAR Filed with FinCEN Regulatory Network"}

@app.get("/api/export/transactions")
def export_transactions_csv():
    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tx_id, date, time, sender_account, receiver_account, amount,
                   payment_currency, sender_bank_location, receiver_bank_location,
                   payment_type, is_laundering, laundering_type, risk_score, risk_tier, rule_violations
            FROM transactions
            WHERE risk_score >= 50.0 OR is_laundering = 1
            LIMIT 5000
        """)
        rows = cursor.fetchall()
        
    writer.writerow([
        "Transaction ID", "Date", "Time", "Sender Account", "Receiver Account", "Amount ($)",
        "Currency", "Sender Location", "Receiver Location", "Payment Method",
        "Is Laundering", "Laundering Typology", "Risk Score", "Risk Tier", "Rule Violations"
    ])
    for r in rows:
        writer.writerow(list(r))
        
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=aml_flagged_compliance_audit.csv"}
    )

@app.get("/api/model/metrics")
def get_model_metrics():
    metrics_path = os.path.join(os.path.dirname(__file__), "..", "models", "saved", "metrics.json")
    if os.path.exists(metrics_path):
        import json
        with open(metrics_path, "r") as f:
            return json.load(f)
    return {"message": "Model metrics not generated yet."}


# ==================== HIGH-SPEED SQL CONSOLE API ====================

class SQLQueryRequest(BaseModel):
    query: str
    limit: Optional[int] = 500

@app.post("/api/sql/execute")
def execute_sql_query(req: SQLQueryRequest):
    raw_query = req.query.strip()
    if not raw_query:
        raise HTTPException(status_code=400, detail="SQL query cannot be empty.")
        
    is_select = raw_query.upper().startswith(('SELECT', 'PRAGMA', 'EXPLAIN', 'WITH'))
    
    t0 = time.time()
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(raw_query)
            
            if is_select:
                columns = [col[0] for col in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                data = [list(r) for r in rows[:req.limit]]
                elapsed_ms = round((time.time() - t0) * 1000, 2)
                return {
                    "status": "success",
                    "type": "SELECT",
                    "columns": columns,
                    "rows": data,
                    "row_count": len(data),
                    "total_matching": len(rows),
                    "execution_time_ms": elapsed_ms
                }
            else:
                conn.commit()
                affected = cursor.rowcount
                elapsed_ms = round((time.time() - t0) * 1000, 2)
                global _STATS_CACHE
                _STATS_CACHE["last_updated"] = 0
                return {
                    "status": "success",
                    "type": "MUTATION",
                    "affected_rows": affected,
                    "execution_time_ms": elapsed_ms,
                    "message": f"Query executed successfully. {affected} row(s) affected."
                }
    except Exception as e:
        elapsed_ms = round((time.time() - t0) * 1000, 2)
        return {
            "status": "error",
            "error_message": str(e),
            "execution_time_ms": elapsed_ms
        }

_SCHEMA_CACHE = None

@app.get("/api/sql/schema")
def get_database_schema():
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE:
        return _SCHEMA_CACHE
        
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [r[0] for r in cursor.fetchall()]
        
        schema_dict = {}
        for t in tables:
            cursor.execute(f"PRAGMA table_info({t});")
            cols = [{"name": c[1], "type": c[2], "notnull": bool(c[3]), "pk": bool(c[5])} for c in cursor.fetchall()]
            cursor.execute(f"SELECT COUNT(*) FROM {t};")
            count = cursor.fetchone()[0]
            schema_dict[t] = {"columns": cols, "total_records": count}
            
    _SCHEMA_CACHE = {"tables": schema_dict}
    return _SCHEMA_CACHE
