"""Tests for project tool functions."""

import pytest

from studio_data.db import get_connection
from studio_data.tools.clients import create_client
from studio_data.tools.projects import create_project


@pytest.fixture()
def client() -> dict:
    """Create a client to attach projects to."""
    return create_client("Test Client", email="test@example.com")


@pytest.fixture(autouse=True)
def _seed_workflow_templates():
    """Insert sample workflow templates for testing.

    We seed a mix of universal tasks and renovation-only tasks
    to verify that furnishings projects correctly skip the
    renovation-only ones.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.executemany(
            """
                INSERT INTO workflow_templates
                    (phase, task_order, name, is_renovation_only)
                VALUES
                    (%(phase)s, %(order)s, %(name)s, %(reno)s)
                """,
            [
                # Universal tasks (all project types)
                {
                    "phase": "conceptual_design",
                    "order": 1,
                    "name": "Set up client in systems",
                    "reno": False,
                },
                {
                    "phase": "conceptual_design",
                    "order": 2,
                    "name": "Capture financial info",
                    "reno": False,
                },
                {
                    "phase": "conceptual_design",
                    "order": 3,
                    "name": "Schedule the project",
                    "reno": False,
                },
                {
                    "phase": "conceptual_design",
                    "order": 7,
                    "name": "Site Documentation Meeting",
                    "reno": False,
                },
                {
                    "phase": "detailed_design",
                    "order": 10,
                    "name": "Create inspiration boards",
                    "reno": False,
                },
                # Renovation-only tasks (skipped for furnishings)
                {
                    "phase": "conceptual_design",
                    "order": 4,
                    "name": "Layout Meeting",
                    "reno": True,
                },
                {
                    "phase": "conceptual_design",
                    "order": 5,
                    "name": "Layout Revision Meeting",
                    "reno": True,
                },
                {
                    "phase": "construction",
                    "order": 8,
                    "name": "Weekly site meeting",
                    "reno": True,
                },
            ],
        )


class TestCreateProject:
    """Tests for create_project()."""

    def test_creates_project_with_correct_fields(self, client):
        """Basic project creation with all fields populated."""
        result = create_project(
            client_id=str(client["id"]),
            name="Nguyen Living Room",
            project_type="furnishings",
            address="123 Main St, Olathe, KS",
            investment_estimate=100_000.00,
        )

        project = result["project"]
        assert project["name"] == "Nguyen Living Room"
        assert project["project_type"] == "furnishings"
        assert project["phase"] == "conceptual_design"  # default
        assert project["address"] == "123 Main St, Olathe, KS"
        assert float(project["investment_estimate"]) == 100_000.00

    def test_furnishings_project_skips_renovation_tasks(self, client):
        """Furnishings projects should only get universal tasks."""
        result = create_project(
            client_id=str(client["id"]),
            name="Furnishings Only",
            project_type="furnishings",
        )

        # 5 universal tasks, 3 renovation-only → should get 5
        assert result["tasks_created"] == 5

    def test_renovation_project_gets_all_tasks(self, client):
        """Renovation projects should get every template."""
        result = create_project(
            client_id=str(client["id"]),
            name="Full Renovation",
            project_type="renovation",
        )

        # All 8 templates (5 universal + 3 renovation-only)
        assert result["tasks_created"] == 8

    def test_mixed_project_gets_all_tasks(self, client):
        """Mixed projects (furnishings + renovation) get everything."""
        result = create_project(
            client_id=str(client["id"]),
            name="Mixed Project",
            project_type="mixed",
        )

        assert result["tasks_created"] == 8

    def test_tasks_are_linked_to_project(self, client):
        """Each instantiated task should reference the project."""
        result = create_project(
            client_id=str(client["id"]),
            name="Task Check",
            project_type="furnishings",
        )

        with get_connection() as conn:
            tasks = conn.execute(
                """
                SELECT pt.status, wt.name, wt.phase
                FROM project_tasks pt
                JOIN workflow_templates wt ON pt.template_id = wt.id
                WHERE pt.project_id = %(pid)s
                ORDER BY wt.task_order
                """,
                {"pid": result["project"]["id"]},
            ).fetchall()

        # All tasks should start as 'not_started'
        assert all(t["status"] == "not_started" for t in tasks)
        # First task should be "Set up client in systems"
        assert tasks[0]["name"] == "Set up client in systems"
        # No renovation-only tasks should appear
        task_names = [t["name"] for t in tasks]
        assert "Layout Meeting" not in task_names
        assert "Weekly site meeting" not in task_names

    def test_logs_activity_on_creation(self, client):
        """Creating a project should log to activity_log."""
        result = create_project(
            client_id=str(client["id"]),
            name="Activity Check",
            project_type="renovation",
        )

        with get_connection() as conn:
            log = conn.execute(
                """
                SELECT entity_type, action, metadata
                FROM activity_log
                WHERE entity_id = %(id)s
                AND entity_type = 'project'
                """,
                {"id": result["project"]["id"]},
            ).fetchone()

        assert log is not None
        assert log["action"] == "created"
        assert log["metadata"]["project_type"] == "renovation"
        assert log["metadata"]["tasks_created"] == 8

    def test_rejects_invalid_project_type(self, client):
        """Should raise ValueError for unknown project types."""
        with pytest.raises(ValueError, match="project_type must be"):
            create_project(
                client_id=str(client["id"]),
                name="Bad Type",
                project_type="unknown",
            )
