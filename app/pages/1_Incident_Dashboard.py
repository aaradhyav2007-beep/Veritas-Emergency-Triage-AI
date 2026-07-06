import json
from pathlib import Path

import pandas as pd
import streamlit as st

st.title("📊 Incident Dashboard")

path = Path("data/incidents.jsonl")
if not path.exists():
    st.info("No incidents yet.")
    st.stop()

records = []
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            obj = json.loads(line)
            if obj.get("result"):
                r = obj["result"]
                t = r.get("triage", {})
                records.append(
                    {
                        "timestamp": obj.get("timestamp"),
                        "status": r.get("status"),
                        "tier": t.get("tier"),
                        "score": t.get("final_score"),
                        "location": obj.get("incident", {}).get("location"),
                        "verdict": r.get("evidence", {}).get("assessment", {}).get("verdict", "Unknown"),
                    }
                )
        except Exception:
            pass

if not records:
    st.warning("No processed incident records found.")
    st.stop()

df = pd.DataFrame(records)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total incidents", len(df))
c2.metric("Needs human review", int((df["status"] == "needs_human_review").sum()))
c3.metric("Blocked", int((df["status"] == "blocked").sum()))
avg_score = round(df["score"].mean(), 1) if not df["score"].isna().all() else 0
c4.metric("Avg Severity Score", avg_score)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Severity distribution")
    st.bar_chart(df["tier"].value_counts())
with col_b:
    st.subheader("Evidence Verdicts")
    st.bar_chart(df["verdict"].value_counts())

st.subheader("Score trend")
df2 = df.copy()
df2["timestamp"] = pd.to_datetime(df2["timestamp"], errors="coerce")
df2 = df2.dropna(subset=["timestamp"]).sort_values("timestamp")
if len(df2) > 0:
    chart_df = df2.set_index("timestamp")[["score"]]
    st.line_chart(chart_df)

with st.expander("Table view"):
    st.dataframe(df.sort_values("timestamp", ascending=False), use_container_width=True)
