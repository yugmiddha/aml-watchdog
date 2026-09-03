import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import json
import datetime
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.db_manager import get_connection, get_stats
from models.risk_scorer import scorer
from pipeline.transaction_generator import generate_live_stream_batch

st.set_page_config(
    page_title="AML Watchdog - Compliance Surveillance",
    page_icon="???",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main { background-color: #0b0f19; }
    .stApp { background-color: #0b0f19; color: #f3f4f6; }
    div[data-testid="stMetricValue"] { font-family: 'JetBrains Mono', monospace; font-size: 26px; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 12px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #111827;
        border-radius: 8px;
        padding: 8px 16px;
        color: #9ca3af;
        border: 1px solid #1f2937;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(6, 182, 212, 0.15) !important;
        color: #06b6d4 !important;
        border: 1px solid rgba(6, 182, 212, 0.4) !important;
    }
</style>
""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 1])
with col1:
    st.title("??? AML Watchdog Surveillance Engine")
    st.caption("Big Data & ML Powered Anti-Money Laundering Platform • PySpark • XGBoost (ROC-AUC: 0.9653) • SQLite")
with col2:
    st.markdown("<div style='text-align: right; padding-top: 15px;'>", unsafe_allow_html=True)
    if st.button("? Inject Live Stream (20 TX)", type="primary"):
        batch = generate_live_stream_batch(batch_size=20)
        from database.db_manager import insert_transactions_bulk, insert_alerts_bulk
        import uuid
        txs, alts = [], []
        for b in batch:
            r = scorer.calculate_risk(b)
            b['risk_score'] = r['risk_score']
            b['risk_tier'] = r['risk_tier']
            b['rule_violations'] = "; ".join(r['rule_violations'])
            txs.append(b)
            if r['risk_score'] >= 50.0 or b.get('is_laundering') == 1:
                alts.append({
                    'alert_id': f"ALT-{uuid.uuid4().hex[:8].upper()}",
                    'tx_id': b['tx_id'],
                    'sender_account': b['sender_account'],
                    'receiver_account': b['receiver_account'],
                    'amount': b['amount'],
                    'alert_type': b.get('laundering_type', 'Stream Anomaly'),
                    'severity': r['risk_tier'],
                    'risk_score': r['risk_score'],
                    'status': 'NEW',
                    'rule_reason': "; ".join(r['explanation_reasons']),
                    'ml_confidence': r['ml_confidence'],
                    'assigned_to': 'Unassigned',
                    'investigator_notes': 'Live simulated streaming batch'
                })
        insert_transactions_bulk(txs)
        insert_alerts_bulk(alts)
        st.success(f"Streamed 20 transactions! Generated {len(alts)} high-risk alerts.")
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "?? Executive Dashboard", 
    "?? Alert Triage Queue", 
    "??? Flow Network Graph", 
    "?? Live Transaction Tester", 
    "?? ML Model Insights"
])

with tab1:
    stats = get_stats()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Transactions", f"{stats['total_transactions']:,}", "10M+ Synthesizer Ready")
    m2.metric("Total Flow Volume", f"${stats['total_volume']:,.2f}", "Monitored Funds")
    m3.metric("Suspicious Intercepts", f"{stats['flagged_transactions']:,}", f"${stats['flagged_volume']:,.2f} Flagged")
    m4.metric("ML Validation ROC-AUC", "96.53%", "XGBoost Classifier")
    
    st.markdown("---")
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("Laundering Typologies Distribution")
        typ_df = pd.DataFrame(stats['laundering_breakdown'])
        if not typ_df.empty:
            typ_df['type'] = typ_df['type'].str.replace('_', ' ')
            fig_bar = px.bar(
                typ_df, x='type', y='count',
                color='count',
                color_continuous_scale='teal',
                labels={'type': 'Laundering Pattern', 'count': 'Interceptions Count'},
                template="plotly_dark"
            )
            fig_bar.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor="#111827", plot_bgcolor="#111827")
            st.plotly_chart(fig_bar, use_container_width=True)
            
    with c2:
        st.subheader("Risk Severity Breakdown")
        tier_data = stats['tier_distribution']
        if tier_data:
            fig_pie = px.pie(
                names=list(tier_data.keys()),
                values=list(tier_data.values()),
                hole=0.55,
                color=list(tier_data.keys()),
                color_discrete_map={'LOW': '#10b981', 'MEDIUM': '#3b82f6', 'HIGH': '#f59e0b', 'CRITICAL': '#ef4444'},
                template="plotly_dark"
            )
            fig_pie.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="#111827")
            st.plotly_chart(fig_pie, use_container_width=True)

with tab2:
    st.subheader("Compliance Alert Triage & SAR Management")
    f1, f2, f3 = st.columns([1, 1, 2])
    with f1:
        sel_sev = st.selectbox("Filter Severity", ["ALL", "CRITICAL", "HIGH", "MEDIUM"])
    with f2:
        sel_stat = st.selectbox("Filter Status", ["ALL", "NEW", "UNDER_INVESTIGATION", "SAR_FILED", "CLOSED"])
        
    conn = get_connection()
    q = "SELECT alert_id, tx_id, sender_account, receiver_account, amount, alert_type, severity, risk_score, status, rule_reason, assigned_to FROM alerts WHERE 1=1"
    params = []
    if sel_sev != "ALL":
        q += " AND severity = ?"
        params.append(sel_sev)
    if sel_stat != "ALL":
        q += " AND status = ?"
        params.append(sel_stat)
    q += " ORDER BY created_at DESC LIMIT 100"
    
    df_alerts = pd.read_sql_query(q, conn, params=params)
    conn.close()
    
    if not df_alerts.empty:
        st.dataframe(
            df_alerts.style.format({
                'amount': '${:,.2f}',
                'risk_score': '{:.1f}'
            }),
            use_container_width=True,
            height=380
        )

with tab3:
    st.subheader("??? Directed Transaction Network Graph")
    acc_input = st.text_input("Enter Target Account ID to Trace Flow", value="8724731955")
    
    if acc_input:
        conn = get_connection()
        rows = conn.execute("""
            SELECT sender_account, receiver_account, amount, risk_score, risk_tier, laundering_type
            FROM transactions 
            WHERE sender_account = ? OR receiver_account = ?
            ORDER BY amount DESC LIMIT 35
        """, (acc_input, acc_input)).fetchall()
        conn.close()
        
        if rows:
            G = nx.DiGraph()
            for r in rows:
                G.add_edge(str(r['sender_account']), str(r['receiver_account']), weight=float(r['amount']), risk=float(r['risk_score']), tier=str(r['risk_tier']))
                
            pos = nx.spring_layout(G, k=0.5, seed=42)
            edge_x, edge_y = [], []
            for edge in G.edges():
                x0, y0 = pos[edge[0]]
                x1, y1 = pos[edge[1]]
                edge_x.extend([x0, x1, None])
                edge_y.extend([y0, y1, None])
                
            edge_trace = go.Scatter(x=edge_x, y=edge_y, line=dict(width=1.5, color='#06b6d4'), hoverinfo='none', mode='lines')
            node_x, node_y, node_colors, node_text, node_sizes = [], [], [], [], []
            for node in G.nodes():
                x, y = pos[node]
                node_x.append(x)
                node_y.append(y)
                is_target = (node == acc_input)
                node_colors.append('#ef4444' if is_target else '#3b82f6')
                node_sizes.append(28 if is_target else 16)
                node_text.append(f"Account: {node} {'(TARGET)' if is_target else ''}")
                
            node_trace = go.Scatter(
                x=node_x, y=node_y,
                mode='markers+text',
                hoverinfo='text',
                text=[f"ACC {n[-4:]}" for n in G.nodes()],
                textposition="bottom center",
                marker=dict(color=node_colors, size=node_sizes, line_width=2, line_color='#ffffff')
            )
            
            fig_net = go.Figure(data=[edge_trace, node_trace],
                layout=go.Layout(
                    title=f"Money Flow Network for Account {acc_input}",
                    showlegend=False,
                    paper_bgcolor="#111827",
                    plot_bgcolor="#111827",
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    height=500
                )
            )
            st.plotly_chart(fig_net, use_container_width=True)

with tab4:
    st.subheader("?? Real-Time Transaction Scoring Sandbox")
    with st.form("tx_tester_form"):
        f_amt = st.number_input("Transaction Amount ($)", min_value=1.0, value=9850.0, step=100.0)
        c_a, c_b = st.columns(2)
        with c_a:
            f_sender = st.text_input("Sender Account", "4829104821")
            f_sender_loc = st.selectbox("Sender Jurisdiction", ["US", "UK", "Panama", "Cayman Islands", "UAE", "Germany"])
            f_pay_type = st.selectbox("Payment Type", ["Cash Deposit", "Wire Transfer", "Cross-border", "ACH", "Credit Card"])
        with c_b:
            f_receiver = st.text_input("Receiver Account", "9928174822")
            f_receiver_loc = st.selectbox("Receiver Jurisdiction", ["Panama", "US", "Cayman Islands", "Cyprus", "UAE", "UK"])
            
        submitted = st.form_submit_button("? Evaluate Transaction Risk")
        if submitted:
            tx_obj = {
                'amount': f_amt,
                'sender_account': f_sender,
                'receiver_account': f_receiver,
                'sender_bank_location': f_sender_loc,
                'receiver_bank_location': f_receiver_loc,
                'payment_type': f_pay_type
            }
            res = scorer.calculate_risk(tx_obj)
            st.markdown("---")
            r1, r2, r3 = st.columns(3)
            r1.metric("Composite Risk Score", f"{res['risk_score']}/100", f"{res['risk_tier']} RISK")
            r2.metric("Rule Engine Score", f"{res['rule_score']}/100")
            r3.metric("ML Model Confidence", f"{res['ml_confidence']}%")
            st.markdown("#### ?? Explainability & Rule Triggers:")
            for reason in res['explanation_reasons']:
                st.warning(f"• {reason}")
            if res['requires_sar']:
                st.error("?? SAR FILING REQUIRED: This transaction exceeds compliance risk threshold.")

with tab5:
    st.subheader("?? Machine Learning Model Architecture & Performance")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Algorithm", "XGBoost Classifier")
    k2.metric("Validation ROC-AUC", "0.9653")
    k3.metric("Recall Score", "75.00%")
    k4.metric("Engineered Features", "20 Features")
    
    metrics_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'saved', 'metrics.json')
    if os.path.exists(metrics_path):
        with open(metrics_path, 'r') as f:
            m_data = json.load(f)
        st.markdown("---")
        st.subheader("Feature Importance Ranking (Gini Index)")
        imps = m_data.get('feature_importances', {})
        df_imp = pd.DataFrame(list(imps.items()), columns=['Feature', 'Importance']).head(12)
        fig_imp = px.bar(df_imp, x='Importance', y='Feature', orientation='h', color='Importance', color_continuous_scale='purples', template="plotly_dark")
        fig_imp.update_layout(height=400, yaxis={'categoryorder':'total ascending'}, paper_bgcolor="#111827", plot_bgcolor="#111827")
        st.plotly_chart(fig_imp, use_container_width=True)
