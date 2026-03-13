"""Tool functions for managing clients.

Clients are the top-level entity in StudioOS — every project belongs
to a client, and the client's status tracks where they are in the
sales pipeline (lead → qualified → proposal_sent → contracted → active).

These functions are the "tool layer" that agents will call. They enforce
business rules and log every action to the activity_log for auditability.
"""

from typing import Any

from studio_data.db import get_connection


def create_client(
    name: str,
    *,
    email: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    source: str | None = None,
    screening_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new client with status 'lead'.

    Every new client starts as a lead. The agent system will advance
    their status as they move through screening, sales, and onboarding.

    Args:
        name: Client's full name (required).
        email: Contact email.
        phone: Contact phone number.
        address: Client's address (often the project site).
        source: How the client found us (e.g., "referral", "instagram").
        screening_data: Freeform dict of screening responses (stored as JSONB).

    Returns:
        The newly created client row as a dict, including the generated
        UUID and timestamps.
    """
    with get_connection() as conn:
        # Insert the client — Postgres handles the UUID and timestamps
        row = conn.execute(
            """
            INSERT INTO clients (name, email, phone, address, source, screening_data)
            VALUES (%(name)s, %(email)s, %(phone)s, %(address)s, %(source)s,
                    COALESCE(%(screening_data)s::jsonb, '{}'))
            RETURNING *
            """,
            {
                "name": name,
                "email": email,
                "phone": phone,
                "address": address,
                "source": source,
                "screening_data": _json_or_none(screening_data),
            },
        ).fetchone()

        assert row is not None, "INSERT RETURNING should always return a row"

        # Log the creation in the activity trail — this is how we track
        # who/what created every entity in the system
        conn.execute(
            """
            INSERT INTO activity_log
                (entity_type, entity_id, action,
                 actor_type, actor_name, metadata)
            VALUES
                ('client', %(entity_id)s, 'created',
                 %(actor_type)s, %(actor_name)s, %(metadata)s::jsonb)
            """,
            {
                "entity_id": row["id"],
                "actor_type": "system",
                "actor_name": "create_client",
                "metadata": f'{{"source": "{source or "unknown"}"}}',
            },
        )

    return dict(row)


def _json_or_none(data: dict[str, Any] | None) -> str | None:
    """Convert a dict to a JSON string for Postgres, or None if empty.

    psycopg can't pass a Python dict directly to a ::jsonb cast —
    it needs to be a JSON string. This helper handles the conversion.
    """
    if data is None:
        return None
    import json

    return json.dumps(data)
