from __future__ import annotations

import csv
import getpass
import os
from pathlib import Path

import psycopg

from src.dealer_data.config import CONFIG


# =====================================================================
# DATABASE CONFIGURATION
# =====================================================================
#
# Database connection details are read from environment variables.
#
# This is important because passwords must NOT be committed to Git.
#
# Supported variables:
#
#   PGHOST
#   PGPORT
#   PGDATABASE
#   PGUSER
#   PGPASSWORD
#
# Example PowerShell usage:
#
#   $env:PGDATABASE="dealer_ai_copilot"
#   $env:PGUSER="postgres"
#
# If PGPASSWORD is not supplied, this script will securely ask for it.
# =====================================================================


DEFAULT_HOST = "localhost"
DEFAULT_PORT = "5432"
DEFAULT_DATABASE = "dealer_ai_copilot"
DEFAULT_USER = "postgres"


# =====================================================================
# DATASET DEFINITIONS
# =====================================================================
#
# Order matters.
#
# Foreign-key dependencies are:
#
#   dealers
#      ↓
#   leads
#      ↓
#   applications
#      ↓
#   sales
#
# Therefore data must be inserted in exactly this order.
# =====================================================================


DATASETS = {
    "dealers": {
        "path": CONFIG.output_dir / "dealers.csv",
        "columns": [
            "dealer_id",
            "dealer_name",
            "country",
            "city",
            "active",
        ],
    },

    "leads": {
        "path": CONFIG.output_dir / "leads.csv",
        "columns": [
            "lead_id",
            "dealer_id",
            "country",
            "lead_date",
            "lead_source",
        ],
    },

    "applications": {
        "path": CONFIG.output_dir / "applications.csv",
        "columns": [
            "application_id",
            "lead_id",
            "dealer_id",
            "country",
            "application_date",
            "application_channel",
            "status",
        ],
    },

    "sales": {
        "path": CONFIG.output_dir / "sales.csv",
        "columns": [
            "sale_id",
            "application_id",
            "lead_id",
            "dealer_id",
            "country",
            "sale_date",
            "sale_amount_usd",
            "financing_bank",
        ],
    },
}


# =====================================================================
# CONNECTION HELPERS
# =====================================================================


def get_database_connection() -> psycopg.Connection:
    """
    Create a PostgreSQL connection.

    The password is taken from PGPASSWORD if available.

    If PGPASSWORD is not set, the user is prompted securely so the
    password is never written directly into this source file.
    """

    host = os.getenv(
        "PGHOST",
        DEFAULT_HOST,
    )

    port = os.getenv(
        "PGPORT",
        DEFAULT_PORT,
    )

    database = os.getenv(
        "PGDATABASE",
        DEFAULT_DATABASE,
    )

    user = os.getenv(
        "PGUSER",
        DEFAULT_USER,
    )

    password = os.getenv(
        "PGPASSWORD"
    )

    # Prompt securely rather than hard-coding credentials.
    if not password:
        password = getpass.getpass(
            f"PostgreSQL password for {user}: "
        )

    print("\nConnecting to PostgreSQL...")

    print(
        f"Host:     {host}\n"
        f"Port:     {port}\n"
        f"Database: {database}\n"
        f"User:     {user}"
    )

    return psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user=user,
        password=password,
    )


# =====================================================================
# FILE VALIDATION
# =====================================================================


def verify_dataset_files() -> None:
    """
    Confirm that every expected frozen CSV file exists before touching
    the database.

    We fail early rather than truncating PostgreSQL and later discovering
    that one of the CSV files is missing.
    """

    print("\nChecking dataset files...")

    missing_files: list[Path] = []

    for dataset_name, information in DATASETS.items():

        path = information["path"]

        if not path.exists():

            missing_files.append(
                path
            )

            print(
                f"[MISSING] {dataset_name}: {path}"
            )

        else:

            print(
                f"[FOUND]   {dataset_name}: {path}"
            )

    if missing_files:

        raise FileNotFoundError(
            "One or more required dataset files are missing: "
            f"{missing_files}"
        )


def verify_csv_schema() -> None:
    """
    Confirm that CSV headers match the expected PostgreSQL input schema.

    This helps catch accidental column additions, removals, or ordering
    changes before the database load begins.
    """

    print("\nChecking CSV schemas...")

    for dataset_name, information in DATASETS.items():

        path = information["path"]
        expected_columns = information["columns"]

        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as file:

            reader = csv.reader(file)

            actual_columns = next(
                reader
            )

        if actual_columns != expected_columns:

            raise ValueError(
                f"Schema mismatch for {dataset_name}.\n"
                f"Expected: {expected_columns}\n"
                f"Actual:   {actual_columns}"
            )

        print(
            f"[PASS] {dataset_name} schema"
        )


# =====================================================================
# ROW COUNT HELPERS
# =====================================================================


def count_csv_rows(
    path: Path,
) -> int:
    """
    Count data rows in a CSV file.

    The header row is excluded.
    """

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:

        reader = csv.reader(
            file
        )

        # Skip header.
        next(
            reader,
            None,
        )

        return sum(
            1
            for _ in reader
        )


def get_expected_counts() -> dict[str, int]:
    """
    Count source CSV rows before loading.

    These numbers become our post-load reference counts.
    """

    expected_counts: dict[
        str,
        int,
    ] = {}

    for dataset_name, information in DATASETS.items():

        expected_counts[
            dataset_name
        ] = count_csv_rows(
            information["path"]
        )

    return expected_counts


# =====================================================================
# DATABASE PREPARATION
# =====================================================================


def verify_tables_exist(
    connection: psycopg.Connection,
) -> None:
    """
    Confirm that all four experimental tables already exist.

    schema.sql should have been executed before running this loader.
    """

    required_tables = set(
        DATASETS.keys()
    )

    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE';
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query
        )

        existing_tables = {
            row[0]
            for row in cursor.fetchall()
        }

    missing_tables = (
        required_tables
        - existing_tables
    )

    if missing_tables:

        raise RuntimeError(
            "Required PostgreSQL tables are missing: "
            f"{sorted(missing_tables)}. "
            "Run database/schema.sql first."
        )

    print(
        "\n[PASS] Required PostgreSQL tables exist."
    )


def truncate_tables(
    connection: psycopg.Connection,
) -> None:
    """
    Remove previously loaded experimental records.

    TRUNCATE ... RESTART IDENTITY is used even though our current tables
    use UUID primary keys rather than serial IDs.

    CASCADE safely handles foreign-key dependencies.

    The operation occurs inside the same database transaction as loading.
    If loading fails, the transaction is rolled back.
    """

    print(
        "\nClearing existing experimental data..."
    )

    with connection.cursor() as cursor:

        cursor.execute(
            """
            TRUNCATE TABLE
                sales,
                applications,
                leads,
                dealers
            RESTART IDENTITY CASCADE;
            """
        )

    print(
        "[PASS] Existing data cleared."
    )


# =====================================================================
# POSTGRESQL COPY LOADING
# =====================================================================


def copy_csv_to_table(
    connection: psycopg.Connection,
    table_name: str,
    csv_path: Path,
    columns: list[str],
) -> None:
    """
    Load one CSV file into PostgreSQL using COPY FROM STDIN.

    PostgreSQL COPY is substantially faster and cleaner than executing
    thousands of individual INSERT statements.

    Column names are explicitly specified so the mapping between the
    frozen CSV schema and PostgreSQL schema is unambiguous.
    """

    column_list = ", ".join(
        columns
    )

    copy_sql = (
        f"COPY {table_name} "
        f"({column_list}) "
        "FROM STDIN "
        "WITH ("
        "FORMAT CSV, "
        "HEADER TRUE"
        ");"
    )

    print(
        f"Loading {table_name}..."
    )

    with connection.cursor() as cursor:

        with cursor.copy(
            copy_sql
        ) as copy:

            # Open as text because psycopg COPY accepts the CSV content
            # directly.
            with csv_path.open(
                "r",
                encoding="utf-8",
            ) as file:

                while True:

                    chunk = file.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    copy.write(
                        chunk
                    )

    print(
        f"[PASS] Loaded {table_name}"
    )


def load_all_datasets(
    connection: psycopg.Connection,
) -> None:
    """
    Load every visible dataset in foreign-key-safe order.
    """

    for dataset_name, information in DATASETS.items():

        copy_csv_to_table(
            connection=connection,
            table_name=dataset_name,
            csv_path=information["path"],
            columns=information["columns"],
        )


# =====================================================================
# POST-LOAD ROW COUNT VALIDATION
# =====================================================================


def validate_database_counts(
    connection: psycopg.Connection,
    expected_counts: dict[str, int],
) -> None:
    """
    Verify that PostgreSQL contains exactly the same number of rows as
    the frozen CSV files.

    A successful COPY operation alone is not sufficient evidence that
    the experimental database is correct.
    """

    print(
        "\n"
        + "=" * 70
    )

    print(
        "POSTGRESQL ROW COUNT VALIDATION"
    )

    print(
        "=" * 70
    )

    failures: list[str] = []

    with connection.cursor() as cursor:

        for table_name in DATASETS:

            cursor.execute(
                f"SELECT COUNT(*) FROM {table_name};"
            )

            database_count = cursor.fetchone()[0]

            expected_count = expected_counts[
                table_name
            ]

            passed = (
                database_count
                == expected_count
            )

            status = (
                "PASS"
                if passed
                else "FAIL"
            )

            print(
                f"[{status}] "
                f"{table_name:<15} "
                f"CSV={expected_count:,} "
                f"PostgreSQL={database_count:,}"
            )

            if not passed:

                failures.append(
                    table_name
                )

    if failures:

        raise ValueError(
            "Database row count validation failed for: "
            f"{failures}"
        )


# =====================================================================
# RELATIONAL INTEGRITY AUDIT
# =====================================================================


def run_integrity_query(
    connection: psycopg.Connection,
    name: str,
    query: str,
) -> bool:
    """
    Run an integrity query expected to return zero violations.

    Returns True when no invalid rows are found.
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query
        )

        violation_count = int(
            cursor.fetchone()[0]
        )

    passed = (
        violation_count
        == 0
    )

    status = (
        "PASS"
        if passed
        else "FAIL"
    )

    print(
        f"[{status}] "
        f"{name}: "
        f"{violation_count} violations"
    )

    return passed


def validate_relational_integrity(
    connection: psycopg.Connection,
) -> None:
    """
    Run post-load business-rule checks.

    PostgreSQL foreign keys already guarantee that referenced rows exist.

    These checks focus on relationships that ordinary foreign keys do not
    fully express, such as chronology and cross-table consistency.
    """

    print(
        "\n"
        + "=" * 70
    )

    print(
        "POSTGRESQL RELATIONAL INTEGRITY AUDIT"
    )

    print(
        "=" * 70
    )

    checks: list[
        tuple[str, str]
    ] = [

        # -------------------------------------------------------------
        # APPLICATION -> LEAD DEALER CONSISTENCY
        # -------------------------------------------------------------
        (
            "Application dealer matches originating lead",
            """
            SELECT COUNT(*)
            FROM applications a
            JOIN leads l
                ON a.lead_id = l.lead_id
            WHERE a.dealer_id <> l.dealer_id;
            """,
        ),

        # -------------------------------------------------------------
        # APPLICATION -> LEAD COUNTRY CONSISTENCY
        # -------------------------------------------------------------
        (
            "Application country matches originating lead",
            """
            SELECT COUNT(*)
            FROM applications a
            JOIN leads l
                ON a.lead_id = l.lead_id
            WHERE a.country <> l.country;
            """,
        ),

        # -------------------------------------------------------------
        # APPLICATION CHRONOLOGY
        # -------------------------------------------------------------
        (
            "Applications occur on or after leads",
            """
            SELECT COUNT(*)
            FROM applications a
            JOIN leads l
                ON a.lead_id = l.lead_id
            WHERE a.application_date < l.lead_date;
            """,
        ),

        # -------------------------------------------------------------
        # SALE MUST COME FROM APPROVED APPLICATION
        # -------------------------------------------------------------
        (
            "Sales originate only from approved applications",
            """
            SELECT COUNT(*)
            FROM sales s
            JOIN applications a
                ON s.application_id = a.application_id
            WHERE a.status <> 'approved';
            """,
        ),

        # -------------------------------------------------------------
        # SALE -> APPLICATION LEAD CONSISTENCY
        # -------------------------------------------------------------
        (
            "Sale lead matches application lead",
            """
            SELECT COUNT(*)
            FROM sales s
            JOIN applications a
                ON s.application_id = a.application_id
            WHERE s.lead_id <> a.lead_id;
            """,
        ),

        # -------------------------------------------------------------
        # SALE -> APPLICATION DEALER CONSISTENCY
        # -------------------------------------------------------------
        (
            "Sale dealer matches application dealer",
            """
            SELECT COUNT(*)
            FROM sales s
            JOIN applications a
                ON s.application_id = a.application_id
            WHERE s.dealer_id <> a.dealer_id;
            """,
        ),

        # -------------------------------------------------------------
        # SALE -> APPLICATION COUNTRY CONSISTENCY
        # -------------------------------------------------------------
        (
            "Sale country matches application country",
            """
            SELECT COUNT(*)
            FROM sales s
            JOIN applications a
                ON s.application_id = a.application_id
            WHERE s.country <> a.country;
            """,
        ),

        # -------------------------------------------------------------
        # SALE CHRONOLOGY
        # -------------------------------------------------------------
        (
            "Sales occur on or after applications",
            """
            SELECT COUNT(*)
            FROM sales s
            JOIN applications a
                ON s.application_id = a.application_id
            WHERE s.sale_date < a.application_date;
            """,
        ),

        # -------------------------------------------------------------
        # FULL FUNNEL DEALER CONSISTENCY
        # -------------------------------------------------------------
        (
            "Sale dealer matches original lead dealer",
            """
            SELECT COUNT(*)
            FROM sales s
            JOIN leads l
                ON s.lead_id = l.lead_id
            WHERE s.dealer_id <> l.dealer_id;
            """,
        ),

        # -------------------------------------------------------------
        # POSITIVE SALES VALUES
        # -------------------------------------------------------------
        (
            "Sale amounts are positive",
            """
            SELECT COUNT(*)
            FROM sales
            WHERE sale_amount_usd <= 0;
            """,
        ),
    ]

    failed_checks: list[str] = []

    for name, query in checks:

        passed = run_integrity_query(
            connection=connection,
            name=name,
            query=query,
        )

        if not passed:

            failed_checks.append(
                name
            )

    if failed_checks:

        raise ValueError(
            "PostgreSQL integrity validation failed: "
            f"{failed_checks}"
        )


# =====================================================================
# ANALYTICAL SANITY CHECK
# =====================================================================


def print_database_summary(
    connection: psycopg.Connection,
) -> None:
    """
    Print a small SQL-derived summary from PostgreSQL.

    This is our first confirmation that analytical SQL over the loaded
    database returns the expected funnel structure.
    """

    query = """
        SELECT
            (SELECT COUNT(*) FROM dealers) AS dealers,
            (SELECT COUNT(*) FROM leads) AS leads,
            (SELECT COUNT(*) FROM applications) AS applications,
            (
                SELECT COUNT(*)
                FROM applications
                WHERE status = 'approved'
            ) AS approved_applications,
            (SELECT COUNT(*) FROM sales) AS sales,
            (
                SELECT ROUND(
                    SUM(sale_amount_usd),
                    2
                )
                FROM sales
            ) AS total_revenue_usd;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query
        )

        row = cursor.fetchone()

    print(
        "\n"
        + "=" * 70
    )

    print(
        "POSTGRESQL DATASET SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        f"Dealers:               {row[0]:,}"
    )

    print(
        f"Leads:                 {row[1]:,}"
    )

    print(
        f"Applications:          {row[2]:,}"
    )

    print(
        f"Approved applications: {row[3]:,}"
    )

    print(
        f"Sales:                 {row[4]:,}"
    )

    print(
        f"Revenue USD:           {row[5]:,.2f}"
    )


# =====================================================================
# DATABASE STATISTICS
# =====================================================================


def analyze_database(
    connection: psycopg.Connection,
) -> None:
    """
    Refresh PostgreSQL query-planner statistics after bulk loading.

    ANALYZE helps PostgreSQL make better decisions when executing the
    analytical SQL queries used later in our benchmark.
    """

    print(
        "\nUpdating PostgreSQL planner statistics..."
    )

    with connection.cursor() as cursor:

        cursor.execute(
            "ANALYZE dealers;"
        )

        cursor.execute(
            "ANALYZE leads;"
        )

        cursor.execute(
            "ANALYZE applications;"
        )

        cursor.execute(
            "ANALYZE sales;"
        )

    print(
        "[PASS] PostgreSQL statistics updated."
    )


# =====================================================================
# MASTER LOADING PIPELINE
# =====================================================================


def main() -> None:
    """
    Execute the complete CSV -> PostgreSQL loading pipeline.

    Process
    -------

    1. Check frozen CSV files.
    2. Check CSV schemas.
    3. Determine expected row counts.
    4. Connect to PostgreSQL.
    5. Verify expected database tables.
    6. Begin transaction.
    7. Clear existing experimental data.
    8. Load dealers.
    9. Load leads.
    10. Load applications.
    11. Load sales.
    12. Validate row counts.
    13. Validate relational/business integrity.
    14. Commit transaction.
    15. Run ANALYZE.
    16. Print database summary.

    If any failure occurs before commit, PostgreSQL rolls back the
    transaction so we do not leave a partially loaded experiment.
    """

    print(
        "\n"
        + "=" * 70
    )

    print(
        "DEALER AI COPILOT 2.0"
    )

    print(
        "POSTGRESQL DATA LOADER"
    )

    print(
        "=" * 70
    )

    # ---------------------------------------------------------------
    # VERIFY SOURCE DATA BEFORE MODIFYING DATABASE
    # ---------------------------------------------------------------

    verify_dataset_files()

    verify_csv_schema()

    expected_counts = (
        get_expected_counts()
    )

    print(
        "\nExpected source row counts:"
    )

    for (
        dataset_name,
        count,
    ) in expected_counts.items():

        print(
            f"  {dataset_name:<15} "
            f"{count:,}"
        )

    # ---------------------------------------------------------------
    # CONNECT
    # ---------------------------------------------------------------

    connection = (
        get_database_connection()
    )

    try:

        verify_tables_exist(
            connection
        )

        # -----------------------------------------------------------
        # LOAD INSIDE A SINGLE TRANSACTION
        # -----------------------------------------------------------

        print(
            "\nBeginning transactional load..."
        )

        try:

            truncate_tables(
                connection
            )

            load_all_datasets(
                connection
            )

            validate_database_counts(
                connection,
                expected_counts,
            )

            validate_relational_integrity(
                connection
            )

            # Everything succeeded.
            connection.commit()

            print(
                "\n[PASS] Database transaction committed."
            )

        except Exception:

            # Any failure restores the previous database state.
            connection.rollback()

            print(
                "\n[ROLLBACK] Database load failed. "
                "No partial load was committed."
            )

            raise

        # -----------------------------------------------------------
        # POST-COMMIT OPERATIONS
        # -----------------------------------------------------------

        analyze_database(
            connection
        )

        # ANALYZE also runs transactionally under psycopg.
        connection.commit()

        print_database_summary(
            connection
        )

        print(
            "\n"
            + "=" * 70
        )

        print(
            "POSTGRESQL LOAD COMPLETED SUCCESSFULLY"
        )

        print(
            "=" * 70
        )

    finally:

        connection.close()

        print(
            "\nPostgreSQL connection closed."
        )


if __name__ == "__main__":
    main()