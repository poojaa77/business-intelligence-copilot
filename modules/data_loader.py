"""
data_loader.py
Handles loading one or many CSV/Excel files, tags each row with a
detected reporting period (month), concatenates them, and cleans the
combined dataframe. Designed to accept:
  - Multiple single-month files (one file per month)
  - One file already containing a date/period column spanning many months
  - A mix of both
"""

import io
import re
import pandas as pd
import numpy as np

MONTH_NAME_RE = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s_\-]?(\d{2,4})?",
    re.IGNORECASE,
)


def _guess_period_from_filename(filename: str):
    """Try to pull a month/period label out of a filename like
    'sales_march_2025.csv' or 'Jan2026.xlsx'. Returns a string label or None."""
    match = MONTH_NAME_RE.search(filename)
    if not match:
        return None
    month_part = match.group(1).capitalize()
    year_part = match.group(2) or ""
    label = f"{month_part} {year_part}".strip()
    return label


def _read_single_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name
    raw = uploaded_file.read()
    buffer = io.BytesIO(raw)
    if name.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(buffer)
    else:
        # Try a couple of encodings/separators defensively
        try:
            df = pd.read_csv(buffer)
        except UnicodeDecodeError:
            buffer.seek(0)
            df = pd.read_csv(buffer, encoding="latin-1")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_multiple_files(uploaded_files, date_column_hint: str = None):
    """
    Accepts a list of Streamlit UploadedFile objects.
    Returns:
        combined_df: pandas DataFrame with a guaranteed 'period' column
        cleaning_log: list[str] describing what was done
        file_summaries: dict[filename -> row count]
    """
    cleaning_log = []
    frames = []
    file_summaries = {}

    for f in uploaded_files:
        df = _read_single_file(f)
        file_summaries[f.name] = len(df)

        has_date_col = date_column_hint and date_column_hint in df.columns
        if not has_date_col:
            # look for any column that looks like a date
            for col in df.columns:
                if re.search(r"date|month|period", col, re.IGNORECASE):
                    date_column_hint = col
                    has_date_col = True
                    break

        if has_date_col:
            df["_source_period"] = pd.to_datetime(
                df[date_column_hint], errors="coerce"
            ).dt.to_period("M").astype(str)
            missing = df["_source_period"].isna().sum()
            if missing:
                cleaning_log.append(
                    f"{f.name}: {missing} row(s) had an unparseable date and were tagged 'Unknown'."
                )
                df["_source_period"] = df["_source_period"].fillna("Unknown")
        else:
            guessed = _guess_period_from_filename(f.name) or f.name
            df["_source_period"] = guessed
            cleaning_log.append(
                f"{f.name}: no date column found, tagged every row as period '{guessed}' from the filename."
            )

        frames.append(df)

    combined = pd.concat(frames, ignore_index=True, sort=False)
    cleaning_log.append(
        f"Combined {len(uploaded_files)} file(s) into {len(combined)} rows across "
        f"{combined['_source_period'].nunique()} period(s)."
    )
    combined = clean_dataframe(combined, cleaning_log)
    return combined, cleaning_log, file_summaries


def clean_dataframe(df: pd.DataFrame, cleaning_log: list) -> pd.DataFrame:
    before_rows = len(df)
    df = df.dropna(axis=1, how="all")
    df = df.dropna(axis=0, how="all")
    dropped = before_rows - len(df)
    if dropped:
        cleaning_log.append(f"Dropped {dropped} fully-empty row(s).")

    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()

    # Coerce numeric-looking text columns (e.g. "$1,200", "15%")
    for col in df.columns:
        if df[col].dtype == object and col != "_source_period":
            sample = df[col].dropna().astype(str).head(20)
            looks_numeric = sample.str.match(r"^-?\$?\s?[\d,]+\.?\d*%?$").mean() > 0.7 if len(sample) else False
            if looks_numeric:
                cleaned = (
                    df[col]
                    .astype(str)
                    .str.replace(r"[$,%\s]", "", regex=True)
                )
                converted = pd.to_numeric(cleaned, errors="coerce")
                if converted.notna().mean() > 0.7:
                    df[col] = converted
                    cleaning_log.append(f"Converted column '{col}' from text to numeric.")

    dupes = df.duplicated().sum()
    if dupes:
        df = df.drop_duplicates()
        cleaning_log.append(f"Removed {dupes} exact duplicate row(s).")

    return df.reset_index(drop=True)


def period_sort_key(period_label: str):
    """Sorts 'YYYY-MM' style strings chronologically; falls back to
    alphabetical for anything else (e.g. 'Unknown')."""
    try:
        return pd.Period(period_label, freq="M").ordinal
    except Exception:
        return float("inf")
