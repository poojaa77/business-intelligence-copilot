"""
column_detector.py
Detects numeric, categorical, and date columns, and matches column
names against a keyword bank of common business KPIs so the app can
auto-select sensible metrics without the user configuring anything.
"""

import pandas as pd

KPI_KEYWORDS = {
    "Revenue": ["revenue", "sales", "income", "turnover", "gmv"],
    "Profit": ["profit", "margin", "ebitda", "net_income"],
    "Cost": ["cost", "expense", "spend", "cogs"],
    "Customers": ["customer", "client", "users", "accounts"],
    "Orders": ["order", "transaction", "invoice"],
    "Churn": ["churn", "attrition", "cancellation"],
    "Satisfaction": ["satisfaction", "csat", "nps", "rating"],
    "Delivery": ["delivery", "shipping", "fulfillment", "lead_time"],
    "Conversion": ["conversion", "ctr", "close_rate"],
    "Headcount": ["headcount", "employee", "staff"],
}


def detect_columns(df: pd.DataFrame):
    numeric_cols = [c for c in df.select_dtypes(include="number").columns]
    date_cols = []
    categorical_cols = []

    for col in df.columns:
        if col in numeric_cols or col == "_source_period":
            continue
        lc = col.lower()
        if "date" in lc or "period" in lc or "month" in lc:
            date_cols.append(col)
        else:
            # low-cardinality object columns are treated as categorical
            if df[col].nunique(dropna=True) <= max(20, int(len(df) * 0.2)):
                categorical_cols.append(col)

    return {
        "numeric": numeric_cols,
        "categorical": categorical_cols,
        "date": date_cols,
    }


def match_kpi_columns(numeric_cols: list):
    """Returns dict: KPI label -> matching column name(s) found in the data."""
    matches = {}
    for kpi_label, keywords in KPI_KEYWORDS.items():
        found = [
            col for col in numeric_cols
            if any(kw in col.lower() for kw in keywords)
        ]
        if found:
            matches[kpi_label] = found
    return matches
