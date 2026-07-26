"""
llm_insights.py
- Wraps OpenAI and Gemini chat-completion calls behind one interface.
- Turns aggregated KPI/trend/forecast/anomaly stats into a structured
  AI diagnostic (never sends raw rows to the LLM).
- Provides a lightweight retrieval layer (TF-IDF, no extra API calls or
  vector DB needed) so "chat with your data" stays cheap and fast for
  small datasets, and automatically switches to retrieval-augmented
  mode once the number of monthly chunks grows past a threshold.
"""

import json
import re

RAG_TRIGGER_CHUNK_COUNT = 8  # once we have more than this many chunks, retrieve instead of stuffing everything in context


# ---------------------------------------------------------------------------
# Provider-agnostic LLM call
# ---------------------------------------------------------------------------

def call_llm(provider: str, api_key: str, system_prompt: str, user_prompt: str,
             max_tokens: int = 900, temperature: float = 0.4) -> str:
    if not api_key:
        raise ValueError("No API key provided for the selected LLM provider.")

    if provider == "OpenAI":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content

    elif provider == "Gemini":
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            system_instruction=system_prompt,
        )
        resp = model.generate_content(
            user_prompt,
            generation_config={"max_output_tokens": max_tokens, "temperature": temperature},
        )
        return resp.text

    else:
        raise ValueError(f"Unknown provider: {provider}")


def _extract_json(text: str) -> dict:
    """LLMs sometimes wrap JSON in ```json fences or add stray text — strip that."""
    cleaned = re.sub(r"```json|```", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Structured executive diagnostic
# ---------------------------------------------------------------------------

DIAGNOSTIC_SYSTEM_PROMPT = (
    "You are a senior business analyst producing a concise executive diagnostic "
    "from aggregated business statistics. You never see raw customer records, only "
    "summary statistics. Respond ONLY with valid JSON, no markdown fences, no preamble, "
    "matching exactly this schema: "
    '{"executive_summary": str, "positive_trends": [str], "areas_of_concern": [str], '
    '"risks": [str], "growth_opportunities": [str], "recommendations": [str]}'
)


def build_stats_payload(monthly_summary_dict: dict, trends: dict, anomalies: dict, forecasts: dict) -> str:
    """Serializes only aggregated stats (no raw rows) into a compact JSON string for the LLM."""
    payload = {
        "monthly_summary": monthly_summary_dict,
        "trends": {
            m: {
                "latest_value": d["latest_value"],
                "latest_pct_change": d["latest_pct_change"],
                "overall_direction": d["overall_direction"],
                "streak_months": d["streak_months"],
            } for m, d in trends.items()
        },
        "anomalies": anomalies,
        "forecasts": forecasts,
    }
    return json.dumps(payload, default=str)


def generate_diagnostic(monthly_summary_dict, trends, anomalies, forecasts, provider, api_key) -> dict:
    stats_json = build_stats_payload(monthly_summary_dict, trends, anomalies, forecasts)
    user_prompt = (
        "Here are the aggregated monthly business statistics (JSON). "
        "Produce the executive diagnostic described in your instructions.\n\n"
        f"{stats_json}"
    )
    raw = call_llm(provider, api_key, DIAGNOSTIC_SYSTEM_PROMPT, user_prompt)
    return _extract_json(raw)


# ---------------------------------------------------------------------------
# Chat with your data (lite-RAG)
# ---------------------------------------------------------------------------

def build_context_chunks(monthly_summary_df, trends: dict, anomalies: dict, forecasts: dict) -> list:
    """
    Builds one short text chunk per period (plus one chunk per metric with
    anomalies/forecast) so retrieval can operate at a useful granularity.
    """
    chunks = []
    for _, row in monthly_summary_df.iterrows():
        period = row["period"]
        parts = [f"Period {period}:"]
        for col in monthly_summary_df.columns:
            if col in ("period",):
                continue
            parts.append(f"{col}={row[col]}")
        chunks.append(" ".join(parts))

    for metric, data in trends.items():
        chunks.append(
            f"Trend for {metric}: latest value {data['latest_value']}, "
            f"latest change {data['latest_pct_change']}%, "
            f"overall direction {data['overall_direction']}, "
            f"{data['streak_months']}-month streak."
        )

    for metric, found in anomalies.items():
        for a in found:
            chunks.append(
                f"Anomaly in {metric} at {a['period']}: value {a['value']} "
                f"({a['direction']}, z={a['z_score']})."
            )

    for metric, f in forecasts.items():
        chunks.append(
            f"Forecast for {metric} next period: {f['forecast']} "
            f"(confidence: {f['confidence']}). {f['note']}"
        )

    return chunks


def retrieve_relevant_chunks(chunks: list, query: str, top_k: int = 6) -> list:
    """TF-IDF cosine-similarity retrieval — no external embedding API needed."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    if len(chunks) <= top_k:
        return chunks

    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(chunks + [query])
    sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
    ranked_idx = sims.argsort()[::-1][:top_k]
    return [chunks[i] for i in sorted(ranked_idx)]


CHAT_SYSTEM_PROMPT = (
    "You are a business intelligence copilot answering questions about the user's "
    "own business data. You are given retrieved context snippets (aggregated stats "
    "only — never raw records). Answer directly and concisely, citing specific "
    "numbers from the context where relevant. If the context doesn't contain the "
    "answer, say so honestly rather than guessing."
)


def chat_with_data(query: str, chunks: list, chat_history: list, provider: str, api_key: str) -> str:
    """
    chat_history: list of {"role": "user"/"assistant", "content": str}
    Uses retrieval automatically once the chunk count passes RAG_TRIGGER_CHUNK_COUNT,
    otherwise stuffs all chunks into context directly (cheaper for small datasets).
    """
    if len(chunks) > RAG_TRIGGER_CHUNK_COUNT:
        relevant = retrieve_relevant_chunks(chunks, query, top_k=8)
        mode_note = "(retrieval-augmented — dataset is large enough that only the most relevant snippets were retrieved)"
    else:
        relevant = chunks
        mode_note = "(full context — small dataset)"

    context_block = "\n".join(f"- {c}" for c in relevant)
    history_block = "\n".join(f"{m['role']}: {m['content']}" for m in chat_history[-6:])

    user_prompt = (
        f"Context {mode_note}:\n{context_block}\n\n"
        f"Conversation so far:\n{history_block}\n\n"
        f"User question: {query}"
    )
    return call_llm(provider, api_key, CHAT_SYSTEM_PROMPT, user_prompt, max_tokens=600)
