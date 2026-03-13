"""Tool function for the activity log.

The activity_log table is a polymorphic audit trail — it can track
actions on any entity in the system (clients, projects, meetings,
tasks, etc.) by storing the entity_type and entity_id as plain text
and UUID rather than foreign keys.

This gives the agent system a single, consistent way to record every
action it takes, which is critical for:
  - Debugging agent behavior ("why did this happen?")
  - Client-facing audit trails ("what's been done on my project?")
  - Analytics ("how many meetings were scheduled last month?")
"""

import json
from typing import Any

from studio_data.db import get_connection


def log_activity(
    entity_type: str,
    entity_id: str,
    action: str,
    *,
    actor_type: str = "system",
    actor_name: str = "unknown",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record an action in the activity log.

    This is the general-purpose logging function that any tool or agent
    can call. The create_client() and create_project() functions log
    their own activity inline, but this function is for everything else:
    phase transitions, meetings completed, emails sent, tasks updated, etc.

    Args:
        entity_type: What kind of thing was acted on (e.g., 'client',
            'project', 'meeting', 'task').
        entity_id: UUID of the entity.
        action: What happened (e.g., 'created', 'updated',
            'phase_changed', 'email_sent').
        actor_type: Who did it — 'system', 'agent', or 'user'.
        actor_name: Specific actor (e.g., 'create_project',
            'screening_agent', 'jamie').
        metadata: Optional freeform dict of additional context
            (stored as JSONB). Use this for things like before/after
            values on updates, email template names, etc.

    Returns:
        The newly created activity_log row as a dict.
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO activity_log
                (entity_type, entity_id, action,
                 actor_type, actor_name, metadata)
            VALUES
                (%(entity_type)s, %(entity_id)s, %(action)s,
                 %(actor_type)s, %(actor_name)s,
                 COALESCE(%(metadata)s::jsonb, '{}'))
            RETURNING *
            """,
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "actor_type": actor_type,
                "actor_name": actor_name,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        ).fetchone()

        assert row is not None

    return dict(row)
