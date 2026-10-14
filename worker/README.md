# Background Worker Architecture

This directory is designated for asynchronous task processing in the AI Data Intelligence Cloud platform.

## Planned Responsibilities (Phase 6 Activation)
- **Asynchronous Task Execution**: Handling long-running ingestion, data profiling, transformations, and ML training off the HTTP request/response loop.
- **Task Broker & State**: Backed by Redis broker and PostgreSQL result backend via Celery or ARQ.
- **Job Lifecycle**: Task queuing, status tracking, progressive progress updates, retry policies with exponential backoff, cancellation tokens, and dead-letter queue auditing.

## Directory Structure (Target)
```
worker/
├── __init__.py
├── celery_app.py      # Celery instance configuration and task registration
├── tasks/
│   ├── ingestion.py   # Multi-format async ingestion workers
│   ├── profiling.py   # Large-scale profiling jobs
│   ├── pipeline.py    # Visual ETL execution workers
│   └── ml.py          # Machine learning training workers
└── schedules/         # Periodic cron-like recurring jobs
```
