"""
Business Intelligence Copilot
A Streamlit app that turns multi-month business data into an
interactive dashboard, AI-generated diagnostic, forecasts, anomaly
flags, a chat-with-your-data assistant, and downloadable PPTX/PDF reports.
"""

import streamlit as st
import pandas as pd

from modules import data_loader, column_detector, kpi_engine
from modules import forecast_engine, anomaly_engine, charts
from modules import llm_insights, report_export

st.set_page_config(page_title="Business Intelligence Copilot", layout="wide", page_icon="📊")

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
for key, default in [
    ("combined_df", None), ("cleaning_log", []), ("numeric_cols", []),
    ("monthly_summary", None), ("trends", {}), ("forecasts", {}), ("anomalies", {}),
    ("diagnostic", None), ("chat_history", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# Sidebar: upload + LLM config
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 BI Copilot")
    st.caption("Upload one or more monthly business data files.")

    uploaded_files = st.file_uploader(
        "Upload CSV / Excel (one or many months)",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )

    date_hint = st.text_input(
        "Date column name (optional — auto-detected if left blank)", value=""
    )

    if uploaded_files:
        if st.button("Process files", type="primary", use_container_width=True):
            with st.spinner("Loading and cleaning data..."):
                combined, log, summaries = data_loader.load_multiple_files(
                    uploaded_files, date_column_hint=date_hint or None
                )
                st.session_state.combined_df = combined
                st.session_state.cleaning_log = log

                detected = column_detector.detect_columns(combined)
                st.session_state.numeric_cols = detected["numeric"]

                monthly = kpi_engine.build_monthly_summary(combined, detected["numeric"])
                st.session_state.monthly_summary = monthly

                metric_cols = [c for c in monthly.columns if c != "period"]
                trends = kpi_engine.compute_trends(monthly, metric_cols)
                st.session_state.trends = trends
                st.session_state.forecasts = forecast_engine.forecast_all_metrics(trends)
                st.session_state.anomalies = anomaly_engine.detect_anomalies_all_metrics(trends)
                st.session_state.diagnostic = None
                st.session_state.chat_history = []
            st.success("Data processed — explore the tabs below.")

    st.divider()
    st.subheader("AI Provider")
    provider = st.selectbox("Provider", ["OpenAI", "Gemini"])

    secret_key_name = "OPENAI_API_KEY" if provider == "OpenAI" else "GEMINI_API_KEY"
    saved_key = st.secrets.get(secret_key_name, "")

    if saved_key:
        api_key = saved_key
        st.success(f"{provider} key loaded from saved secrets.")
    else:
        api_key = st.text_input(f"{provider} API key", type="password",
                                 help="Used only for this session; never saved to disk. "
                                      "Add it under app Settings → Secrets on Streamlit Cloud "
                                      "to avoid re-entering it every time.")
    st.caption(
        "Only aggregated statistics (totals, averages, % changes, trends) are ever "
        "sent to the LLM. Individual rows are never shared."
    )

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
st.title("Business Intelligence Copilot")

if st.session_state.combined_df is None:
    st.info("Upload one or more monthly CSV/Excel files in the sidebar to get started, "
            "then click **Process files**.")
    st.stop()

combined_df = st.session_state.combined_df
monthly = st.session_state.monthly_summary
trends = st.session_state.trends
forecasts = st.session_state.forecasts
anomalies = st.session_state.anomalies
metric_cols = [c for c in monthly.columns if c != "period"] if monthly is not None else []

tab_dashboard, tab_trends, tab_diagnostic, tab_chat, tab_export, tab_log = st.tabs(
    ["📈 Dashboard", "🔮 Trends & Forecast", "🧠 AI Diagnostic", "💬 Chat with Data",
     "⬇️ Export Report", "🧹 Cleaning Log"]
)

# --- Dashboard tab ---------------------------------------------------------
with tab_dashboard:
    st.subheader("KPI Overview")
    if not metric_cols:
        st.warning("No numeric KPI columns were detected in the uploaded data.")
    else:
        n_periods = len(monthly)
        cols = st.columns(min(4, max(1, len(metric_cols))))
        for i, metric in enumerate(metric_cols[:8]):
            latest = trends[metric]["latest_value"]
            change = trends[metric]["latest_pct_change"]
            cols[i % len(cols)].metric(
                metric.replace("_", " "), f"{latest:,.2f}", f"{change:+.1f}% vs prior month"
            )

        st.divider()
        selected_metrics = st.multiselect(
            "Chart metrics", metric_cols, default=metric_cols[:2]
        )
        for metric in selected_metrics:
            fig = charts.trend_line_with_forecast(
                metric, trends[metric]["periods"], trends[metric]["values"],
                forecast=forecasts.get(metric), anomalies=anomalies.get(metric),
            )
            st.plotly_chart(fig, use_container_width=True)

# --- Trends & Forecast tab -------------------------------------------------
with tab_trends:
    st.subheader("Trend Detection & Forecasts")
    if not metric_cols:
        st.warning("No numeric KPI columns detected.")
    else:
        rows = []
        for metric in metric_cols:
            t = trends[metric]
            f = forecasts.get(metric, {})
            rows.append({
                "Metric": metric,
                "Latest Value": t["latest_value"],
                "MoM % Change": t["latest_pct_change"],
                "Direction": t["overall_direction"],
                "Streak (months)": t["streak_months"],
                "Next-Month Forecast": f.get("forecast"),
                "Forecast Confidence": f.get("confidence"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("⚠️ Anomalies Detected")
        if not anomalies:
            st.success("No anomalies detected in any metric.")
        else:
            for metric, found in anomalies.items():
                with st.expander(f"{metric} — {len(found)} anomaly(ies)"):
                    st.dataframe(pd.DataFrame(found), use_container_width=True, hide_index=True)

# --- AI Diagnostic tab ------------------------------------------------------
with tab_diagnostic:
    st.subheader("AI-Generated Executive Diagnostic")
    if st.button("Generate diagnostic", type="primary"):
        if not api_key:
            st.error("Add your API key in the sidebar first.")
        else:
            with st.spinner("Asking the AI to analyze your business stats..."):
                try:
                    monthly_dict = monthly.to_dict(orient="records")
                    diagnostic = llm_insights.generate_diagnostic(
                        monthly_dict, trends, anomalies, forecasts, provider, api_key
                    )
                    st.session_state.diagnostic = diagnostic
                except Exception as e:
                    st.error(f"Could not generate diagnostic: {e}")

    diagnostic = st.session_state.diagnostic
    if diagnostic:
        st.markdown(f"**Executive Summary**\n\n{diagnostic.get('executive_summary','')}")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**✅ Positive Trends**")
            for item in diagnostic.get("positive_trends", []):
                st.write(f"- {item}")
            st.markdown("**⚠️ Areas of Concern**")
            for item in diagnostic.get("areas_of_concern", []):
                st.write(f"- {item}")
        with c2:
            st.markdown("**🚩 Risks**")
            for item in diagnostic.get("risks", []):
                st.write(f"- {item}")
            st.markdown("**🚀 Growth Opportunities**")
            for item in diagnostic.get("growth_opportunities", []):
                st.write(f"- {item}")
        st.markdown("**📋 Recommendations**")
        for item in diagnostic.get("recommendations", []):
            st.write(f"- {item}")
    else:
        st.caption("Click 'Generate diagnostic' to have the AI analyze your KPIs, trends, and anomalies.")

# --- Chat tab ---------------------------------------------------------------
with tab_chat:
    st.subheader("Chat With Your Business Data")
    chunks = llm_insights.build_context_chunks(monthly, trends, anomalies, forecasts)
    mode = "retrieval-augmented (RAG)" if len(chunks) > llm_insights.RAG_TRIGGER_CHUNK_COUNT else "full-context"
    st.caption(f"Context mode: **{mode}** — {len(chunks)} data chunk(s) available.")

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_q = st.chat_input("Ask about your business data (e.g. 'Why did revenue drop in March?')")
    if user_q:
        if not api_key:
            st.error("Add your API key in the sidebar first.")
        else:
            st.session_state.chat_history.append({"role": "user", "content": user_q})
            with st.spinner("Thinking..."):
                try:
                    answer = llm_insights.chat_with_data(
                        user_q, chunks, st.session_state.chat_history, provider, api_key
                    )
                except Exception as e:
                    answer = f"Something went wrong calling the AI provider: {e}"
            st.session_state.chat_history.append({"role": "assistant", "content": answer})
            st.rerun()

# --- Export tab --------------------------------------------------------------
with tab_export:
    st.subheader("Download a Shareable Report")
    if not st.session_state.diagnostic:
        st.info("Generate the AI diagnostic first (in the 'AI Diagnostic' tab) for a richer report — "
                 "or export now with just the KPI/trend/forecast/anomaly data.")

    export_metrics = st.multiselect(
        "Include charts for these metrics", metric_cols, default=metric_cols[:3]
    )
    report_title = st.text_input("Report title", value="Business Health Report")

    fallback_diagnostic = {
        "executive_summary": "No AI diagnostic was generated for this export — see the KPI, trend, "
                              "forecast, and anomaly tables below for the raw findings.",
        "positive_trends": [], "areas_of_concern": [], "risks": [],
        "growth_opportunities": [], "recommendations": [],
    }
    diagnostic_for_export = st.session_state.diagnostic or fallback_diagnostic

    chart_figs = {
        m: charts.trend_line_with_forecast(
            m, trends[m]["periods"], trends[m]["values"],
            forecast=forecasts.get(m), anomalies=anomalies.get(m),
        ) for m in export_metrics
    }

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Build PowerPoint", use_container_width=True):
            with st.spinner("Building .pptx..."):
                try:
                    pptx_bytes = report_export.build_pptx(
                        report_title, diagnostic_for_export, chart_figs, forecasts, anomalies
                    )
                    st.download_button(
                        "⬇️ Download PowerPoint", data=pptx_bytes,
                        file_name="business_health_report.pptx",
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"Could not build PowerPoint: {e}")
    with col2:
        if st.button("Build PDF", use_container_width=True):
            with st.spinner("Building .pdf..."):
                try:
                    pdf_bytes = report_export.build_pdf(
                        report_title, diagnostic_for_export, chart_figs, forecasts, anomalies
                    )
                    st.download_button(
                        "⬇️ Download PDF", data=pdf_bytes,
                        file_name="business_health_report.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"Could not build PDF: {e}")

# --- Cleaning log tab --------------------------------------------------------
with tab_log:
    st.subheader("Data Cleaning Log")
    for line in st.session_state.cleaning_log:
        st.write(f"- {line}")
    st.divider()
    st.subheader("Combined Data Preview")
    st.dataframe(combined_df.head(50), use_container_width=True)
