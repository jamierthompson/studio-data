"""Tool functions for managing projects.

A project belongs to a client and moves through a defined lifecycle:
conceptual_design → detailed_design → purchasing → construction →
reveal_punch_list → completed.

When a project is created, the system instantiates workflow templates
into concrete project_tasks. For furnishings-only projects, all
renovation-only tasks are skipped — this is the key business rule
that compresses the timeline (no Layout Meeting cycle, no GC
coordination, no site meetings, etc.).
"""

import json
from typing import Any

from studio_data.db import get_connection


def create_project(
    client_id: str,
    name: str,
    project_type: str,
    *,
    address: str | None = None,
    investment_estimate: float | None = None,
) -> dict[str, Any]:
    """Create a project and instantiate its workflow tasks.

    This is the core "project setup" operation (Week 0 in the process).
    It creates the project record, then copies the relevant workflow
    templates into project_tasks so the project has a concrete task list
    from day one.

    Args:
        client_id: UUID of the client who owns this project.
        name: Project name (e.g., "Nguyen Living Room Renovation").
        project_type: One of 'furnishings', 'renovation', or 'mixed'.
            Controls which workflow templates get instantiated.
        address: Project site address.
        investment_estimate: Estimated total investment (furnishings +
            trades), used for the Exhibit B / investment amount tracking.

    Returns:
        Dict with 'project' (the new row) and 'tasks_created' (count
        of workflow tasks instantiated).

    Raises:
        ValueError: If project_type is not one of the allowed values.
    """
    allowed_types = {"furnishings", "renovation", "mixed"}
    if project_type not in allowed_types:
        raise ValueError(
            f"project_type must be one of {allowed_types}, got '{project_type}'"
        )

    with get_connection() as conn:
        # Step 1: Insert the project
        project = conn.execute(
            """
            INSERT INTO projects
                (client_id, name, address, project_type,
                 investment_estimate)
            VALUES
                (%(client_id)s, %(name)s, %(address)s,
                 %(project_type)s, %(investment_estimate)s)
            RETURNING *
            """,
            {
                "client_id": client_id,
                "name": name,
                "address": address,
                "project_type": project_type,
                "investment_estimate": investment_estimate,
            },
        ).fetchone()

        assert project is not None

        # Step 2: Instantiate workflow templates into project_tasks.
        # For furnishings projects, skip renovation-only tasks (the
        # Layout Meeting cycle, GC coordination, site meetings, etc.).
        # For renovation or mixed projects, include everything.
        tasks_created = _instantiate_workflow_tasks(conn, project["id"], project_type)

        # Step 3: Log the activity
        conn.execute(
            """
            INSERT INTO activity_log
                (entity_type, entity_id, action,
                 actor_type, actor_name, metadata)
            VALUES
                ('project', %(entity_id)s, 'created',
                 %(actor_type)s, %(actor_name)s,
                 %(metadata)s::jsonb)
            """,
            {
                "entity_id": project["id"],
                "actor_type": "system",
                "actor_name": "create_project",
                "metadata": json.dumps(
                    {
                        "project_type": project_type,
                        "tasks_created": tasks_created,
                    }
                ),
            },
        )

    return {
        "project": dict(project),
        "tasks_created": tasks_created,
    }


def _instantiate_workflow_tasks(
    conn: Any,
    project_id: Any,
    project_type: str,
) -> int:
    """Copy workflow templates into project_tasks for a new project.

    Furnishings projects skip renovation-only tasks. Renovation and
    mixed projects get the full template set.

    Returns the number of tasks created.
    """
    # Build the filter — furnishings projects exclude renovation-only
    # tasks; renovation and mixed projects include everything
    if project_type == "furnishings":
        templates = conn.execute(
            """
            SELECT id, phase, task_order
            FROM workflow_templates
            WHERE is_renovation_only = false
            ORDER BY task_order
            """
        ).fetchall()
    else:
        templates = conn.execute(
            """
            SELECT id, phase, task_order
            FROM workflow_templates
            ORDER BY task_order
            """
        ).fetchall()

    if not templates:
        return 0

    # Bulk insert project_tasks — one per template.
    # psycopg 3 puts executemany on the Cursor, not Connection,
    # so we open an explicit cursor for the batch insert.
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO project_tasks (project_id, template_id)
            VALUES (%(project_id)s, %(template_id)s)
            """,
            [{"project_id": project_id, "template_id": t["id"]} for t in templates],
        )

    return len(templates)
