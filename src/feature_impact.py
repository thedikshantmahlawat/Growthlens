"""
feature_impact.py
-------------------
Scenario: a one-click checkout flow shipped for electronics on 2025-12-01.
Question the business actually asked: "did the checkout change work?"

This module deliberately shows TWO answers to that question:

1. NAIVE BEFORE/AFTER on the treated group alone. This is the number a
   dashboard will show you by default, and it's wrong here -- it bakes in
   whatever else changed around the same date (in this case, a broad
   holiday-season lift in cart->purchase conversion that has nothing to do
   with the checkout change).

2. DIFF-IN-DIFF against a matched control group of categories that did NOT
   get the change (apparel + furniture), which nets out that shared
   seasonal shift and isolates the incremental effect actually attributable
   to the launch. Reported two ways: a plain 2x2 means table (intuitive),
   and an OLS regression with a treatment x post interaction term (formal
   estimate + standard error + p-value on that interaction).

Caveat stated explicitly, not just implied: this is an observational
before/after across category groups, not a randomized experiment. Category
groups differ in customer base and seasonal sensitivity, so a DiD estimate
is a stronger read than a naive before/after, but still not proof of
causality the way a proper randomized A/B test would be.
"""

import sqlite3
import pandas as pd
import statsmodels.formula.api as smf

DB_PATH = "data/processed/growthlens.db"
LAUNCH_DATE = "2025-12-01"
TREATMENT_GROUPS = {"electronics"}
CONTROL_GROUPS = {"apparel", "furniture"}


def get_conn():
    return sqlite3.connect(DB_PATH)


def cart_and_purchase_events(conn):
    q = """
    SELECT e.event_time, e.event_type, e.user_id, e.product_id, e.user_session,
           p.category_group
    FROM fact_events e
    JOIN dim_products p ON p.product_id = e.product_id
    WHERE e.event_type IN ('cart', 'purchase')
      AND p.category_group IN ({groups})
    """.format(groups=",".join(f"'{g}'" for g in TREATMENT_GROUPS | CONTROL_GROUPS))
    df = pd.read_sql(q, conn, parse_dates=["event_time"])
    df["group"] = df["category_group"].apply(lambda g: "treatment" if g in TREATMENT_GROUPS else "control")
    df["period"] = (df["event_time"] >= LAUNCH_DATE).map({True: "post", False: "pre"})
    return df


def cart_level_conversion(df):
    """
    One row per cart-add: did that (user, product, session) cart-add convert
    to a purchase of the same product in the same session? Grain matches how
    the data was generated (purchases are session-scoped), and is the
    correct unit for a conversion-rate DiD -- NOT raw event counts, which
    would conflate multi-view browsing intensity with actual conversion.
    """
    carts = df[df["event_type"] == "cart"][["user_id", "product_id", "user_session", "group", "period"]].copy()
    purchases = df[df["event_type"] == "purchase"][["user_id", "product_id", "user_session"]].copy()
    purchases["purchased"] = 1
    merged = carts.merge(purchases, on=["user_id", "product_id", "user_session"], how="left")
    merged["purchased"] = merged["purchased"].fillna(0)
    return merged


def naive_before_after(cart_conv):
    treated = cart_conv[cart_conv["group"] == "treatment"]
    pre = treated[treated["period"] == "pre"]["purchased"].mean()
    post = treated[treated["period"] == "post"]["purchased"].mean()
    return pre, post, post - pre


def diff_in_diff_table(cart_conv):
    tbl = cart_conv.groupby(["group", "period"])["purchased"].mean().unstack()
    tbl = tbl[["pre", "post"]]
    tbl["change"] = tbl["post"] - tbl["pre"]
    did_estimate = tbl.loc["treatment", "change"] - tbl.loc["control", "change"]
    return tbl, did_estimate


def diff_in_diff_regression(cart_conv):
    d = cart_conv.copy()
    d["treatment"] = (d["group"] == "treatment").astype(int)
    d["post"] = (d["period"] == "post").astype(int)
    model = smf.ols("purchased ~ treatment * post", data=d).fit(cov_type="HC1")
    return model


def weekly_conversion_series(cart_conv, df):
    d = cart_conv.merge(df[["user_id", "product_id", "user_session", "event_time"]].drop_duplicates(
        subset=["user_id", "product_id", "user_session"]), on=["user_id", "product_id", "user_session"], how="left")
    d["week"] = d["event_time"].dt.to_period("W").apply(lambda p: p.start_time)
    weekly = d.groupby(["week", "group"])["purchased"].mean().unstack()
    return weekly


if __name__ == "__main__":
    conn = get_conn()
    df = cart_and_purchase_events(conn)
    cart_conv = cart_level_conversion(df)

    print(f"Cart-adds analyzed: {len(cart_conv):,} "
          f"(treatment={len(cart_conv[cart_conv['group']=='treatment']):,}, "
          f"control={len(cart_conv[cart_conv['group']=='control']):,})")

    pre, post, naive_delta = naive_before_after(cart_conv)
    print(f"\n=== 1. Naive before/after (treatment group only) ===")
    print(f"Pre-launch cart->purchase:  {pre:.1%}")
    print(f"Post-launch cart->purchase: {post:.1%}")
    print(f"Naive delta: {naive_delta:+.1%}  <-- includes whatever else changed after Dec 1 too")

    tbl, did = diff_in_diff_table(cart_conv)
    print(f"\n=== 2. Diff-in-diff table ===")
    print(tbl.map(lambda x: f"{x:.1%}" if isinstance(x, float) else x).to_string())
    print(f"\nDiff-in-diff estimate: {did:+.1%}  <-- nets out the shared seasonal shift; this is the")
    print("defensible read on the checkout launch's true incremental effect.")

    model = diff_in_diff_regression(cart_conv)
    interaction = model.params["treatment:post"]
    se = model.bse["treatment:post"]
    pval = model.pvalues["treatment:post"]
    print(f"\n=== 3. OLS regression confirmation (purchased ~ treatment * post, robust SE) ===")
    print(f"treatment:post interaction coefficient: {interaction:+.4f}  (SE={se:.4f}, p={pval:.4g})")
    print("This coefficient IS the diff-in-diff estimate -- matches the table above by construction,")
    print("but the regression also gives a standard error and p-value on it.")

    print("\n=== Caveat ===")
    print("This is an observational before/after across category groups, not a randomized experiment.")
    print("Electronics and apparel/furniture shoppers may differ in ways correlated with the launch")
    print("timing (e.g. differential exposure to holiday deals). Treat the DiD estimate as a stronger,")
    print("but still not bulletproof, read -- the gold-standard follow-up would be a randomized holdback.")

    conn.close()
