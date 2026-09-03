# Anti-Money Laundering (AML) Project - Deep Dive & College Viva Defense Guide

This comprehensive guide explains the theoretical foundations, algorithms, math, architecture, and regulatory frameworks behind the **AML Watchdog Surveillance Platform**.

---

## 1. Theoretical Foundation: The 3 Stages of Money Laundering

```
   ┌─────────────────────────────────────────────────────────────┐
   │                   1. PLACEMENT STAGE                        │
   │  - Introducing dirty cash into the legitimate financial     │
   │    system in small amounts to avoid detection.             │
   │  - Detection: Structuring / Smurfing detection ($8.5k-$9.9k)│
   └──────────────────────────────┬──────────────────────────────┘
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                    2. LAYERING STAGE                        │
   │  - Concealing the paper trail through complex webs of       │
   │    cross-border transfers, shell companies, and rapid hops. │
   │  - Detection: Flow Network Graph, Directed Cycles (A->B->C),│
   │    Fan-In/Fan-Out, High-Risk Jurisdictions (Panama, UAE)    │
   └──────────────────────────────┬──────────────────────────────┘
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                  3. INTEGRATION STAGE                       │
   │  - Re-entering the economy as "clean" funds via real estate,│
   │    investments, payroll, or business revenues.              │
   │  - Detection: Inflow-Outflow Velocity, Net Flow Anomalies   │
   └─────────────────────────────────────────────────────────────┘
```

---

## 2. Distributed Feature Engineering Pipeline (PySpark / Pandas)

Our Big Data engine extracts **28 engineered dimensions** per transaction:

### A. Non-Linear Amount Representations
- **Log Amount**: $\ln(1 + \text{Amount})$ compresses extreme dollar ranges.
- **Log Amount Squared**: Captures parabolic tail risk.

### B. Proximity to Regulatory Threshold ($10,000 Rule)
- Under the **US Bank Secrecy Act (BSA)**, banks must file a **Currency Transaction Report (CTR)** for cash $> \$10,000$.
- Laundering criminals split amounts to $\$9,000 - \$9,950$.
- **Structuring Proximity Metric**:
  $$\text{dist\_to\_10k} = |\text{Amount} - 10000|$$
  $$\text{is\_structuring} = \begin{cases} 1 & \text{if } 8500 \le \text{Amount} < 10000 \\ 0 & \text{otherwise} \end{cases}$$

### C. Account Velocity & Acceleration (Z-Score)
Measures how many standard deviations a transaction deviates from the sender's historical baseline:
$$Z = \frac{\text{Amount} - \mu_{\text{sender}}}{\sigma_{\text{sender}} + \epsilon}$$
- $Z > 3.0 \rightarrow$ High-velocity surge trigger.

### D. Graph Centrality: Fan-In / Fan-Out Ratio
- **Fan-In (Funnel Account)**: Multiple senders depositing into a single destination account.
- **Fan-Out (Dispersal Account)**: Single source dispersing micro-payments to hundreds of accounts.
$$\text{Fan Ratio} = \frac{\text{Degree}_{\text{out}}(\text{Sender})}{\text{Degree}_{\text{in}}(\text{Receiver}) + 1}$$

---

## 3. Machine Learning Architecture (XGBoost)

### The Extreme Class Imbalance Challenge
In financial surveillance, $>99.8\%$ of transactions are legitimate and $<0.2\%$ are laundering. Standard ML models fail by predicting 0 for everything (Accuracy Paradox).

### Our Solution:
1. **Cost-Sensitive Loss with `scale_pos_weight`**:
   $$\text{scale\_pos\_weight} = \frac{N_{\text{normal}}}{N_{\text{laundering}}} = 101.3$$
   Penalizes the gradient 101x more heavily when missing a money laundering case.
2. **Dynamic Decision Cutoff**:
   We optimize the decision boundary on the **Precision-Recall Curve (PR-AUC: 86.65%)** rather than standard arbitrary 0.5 probability.

---

## 4. Hybrid Risk Scoring Engine Formula

The final 0–100 Risk Score is computed as a weighted fusion:
$$\text{Final Risk Score} = \begin{cases} 0.50 \cdot R_{\text{rule}} + 0.50 \cdot S_{\text{ML}} & \text{if } R_{\text{rule}} \ge 80 \\ 0.35 \cdot R_{\text{rule}} + 0.65 \cdot S_{\text{ML}} & \text{otherwise} \end{cases}$$

Where:
- $R_{\text{rule}} \in [0, 100]$: Max heuristic penalty (Structuring, High-Risk Jurisdiction, Single Large Outlier).
- $S_{\text{ML}} \in [0, 100]$: Calibrated XGBoost probability ($\text{prob} \times 100$).

### Risk Tiers:
- **`CRITICAL`** ($\ge 75$): Instant SAR filing required & account freeze alert.
- **`HIGH`** ($50 - 74$): Escalated to senior compliance officer.
- **`MEDIUM`** ($25 - 49$): Flagged for batch audit review.
- **`LOW`** ($< 25$): Normal automated clearance.

---

## 5. College Viva / Technical Defense Questions & Answers

### Q1: Why did you choose XGBoost over Deep Learning (ANN)?
> **Answer**: Tabular transaction data with high categorical cardinality (bank locations, payment types) and severe class imbalance performs significantly better and trains orders of magnitude faster with Gradient Boosted Decision Trees (XGBoost) than Deep Learning. Furthermore, XGBoost provides exact feature importances (Gini Index) required for regulatory audit explainability.

### Q2: Why use SQLite instead of MySQL or PostgreSQL?
> **Answer**: SQLite 3 with Write-Ahead Logging (WAL mode) is zero-configuration, serverless, and provides microsecond query latency directly from disk without database daemon overhead. For cloud scaling on AWS, the schema is 100% ANSI SQL compatible with Amazon RDS / Aurora.

### Q3: How do you handle false positives in AML?
> **Answer**: We combine heuristic rules with an ML model tuned for high Precision (88.47%) and dynamic PR thresholding. In our test set of 201,975 transactions, our model generated only 195 false alarms while capturing 1,496 laundering transactions.

### Q4: What is a SAR and why is it important?
> **Answer**: A **Suspicious Activity Report (SAR)** is a regulatory filing mandated by FinCEN (US) and FIU (Global) under FATF guidelines. Financial institutions must file SARs within 30 days of detecting suspicious patterns exceeding reporting thresholds.
