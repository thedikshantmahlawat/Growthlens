"""
retention_analysis.py
----------------------
Classic cohort retention triangle: users grouped by their acquisition month
(first-ever event), then checked for whether they had ANY event on exactly
day+1, day+7, and day+30 after their first-seen date.

Definition used: "Day N retention" = active ON day N specifically (the
Amplitude/Mixpanel convention), not "active by day N" (a looser, cumulative
definition that inflates numbers and hides churn). This is the harder,
more honest bar and it's the one interviewers expect you to be able to
name and defend.

Cohorts that haven't yet reached day+30 relative to the dataset's last date
can't be measured for D30 -- those cells are left as NaN (rendered blank),
never silently coerced to 0 or skipped.
"""

import sqlite3
import pandas as pd

DB_PATH = "data/processed/growthlens.db"
DAY_OFFSETS = [1, 7, 30]


def get_conn():
    return sqlite3.connect(DB_PATH)


def retention_triangle(conn):
    users = pd.read_sql("SELECT user_id, first_seen_date, cohort_month FROM dim_users", conn,
                         parse_dates=["first_seen_date"])
    events = pd.read_sql("SELECT DISTINCT user_id, event_date FROM fact_events", conn,
                          parse_dates=["event_date"])

    last_data_date = events["event_date"].max()

    # set of (user_id, date) the user was active on, for fast lookup
    active_dates = events.groupby("user_id")["event_date"].apply(set).to_dict()

    rows = []
    cohort_sizes = users.groupby("cohort_month")["user_id"].count()

    for cohort, grp in users.groupby("cohort_month"):
        n_cohort = len(grp)
        row = {"cohort_month": cohort, "cohort_size": n_cohort}
        for offset in DAY_OFFSETS:
            retained, measurable = 0, 0
            for _, u in grp.iterrows():
                target_date = u["first_seen_date"] + pd.Timedelta(days=offset)
                if target_date > last_data_date:
                    continue  # not yet observable for this user
                measurable += 1
                if target_date in active_dates.get(u["user_id"], set()):
                    retained += 1
            row[f"D{offset}_measurable_n"] = measurable
            row[f"D{offset}_retention"] = (retained / measurable) if measurable > 0 else None
        rows.append(row)

    return pd.DataFrame(rows).sort_values("cohort_month")


def cumulative_retention(conn, windows=(7, 30)):
    """
    Softer, complementary metric to the strict D-day triangle: 'was the user
    active AT LEAST ONCE in the N days after their first-seen date' (not
    specifically ON day N). Reported alongside the strict triangle, never as
    a replacement -- conflating the two definitions is a common way analysts
    accidentally make retention look better than it is.
    """
    users = pd.read_sql("SELECT user_id, first_seen_date, cohort_month FROM dim_users", conn,
                         parse_dates=["first_seen_date"])
    events = pd.read_sql("SELECT DISTINCT user_id, event_date FROM fact_events", conn,
                          parse_dates=["event_date"])
    last_data_date = events["event_date"].max()
    active_dates = events.groupby("user_id")["event_date"].apply(set).to_dict()

    rows = []
    for cohort, grp in users.groupby("cohort_month"):
        row = {"cohort_month": cohort, "cohort_size": len(grp)}
        for w in windows:
            retained, measurable = 0, 0
            for _, u in grp.iterrows():
                window_end = u["first_seen_date"] + pd.Timedelta(days=w)
                if window_end > last_data_date:
                    continue
                measurable += 1
                user_active = active_dates.get(u["user_id"], set())
                window_days = {u["first_seen_date"] + pd.Timedelta(days=d) for d in range(1, w + 1)}
                if user_active & window_days:
                    retained += 1
            row[f"L{w}_measurable_n"] = measurable
            row[f"L{w}_retention"] = (retained / measurable) if measurable > 0 else None
        rows.append(row)
    return pd.DataFrame(rows).sort_values("cohort_month")


if __name__ == "__main__":
    conn = get_conn()
    triangle = retention_triangle(conn)
    cumulative = cumulative_retention(conn)

    pd.set_option("display.float_format", lambda x: f"{x:.1%}" if pd.notnull(x) and abs(x) < 2 else str(x))
    print("=== Strict retention triangle: active EXACTLY on day N (Amplitude/Mixpanel convention) ===")
    print(triangle[["cohort_month", "cohort_size", "D1_retention", "D7_retention", "D30_retention"]]
          .to_string(index=False))
    print("\n(blank/NaN = cohort hasn't reached that day-offset yet relative to the dataset's last date)")

    print("\n=== Cumulative retention: active AT LEAST ONCE within N days (softer, complementary view) ===")
    print(cumulative[["cohort_month", "cohort_size", "L7_retention", "L30_retention"]].to_string(index=False))
    print("\nNote: e-commerce D1/D7 by the strict same-day definition runs low by design -- shopping is")
    print("need-driven, not habitual like a social or gaming app, so most value in these numbers is in")
    print("the L30 window and in the loyal/casual/one-time mix behind the average, not the D1 headline.")
    conn.close()
