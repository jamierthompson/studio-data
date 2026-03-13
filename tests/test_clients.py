"""Tests for client tool functions."""

from studio_data.tools.clients import create_client


class TestCreateClient:
    """Tests for create_client()."""

    def test_creates_client_with_required_fields_only(self):
        """Minimal call — just a name. Everything else should default."""
        client = create_client("Alice Smith")

        assert client["name"] == "Alice Smith"
        assert client["status"] == "lead"  # default status
        assert client["email"] is None
        assert client["phone"] is None
        assert client["screening_data"] == {}  # JSONB default

    def test_creates_client_with_all_fields(self):
        """Full call — every optional field populated."""
        client = create_client(
            "Bob Jones",
            email="bob@example.com",
            phone="555-0101",
            address="123 Main St",
            source="instagram",
            screening_data={"rooms": 3, "style": "transitional"},
        )

        assert client["name"] == "Bob Jones"
        assert client["email"] == "bob@example.com"
        assert client["phone"] == "555-0101"
        assert client["address"] == "123 Main St"
        assert client["source"] == "instagram"
        assert client["screening_data"]["rooms"] == 3

    def test_returns_uuid_and_timestamps(self):
        """The returned dict should include Postgres-generated fields."""
        client = create_client("Carol White")

        assert client["id"] is not None  # UUID was generated
        assert client["created_at"] is not None
        assert client["updated_at"] is not None

    def test_logs_activity_on_creation(self):
        """Creating a client should also insert an activity_log entry."""
        from studio_data.db import get_connection

        client = create_client("Diana Prince", source="referral")

        with get_connection() as conn:
            log = conn.execute(
                """
                SELECT entity_type, entity_id, action, actor_name, metadata
                FROM activity_log
                WHERE entity_id = %(id)s
                """,
                {"id": client["id"]},
            ).fetchone()

        assert log is not None
        assert log["entity_type"] == "client"
        assert log["action"] == "created"
        assert log["actor_name"] == "create_client"

    def test_each_client_gets_unique_id(self):
        """Two clients with the same name should still get different UUIDs."""
        client1 = create_client("Same Name")
        client2 = create_client("Same Name")

        assert client1["id"] != client2["id"]
