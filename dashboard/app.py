"""
GrowthLens dashboard
---------------------
Run from the project root:  streamlit run dashboard/app.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

from src import funnel_analysis as fa
from src import retention_analysis as ra
from src import growth_metrics as gm
from src import feature_impact as fi

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "growthlens.db")

st.set_page_config(page_title="GrowthLens", page_icon="\U0001F4C8", layout="wide")

PALETTE = {
    "ink": "#1C2333", "slate": "#5B6478", "accent": "#E8734A",
    "accent2": "#2E7D6B", "bg_card": "#F7F5F1", "grid": "#E4E1DA",
}

st.markdown(f"""
<style>
    .stApp {{ background-color: #FCFBF9; }}
    h1, h2, h3 {{ color: {PALETTE['ink']}; font-family: 'Georgia', serif; }}
    [data-testid="stMetricValue"] {{ color: {PALETTE['ink']}; font-weight: 700; }}
    [data-testid="stMetricLabel"] {{ color: {PALETTE['slate']}; }}
    div[data-testid="stMetric"] {{
        background-color: {PALETTE['bg_card']}; border: 1px solid {PALETTE['grid']};
        border-radius: 10px; padding: 14px 16px;
    }}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


@st.cache_data
def load_overview(_conn):
    overall = fa.overall_funnel(_conn)
    triangle = ra.retention_triangle(_conn)
    cum = ra.cumulative_retention(_conn)
    dms = gm.dau_mau_stickiness(_conn)
    df = fi.cart_and_purchase_events(_conn)
    cart_conv = fi.cart_level_conversion(df)
    _, did = fi.diff_in_diff_table(cart_conv)
    return overall, triangle, cum, dms, did


conn = get_connection()
overall, triangle, cum, dms, did = load_overview(conn)

st.title("GrowthLens")
st.caption("Funnel, retention, growth, and feature-impact analytics on e-commerce clickstream data")

tabs = st.tabs(["Overview", "Funnel", "Retention", "Growth", "Feature Impact"])

# ---------------------------------------------------------------------------
# OVERVIEW
# ---------------------------------------------------------------------------
with tabs[0]:
    n_users = int(overall.loc[overall["event_type"] == "view", "distinct_users"].iloc[0])
    view_to_purchase = overall.loc[overall["event_type"] == "purchase", "conversion_from_view"].iloc[0]
    l30_avg = cum["L30_retention"].dropna().mean()
    stickiness_stable = dms[dms["date"] >= "2025-12-01"]["stickiness"].mean()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Users in dataset", f"{n_users:,}")
    c2.metric("View \u2192 purchase", f"{view_to_purchase:.1%}")
    c3.metric("Avg L30 retention", f"{l30_avg:.1%}")
    c4.metric("Checkout DiD effect", f"{did:+.1%}", help="Diff-in-diff estimate of the Dec 1 checkout launch")

    st.markdown("---")
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.subheader("What this dashboard covers")
        st.markdown("""
- **Funnel** \u2014 view \u2192 cart \u2192 purchase drop-off, overall / by category / by month
- **Retention** \u2014 cohort triangle (D1/D7/D30 exact-day, plus L7/L30 cumulative)
- **Growth** \u2014 DAU, 30-day MAU, stickiness, new-vs-returning split
- **Feature Impact** \u2014 naive before/after vs. diff-in-diff on a simulated checkout launch
        """)
    with col_b:
        st.subheader("Data note")
        st.info(
            "This dashboard runs on a **synthetic** dataset built to the exact schema of the real "
            "REES46 'eCommerce behavior data from multi-category store' Kaggle dataset, since the "
            "real file is Kaggle-gated and multiple GB per month. Every query below runs unchanged "
            "against the real file too \u2014 see README for the swap-in steps.",
            icon="\u2139\ufe0f",
        )

# ---------------------------------------------------------------------------
# FUNNEL
# ---------------------------------------------------------------------------
with tabs[1]:
    st.subheader("View \u2192 Cart \u2192 Purchase")
    fig = go.Figure(go.Funnel(
        y=overall["event_type"].str.capitalize(),
        x=overall["distinct_users"],
        marker={"color": [PALETTE["ink"], PALETTE["slate"], PALETTE["accent"]]},
        textinfo="value+percent initial",
    ))
    fig.update_layout(height=380, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**By category group**")
        by_cat = fa.funnel_by_category_group(conn)
        fig2 = px.bar(by_cat, x="category_group", y="view_to_purchase",
                      color_discrete_sequence=[PALETTE["accent2"]])
        fig2.update_layout(yaxis_tickformat=".0%", height=340, margin=dict(t=10))
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("Electronics converts highest end-to-end \u2014 see Feature Impact for why.")
    with col2:
        st.markdown("**By month**")
        by_month = fa.funnel_by_month(conn)
        fig3 = px.line(by_month, x="month_label", y=["view_to_cart", "cart_to_purchase", "view_to_purchase"],
                        markers=True, color_discrete_sequence=[PALETTE["slate"], PALETTE["accent"], PALETTE["ink"]])
        fig3.update_layout(yaxis_tickformat=".0%", height=340, margin=dict(t=10), legend_title="")
        st.plotly_chart(fig3, use_container_width=True)

    with st.expander("Methodology"):
        st.markdown(
            "Event-based funnel: distinct users reaching each stage within the period, not a strict "
            "same-session sequential funnel. Real shoppers often cart in one session and buy days "
            "later \u2014 requiring strict in-session order would undercount genuine conversions."
        )

# ---------------------------------------------------------------------------
# RETENTION
# ---------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Cohort retention triangle")
    heat_df = triangle.set_index("cohort_month")[["D1_retention", "D7_retention", "D30_retention"]]
    heat_df.columns = ["D1", "D7", "D30"]
    fig4 = px.imshow(heat_df.astype(float), text_auto=".1%", color_continuous_scale="Oranges", aspect="auto")
    fig4.update_layout(height=300, margin=dict(t=10))
    st.plotly_chart(fig4, use_container_width=True)
    st.caption("Blank cell = that cohort hasn't reached that day-offset yet relative to the data's last date.")

    st.markdown("**Cumulative view (active at least once within N days)**")
    cum_disp = cum.set_index("cohort_month")[["L7_retention", "L30_retention"]]
    cum_disp.columns = ["L7", "L30"]
    fig5 = px.imshow(cum_disp.astype(float), text_auto=".1%", color_continuous_scale="Teal", aspect="auto")
    fig5.update_layout(height=260, margin=dict(t=10))
    st.plotly_chart(fig5, use_container_width=True)

    with st.expander("Why D1/D7 look low, and which number to actually use"):
        st.markdown("""
"Day N retention" here means active **exactly on** day N (the Amplitude/Mixpanel convention) \u2014
a harder, more honest bar than "active by day N." E-commerce D1/D7 runs low by this definition
because shopping is need-driven, not habitual like a social or gaming app \u2014 most of the signal
worth acting on is in **L30** (\u224847\u201349% return at least once in 30 days) and in the mix of
loyal/casual/one-time visitors behind that average, not the D1 headline.
        """)

# ---------------------------------------------------------------------------
# GROWTH
# ---------------------------------------------------------------------------
with tabs[3]:
    st.subheader("DAU, 30-day MAU, and stickiness")
    fig6 = go.Figure()
    fig6.add_trace(go.Scatter(x=dms["date"], y=dms["mau_30d"], name="30d MAU", fill="tozeroy",
                               line=dict(color=PALETTE["grid"])))
    fig6.add_trace(go.Scatter(x=dms["date"], y=dms["dau"], name="DAU", line=dict(color=PALETTE["accent"])))
    fig6.update_layout(height=360, margin=dict(t=10), legend_title="")
    st.plotly_chart(fig6, use_container_width=True)

    stable = dms[dms["date"] >= "2025-12-01"]
    st.metric("Stable-period stickiness (Dec\u2013Feb avg, DAU/MAU)", f"{stable['stickiness'].mean():.1%}")
    st.caption(
        "November is excluded from this average: its 30-day MAU window partly extends before the "
        "dataset starts, which artificially shrinks the denominator and inflates that month's ratio."
    )

    st.markdown("**New vs. returning active users**")
    nvr = gm.new_vs_returning(conn)
    fig7 = px.area(nvr, x="date", y=["new", "returning"],
                    color_discrete_sequence=[PALETTE["accent"], PALETTE["slate"]])
    fig7.update_layout(height=320, margin=dict(t=10), legend_title="")
    st.plotly_chart(fig7, use_container_width=True)

# ---------------------------------------------------------------------------
# FEATURE IMPACT
# ---------------------------------------------------------------------------
with tabs[4]:
    st.subheader("Did the Dec 1 one-click checkout launch work?")
    df_fi = fi.cart_and_purchase_events(conn)
    cart_conv = fi.cart_level_conversion(df_fi)
    pre, post, naive_delta = fi.naive_before_after(cart_conv)
    tbl, did_est = fi.diff_in_diff_table(cart_conv)
    model = fi.diff_in_diff_regression(cart_conv)
    interaction, se, pval = (model.params["treatment:post"], model.bse["treatment:post"],
                              model.pvalues["treatment:post"])

    c1, c2 = st.columns(2)
    c1.metric("Naive before/after (treatment only)", f"{naive_delta:+.1%}",
              help="Overstated: includes the shared holiday-season lift")
    c2.metric("Diff-in-diff (true incremental effect)", f"{did_est:+.1%}",
              help=f"OLS interaction term: {interaction:+.4f}, SE={se:.4f}, p={pval:.2g}")

    weekly = fi.weekly_conversion_series(cart_conv, df_fi)
    fig8 = go.Figure()
    fig8.add_trace(go.Scatter(x=weekly.index, y=weekly["treatment"], name="Electronics (treatment)",
                               line=dict(color=PALETTE["accent"])))
    fig8.add_trace(go.Scatter(x=weekly.index, y=weekly["control"], name="Apparel + Furniture (control)",
                               line=dict(color=PALETTE["slate"])))
    fig8.add_vline(x=pd.Timestamp("2025-12-01"), line_dash="dash", line_color=PALETTE["ink"],
                   annotation_text="Launch")
    fig8.update_layout(yaxis_tickformat=".0%", height=360, margin=dict(t=10), legend_title="",
                        yaxis_title="Cart\u2192purchase conversion")
    st.plotly_chart(fig8, use_container_width=True)

    st.markdown("**Diff-in-diff table**")
    st.dataframe(tbl.style.format("{:.1%}"), use_container_width=True)

    st.warning(
        "This is an observational before/after across category groups, not a randomized experiment. "
        "Electronics and apparel/furniture shoppers may differ in ways correlated with launch timing "
        "(e.g. differential exposure to holiday deals). Treat the DiD estimate as a stronger, but "
        "still not bulletproof, read \u2014 the gold-standard follow-up is a randomized holdback test.",
        icon="\u26a0\ufe0f",
    )
