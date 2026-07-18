# GrowthLens

**Funnel, retention, growth, and feature-impact analytics for an e-commerce clickstream dataset.**

Built to map directly onto a Product Analyst job description bullet: *"Analyze user journeys, funnels, retention, growth metrics, and feature impact to drive product and business decisions."* Each of those five nouns is a module in this repo.

---

## What's in here

| Question a PM/analyst would ask | Module | 
|---|---|
| Where do users drop off between viewing, carting, and buying? | `src/funnel_analysis.py` |
| Do users come back? Which cohorts stick? | `src/retention_analysis.py` |
| Is the user base growing, and is engagement healthy? | `src/growth_metrics.py` |
| Did the thing we shipped actually work? | `src/feature_impact.py` |

All four sit on top of one SQLite star schema (`sql/schema.sql`) and are wired into an interactive dashboard (`dashboard/app.py`).

## A note on the data, upfront

The real-world dataset this project targets is [REES46's "eCommerce behavior data from multi-category store"](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store) on Kaggle \u2014 genuine view/cart/purchase clickstream, hundreds of millions of rows across several months. It's Kaggle-gated (needs an authenticated download) and shipped as multi-GB monthly files, so this repo ships with a **synthetic dataset generated to that exact schema** (`src/generate_data.py`) instead of a scraped or partial copy.

This isn't a cosmetic stand-in: the generator encodes real funnel economics (view/cart/purchase drop-off rates), realistic user heterogeneity (loyal / casual / one-time visitor mixes with different churn), acquisition trends, seasonality, and a deliberately-planted feature launch with a known ground-truth effect \u2014 so every query, cohort calculation, and regression in this repo is exercised exactly as it would be on the real file, and the feature-impact module can be checked against a known right answer (see below).

**To swap in the real data:** download any monthly CSV from the Kaggle page above, save it as `data/raw/events.csv` (same column names: `event_time, event_type, product_id, category_id, category_code, brand, price, user_id, user_session`), and re-run `python src/build_database.py`. Nothing else in the pipeline changes.

## Architecture

```
Raw events (CSV, REES46 schema)
        |
        v
sql/schema.sql  --->  SQLite star schema
                       - dim_users (user_id, first_seen_date, cohort_month)
                       - dim_products (product_id, category_code, category_group, brand, price)
                       - dim_dates (calendar dimension)
                       - fact_events (event_time, event_type, user_id, product_id, user_session)
        |
        v
src/funnel_analysis.py, retention_analysis.py, growth_metrics.py, feature_impact.py
        |
        v
dashboard/app.py  (Streamlit, 5 tabs, Plotly charts)
```

## Key findings (from the shipped synthetic dataset)

**Funnel.** Of 5,000 users, 3,828 (76.6%) added something to a cart and 3,070 (61.4%) purchased \u2014 an 80.2% cart\u2192purchase rate once someone carts at all. Electronics converts highest end-to-end (33.0% view\u2192purchase); kids' products lowest (19.1%).

**Retention.** Using the strict "active exactly on day N" definition, D1/D7/D30 run in the high single digits to low teens across cohorts \u2014 low by social-app standards, but that's expected: shopping is need-driven, not habitual. The more useful number is the cumulative view \u2014 **~47\u201349% of users return at least once within 30 days** \u2014 alongside knowing roughly half of all users are one-and-done visitors by design.

**Growth.** Stable-period (Dec\u2013Feb) stickiness (DAU/30d-MAU) runs **~7.1%**. November reads higher, but that's a measurement artifact \u2014 its 30-day lookback window partially precedes the dataset's start, shrinking the MAU denominator \u2014 not a real engagement spike; it's excluded from the stable-period average for that reason.

**Feature impact.** A simulated Dec 1 one-click checkout launch for electronics: naive before/after on the treated group alone shows **+15.1pp** \u2014 but a diff-in-diff against an apparel/furniture control group isolates the true incremental effect at **+12.2pp** (OLS interaction term +0.122, p=2.7e-06). The gap between those two numbers *is* the point: the naive read baked in a holiday-season conversion lift (+2.9pp, visible in the control group too) that had nothing to do with the launch. This is exactly the kind of "your first instinct overstates it" result worth walking an interviewer through.

## Methodology notes (the parts worth being able to defend out loud)

- **Funnel is event-based, not strict-sequence.** A user counts toward "cart" if they have a cart event in the period at all, not specifically right after a view in the same session \u2014 real shoppers cart today and buy in three days, and a same-session-only funnel would undercount that.
- **Retention has two definitions on purpose.** D1/D7/D30 = active *exactly* on that day (Amplitude/Mixpanel convention, the harder bar). L7/L30 = active *at least once* within that window (softer, complementary). Reporting only the cumulative number is a common way retention gets accidentally oversold.
- **Feature impact is DiD, not a randomized A/B test**, because the "launch" is observational (all electronics got it, nothing was held out). Diff-in-diff is a materially stronger read than before/after, but electronics vs. apparel/furniture shoppers can still differ in ways correlated with launch timing \u2014 stated as a real caveat, not a footnote to skip.

## Running it locally

```bash
git clone https://github.com/thedikshantmahlawat/growthlens.git
cd growthlens
pip install -r requirements.txt

# data + database are committed to the repo, so this step is optional unless
# you want to regenerate from scratch or swap in the real Kaggle CSV:
python src/generate_data.py
python src/build_database.py

streamlit run dashboard/app.py
```

Each analysis module also runs standalone and prints its findings to the terminal, e.g. `python src/feature_impact.py`.

## Deploying (Streamlit Community Cloud)

1. Push this repo to GitHub (steps below).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, "New app."
3. Point it at this repo, branch `main`, main file path `dashboard/app.py`.
4. Deploy. The committed SQLite DB means it works with no extra setup.

## Tech stack

Python, pandas, SQLite, Streamlit, Plotly, statsmodels (OLS for the diff-in-diff regression).

## Project structure

```
growthlens/
├── README.md
├── requirements.txt
├── .streamlit/config.toml
├── data/
│   ├── raw/events.csv
│   └── processed/growthlens.db
├── sql/schema.sql
├── src/
│   ├── generate_data.py
│   ├── build_database.py
│   ├── funnel_analysis.py
│   ├── retention_analysis.py
│   ├── growth_metrics.py
│   └── feature_impact.py
└── dashboard/app.py
```
