"""Tests for activity log tool function."""

import uuid

from studio_data.tools.activity import log_activity


class TestLogActivity:
    """Tests for log_activity()."""

    def test_logs_with_required_fields_only(self):
        """Minimal call — just entity info and action."""
        entry = log_activity(
            entity_type="project",
            entity_id=str(uuid.uuid4()),
            action="phase_changed",
        )

        assert entry["entity_type"] == "project"
        assert entry["action"] == "phase_changed"
        assert entry["actor_type"] == "system"  # default
        assert entry["actor_name"] == "unknown"  # default
        assert entry["metadata"] == {}  # JSONB default

    def test_logs_with_all_fields(self):
        """Full call — every field populated."""
        entity_id = str(uuid.uuid4())
        entry = log_activity(
            entity_type="meeting",
            entity_id=entity_id,
            action="completed",
            actor_type="agent",
            actor_name="meeting_notes_agent",
            metadata={
                "meeting_type": "cdm",
                "duration_minutes": 90,
                "transcript_processed": True,
            },
        )

        assert entry["entity_type"] == "meeting"
        assert entry["entity_id"] == uuid.UUID(entity_id)
        assert entry["action"] == "completed"
        assert entry["actor_type"] == "agent"
        assert entry["actor_name"] == "meeting_notes_agent"
        assert entry["metadata"]["meeting_type"] == "cdm"
        assert entry["metadata"]["duration_minutes"] == 90

    def test_returns_generated_id_and_timestamp(self):
        """Should include the Postgres-generated UUID and created_at."""
        entry = log_activity(
            entity_type="client",
            entity_id=str(uuid.uuid4()),
            action="status_changed",
        )

        assert entry["id"] is not None
        assert entry["created_at"] is not None

    def test_supports_any_entity_type(self):
        """The activity log is polymorphic — any entity type works."""
        for entity_type in ["client", "project", "task", "email", "invoice"]:
            entry = log_activity(
                entity_type=entity_type,
                entity_id=str(uuid.uuid4()),
                action="test_action",
            )
            assert entry["entity_type"] == entity_type

    def test_metadata_preserves_nested_structure(self):
        """JSONB should handle nested dicts and lists."""
        entry = log_activity(
            entity_type="project",
            entity_id=str(uuid.uuid4()),
            action="phase_changed",
            metadata={
                "from_phase": "conceptual_design",
                "to_phase": "detailed_design",
                "gate_checks": {
                    "exhibit_b_signed": True,
                    "design_fee_paid": True,
                },
                "skipped_tasks": ["layout_meeting", "layout_revision"],
            },
        )

        assert entry["metadata"]["from_phase"] == "conceptual_design"
        assert entry["metadata"]["gate_checks"]["exhibit_b_signed"] is True
        assert len(entry["metadata"]["skipped_tasks"]) == 2
