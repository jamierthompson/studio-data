-- StudioOS Data Layer — Initial Schema Migration
-- Run against a fresh Postgres 16+ database

-- ============================================================
-- Extensions
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Enums
-- ============================================================

CREATE TYPE client_status AS ENUM (
    'lead',
    'qualified',
    'proposal_sent',
    'contracted',
    'active',
    'completed',
    'churned'
);

CREATE TYPE project_type AS ENUM (
    'furnishings',
    'renovation',
    'mixed'
);

CREATE TYPE project_phase AS ENUM (
    'conceptual_design',
    'detailed_design',
    'purchasing',
    'construction',
    'reveal_punch_list',
    'completed',
    'on_hold'
);

CREATE TYPE fee_status AS ENUM (
    'pending',
    'invoiced',
    'paid',
    'overdue'
);

CREATE TYPE document_type AS ENUM (
    'agreement',
    'proposal',
    'exhibit_a',
    'exhibit_b',
    'investment_estimate',
    'presentation',
    'meeting_notes',
    'rfq',
    'scope_delineation',
    'build_reno_binder',
    'photo',
    'other'
);

CREATE TYPE task_status AS ENUM (
    'not_started',
    'in_progress',
    'blocked',
    'completed',
    'skipped'
);

CREATE TYPE trade_role AS ENUM (
    'gc',
    'soft_trade',
    'subcontractor'
);

CREATE TYPE quote_status AS ENUM (
    'invited',
    'ballpark_received',
    'final_rfq_sent',
    'final_quote_received'
);

CREATE TYPE meeting_type AS ENUM (
    'screening',
    'sales',
    'site_documentation',
    'layout',
    'layout_revision',
    'trade_day',
    'cdm',
    'cdm_revision',
    'ddm',
    'ddm_revision',
    'site_meeting',
    'other'
);

CREATE TYPE meeting_status AS ENUM (
    'scheduled',
    'confirmed',
    'completed',
    'cancelled',
    'rescheduled'
);

CREATE TYPE action_item_status AS ENUM (
    'open',
    'in_progress',
    'completed',
    'cancelled'
);

CREATE TYPE line_item_status AS ENUM (
    'estimated',
    'specified',
    'quoted',
    'ordered',
    'shipped',
    'delivered',
    'installed'
);

CREATE TYPE po_status AS ENUM (
    'draft',
    'submitted',
    'acknowledged',
    'in_production',
    'shipped',
    'delivered',
    'cancelled'
);

-- ============================================================
-- Core tables
-- ============================================================

-- Clients
CREATE TABLE clients (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    address         TEXT,
    status          client_status NOT NULL DEFAULT 'lead',
    source          TEXT,
    screening_data  JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_clients_status ON clients (status);

-- Projects
CREATE TABLE projects (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id           UUID NOT NULL REFERENCES clients(id),
    name                TEXT NOT NULL,
    address             TEXT,
    project_type        project_type NOT NULL,
    phase               project_phase NOT NULL DEFAULT 'conceptual_design',
    investment_estimate NUMERIC(12,2),
    exhibit_b_total     NUMERIC(12,2),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_projects_client ON projects (client_id);
CREATE INDEX idx_projects_phase ON projects (phase);

-- Project rooms
CREATE TABLE project_rooms (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id          UUID NOT NULL REFERENCES projects(id),
    name                TEXT NOT NULL,
    scope               TEXT,
    investment_estimate NUMERIC(12,2),
    exhibit_b_amount    NUMERIC(12,2),
    actual_amount       NUMERIC(12,2),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_project_rooms_project ON project_rooms (project_id);

-- ============================================================
-- Financial tables
-- ============================================================

-- Design fees
CREATE TABLE design_fees (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    label           TEXT NOT NULL,
    amount          NUMERIC(12,2) NOT NULL,
    payment_number  INTEGER NOT NULL,
    status          fee_status NOT NULL DEFAULT 'pending',
    due_at          TIMESTAMPTZ,
    paid_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_design_fees_project ON design_fees (project_id);

-- Pricing benchmarks (designer's internal pricing knowledge)
CREATE TABLE pricing_benchmarks (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    category            TEXT NOT NULL,
    item_type           TEXT NOT NULL,
    quality_tier        TEXT NOT NULL DEFAULT 'mid-high',
    unit_price_estimate NUMERIC(12,2) NOT NULL,
    freight_factor      NUMERIC(5,4) DEFAULT 0.18,
    notes               TEXT,
    last_updated        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_benchmarks_category ON pricing_benchmarks (category, item_type);

-- Vendors
CREATE TABLE vendors (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    category        TEXT,
    contact_name    TEXT,
    email           TEXT,
    phone           TEXT,
    account_number  TEXT,
    discount_tier   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Line items (CDM estimates → DDM specified products)
CREATE TABLE line_items (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id             UUID NOT NULL REFERENCES project_rooms(id),
    benchmark_id        UUID REFERENCES pricing_benchmarks(id),
    description_generic TEXT NOT NULL,
    quantity            INTEGER NOT NULL DEFAULT 1,
    estimated_unit_price NUMERIC(12,2),
    product_name        TEXT,
    product_spec        TEXT,
    selected_vendor_id  UUID REFERENCES vendors(id),
    designer_net        NUMERIC(12,2),
    unit_retail_price   NUMERIC(12,2),
    freight             NUMERIC(12,2),
    status              line_item_status NOT NULL DEFAULT 'estimated',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_line_items_room ON line_items (room_id);
CREATE INDEX idx_line_items_status ON line_items (status);

-- Vendor quotes (real quotes for specified products, DDM phase)
CREATE TABLE vendor_quotes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    line_item_id    UUID NOT NULL REFERENCES line_items(id),
    vendor_id       UUID NOT NULL REFERENCES vendors(id),
    unit_cost       NUMERIC(12,2) NOT NULL,
    freight         NUMERIC(12,2),
    lead_time_weeks INTEGER,
    notes           TEXT,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_vendor_quotes_line_item ON vendor_quotes (line_item_id);

-- Purchase orders (post-DDM approval)
CREATE TABLE purchase_orders (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    line_item_id        UUID NOT NULL REFERENCES line_items(id),
    vendor_id           UUID NOT NULL REFERENCES vendors(id),
    po_number           TEXT,
    amount              NUMERIC(12,2) NOT NULL,
    freight             NUMERIC(12,2),
    status              po_status NOT NULL DEFAULT 'draft',
    estimated_delivery  DATE,
    actual_delivery     DATE,
    ordered_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_purchase_orders_line_item ON purchase_orders (line_item_id);
CREATE INDEX idx_purchase_orders_status ON purchase_orders (status);

-- ============================================================
-- Workflow tables
-- ============================================================

-- Email templates
CREATE TABLE email_templates (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name              TEXT NOT NULL,
    phase             TEXT,
    subject_template  TEXT NOT NULL,
    body_template     TEXT NOT NULL,
    requires_review   BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Workflow templates (the 160-task master list)
CREATE TABLE workflow_templates (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phase               TEXT NOT NULL,
    task_order          INTEGER NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT,
    duration_days       INTEGER,
    is_renovation_only  BOOLEAN NOT NULL DEFAULT false,
    is_recurring        BOOLEAN NOT NULL DEFAULT false,
    email_template_id   UUID REFERENCES email_templates(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_workflow_templates_phase ON workflow_templates (phase);

-- Project tasks (instances of workflow templates per project)
CREATE TABLE project_tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    template_id     UUID REFERENCES workflow_templates(id),
    status          task_status NOT NULL DEFAULT 'not_started',
    assigned_to     TEXT,
    due_date        DATE,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_project_tasks_project ON project_tasks (project_id);
CREATE INDEX idx_project_tasks_status ON project_tasks (status);
CREATE INDEX idx_project_tasks_due ON project_tasks (due_date) WHERE status NOT IN ('completed', 'skipped');

-- ============================================================
-- Trades
-- ============================================================

CREATE TABLE trades (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    specialty   TEXT,
    company     TEXT,
    email       TEXT,
    phone       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_trades (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    trade_id        UUID NOT NULL REFERENCES trades(id),
    role            trade_role NOT NULL DEFAULT 'soft_trade',
    scope           TEXT,
    quote_status    quote_status NOT NULL DEFAULT 'invited',
    ballpark_amount NUMERIC(12,2),
    final_amount    NUMERIC(12,2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_project_trades_project ON project_trades (project_id);

-- ============================================================
-- Meetings
-- ============================================================

CREATE TABLE meetings (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id          UUID NOT NULL REFERENCES projects(id),
    meeting_type        meeting_type NOT NULL,
    scheduled_date      DATE,
    transcript_s3_key   TEXT,
    notes_s3_key        TEXT,
    status              meeting_status NOT NULL DEFAULT 'scheduled',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_meetings_project ON meetings (project_id);

CREATE TABLE meeting_action_items (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id  UUID NOT NULL REFERENCES meetings(id),
    description TEXT NOT NULL,
    assigned_to TEXT,
    status      action_item_status NOT NULL DEFAULT 'open',
    due_date    DATE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_action_items_meeting ON meeting_action_items (meeting_id);

-- ============================================================
-- Documents
-- ============================================================

CREATE TABLE documents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id  UUID NOT NULL REFERENCES projects(id),
    doc_type    document_type NOT NULL,
    s3_key      TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_project ON documents (project_id);

-- ============================================================
-- Phase transitions (audit trail for project state changes)
-- ============================================================

CREATE TABLE phase_transitions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    from_phase      TEXT NOT NULL,
    to_phase        TEXT NOT NULL,
    triggered_by    TEXT NOT NULL,
    gate_checks     JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_phase_transitions_project ON phase_transitions (project_id);

-- ============================================================
-- Activity log (polymorphic audit trail for all entities)
-- ============================================================

CREATE TABLE activity_log (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type TEXT NOT NULL,
    entity_id   UUID NOT NULL,
    action      TEXT NOT NULL,
    actor_type  TEXT NOT NULL,
    actor_name  TEXT NOT NULL,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_activity_log_entity ON activity_log (entity_type, entity_id);
CREATE INDEX idx_activity_log_created ON activity_log (created_at);

-- ============================================================
-- Updated_at triggers
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_clients_updated BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_projects_updated BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_line_items_updated BEFORE UPDATE ON line_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_purchase_orders_updated BEFORE UPDATE ON purchase_orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_project_tasks_updated BEFORE UPDATE ON project_tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_meetings_updated BEFORE UPDATE ON meetings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_action_items_updated BEFORE UPDATE ON meeting_action_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
