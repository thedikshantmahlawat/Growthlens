"""
funnel_analysis.py
-------------------
Stage-by-stage view -> cart -> purchase funnel, overall and sliced by
category group and by month.

Methodology note: this is an event-based funnel (distinct users reaching
each stage within a period), not a strict same-session sequential funnel.
That's a deliberate, standard simplification -- real shoppers often cart an
item in one session and buy it days later, so requiring strict in-session
sequence would undercount genuine conversions. Documented here so the
definition is explicit and defensible, not implicit.
"""

import sqlite3
import pandas as pd

DB_PATH = "data/processed/growthlens.db"
STAGES = ["view", "cart", "purchase"]


def get_conn():
    return sqlite3.connect(DB_PATH)


def overall_funnel(conn):
    q = """
    SELECT event_type, COUNT(DISTINCT user_id) AS distinct_users, COUNT(*) AS n_events
    FROM fact_events
    GROUP BY event_type
    """
    df = pd.read_sql(q, conn).set_index("event_type").reindex(STAGES)
    df["conversion_from_prev"] = df["distinct_users"] / df["distinct_users"].shift(1)
    df["conversion_from_view"] = df["distinct_users"] / df.loc["view", "distinct_users"]
    return df.reset_index()


def funnel_by_category_group(conn):
    q = """
    SELECT p.category_group, e.event_type, COUNT(DISTINCT e.user_id) AS distinct_users
    FROM fact_events e
    JOIN dim_products p ON p.product_id = e.product_id
    GROUP BY p.category_group, e.event_type
    """
    df = pd.read_sql(q, conn)
    pivot = df.pivot(index="category_group", columns="event_type", values="distinct_users").fillna(0)
    pivot = pivot[STAGES]
    pivot["view_to_cart"] = pivot["cart"] / pivot["view"]
    pivot["cart_to_purchase"] = pivot["purchase"] / pivot["cart"]
    pivot["view_to_purchase"] = pivot["purchase"] / pivot["view"]
    return pivot.sort_values("view", ascending=False).reset_index()


def funnel_by_month(conn):
    q = """
    SELECT d.month_label, e.event_type, COUNT(DISTINCT e.user_id) AS distinct_users
    FROM fact_events e
    JOIN dim_dates d ON d.date = e.event_date
    GROUP BY d.month_label, e.event_type
    """
    df = pd.read_sql(q, conn)
    pivot = df.pivot(index="month_label", columns="event_type", values="distinct_users").fillna(0)
    pivot = pivot[STAGES]
    pivot["view_to_cart"] = pivot["cart"] / pivot["view"]
    pivot["cart_to_purchase"] = pivot["purchase"] / pivot["cart"]
    pivot["view_to_purchase"] = pivot["purchase"] / pivot["view"]
    return pivot.reset_index()


if __name__ == "__main__":
    conn = get_conn()

    print("=== Overall funnel (distinct users) ===")
    overall = overall_funnel(conn)
    print(overall.to_string(index=False))

    print("\n=== Funnel by category group ===")
    by_cat = funnel_by_category_group(conn)
    print(by_cat.to_string(index=False))

    print("\n=== Funnel by month ===")
    by_month = funnel_by_month(conn)
    print(by_month.to_string(index=False))

    conn.close()
