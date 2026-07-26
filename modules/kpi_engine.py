"""
kpi_engine.py
Aggregates numeric columns by period (month) and computes month-over-month
trend statistics: % change, direction, streaks, and volatility.
"""

import pandas as pd
import numpy as np
from .data_loader import period_sort_key


def build_monthly_summary(df: pd.DataFrame, numeric_cols: list) -> pd.DataFrame:
    """Returns one row per period with the sum and mean of each numeric column."""
    if not numeric_cols:
        return pd.DataFrame()

    agg = df.groupby("_source_period")[numeric_cols].agg(["sum", "mean"])
    agg.columns = [f"{col}_{stat}" for col, stat in agg.columns]
    agg = agg.reset_index().rename(columns={"_source_period": "period"})
    agg["_sort_key"] = agg["period"].apply(period_sort_key)
    agg = agg.sort_values("_sort_key").drop(columns="_sort_key").reset_index(drop=True)
    return agg


def compute_trends(monthly_summary: pd.DataFrame, metric_cols: list):
    """
    For each metric column, compute month-over-month % change, overall
    direction, and a simple streak count (consecutive months moving the
    same direction).
    Returns dict: metric -> {values, pct_change, direction, streak, latest_value}
    """
    trends = {}
    periods = monthly_summary["period"].tolist()

    for metric in metric_cols:
        if metric not in monthly_summary.columns:
            continue
        values = monthly_summary[metric].tolist()
        pct_change = monthly_summary[metric].pct_change().fillna(0) * 100

        # direction streak from the end
        streak = 0
        if len(values) >= 2:
            last_diff_sign = None
            for i in range(len(values) - 1, 0, -1):
                diff = values[i] - values[i - 1]
                sign = 1 if diff > 0 else (-1 if diff < 0 else 0)
                if last_diff_sign is None:
                    last_diff_sign = sign
                    streak = 1 if sign != 0 else 0
                elif sign == last_diff_sign and sign != 0:
                    streak += 1
                else:
                    break

        overall_direction = "flat"
        if len(values) >= 2 and values[0] != 0:
            overall_change = (values[-1] - values[0]) / abs(values[0]) * 100
            if overall_change > 2:
                overall_direction = "up"
            elif overall_change < -2:
                overall_direction = "down"
        elif len(values) >= 2:
            overall_direction = "up" if values[-1] > values[0] else (
                "down" if values[-1] < values[0] else "flat"
            )

        trends[metric] = {
            "periods": periods,
            "values": values,
            "pct_change": pct_change.tolist(),
            "latest_pct_change": round(pct_change.tolist()[-1], 2) if pct_change.tolist() else 0,
            "overall_direction": overall_direction,
            "streak_months": streak,
            "latest_value": values[-1] if values else None,
        }

    return trends


def top_movers(trends: dict, n: int = 3):
    """Returns the n metrics with the largest absolute latest % change."""
    ranked = sorted(
        trends.items(),
        key=lambda kv: abs(kv[1]["latest_pct_change"]),
        reverse=True,
    )
    return ranked[:n]
