# AI Data Intelligence Cloud - Contributing & Developer Guide

Welcome! This guide is written specifically for engineers developing on **Windows** using **PowerShell**.

---

## 1. Prerequisites

Ensure the following tools are installed:
- **Git** (`git --version`)
- **Python 3.12+** (`python --version`)
- **Node.js 20+** (`node --version`)
- **npm** (`npm.cmd --version`)

> **Windows PowerShell Execution Policy Note:**
> PowerShell may block running `.ps1` wrapper scripts by default. To avoid security permission issues without lowering system protections, always use direct executable forms:
> - Use `npm.cmd` instead of `npm`
> - Use `npx.cmd` instead of `npx`
> - Call Python binaries directly from the virtual environment: `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\pytest.exe`.

---

## 2. Setting Up the Local Environment

Run the following commands in Windows PowerShell from the repository root:

### A. Python Backend Virtual Environment
```powershell
# Create Python virtual environment
python -m venv .venv

# Install backend dependencies
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
```

### B. Node.js Frontend Setup
```powershell
# Install frontend dependencies
cd frontend
npm.cmd install
cd ..
```

### C. Environment Configuration
```powershell
# Copy example configuration if .env does not exist
Copy-Item .env.example .env
```

---

## 3. Running the Verification Suites

Always run the automated test suites to ensure everything works before making changes:

### Run Backend Tests
```powershell
.\.venv\Scripts\pytest.exe
```

### Run Frontend Tests
```powershell
npm.cmd test --prefix frontend
```

### Run Production Build Verification
```powershell
npm.cmd run build --prefix frontend
```

### Run LOC & Code Quality Audit
```powershell
.\.venv\Scripts\python.exe scripts\count_loc.py
```

---

## 4. Starting the Development Servers

### Terminal 1: Backend Server (FastAPI)
```powershell
.\.venv\Scripts\uvicorn.exe backend.app.main:app --reload --host 127.0.0.1 --port 8000
```
- Interactive API Docs: `http://127.0.0.1:8000/api/v1/docs`
- Health Diagnostic: `http://127.0.0.1:8000/api/v1/health`

### Terminal 2: Frontend Server (Vite)
```powershell
cd frontend
npm.cmd run dev
```
- Web Application: `http://localhost:5173`

---

## 5. Git and Pull Request Workflow

1. **Check Status First**:
   ```powershell
   git status
   ```

2. **Branching**:
   Use descriptive branch names:
   - `feature/phase1-user-auth`
   - `fix/health-check-header`

3. **Conventional Commits**:
   - `feat(backend): implement health check endpoint`
   - `test(frontend): add Vitest suite for telemetry card`
   - `docs: add architecture overview and backlog`

4. **Pull Requests Policy**:
   - Only create PRs for real, implemented features.
   - Every PR must list:
     - Problem solved.
     - Summary of changes.
     - Actual commands run and test results.
     - Limitations or migrations required.
   - Never commit secrets, generated bundles (`node_modules`, `dist`, `.venv`), or placeholder code.
