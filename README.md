# AI Data Intelligence Cloud

[![Continuous Integration](https://github.com/organization/ai-data-intelligence-cloud/actions/workflows/ci.yml/badge.svg)](https://github.com/organization/ai-data-intelligence-cloud/actions)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%2019-61DAFB.svg)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/Language-TypeScript%206-3178C6.svg)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Styles-Tailwind%20CSS%20v4-38B2AC.svg)](https://tailwindcss.com/)

A modular, full-stack enterprise data intelligence and AI cloud platform built for multi-format data ingestion, automated schema inference, visual ETL pipeline construction, data quality rules, and machine learning operations.

---

## Architecture Overview

Built as a **Modular Monolith** with decoupled background workers:
- **Backend:** Python 3.12+ / 3.14 with FastAPI, Pydantic Settings, and async architecture.
- **Frontend:** React 19, TypeScript, Vite 8, Tailwind CSS v4, Lucide Icons.
- **Testing:** Pytest for backend, Vitest & React Testing Library for frontend.
- **Code Quality:** Reproducible zero-padding LOC reporting script (`scripts/count_loc.py`).
- **Orchestration:** Docker Compose development environment and GitHub Actions CI.

For detailed architecture diagrams and layer boundaries, see [docs/architecture.md](file:///c:/Users/JK/Desktop/AI%20Data%20Intelligence%20Cloud/docs/architecture.md).

---

## Quickstart Guide (Windows PowerShell)

All commands are tested and verified on Windows PowerShell.

### 1. Set Up Python Backend Virtual Environment
```powershell
# Create the virtual environment
python -m venv .venv

# Install dependencies into .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
```

### 2. Set Up Frontend
```powershell
# Install Node dependencies using npm.cmd (bypasses execution policy restrictions)
npm.cmd install --prefix frontend
```

### 3. Configure Environment
```powershell
# Create your local .env file
Copy-Item .env.example .env
```

---

## Running Verification & Tests

### Run Backend Tests (Pytest - 76 Tests)
```powershell
.\.venv\Scripts\pytest.exe
```

### Run Frontend Tests (Vitest - 25 Tests)
```powershell
npm.cmd test --prefix frontend
```

### Run Frontend Production Build
```powershell
npm.cmd run build --prefix frontend
```

### Run Reproducible LOC & Anti-Padding Audit
```powershell
.\.venv\Scripts\python.exe scripts\count_loc.py
```

### Run Full Platform with Docker Compose
```powershell
docker compose up --build
```

---

## Starting Development Servers

To run the full stack locally:

### Terminal 1: Backend Server (FastAPI)
```powershell
.\.venv\Scripts\uvicorn.exe backend.app.main:app --reload --host 127.0.0.1 --port 8000
```
- API Root: `http://127.0.0.1:8000/`
- Health Diagnostic: `http://127.0.0.1:8000/api/v1/health`
- Interactive OpenAPI Docs: `http://127.0.0.1:8000/api/v1/docs`

### Terminal 2: Frontend Server (Vite)
```powershell
cd frontend
npm.cmd run dev
```
- Web Application: `http://localhost:5173/`

---

## Progressive Implementation Roadmap

| Phase | Module | Status |
| :---: | :--- | :---: |
| **0** | **Foundation, Tooling & Monorepo Architecture** | **COMPLETED & VERIFIED** |
| **1** | **Identity, Authentication & Workspace Isolation** | **COMPLETED & VERIFIED** |
| **2** | **Multi-Format Ingestion (CSV, JSON, Excel, Parquet)** | **COMPLETED & VERIFIED** |
| **3** | **Dataset Catalog, Schema Inference & Profiling** | **COMPLETED & VERIFIED** |
| **4** | **Data Cleaning & Transformation Operators** | **COMPLETED & VERIFIED** |
| **5** | **Visual ETL Pipeline Builder (DAG Topological Execution)** | **COMPLETED & VERIFIED** |
| **6** | **Async Background Workers & Job Scheduling (Celery/Redis)** | **COMPLETED & VERIFIED** |
| **7** | **Data Quality Rules, Validation & Alerts (Health Grading)** | **COMPLETED & VERIFIED** |
| **8** | **Data Lineage, Ownership & Governance (PII Classifier)** | **COMPLETED & VERIFIED** |
| **9** | **AutoML Operations, Model Registry & Online Inference** | **COMPLETED & VERIFIED** |
| **10** | **Interactive Analytics & BI Dashboards (Aggregations Engine)** | **COMPLETED & VERIFIED** |
| **11** | **AI Data Intelligence Assistant (Conversational Analytics)** | **COMPLETED & VERIFIED** |
| **12** | **Platform Hardening, Enterprise Deployment & Orchestration** | **COMPLETED & VERIFIED** |

See [PROJECT_STATUS.md](file:///c:/Users/JK/Desktop/AI%20Data%20Intelligence%20Cloud/PROJECT_STATUS.md) and [docs/backlog.md](file:///c:/Users/JK/Desktop/AI%20Data%20Intelligence%20Cloud/docs/backlog.md) for full details.
