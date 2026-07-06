import json
from pathlib import Path
import pandas as pd
import streamlit as st

st.title("📜 Veritas Audit Log")

path = Path("data/incidents.jsonl")
if not path.exists():
    st.info("No incidents logged yet.")
    st.stop()

rows = []
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            obj = json.loads(line)

            if obj.get("type") == "human_review_action":
                rows.append({
                    "timestamp": obj.get("timestamp"),
                    "event_type": "human_review_action",
                    "status": obj.get("action"),
                    "tier": obj.get("triage", {}).get("tier"),
                    "score": obj.get("triage", {}).get("final_score"),
                    "location": obj.get("incident", {}).get("location"),
                    "report": obj.get("incident", {}).get("report_text"),
                    "reviewer": obj.get("reviewer"),
                    "note": obj.get("note"),
                })
            else:
                rows.append({
                    "timestamp": obj.get("timestamp"),
                    "event_type": "incident_processed",
                    "status": obj.get("result", {}).get("status"),
                    "tier": obj.get("result", {}).get("triage", {}).get("tier"),
                    "score": obj.get("result", {}).get("triage", {}).get("final_score"),
                    "location": obj.get("incident", {}).get("location"),
                    "report": obj.get("incident", {}).get("report_text"),
                    "reviewer": "",
                    "note": "",
                })
        except Exception:
            pass

df = pd.DataFrame(rows)
if len(df) == 0:
    st.warning("No valid records.")
else:
    st.dataframe(df.sort_values("timestamp", ascending=False), use_container_width=True)

if st.checkbox("Show raw log entries"):
    st.write(rows)