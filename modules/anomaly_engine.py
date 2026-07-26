"""
anomaly_engine.py
Flags anomalous months per metric using a z-score test (for series with
enough spread) with an IQR fallback for short/skewed series. Designed
for the small monthly series typical of this app (often under ~12 points).
"""

import numpy as np


def detect_anomalies(values: list, periods: list, z_thresh: float = 1.8):
    n = len(values)
    if n < 3:
        return []

    arr = np.array(values, dtype=float)
    mean = arr.mean()
    std = arr.std()
    anomalies = []

    if std > 1e-9:
        z_scores = (arr - mean) / std
        for i, z in enumerate(z_scores):
            if abs(z) >= z_thresh:
                anomalies.append({
                    "period": periods[i],
                    "value": round(float(arr[i]), 2),
                    "z_score": round(float(z), 2),
                    "direction": "spike" if z > 0 else "drop",
                    "method": "z-score",
                })
    else:
        # no variance at all, use IQR as a fallback (handles constant-ish series)
        q1, q3 = np.percentile(arr, [25, 75])
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for i, v in enumerate(arr):
            if v < lower or v > upper:
                anomalies.append({
                    "period": periods[i],
                    "value": round(float(v), 2),
                    "z_score": None,
                    "direction": "spike" if v > upper else "drop",
                    "method": "IQR",
                })

    return anomalies


def detect_anomalies_all_metrics(trends: dict):
    """trends: output of kpi_engine.compute_trends. Returns metric -> list of anomalies."""
    results = {}
    for metric, data in trends.items():
        found = detect_anomalies(data["values"], data["periods"])
        if found:
            results[metric] = found
    return results
