from __future__ import annotations

from src.db.connection import get_connection


def print_section(title: str) -> None:
    """Print a readable terminal section heading."""

    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    """
    Run deterministic analytical queries against PostgreSQL.

    This script verifies that:

    1. the expected experimental tables exist;
    2. hidden research-truth tables do not exist;
    3. basic aggregations work;
    4. joins across the business funnel work;
    5. temporal analytics work.

    These are database sanity checks, not the final AI benchmark.
    """

    connection = get_connection()

    try:

        # =============================================================
        # 1. TABLE AUDIT
        # =============================================================

        print_section(
            "DATABASE TABLES"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name;
                """
            )

            tables = [
                row["table_name"]
                for row in cursor.fetchall()
            ]

        for table in tables:
            print(table)

        expected_tables = {
            "dealers",
            "leads",
            "applications",
            "sales",
        }

        if set(tables) != expected_tables:

            raise ValueError(
                "Unexpected database tables detected. "
                f"Expected {sorted(expected_tables)}, "
                f"found {sorted(tables)}"
            )

        print(
            "\n[PASS] Experimental database contains "
            "exactly the expected tables."
        )

        # =============================================================
        # 2. BASIC TABLE COUNTS
        # =============================================================

        print_section(
            "TABLE COUNTS"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM dealers)
                        AS dealers,

                    (SELECT COUNT(*) FROM leads)
                        AS leads,

                    (SELECT COUNT(*) FROM applications)
                        AS applications,

                    (
                        SELECT COUNT(*)
                        FROM applications
                        WHERE status = 'approved'
                    )
                        AS approved_applications,

                    (SELECT COUNT(*) FROM sales)
                        AS sales;
                """
            )

            counts = cursor.fetchone()

        for key, value in counts.items():
            print(
                f"{key:<25} {value:,}"
            )

        # =============================================================
        # 3. OVERALL BUSINESS FUNNEL
        # =============================================================

        print_section(
            "OVERALL BUSINESS FUNNEL"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                WITH funnel AS (
                    SELECT
                        (SELECT COUNT(*) FROM leads)::numeric
                            AS leads,

                        (SELECT COUNT(*) FROM applications)::numeric
                            AS applications,

                        (
                            SELECT COUNT(*)
                            FROM applications
                            WHERE status = 'approved'
                        )::numeric
                            AS approved,

                        (SELECT COUNT(*) FROM sales)::numeric
                            AS sales
                )

                SELECT
                    leads,
                    applications,
                    approved,
                    sales,

                    ROUND(
                        applications / NULLIF(leads, 0),
                        4
                    ) AS lead_to_application_rate,

                    ROUND(
                        approved / NULLIF(applications, 0),
                        4
                    ) AS application_approval_rate,

                    ROUND(
                        sales / NULLIF(approved, 0),
                        4
                    ) AS approved_to_sale_rate,

                    ROUND(
                        sales / NULLIF(leads, 0),
                        4
                    ) AS lead_to_sale_rate

                FROM funnel;
                """
            )

            funnel = cursor.fetchone()

        for key, value in funnel.items():
            print(
                f"{key:<30} {value}"
            )

        # =============================================================
        # 4. COUNTRY-LEVEL FUNNEL
        # =============================================================

        print_section(
            "COUNTRY-LEVEL ANALYTICS"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                WITH
                dealer_counts AS (
                    SELECT
                        country,
                        COUNT(*) AS dealers
                    FROM dealers
                    GROUP BY country
                ),

                lead_counts AS (
                    SELECT
                        country,
                        COUNT(*) AS leads
                    FROM leads
                    GROUP BY country
                ),

                application_counts AS (
                    SELECT
                        country,
                        COUNT(*) AS applications,
                        COUNT(*) FILTER (
                            WHERE status = 'approved'
                        ) AS approved
                    FROM applications
                    GROUP BY country
                ),

                sale_counts AS (
                    SELECT
                        country,
                        COUNT(*) AS sales,
                        ROUND(
                            SUM(sale_amount_usd),
                            2
                        ) AS revenue_usd
                    FROM sales
                    GROUP BY country
                )

                SELECT
                    d.country,
                    d.dealers,
                    l.leads,
                    a.applications,
                    a.approved,
                    s.sales,
                    s.revenue_usd,

                    ROUND(
                        a.applications::numeric
                        / NULLIF(l.leads, 0),
                        4
                    ) AS lead_to_application_rate,

                    ROUND(
                        s.sales::numeric
                        / NULLIF(l.leads, 0),
                        4
                    ) AS lead_to_sale_rate

                FROM dealer_counts d

                JOIN lead_counts l
                    USING (country)

                JOIN application_counts a
                    USING (country)

                JOIN sale_counts s
                    USING (country)

                ORDER BY d.country;
                """
            )

            rows = cursor.fetchall()

        for row in rows:

            print(
                f"{row['country']} | "
                f"dealers={row['dealers']} | "
                f"leads={row['leads']:,} | "
                f"applications={row['applications']:,} | "
                f"sales={row['sales']:,} | "
                f"lead→sale={row['lead_to_sale_rate']} | "
                f"revenue=${row['revenue_usd']:,.2f}"
            )

        # =============================================================
        # 5. TOP DEALERS BY SALES
        # =============================================================

        print_section(
            "TOP 10 DEALERS BY SALES"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    d.dealer_name,
                    d.country,
                    COUNT(s.sale_id) AS sales,
                    ROUND(
                        SUM(s.sale_amount_usd),
                        2
                    ) AS revenue_usd

                FROM dealers d

                JOIN sales s
                    ON d.dealer_id = s.dealer_id

                GROUP BY
                    d.dealer_id,
                    d.dealer_name,
                    d.country

                ORDER BY
                    sales DESC

                LIMIT 10;
                """
            )

            rows = cursor.fetchall()

        for position, row in enumerate(
            rows,
            start=1,
        ):

            print(
                f"{position:>2}. "
                f"{row['dealer_name']} "
                f"({row['country']}) | "
                f"sales={row['sales']} | "
                f"revenue=${row['revenue_usd']:,.2f}"
            )

        # =============================================================
        # 6. MONTHLY ANALYTICS
        # =============================================================

        print_section(
            "MONTHLY SALES - 2025"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    DATE_TRUNC(
                        'month',
                        sale_date
                    )::date AS month,

                    COUNT(*) AS sales,

                    ROUND(
                        SUM(sale_amount_usd),
                        2
                    ) AS revenue_usd

                FROM sales

                WHERE sale_date >= DATE '2025-01-01'
                  AND sale_date < DATE '2026-01-01'

                GROUP BY
                    DATE_TRUNC(
                        'month',
                        sale_date
                    )

                ORDER BY month;
                """
            )

            rows = cursor.fetchall()

        for row in rows:

            print(
                f"{row['month']} | "
                f"sales={row['sales']:,} | "
                f"revenue=${row['revenue_usd']:,.2f}"
            )

        # =============================================================
        # 7. MULTI-STAGE DEALER PERFORMANCE
        # =============================================================

        print_section(
            "SAMPLE DEALER FUNNEL PERFORMANCE"
        )

        with connection.cursor() as cursor:

            cursor.execute(
                """
                WITH dealer_funnel AS (

                    SELECT
                        d.dealer_id,
                        d.dealer_name,
                        d.country,

                        COUNT(
                            DISTINCT l.lead_id
                        ) AS leads,

                        COUNT(
                            DISTINCT a.application_id
                        ) AS applications,

                        COUNT(
                            DISTINCT a.application_id
                        ) FILTER (
                            WHERE a.status = 'approved'
                        ) AS approved,

                        COUNT(
                            DISTINCT s.sale_id
                        ) AS sales

                    FROM dealers d

                    LEFT JOIN leads l
                        ON d.dealer_id = l.dealer_id

                    LEFT JOIN applications a
                        ON l.lead_id = a.lead_id

                    LEFT JOIN sales s
                        ON a.application_id
                        = s.application_id

                    GROUP BY
                        d.dealer_id,
                        d.dealer_name,
                        d.country
                )

                SELECT
                    dealer_name,
                    country,
                    leads,
                    applications,
                    approved,
                    sales,

                    ROUND(
                        applications::numeric
                        / NULLIF(leads, 0),
                        4
                    ) AS application_rate,

                    ROUND(
                        approved::numeric
                        / NULLIF(applications, 0),
                        4
                    ) AS approval_rate,

                    ROUND(
                        sales::numeric
                        / NULLIF(approved, 0),
                        4
                    ) AS sale_conversion_rate

                FROM dealer_funnel

                ORDER BY sales DESC

                LIMIT 10;
                """
            )

            rows = cursor.fetchall()

        for row in rows:

            print(
                f"{row['dealer_name']} | "
                f"{row['country']} | "
                f"leads={row['leads']} | "
                f"apps={row['applications']} | "
                f"approved={row['approved']} | "
                f"sales={row['sales']} | "
                f"app_rate={row['application_rate']} | "
                f"approval_rate={row['approval_rate']} | "
                f"sale_rate={row['sale_conversion_rate']}"
            )

        print_section(
            "DATABASE VERIFICATION COMPLETE"
        )

        print(
            "Database is ready for experimental system development."
        )

    finally:

        connection.close()


if __name__ == "__main__":
    main()