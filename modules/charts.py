"""
charts.py
Plotly chart builders: trend lines (with an optional forecast point and
anomaly markers), and a KPI comparison bar chart.
"""

import plotly.graph_objects as go


def trend_line_with_forecast(metric_name: str, periods: list, values: list,
                              forecast: dict = None, anomalies: list = None):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=periods, y=values, mode="lines+markers", name=metric_name,
        line=dict(width=3),
    ))

    if forecast:
        next_label = "Forecast"
        fig.add_trace(go.Scatter(
            x=[periods[-1], next_label],
            y=[values[-1], forecast["forecast"]],
            mode="lines+markers",
            name="Forecast",
            line=dict(dash="dash", color="orange"),
            marker=dict(symbol="star", size=10),
        ))

    if anomalies:
        anomaly_periods = [a["period"] for a in anomalies]
        anomaly_values = [a["value"] for a in anomalies]
        fig.add_trace(go.Scatter(
            x=anomaly_periods, y=anomaly_values, mode="markers",
            name="Anomaly",
            marker=dict(color="red", size=13, symbol="x"),
        ))

    fig.update_layout(
        title=f"{metric_name} — trend, forecast & anomalies",
        xaxis_title="Period",
        yaxis_title=metric_name,
        template="plotly_white",
        height=380,
        margin=dict(t=50, b=30, l=30, r=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def kpi_comparison_bar(metric_name: str, periods: list, values: list):
    fig = go.Figure(go.Bar(x=periods, y=values, marker_color="#4C78A8"))
    fig.update_layout(
        title=f"{metric_name} by period",
        template="plotly_white",
        height=320,
        margin=dict(t=40, b=30, l=30, r=30),
    )
    return fig
