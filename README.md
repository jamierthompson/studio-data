# StudioData

The **data layer and tool functions** for [StudioOS](https://github.com/jamierthompson/studio-os) — a Postgres-backed foundation that manages clients, projects, workflow templates, and a full audit trail for an AI-native interior design practice.

## Why a Tool Layer?

In StudioOS, AI agents never touch the database directly. They call validated Python functions — the "tool layer" — that enforce business rules, required fields, and audit logging on every operation. This keeps the agents focused on decision-making while the tool layer guarantees data integrity.

```
Agent System (Project 3)
    │
    ▼
┌──────────────────────────────┐
│  Tool Layer (this project)   │
│                              │
│  create_client()             │
│  create_project()            │
│  log_activity()              │
│  ... more to come            │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│  Postgres 16                 │
│                              │
│  19 tables · 13 enums        │
│  Workflow templates          │
│  Activity log (audit trail)  │
│  Auto-updated timestamps     │
└──────────────────────────────┘
```

## Architecture Decisions

**Structured vs. unstructured split** — Operational data (clients, projects, templates, billing) lives here in Postgres. Institutional knowledge (design philosophy, pricing standards, trade procedures) lives in a vector store via [DesignRAG](https://github.com/jamierthompson/design-rag). This separation lets each system use the storage model that fits its data: relational queries for structured operations, semantic search for unstructured knowledge.

**Workflow template instantiation** — The schema includes a `workflow_templates` table (the master task list) and a `project_tasks` table (concrete task instances per project). When `create_project()` is called, it copies the relevant templates into `project_tasks` based on `project_type` — furnishings-only projects skip renovation-specific tasks (Layout Meeting cycle, GC coordination, site meetings), compressing the timeline by ~25 tasks.

**Polymorphic activity log** — Every tool function logs its actions to a single `activity_log` table using `entity_type` + `entity_id` (not foreign keys). This gives the system a unified audit trail across all entity types, which is critical for debugging agent behavior and building client-facing activity feeds.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Database | PostgreSQL 16 |
| DB Driver | psycopg 3 (with connection pool) |
| Configuration | pydantic-settings (`.env` file) |
| Containerization | Docker Compose |
| Testing | pytest (17 tests) |
| Linting/Formatting | Ruff |
| Package Management | uv |

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Postgres)

### Setup

```bash
# Clone the repository
git clone https://github.com/jamierthompson/studio-data.git
cd studio-data

# Set up environment variables
cp .env.example .env
# The defaults work out of the box with Docker Compose

# Start Postgres (runs the schema migration automatically on first startup)
docker compose up -d

# Install Python dependencies
uv sync

# Run the test suite
uv run pytest -v
```

On the first `docker compose up`, Postgres automatically executes `migrations/001_initial_schema.sql` — creating all 19 tables, 13 enum types, indexes, and triggers. Data persists in a named Docker volume across restarts.

## Database Schema

The schema models the full lifecycle of an interior design practice:

| Table Group | Tables | Purpose |
|---|---|---|
| **Core** | `clients`, `projects`, `project_rooms` | Client pipeline and project tracking |
| **Financial** | `design_fees`, `pricing_benchmarks`, `line_items`, `vendor_quotes`, `purchase_orders`, `vendors` | Investment estimates, sourcing, purchasing |
| **Workflow** | `workflow_templates`, `project_tasks`, `email_templates` | Master task list and per-project task instances |
| **Trades** | `trades`, `project_trades` | Trade coordination and quote tracking |
| **Meetings** | `meetings`, `meeting_action_items` | Meeting scheduling and action item tracking |
| **Documents** | `documents` | Document storage references (S3 keys) |
| **Audit** | `activity_log`, `phase_transitions` | Polymorphic audit trail and phase change history |

### Key Enums

Projects move through a defined lifecycle via the `project_phase` enum:

```
conceptual_design → detailed_design → purchasing → construction → reveal_punch_list → completed
```

Clients progress through the sales pipeline via `client_status`:

```
lead → qualified → proposal_sent → contracted → active → completed
```

## Tool Functions

Tool functions are the validated interface between the agent system and the database. Each function handles its own transaction, enforces business rules, and logs to the activity trail.

### `create_client()`

Creates a new client with `'lead'` status. Accepts optional contact info and freeform screening data (stored as JSONB).

```python
from studio_data.tools.clients import create_client

client = create_client(
    "David & Linh Nguyen",
    email="linh@example.com",
    source="referral",
    screening_data={"style": "modern", "budget_range": "90k-110k"},
)
# → {"id": "uuid-...", "name": "David & Linh Nguyen", "status": "lead", ...}
```

### `create_project()`

Creates a project and instantiates workflow templates into concrete tasks. The `project_type` controls which templates are included:

- **`furnishings`** — Skips all renovation-only tasks (~25 fewer tasks). No Layout Meeting cycle, no GC coordination, no site meetings.
- **`renovation`** or **`mixed`** — Gets the full template set including construction-phase tasks.

```python
from studio_data.tools.projects import create_project

result = create_project(
    client_id=str(client["id"]),
    name="Nguyen LR/DR/MBED",
    project_type="furnishings",
    address="123 Main St, Olathe, KS",
    investment_estimate=100_000.00,
)
# → {"project": {...}, "tasks_created": 135}
```

### `log_activity()`

General-purpose audit trail for any entity and action. Supports `system`, `agent`, or `user` as actor types, with freeform JSONB metadata.

```python
from studio_data.tools.activity import log_activity

log_activity(
    entity_type="project",
    entity_id=str(project["id"]),
    action="phase_changed",
    actor_type="agent",
    actor_name="lifecycle_agent",
    metadata={
        "from_phase": "conceptual_design",
        "to_phase": "detailed_design",
        "gate_checks": {"exhibit_b_signed": True, "design_fee_paid": True},
    },
)
```

## Connection Layer

The database module (`db.py`) provides a connection pool with automatic transaction management:

```python
from studio_data.db import get_connection

with get_connection() as conn:
    row = conn.execute("SELECT * FROM clients WHERE id = %s", (client_id,)).fetchone()
    # row is a dict (not a tuple) thanks to dict_row default
    # commits automatically on exit; rolls back on exception
```

Key design choices:
- **psycopg 3 `ConnectionPool`** — Reuses connections instead of opening a new TCP connection per call
- **`dict_row` by default** — All queries return dicts, not tuples
- **Lazy initialization** — Pool connects on first use, not at import time
- **Context manager transactions** — Auto-commit on success, auto-rollback on exception

## Testing

Tests run against a real Postgres instance (no mocking). Each test is wrapped in a transaction that rolls back on teardown, so tests stay isolated and leave no data behind.

```bash
# Run all 17 tests
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_projects.py -v
```

## Project Structure

```
studio-data/
├── src/
│   └── studio_data/
│       ├── __init__.py
│       ├── config.py              # Settings via pydantic-settings + .env
│       ├── db.py                  # Connection pool and transaction helpers
│       └── tools/
│           ├── __init__.py
│           ├── clients.py         # create_client()
│           ├── projects.py        # create_project() + workflow instantiation
│           └── activity.py        # log_activity()
├── tests/
│   ├── conftest.py                # Per-test rollback fixture
│   ├── test_clients.py            # 5 tests
│   ├── test_projects.py           # 7 tests
│   └── test_activity.py           # 5 tests
├── migrations/
│   └── 001_initial_schema.sql     # Full schema (19 tables, 13 enums, triggers)
├── docker-compose.yml             # Postgres 16 with persistent volume
├── .env.example
├── pyproject.toml
├── uv.lock
├── LICENSE
└── README.md
```

## Part of StudioOS

StudioData is **Project 2** in the [StudioOS](https://github.com/jamierthompson/studio-os) roadmap:

| Project | Repository | Purpose |
|---|---|---|
| 1. DesignRAG | [design-rag](https://github.com/jamierthompson/design-rag) | Knowledge layer — RAG over institutional design expertise |
| **2. StudioData** | **[studio-data](https://github.com/jamierthompson/studio-data)** | **Data layer — Postgres schema and validated tool functions** |
| 3. Agent System | *coming soon* | AI agents that orchestrate the client lifecycle |
| 4. StudioOS | [studio-os](https://github.com/jamierthompson/studio-os) | React application with role-based dashboards |

## License

[MIT](LICENSE)
