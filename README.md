# Anti-Money Laundering (AML) Compliance & Surveillance Platform

A production-grade, college-ready Anti-Money Laundering analytics and surveillance platform built with **PySpark**, **XGBoost Machine Learning**, **NumPy**, **Pandas**, **SQLite**, and a **FastAPI** interactive compliance dashboard.

---

## Key Features

1. **Hybrid Detection Engine**:
   - **FATF Heuristic Rules**: Structuring / Smurfing ($8.5k–$9.99k detection), High-Risk Jurisdictions (Panama, Cayman Islands, UAE), High-Value Outliers, Rapid Pass-Through Velocity.
   - **XGBoost ML Model**: Trained on 300,000+ real IBM/Kaggle AML transaction patterns with severe class rebalancing (`scale_pos_weight: 838.2`). **ROC-AUC: 0.9653**.
   - **Composite Risk Scorer**: 0–100 dynamic risk score with explainable AI factors (Low, Medium, High, Critical).

2. **Big Data Scalability**:
   - Scalable to **10M+ transactions** using NumPy/Pandas vectorization and PySpark window aggregations.
   - Live stream simulator to inject real-time batches on demand.

3. **Interactive Compliance UI**:
   - **Executive Dashboard**: Intercepted AML dollars, alert metrics, typology breakdown, and risk distribution.
   - **Alert Triage Queue**: Investigate cases, change status (New, Under Investigation, Closed), assign compliance officers.
   - **Vis.js Money Flow Graph**: Interactive node-link visualization showing circular routing, smurfing clusters, and counterparty paths.
   - **Sandbox Tester**: Test custom transactions in real time with instant risk decomposition.
   - **Automated SAR Filing**: FinCEN-compliant Suspicious Activity Report generation with one-click filing.

4. **Zero-Config Storage**:
   - Powered by high-speed local **SQLite 3 (WAL mode)**. No MySQL server setup required!

5. **AWS Deployment Ready**:
   - Includes Dockerfile, docker-compose, and complete AWS EC2 / ECS / S3 deployment guide in `deployment/aws_deploy.md`.

---

## Quick Start Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Database Ingestion & Train ML Model
```bash
# Feature extraction & ML Model Training
python -m models.train_model

# Ingest sample transactions & alerts into SQLite
python -m pipeline.data_ingestion
```

### 3. Launch Dashboard & API
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser and navigate to: **`http://127.0.0.1:8000/`**

---

## Project Structure

```
D:\fintech\AML\
+-- backend/
¦   +-- main.py                  # FastAPI routes, endpoints & logic
¦   +-- static/
¦       +-- index.html           # Dark-mode Fintech Compliance Dashboard
+-- database/
¦   +-- aml_compliance.db        # SQLite 3 Database
¦   +-- db_manager.py            # SQLite connection pool & queries
¦   +-- schema.sql               # Database schema
+-- data/
¦   +-- raw/SAML-D.csv           # Unzipped AML benchmark dataset (9.5M rows)
¦   +-- processed/               # Parquet engineered features
+-- deployment/
¦   +-- Dockerfile.backend
¦   +-- docker-compose.yml
¦   +-- aws_deploy.md            # Complete AWS Deployment Guide
+-- models/
¦   +-- rules_engine.py          # AML Rule Heuristics
¦   +-- ml_detector.py           # XGBoost inference wrapper
¦   +-- risk_scorer.py           # Composite Risk Scoring
¦   +-- train_model.py           # Model training pipeline
¦   +-- saved/                   # Saved .joblib model & metrics
+-- pipeline/
¦   +-- data_ingestion.py        # Dataset extraction & SQLite loader
¦   +-- spark_etl.py             # PySpark feature engineering
¦   +-- transaction_generator.py # Scalable transaction generator (10M+)
+-- requirements.txt
+-- README.md
```
