"""
build_database.py
------------------
Loads data/raw/events.csv (any file matching the REES46 schema -- synthetic
or the real Kaggle CSV, see README) into a star-schema SQLite database at
data/processed/growthlens.db.

Run after generate_data.py (or after dropping a real Kaggle CSV into
data/raw/ with the same column names).
"""

import pandas as pd
import sqlite3
import os

RAW_PATH = "data/raw/events.csv"
DB_PATH = "data/processed/growthlens.db"
SCHEMA_PATH = "sql/schema.sql"


def main():
    print(f"Loading {RAW_PATH} ...")
    df = pd.read_csv(RAW_PATH, parse_dates=["event_time"])
    df["event_date"] = df["event_time"].dt.date.astype(str)

    # category_group: top-level token of category_code (electronics.laptop -> electronics)
    df["category_group"] = df["category_code"].str.split(".").str[0]

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)

    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    # --- dim_dates: every calendar day spanned by the data ---
    all_dates = pd.date_range(df["event_time"].dt.date.min(), df["event_time"].dt.date.max(), freq="D")
    dim_dates = pd.DataFrame({"date": all_dates.astype(str)})
    dim_dates["year"] = all_dates.year
    dim_dates["month"] = all_dates.month
    dim_dates["day"] = all_dates.day
    dim_dates["month_label"] = all_dates.strftime("%Y-%m")
    dim_dates["day_of_week"] = all_dates.dayofweek
    dim_dates["is_weekend"] = (all_dates.dayofweek >= 5).astype(int)
    dim_dates.to_sql("dim_dates", conn, if_exists="append", index=False)

    # --- dim_products: one row per product_id (attributes are static here) ---
    dim_products = (df[["product_id", "category_id", "category_code", "category_group", "brand", "price"]]
                     .drop_duplicates("product_id")
                     .reset_index(drop=True))
    dim_products.to_sql("dim_products", conn, if_exists="append", index=False)

    # --- dim_users: first_seen + cohort_month derived from the events themselves ---
    first_seen = df.groupby("user_id")["event_time"].min().reset_index()
    first_seen.columns = ["user_id", "first_seen_ts"]
    first_seen["first_seen_date"] = first_seen["first_seen_ts"].dt.date.astype(str)
    first_seen["cohort_month"] = first_seen["first_seen_ts"].dt.strftime("%Y-%m")
    dim_users = first_seen[["user_id", "first_seen_date", "cohort_month"]]
    dim_users.to_sql("dim_users", conn, if_exists="append", index=False)

    # --- fact_events ---
    fact = df[["event_time", "event_date", "event_type", "user_id", "product_id", "user_session"]].copy()
    fact["event_time"] = fact["event_time"].astype(str)
    fact.to_sql("fact_events", conn, if_exists="append", index=False)

    conn.commit()

    # sanity checks
    cur = conn.cursor()
    for tbl in ["dim_dates", "dim_products", "dim_users", "fact_events"]:
        n = cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"{tbl}: {n:,} rows")

    conn.close()
    print(f"\nDatabase built at {DB_PATH}")


if __name__ == "__main__":
    main()
