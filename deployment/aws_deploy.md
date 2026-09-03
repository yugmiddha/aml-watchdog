# AWS Cloud Deployment Guide for AML Platform

This guide outlines the production deployment of the **Anti-Money Laundering (AML) Compliance Engine** on Amazon Web Services (AWS).

---

## Architecture on AWS

```
 [Users / Compliance Officers]
               ¦
               ? (HTTPS: 443)
       [AWS Route 53 & ALB]
               ¦
               ?
 +----------------------------------------------+
 ¦             AWS ECS (Fargate) / EC2          ¦
 ¦  +----------------------------------------+  ¦
 ¦  ¦ FastAPI + Web UI Container (Port 8000) ¦  ¦
 ¦  ¦  - PySpark ETL & Aggregations          ¦  ¦
 ¦  ¦  - XGBoost ML Risk Inference           ¦  ¦
 ¦  ¦  - AML Heuristics Rules Engine         ¦  ¦
 ¦  +----------------------------------------+  ¦
 +----------------------------------------------+
                        ¦
       +---------------------------------+
       ?                                 ?
 [Amazon S3]                     [Amazon EFS / RDS]
 - Raw 10M+ Datasets (.csv/.parquet) - SQLite DB or Aurora Postgres
 - Model Checkpoints (.joblib)      - Audit logs & SAR filings
```

---

## Option A: One-Click EC2 Deployment (Amazon Linux 2023 / Ubuntu)

1. **Launch EC2 Instance**:
   - Instance Type: `t3.large` or `c6i.large` (2 vCPUs, 4-8 GB RAM recommended for PySpark/XGBoost).
   - Security Group: Inbound Port 22 (SSH), Port 80 (HTTP), Port 8000 (FastAPI UI).

2. **Connect and Clone**:
   ```bash
   ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
   sudo apt update && sudo apt install -y python3-pip git docker.io docker-compose
   git clone <YOUR_REPO_URL> /home/ubuntu/AML
   cd /home/ubuntu/AML
   ```

3. **Run with Docker Compose**:
   ```bash
   docker-compose -f deployment/docker-compose.yml up -d --build
   ```

4. **Access UI**:
   Open browser at `http://<EC2_PUBLIC_IP>:8000/`

---

## Option B: AWS ECS Fargate (Serverless Containers)

1. **Push Container to Amazon ECR**:
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
   docker build -t aml-platform -f deployment/Dockerfile.backend .
   docker tag aml-platform:latest <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/aml-platform:latest
   docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/aml-platform:latest
   ```

2. **Create ECS Task Definition**:
   - Assign CPU: 1 vCPU, Memory: 2 GB
   - Mount Amazon EFS volume to `/app/database` for persistent SQLite / logs.

3. **Create Service behind Application Load Balancer (ALB)**.

---

## Option C: Big Data Scaling with Amazon EMR & S3 (10M+ to 100M+ Scale)

- Store raw transaction batches on **Amazon S3** (`s3://aml-data-bucket/raw/`).
- Run `pipeline/spark_etl.py` as an **AWS EMR (Elastic MapReduce)** PySpark step for distributed processing.
- Model inferences served via **FastAPI** container.
