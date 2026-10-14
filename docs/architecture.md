# AI Data Intelligence Cloud - System Architecture

## 1. Architectural Philosophy

The AI Data Intelligence Cloud is architected as a **Modular Monolith** with decoupled asynchronous background workers.

### Core Principles
1. **Separation of Concerns**: Business logic, API endpoints, persistence, and presentation are strictly decoupled.
2. **Single Authoritative Implementation**: Each capability (e.g., schema inference, dataset storage) has exactly one canonical service implementation.
3. **Explicit Dependency Flow**:
   - Web API / Presentation layer (`api/`, `frontend/`) -> Core Services & Domain Logic (`services/`, `core/`) -> Persistence & Storage (`models/`, `db/`).
   - Domain logic never imports API route handlers.
4. **Isolated Workspaces**: Data catalogs, datasets, pipelines, and ML models belong to an explicit workspace tenancy boundary.

```
                      +-----------------------------+
                      |   React 19 + TypeScript     |
                      |   Vite + Tailwind CSS v4    |
                      +--------------+--------------+
                                     |
                                     | REST / JSON
                                     v
                      +-----------------------------+
                      |      FastAPI Backend        |
                      |   (Modular Monolith Core)   |
                      +--------------+--------------+
                                     |
             +-----------------------+-----------------------+
             |                                               |
             v                                               v
+-------------------------+                     +-------------------------+
|    PostgreSQL + Alembic  |                     |      Redis Broker       |
|  (Metadata, Schemas,    |                     |   & State Management    |
|   Lineage, Audit Logs)  |                     +------------+------------+
+-------------------------+                                  |
                                                             v
                                                +-------------------------+
                                                |   Background Workers    |
                                                | (Ingestion, ETL, ML)    |
                                                +-------------------------+
```

---

## 2. Monorepo Directory Organization

```
AI Data Intelligence Cloud/
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI for backend, frontend, and LOC checks
├── backend/
│   ├── app/
│   │   ├── api/                 # Versioned API routes (v1/)
│   │   │   └── v1/
│   │   │       ├── endpoints/   # Endpoint controllers (health, auth, datasets...)
│   │   │       └── api.py       # Aggregated router
│   │   ├── core/                # Configuration, security, constants
│   │   ├── models/              # SQLAlchemy database ORM models
│   │   ├── schemas/             # Pydantic request/response validation schemas
│   │   ├── services/            # Pure business logic and domain processing
│   │   └── main.py              # FastAPI application instance
│   ├── tests/                   # Pytest test suites (unit, integration, API)
│   ├── Dockerfile
│   ├── pyproject.toml           # Pytest & Ruff linter settings
│   ├── requirements.txt         # Production dependencies
│   └── requirements-dev.txt     # Test and lint dependencies
├── frontend/
│   ├── src/
│   │   ├── components/          # Reusable, accessible UI components
│   │   ├── services/            # Typed HTTP API client and error handling
│   │   ├── test/                # Test harness and Vitest setups
│   │   ├── App.tsx              # Main application shell
│   │   ├── App.test.tsx         # Component integration tests
│   │   └── main.tsx             # DOM mount point
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── index.html
├── worker/
│   ├── __init__.py
│   └── README.md                # Background worker architecture
├── scripts/
│   └── count_loc.py             # Reproducible, zero-padding LOC auditor
├── docs/
│   ├── architecture.md          # Architectural blueprints and boundaries
│   ├── contributing.md          # Developer setup and contribution guidelines
│   └── backlog.md               # Phase-by-phase feature backlog
├── docker-compose.yml           # Reproducible multi-service development environment
├── .env.example                 # Config template
├── PROJECT_STATUS.md            # Living source of truth for project progress
└── README.md                    # Primary repository overview
```

---

## 3. Product Module Roadmaps

1. **Phase 0: Foundation & Tooling** (Completed) - Monorepo structure, verified FastAPI & React foundations, automated test runners, LOC auditor, and CI pipeline.
2. **Phase 1: Identity & Workspace Isolation** (Next) - User authentication (JWT), RBAC roles, workspace multi-tenancy, and audit logs.
3. **Phase 2: Ingestion Engine** - Resilient upload, streaming parsing, and chunking for CSV, JSON, Excel, and Parquet.
4. **Phase 3: Catalog & Profiling** - Schema inference, automated statistical summaries, null-distribution, and dataset versioning.
5. **Phase 4: Transformation Engine** - Type casting, missing value imputation, deduplication, filtering, and expression evaluator.
6. **Phase 5: Visual ETL Pipelines** - React Flow node-based pipeline designer, DAG validation, and execution engine.
7. **Phase 6: Async Job Processing** - Celery/Redis background queue, cancellation tokens, job history, and retry policies.
8. **Phase 7: Data Quality & Rules** - Expectation testing, anomaly detection, threshold assertions, and alert webhooks.
9. **Phase 8: Lineage & Governance** - Upstream/downstream dependency graphing, ownership tagging, and data dictionaries.
10. **Phase 9: Machine Learning Operations** - Train/validation splits, scikit-learn models, metric tracking, and model registry.
11. **Phase 10: Dashboards & Analytics** - Interactive chart visualizer, data aggregation endpoints, and reporting exports.
12. **Phase 11: AI Data Intelligence** - Safe SQL/transform translation, anomaly insights, natural language dataset queries.
13. **Phase 12: Administration & Monitoring** - Prometheus metrics, system logs, disaster recovery backups, and deployment orchestration.
