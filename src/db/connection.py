from __future__ import annotations

import getpass
import os

import psycopg
from psycopg.rows import dict_row


def get_connection() -> psycopg.Connection:
    """
    Create a connection to the experimental PostgreSQL database.

    Credentials are read from environment variables.

    Required / supported variables:
        PGHOST
        PGPORT
        PGDATABASE
        PGUSER
        PGPASSWORD

    The password is requested securely if PGPASSWORD is not set.
    """

    host = os.getenv(
        "PGHOST",
        "localhost",
    )

    port = os.getenv(
        "PGPORT",
        "5432",
    )

    database = os.getenv(
        "PGDATABASE",
        "dealer_ai_copilot",
    )

    user = os.getenv(
        "PGUSER",
        "postgres",
    )

    password = os.getenv(
        "PGPASSWORD"
    )

    if not password:
        password = getpass.getpass(
            f"PostgreSQL password for {user}: "
        )

    return psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,

        # Returning dictionaries will make later analytics and
        # agent-tool outputs easier to work with.
        row_factory=dict_row,
    )