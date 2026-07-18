"""
growth_metrics.py
-------------------
Daily active users, rolling 30-day MAU, stickiness (DAU/MAU), and the
new-vs-returning user split over time.
"""

import sqlite3
import pandas as pd

DB_PATH = "data/processed/growthlens.db"


def get_conn():
    return sqlite3.connect(DB_PATH)


def daily_active_users(conn):
    q = """
    SELECT event_date AS date, COUNT(DISTINCT user_id) AS dau
    FROM fact_events
    GROUP BY event_date
    ORDER BY event_date
    """
    return pd.read_sql(q, conn, parse_dates=["date"])


def new_vs_returning(conn):
    events = pd.read_sql("SELECT DISTINCT user_id, event_date FROM fact_events", conn, parse_dates=["event_date"])
    first_seen = events.groupby("user_id")["event_date"].min().rename("first_seen_date")
    events = events.join(first_seen, on="user_id")
    events["user_type"] = (events["event_date"] == events["first_seen_date"]).map({True: "new", False: "returning"})
    daily = events.groupby(["event_date", "user_type"])["user_id"].nunique().unstack(fill_value=0)
    daily = daily.reindex(columns=["new", "returning"], fill_value=0)
    daily["total"] = daily["new"] + daily["returning"]
    return daily.reset_index().rename(columns={"event_date": "date"})


def dau_mau_stickiness(conn, window=30):
    dau = daily_active_users(conn).set_index("date")["dau"]
    full_range = pd.date_range(dau.index.min(), dau.index.max(), freq="D")
    dau = dau.reindex(full_range, fill_value=0)

    events = pd.read_sql("SELECT DISTINCT user_id, event_date FROM fact_events", conn, parse_dates=["event_date"])
    mau_series = []
    for d in full_range:
        window_start = d - pd.Timedelta(days=window - 1)
        mau = events[(events["event_date"] >= window_start) & (events["event_date"] <= d)]["user_id"].nunique()
        mau_series.append(mau)

    out = pd.DataFrame({"date": full_range, "dau": dau.values, "mau_30d": mau_series})
    out["stickiness"] = out["dau"] / out["mau_30d"].replace(0, pd.NA)
    return out


if __name__ == "__main__":
    conn = get_conn()

    nvr = new_vs_returning(conn)
    nvr_monthly = nvr.set_index("date").resample("MS").sum()
    print("=== New vs returning active users, by month ===")
    print(nvr_monthly.to_string())

    dms = dau_mau_stickiness(conn)
    print("\n=== DAU / 30d-MAU / stickiness, monthly averages ===")
    monthly_avg = dms.set_index("date").resample("MS").mean(numeric_only=True)
    print(monthly_avg.round(3).to_string())

    print(f"\nOverall average stickiness (DAU/MAU) across the period: {dms['stickiness'].mean():.1%}")
    conn.close()
