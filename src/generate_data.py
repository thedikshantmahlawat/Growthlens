"""
generate_data.py
----------------
Generates a synthetic e-commerce clickstream dataset that mirrors the exact
schema of the real "eCommerce behavior data from multi-category store"
dataset (REES46, via Kaggle/mkechinov):

    event_time, event_type, product_id, category_id, category_code,
    brand, price, user_id, user_session

WHY SYNTHETIC: the real dataset is Kaggle-gated (needs a logged-in browser
session to download) and shipped as several-GB-per-month files -- not
fetchable from this sandboxed build environment, and too large to be a
laptop-friendly starter dataset anyway. This script instead generates data
with the same columns, same event-funnel logic (view -> cart -> purchase),
and realistic behavioral patterns (segments, churn, seasonality, a feature
launch with a true causal effect baked in), so every downstream query,
funnel, cohort, and DiD calculation is exercised exactly as it would be on
the real file. See README.md for how to swap in the real Kaggle CSV with
zero code changes elsewhere in the pipeline.

Ground-truth generative "segment" labels are used internally to drive
realistic behavior but are NOT written to the output -- retention/growth
analysis has to discover engagement patterns from raw events only, the same
as it would on real data.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os

RNG_SEED = 42
rng = np.random.default_rng(RNG_SEED)

START_DATE = datetime(2025, 11, 1)
END_DATE = datetime(2026, 2, 28, 23, 59, 59)
LAUNCH_DATE = datetime(2025, 12, 1)  # one-click checkout ships for electronics

N_USERS = 5000

OUT_PATH = "data/raw/events.csv"

# ---------------------------------------------------------------------------
# 1. Product catalog: categories, brands, price bands
# ---------------------------------------------------------------------------
# category_code -> (category_group, price_low, price_high, n_products)
# category_group is used only to define the feature-launch treatment/control
# split (electronics = treatment). It is a real column in the actual REES46
# data too (people derive it themselves from category_code), so this isn't
# an invented column -- it's just not pre-labeled "treatment"/"control".
CATEGORIES = {
    "electronics.smartphone":            ("electronics", 150, 1200, 60),
    "electronics.laptop":                ("electronics", 400, 2200, 45),
    "electronics.headphone":             ("electronics", 20, 350, 50),
    "electronics.smartwatch":            ("electronics", 60, 500, 30),
    "appliances.kitchen.refrigerator":   ("appliances", 300, 1800, 25),
    "appliances.kitchen.microwave":      ("appliances", 50, 250, 20),
    "apparel.shoes":                     ("apparel", 30, 220, 70),
    "apparel.outerwear.jacket":          ("apparel", 40, 320, 55),
    "furniture.living_room.sofa":        ("furniture", 300, 2600, 25),
    "furniture.bedroom.bed":             ("furniture", 200, 1600, 20),
    "computers.peripherals.mouse":       ("computers", 10, 90, 35),
    "computers.notebook":                ("computers", 300, 2100, 40),
    "sport.bicycle":                     ("sport", 150, 1600, 30),
    "kids.toys":                         ("kids", 10, 110, 60),
    "accessories.bag":                   ("accessories", 20, 260, 45),
}

BRANDS = ["novatek", "urbana", "kraftex", "comfyhome", "zentek", "vionix",
          "aeroline", "brightway", "solace", "primafit", "nimbus", "corestone",
          np.nan]  # some rows genuinely have no brand, like the real data

category_codes = list(CATEGORIES.keys())
category_group_of = {c: v[0] for c, v in CATEGORIES.items()}
TREATMENT_GROUPS = {"electronics"}

products = []
product_id_counter = 100000000
category_id_map = {c: 2000000000 + i for i, c in enumerate(category_codes)}

for cat_code, (group, plow, phigh, n_products) in CATEGORIES.items():
    cat_brands = rng.choice(BRANDS, size=min(6, len(BRANDS)), replace=False)
    for _ in range(n_products):
        product_id_counter += 1
        base_price = rng.uniform(plow, phigh)
        products.append({
            "product_id": product_id_counter,
            "category_id": category_id_map[cat_code],
            "category_code": cat_code,
            "category_group": group,
            "brand": rng.choice(cat_brands),
            "price": round(base_price, 2),
        })

product_df = pd.DataFrame(products)
# category popularity weights (some categories browsed far more than others)
cat_weights = rng.dirichlet(np.ones(len(category_codes)) * 1.5)
cat_weight_map = dict(zip(category_codes, cat_weights))

print(f"Product catalog: {len(product_df)} products across {len(category_codes)} categories")

# ---------------------------------------------------------------------------
# 2. Users: acquisition cohort, hidden segment (drives behavior, not exported)
# ---------------------------------------------------------------------------
COHORT_MONTHS = [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]
COHORT_WEIGHTS = [0.35, 0.28, 0.22, 0.15]  # acquisition slowing over time
SEGMENTS = ["loyal", "casual", "one_time"]
SEGMENT_WEIGHTS = [0.15, 0.55, 0.30]

def random_day_in_month(year, month):
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    month_start = datetime(year, month, 1)
    days_in_month = (next_month - month_start).days
    offset_days = rng.integers(0, days_in_month)
    offset_seconds = rng.integers(0, 86400)
    return month_start + timedelta(days=int(offset_days), seconds=int(offset_seconds))

users = []
cohort_choices = rng.choice(len(COHORT_MONTHS), size=N_USERS, p=COHORT_WEIGHTS)
segment_choices = rng.choice(SEGMENTS, size=N_USERS, p=SEGMENT_WEIGHTS)

for uid in range(1, N_USERS + 1):
    y, m = COHORT_MONTHS[cohort_choices[uid - 1]]
    first_seen = random_day_in_month(y, m)
    if first_seen > END_DATE:
        first_seen = END_DATE - timedelta(hours=1)
    users.append({
        "user_id": 500000000 + uid,
        "first_seen": first_seen,
        "segment": segment_choices[uid - 1],  # internal only, not exported
    })

user_df = pd.DataFrame(users)
print(f"Users: {len(user_df)}, cohort sizes:\n{user_df['first_seen'].dt.to_period('M').value_counts().sort_index()}")
print(f"Segment mix:\n{user_df['segment'].value_counts()}")

# ---------------------------------------------------------------------------
# 3. Session schedule per user (segment-driven frequency + churn)
# ---------------------------------------------------------------------------
SEGMENT_PARAMS = {
    "loyal":    dict(gap_mean_days=4,  continue_prob=0.93, max_sessions=40),
    "casual":   dict(gap_mean_days=15, continue_prob=0.72, max_sessions=12),
    "one_time": dict(gap_mean_days=None, continue_prob=0.0, max_sessions=1),
}

def build_session_dates(first_seen, segment):
    params = SEGMENT_PARAMS[segment]
    dates = [first_seen]
    if segment == "one_time":
        return dates
    current = first_seen
    while len(dates) < params["max_sessions"]:
        if rng.random() > params["continue_prob"]:
            break
        gap = rng.exponential(params["gap_mean_days"])
        current = current + timedelta(days=float(gap))
        if current > END_DATE:
            break
        dates.append(current)
    return dates

# ---------------------------------------------------------------------------
# 4. Funnel + feature-launch economics
# ---------------------------------------------------------------------------
BASE_CART_PROB = {"loyal": 0.35, "casual": 0.20, "one_time": 0.10}
BASE_PURCHASE_PROB = 0.45          # baseline cart -> purchase
SEASONAL_BUMP = 0.05               # Dec-Feb, ALL categories (holiday season)
LAUNCH_UPLIFT = 0.10               # Dec-Feb, ELECTRONICS only (true feature effect)

def purchase_prob(category_group, event_dt):
    p = BASE_PURCHASE_PROB
    if event_dt >= LAUNCH_DATE:
        p += SEASONAL_BUMP
        if category_group in TREATMENT_GROUPS:
            p += LAUNCH_UPLIFT
    return min(p, 0.95)

# ---------------------------------------------------------------------------
# 5. Generate events
# ---------------------------------------------------------------------------
events = []
session_counter = 0
cat_codes_arr = np.array(category_codes)
cat_weights_arr = np.array([cat_weight_map[c] for c in category_codes])

products_by_cat = {c: product_df[product_df["category_code"] == c].reset_index(drop=True)
                    for c in category_codes}

for _, urow in user_df.iterrows():
    uid = urow["user_id"]
    segment = urow["segment"]
    session_dates = build_session_dates(urow["first_seen"], segment)

    for sess_dt in session_dates:
        session_counter += 1
        session_id = f"s{session_counter:08d}"
        n_views = int(rng.poisson(5)) + 1
        chosen_cats = rng.choice(cat_codes_arr, size=n_views, p=cat_weights_arr)

        clock = sess_dt
        cart_prob = BASE_CART_PROB[segment]

        for cat_code in chosen_cats:
            cat_products = products_by_cat[cat_code]
            prod = cat_products.iloc[rng.integers(0, len(cat_products))]
            clock = clock + timedelta(seconds=float(rng.integers(5, 120)))
            if clock > END_DATE:
                break

            events.append({
                "event_time": clock, "event_type": "view",
                "product_id": prod["product_id"], "category_id": prod["category_id"],
                "category_code": prod["category_code"], "brand": prod["brand"],
                "price": prod["price"], "user_id": uid, "user_session": session_id,
            })

            if rng.random() < cart_prob:
                cart_clock = clock + timedelta(seconds=float(rng.integers(10, 180)))
                if cart_clock > END_DATE:
                    continue
                events.append({
                    "event_time": cart_clock, "event_type": "cart",
                    "product_id": prod["product_id"], "category_id": prod["category_id"],
                    "category_code": prod["category_code"], "brand": prod["brand"],
                    "price": prod["price"], "user_id": uid, "user_session": session_id,
                })

                p_purchase = purchase_prob(prod["category_group"], cart_clock)
                if rng.random() < p_purchase:
                    buy_clock = cart_clock + timedelta(seconds=float(rng.integers(30, 1800)))
                    if buy_clock <= END_DATE:
                        events.append({
                            "event_time": buy_clock, "event_type": "purchase",
                            "product_id": prod["product_id"], "category_id": prod["category_id"],
                            "category_code": prod["category_code"], "brand": prod["brand"],
                            "price": prod["price"], "user_id": uid, "user_session": session_id,
                        })

event_df = pd.DataFrame(events)
event_df = event_df.sort_values("event_time").reset_index(drop=True)

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
event_df.to_csv(OUT_PATH, index=False)

print(f"\nTotal events generated: {len(event_df):,}")
print(event_df["event_type"].value_counts())
print(f"Date range: {event_df['event_time'].min()} -> {event_df['event_time'].max()}")
print(f"Saved to {OUT_PATH}")
