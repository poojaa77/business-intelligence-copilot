# Business Intelligence Copilot

An upgraded successor to [ai-business-health-analyzer](https://github.com/poojaa77/ai-business-health-analyzer) — a Streamlit app that turns **multiple months** of raw business data into a full interactive BI workflow: KPI dashboard, AI diagnostic, forecasting, anomaly detection, a chat assistant over your own data, and downloadable PPTX/PDF reports.

## Features

- **Upload multiple months** — drop in several monthly files at once, or one file that already spans many months; periods are auto-detected from a date column or the filename.
- **Automatic KPI engine** — numeric columns are auto-detected and matched against a bank of common business KPI keywords (revenue, churn, satisfaction, delivery, etc.), then aggregated per month.
- **Interactive dashboard** — KPI cards + Plotly trend charts.
- **AI explanations** — a structured executive diagnostic (summary, positive trends, concerns, risks, opportunities, recommendations) generated from aggregated stats only — raw rows are never sent to the LLM.
- **Trend detection** — month-over-month % change, direction, and streaks per metric.
- **Forecast next month** — a lightweight blend of linear trend extrapolation and a weighted moving average, with a confidence label, for each metric.
- **Anomaly detection** — z-score (with an IQR fallback) flags unusual months per metric.
- **Chat with your business data** — ask questions in plain language. For small datasets, all aggregated stats are stuffed into context; once the dataset grows past ~8 monthly chunks, the app automatically switches to a lightweight TF-IDF retrieval step (no vector DB or extra embedding API needed) so answers stay fast and cheap.
- **Download PowerPoint / PDF** — a shareable report with the executive diagnostic, forecasts, anomalies, and charts, built from the exact same Plotly figures shown on screen.

## Tech stack

- **Streamlit** — UI and app framework
- **Pandas / NumPy** — data cleaning, aggregation, forecasting math
- **Plotly + kaleido** — interactive charts and static chart export for reports
- **scikit-learn** — TF-IDF retrieval for the chat feature
- **python-pptx / reportlab** — PowerPoint and PDF report generation
- **OpenAI API / Google Gemini API** — AI diagnostic + chat

## Project structure

```
business-intelligence-copilot/
├── app.py                       # Main Streamlit app (tabs: Dashboard, Trends & Forecast,
│                                 #   AI Diagnostic, Chat with Data, Export, Cleaning Log)
├── modules/
│   ├── data_loader.py            # Multi-file upload, period tagging, cleaning
│   ├── column_detector.py        # Numeric/categorical/date detection, KPI keyword matching
│   ├── kpi_engine.py              # Monthly aggregation + trend/streak computation
│   ├── forecast_engine.py         # Next-month forecast (trend + weighted moving average blend)
│   ├── anomaly_engine.py          # z-score / IQR anomaly flags per metric
│   ├── charts.py                  # Plotly chart builders (trend + forecast + anomaly overlay)
│   ├── llm_insights.py            # OpenAI/Gemini calls, structured diagnostic, chat + TF-IDF retrieval
│   └── report_export.py           # PPTX and PDF report builders
├── sample_data/
│   └── sample_multimonth_business_data.csv   # 14 months x 3 regions, with a couple of seeded anomalies
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

### 1. Create a virtual environment

```
cd business-intelligence-copilot
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate
```

### 2. Install dependencies

```
pip install -r requirements.txt
```

### 3. Set up your API key

You only need a key for **one** provider (select it in the sidebar):

- **OpenAI**: https://platform.openai.com/api-keys
- **Gemini**: https://aistudio.google.com/app/apikey

Either copy `.env.example` to `.env` and fill it in, or paste the key directly into the sidebar's password field when the app is running — it's used only for that session and never saved to disk.

### 4. Run the app

```
streamlit run app.py
```

### 5. Try it with the sample data

Upload `sample_data/sample_multimonth_business_data.csv` — it has 14 months across 3 regions with a seeded cost spike and a satisfaction dip, so you can see the anomaly detector and forecaster in action immediately.

## Notes on data privacy

Only **aggregated statistics** (monthly totals/averages, % changes, trend direction, forecasts, anomaly flags) are ever sent to the LLM provider, for both the AI diagnostic and the chat feature. Individual rows are never transmitted.

## Deploying

Same flow as the original project: push to GitHub, then deploy on [Streamlit Community Cloud](https://streamlit.io/cloud) pointing at `app.py`. Add `kaleido` to your deployment environment if chart images don't render in exports — some minimal Linux images need `libnss3`/`libgbm1` as system packages for kaleido to render headless Chromium (Streamlit Cloud's default image already has these).

## Future improvements

- Multi-sheet Excel workbook support
- Swap the TF-IDF retrieval for real embeddings once datasets grow into the hundreds of months/metrics
- Natural-language KPI target setting and alerting
- User accounts + saved report history
