-- GrowthLens star schema
-- One fact table (events) around three conformed dimensions (users, products, dates).
-- Kept deliberately simple: sessions are a degenerate dimension (the user_session
-- string lives directly on the fact table) rather than a separate table, since it
-- has no attributes beyond what's derivable from the events themselves.

DROP TABLE IF EXISTS fact_events;
DROP TABLE IF EXISTS dim_users;
DROP TABLE IF EXISTS dim_products;
DROP TABLE IF EXISTS dim_dates;

CREATE TABLE dim_users (
    user_id         INTEGER PRIMARY KEY,
    first_seen_date TEXT NOT NULL,      -- YYYY-MM-DD, derived from MIN(event_time)
    cohort_month    TEXT NOT NULL       -- YYYY-MM
);

CREATE TABLE dim_products (
    product_id      INTEGER PRIMARY KEY,
    category_id     INTEGER NOT NULL,
    category_code   TEXT NOT NULL,
    category_group  TEXT NOT NULL,      -- top-level segment of category_code, e.g. "electronics"
    brand           TEXT,
    price           REAL NOT NULL
);

CREATE TABLE dim_dates (
    date            TEXT PRIMARY KEY,   -- YYYY-MM-DD
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    day             INTEGER NOT NULL,
    month_label     TEXT NOT NULL,      -- YYYY-MM
    day_of_week     INTEGER NOT NULL,   -- 0=Mon .. 6=Sun
    is_weekend      INTEGER NOT NULL
);

CREATE TABLE fact_events (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time      TEXT NOT NULL,
    event_date      TEXT NOT NULL,
    event_type      TEXT NOT NULL,      -- view | cart | purchase
    user_id         INTEGER NOT NULL,
    product_id      INTEGER NOT NULL,
    user_session    TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES dim_users(user_id),
    FOREIGN KEY (product_id) REFERENCES dim_products(product_id),
    FOREIGN KEY (event_date) REFERENCES dim_dates(date)
);

CREATE INDEX idx_fact_events_date ON fact_events(event_date);
CREATE INDEX idx_fact_events_user ON fact_events(user_id);
CREATE INDEX idx_fact_events_type ON fact_events(event_type);
CREATE INDEX idx_fact_events_session ON fact_events(user_session);
CREATE INDEX idx_fact_events_product ON fact_events(product_id);
