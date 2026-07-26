"""
forecast_engine.py
Lightweight, dependency-free forecasting: linear regression trend
extrapolation blended with a 3-month weighted moving average, for a
one-month-ahead projection per metric. No heavy time-series library
needed since we're typically working with a handful of monthly points.
"""

import numpy as np


def forecast_next_period(values: list, periods: list):
    """
    Returns a dict with the forecasted next value, a confidence label,
    and the method notes. Designed to degrade gracefully with few data
    points (as few as 2 months).
    """
    n = len(values)
    if n == 0:
        return None
    if n == 1:
        return {
            "forecast": values[0],
            "confidence": "low",
            "note": "Only one month of data; forecast simply repeats it.",
        }

    x = np.arange(n)
    y = np.array(values, dtype=float)

    # Linear regression trend line
    slope, intercept = np.polyfit(x, y, 1)
    linear_forecast = slope * n + intercept

    # 3-month weighted moving average (more weight on recent months)
    window = y[-min(3, n):]
    weights = np.arange(1, len(window) + 1)
    wma_forecast = np.average(window, weights=weights)

    # Blend: trust the trend line more as we have more data points
    trend_weight = min(0.7, 0.2 + 0.1 * n)
    blended = trend_weight * linear_forecast + (1 - trend_weight) * wma_forecast

    # crude confidence based on how noisy the series is (coefficient of variation)
    residuals = y - (slope * x + intercept)
    cv = np.std(residuals) / (np.mean(np.abs(y)) + 1e-9)
    if n >= 5 and cv < 0.15:
        confidence = "high"
    elif n >= 3 and cv < 0.35:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "forecast": round(float(blended), 2),
        "confidence": confidence,
        "trend_slope": round(float(slope), 3),
        "note": (
            f"Blend of linear trend ({round(float(linear_forecast),2)}) and "
            f"weighted recent average ({round(float(wma_forecast),2)}) "
            f"over {n} month(s) of history."
        ),
    }


def forecast_all_metrics(trends: dict):
    """trends: output of kpi_engine.compute_trends. Returns metric -> forecast dict."""
    forecasts = {}
    for metric, data in trends.items():
        f = forecast_next_period(data["values"], data["periods"])
        if f:
            forecasts[metric] = f
    return forecasts
