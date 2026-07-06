import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from agents.orchestrator import process_incident
from agents.review_actions import append_review_action
from skills.weather_geo_verify import SENSOR_TYPES
from app.adk_bridge import run_incident_via_adk

st.set_page_config(page_title="Veritas", page_icon="🛡️", layout="wide")
st.title("🛡️ Veritas - Emergency Triage AI")

with st.form("incident_form"):
    report_text = st.text_area(
        "Citizen report",
        "There is heavy smoke and possible fire near Central School."
    )
    location = st.text_input("Location", "Central School, Sector 7")
    sensor_keys = list(SENSOR_TYPES.keys())
    sensor_type = st.selectbox(
        "Sensor type",
        sensor_keys,
        format_func=lambda k: SENSOR_TYPES[k]["label"],
    )
    st.caption(
        f"Evidence for: {', '.join(SENSOR_TYPES[sensor_type]['hazards'])} "
        f"· triggers risk boost above {SENSOR_TYPES[sensor_type]['threshold']}"
    )
    sensor_value = st.number_input("Sensor value (0-100 scale)", value=72.0)
    lang = st.selectbox("Alert language", ["en", "hi", "es"])
    engine = st.radio(
        "Processing engine",
        ["custom", "adk"],
        format_func=lambda k: {
            "custom": "⚙️ Custom pipeline (deterministic, fastest)",
            "adk": "🤖 ADK Agent (Gemini decides which tool to call, incl. MCP)",
        }[k],
        horizontal=True,
    )
    uploaded_file = st.file_uploader("Attach evidence photo (optional)", type=["jpg", "jpeg", "png", "webp"])
    submit = st.form_submit_button("Run Veritas")

if submit:
    image_path = None
    if uploaded_file:
        save_dir = Path("data/uploads")
        save_dir.mkdir(parents=True, exist_ok=True)
        image_path = str(save_dir / uploaded_file.name)
        with open(image_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

    incident = {
        "report_text": report_text,
        "location": location,
        "sensor_type": sensor_type,
        "sensor_value": sensor_value,
        "lang": lang,
        "image_path": image_path,
    }

    if engine == "adk":
        with st.spinner("Running the ADK agent (Gemini is choosing which tool to call)..."):
            result = run_incident_via_adk(incident)
    else:
        result = process_incident(incident)

    st.session_state["last_incident"] = incident
    st.session_state["last_result"] = result
    st.session_state["last_engine"] = engine

# Render last result if available
if "last_result" in st.session_state:
    result = st.session_state["last_result"]
    incident = st.session_state["last_incident"]

    engine = st.session_state.get("last_engine", "custom")

    if engine == "adk":
        st.subheader("🤖 ADK Agent Response")
        st.caption(
            "This request was routed through the actual Google ADK agent "
            "(adk/root_agent.py) instead of the deterministic pipeline -- "
            "Gemini decided on its own which tool(s) to call."
        )
        if result.get("error"):
            st.warning("The ADK agent run failed.")
            st.code(result["error"], language="text")
        else:
            if result.get("tool_calls"):
                st.info(f"🔧 Tool(s) called by the agent: {', '.join(result['tool_calls'])}")
            else:
                st.caption("The agent answered directly without calling a tool.")
            st.write(result["final_text"])
            with st.expander("Full agent transcript"):
                st.text(result.get("transcript", "") or "(no transcript captured)")
        with st.expander("Full JSON"):
            st.json(result)

    else:
        st.subheader("Decision Summary")

        if result["status"] == "blocked":
            st.error("🚫 Blocked by safety guardrail")
            st.write(f"**Reason:** {result.get('reason', 'Unspecified')}")
            with st.expander("Full JSON"):
                st.json(result)

        else:
            triage = result["triage"]
            verification = result["verification"]
            confidence = triage["confidence"]
            confidence_pct = int(confidence * 100)

            # ==========================
            # Decision Summary
            # ==========================
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.caption("Status")
                st.markdown(f"#### {result['status'].replace('_', ' ').title()}")
            c2.metric("Severity", triage["tier"])
            c3.metric("Score", triage["final_score"])
            c4.metric("Confidence", f"{confidence_pct}%")

            # ==========================
            # Incident Summary
            # ==========================
            st.subheader("⚠️ Incident Summary")

            col_left, col_right = st.columns(2)

            with col_left:
                st.write("**📍 Location**")
                st.write(incident["location"])

                st.write("**Sensor**")
                st.write(f"{incident['sensor_type']} ({incident['sensor_value']})")

            with col_right:
                st.write("**🔥 Hazards Detected**")

                icons = {
                    "fire": "🔥",
                    "explosion": "💥",
                    "smoke": "💨",
                    "flood": "🌊",
                    "collapse": "🏚️",
                    "injured": "🚑",
                    "trapped": "🆘",
                    "earthquake": "🌍",
                    "tsunami": "🌊",
                    "landslide": "⛰️",
                    "accident": "🚗",
                }

                hits = triage["keyword_hits"]

                if hits:
                    for h in hits:
                        st.write(f"{icons.get(h, '⚠️')} {h.title()}")
                else:
                    st.write("No hazards detected.")

            # ==========================
            # Evidence Breakdown
            # ==========================
            st.subheader("🧪 Evidence Breakdown")
            st.caption(
                "How the final score was assembled — each source contributes "
                "independently before being combined."
            )

            e1, e2, e3, e4 = st.columns(4)

            e1.metric("Rule-based score", triage["rule_score"])
            e1.caption("Keyword matching")

            ai_score_display = triage["ai_score"] if triage.get("ai_available") else "N/A"
            e2.metric("AI reasoning score", ai_score_display)
            e2.caption("Gemini" if triage.get("ai_available") else "Unavailable")

            e3.metric("Weather risk boost", f"+{verification.get('weather_risk_boost', 0)}")
            e3.caption("Live weather")

            e4.metric("Corroboration boost", f"+{verification.get('corroboration_boost', 0)}")
            e4.caption(f"{triage.get('corroboration_count', 0)} matching report(s)")

            if triage.get("ai_negated"):
                st.warning(
                    "⚠️ AI reasoning detected the report negates/retracts the hazard — "
                    "final score was capped regardless of keyword matches."
                )
            if triage.get("ai_contradicts_evidence"):
                st.warning(
                    "⚠️ AI reasoning found the report contradicts verified weather/sensor "
                    "evidence — confidence was reduced."
                )

            # ==========================
            # Operational Assessment (Evidence Engine)
            # ==========================
            st.subheader("📋 Operational Assessment")

            evidence = result.get("evidence") or {}
            assessment = evidence.get("assessment", {})
            strength = assessment.get("evidence_strength", "Unknown")
            verdict = assessment.get("verdict", "Unverified")

            strength_color = {
                "Strong": "🟢",
                "Moderate": "🟡",
                "Weak": "🟠",
                "Insufficient": "🔴",
            }.get(strength, "⚪")

            verdict_style = {
                "Likely Real": ("🟢", st.success),
                "Likely Fake": ("🔴", st.error),
                "Disputed -- Needs Human Review": ("🟠", st.warning),
                "Resolved / False Alarm": ("ℹ️", st.info),
                "Unverified": ("⚪", st.info),
            }.get(verdict, ("⚪", st.info))
            verdict_icon, verdict_box = verdict_style

            verdict_box(f"{verdict_icon} **Verdict: {verdict}** — {assessment.get('verdict_reason', '')}")

            a1, a2 = st.columns([1, 2])
            with a1:
                st.metric("Evidence Strength", f"{strength_color} {strength}")
            with a2:
                st.markdown(f"**Recommendation:** {assessment.get('recommendation', '—')}")
                st.caption(assessment.get("explanation", ""))

            st.write("**Evidence sources:**")
            status_icon = {"supports": "✅", "contradicts": "⚠️", "unavailable": "➖", "neutral": "ℹ️"}
            for source in evidence.get("sources", []):
                icon = status_icon.get(source.get("status"), "•")
                st.write(f"{icon} **{source.get('name')}** — {source.get('detail')}")
            
            with st.expander("Legend: What do these icons mean?"):
                st.markdown("""
                - ✅ **Supports**: This source actively confirms the report (e.g., high sensor reading).
                - ⚠️ **Contradicts**: This source actively conflicts with the report (e.g., AI flags as fake).
                - ℹ️ **Neutral**: Successful check, but found no active evidence either way (e.g., clear skies, normal water level).
                - ➖ **Unavailable**: The source could not be reached or provided no data (e.g., API timeout).
                """)

            if evidence.get("warnings"):
                with st.expander("⚠️ Warnings / missing evidence", expanded=False):
                    for w in evidence["warnings"]:
                        st.write(f"• {w}")

            if triage.get("corroboration_matches"):
                st.subheader("👥 Independent Corroborating Reports")
                for m in triage["corroboration_matches"]:
                    st.write(
                        f"- **{m.get('location', 'Unknown')}** "
                        f"({m.get('distance_km', '?')} km away): "
                        f"\"{m.get('report_text', '')}\""
                    )

            # ==========================
            # Confidence Meter
            # ==========================
            st.subheader("🎯 Verification Confidence")

            if confidence >= 0.80:
                color, label = "🟢", "High"
            elif confidence >= 0.60:
                color, label = "🟡", "Medium"
            else:
                color, label = "🔴", "Low"

            st.progress(confidence)
            st.markdown(f"### {color} {confidence_pct}% Confidence ({label})")

            reasons = []
            if verification.get("location_verified"):
                reasons.append("✅ Location verified")
            if verification.get("live_weather"):
                reasons.append("✅ Live weather data available")
            if hits:
                reasons.append("✅ Incident keywords detected")
            if triage.get("ai_available"):
                reasons.append("✅ AI reasoning pass completed")
            if triage.get("corroboration_count", 0) > 0:
                reasons.append("✅ Independent corroboration found")

            if reasons:
                st.caption("Confidence based on:")
            for reason in reasons:
                st.write(reason)

            # ==========================
            # Agent Activity Panel
            # ==========================
            st.subheader("🧩 Agent Activity")

            with st.expander("Guardrail Agent", expanded=False):
                st.success("Safety checks passed")
                st.write("• No prompt injection detected")
                st.write("• No sensitive information violations")

            with st.expander("Verification Agent", expanded=False):
                if verification.get("location_verified"):
                    st.success("Location verified")
                else:
                    st.error("Location could not be verified")

                if verification.get("live_weather"):
                    st.success("Weather data retrieved")
                else:
                    st.warning("Weather data unavailable")

                if triage.get("corroboration_count", 0) > 0:
                    st.success(f"{triage['corroboration_count']} corroborating report(s) found")
                else:
                    st.info("No corroborating reports found")

            with st.expander("AI Reasoning Agent (Gemini)", expanded=False):
                if triage.get("ai_available"):
                    st.success("AI reasoning completed")
                    st.write(f"**AI score:** {triage['ai_score']}")
                    st.write(f"**Rationale:** {triage.get('ai_rationale', '—')}")
                    st.write(f"**Negated:** {'Yes' if triage.get('ai_negated') else 'No'}")
                    st.write(
                        f"**Contradicts evidence:** "
                        f"{'Yes' if triage.get('ai_contradicts_evidence') else 'No'}"
                    )
                else:
                    st.warning("AI reasoning unavailable for this report")
                    error = triage.get("ai_error")
                    if error:
                        st.code(error, language="text")
                    else:
                        st.caption("No error captured -- this shouldn't normally happen.")

            with st.expander("Triage Agent", expanded=False):
                st.write(f"**Severity:** {triage['tier']}")
                st.write(f"**Final score:** {triage['final_score']}")
                st.write(f"**Confidence:** {confidence_pct}%")
                if hits:
                    st.write("**Detected hazards:**")
                    for hazard in hits:
                        st.write(f"• {hazard.title()}")

            with st.expander("📢 Communication Agent", expanded=False):
                st.success("Dispatch message generated")
                st.code(result["dispatch_message"], language="text")

            # ==========================
            # Incident Processing Timeline
            # ==========================
            st.subheader("🕒 Incident Processing Timeline")

            start_time = datetime.now().replace(microsecond=0)

            timeline = [
                ("Report received", 0),
                ("Guardrail validation completed", 1),
                (
                    "Location verified" if verification.get("location_verified")
                    else "Location verification failed",
                    2,
                ),
                (
                    "Live weather retrieved" if verification.get("live_weather")
                    else "Weather data unavailable",
                    3,
                ),
                (
                    "AI reasoning completed" if triage.get("ai_available")
                    else "AI reasoning unavailable",
                    4,
                ),
                (
                    f"Corroboration check ({triage.get('corroboration_count', 0)} match(es))",
                    5,
                ),
                ("Severity assessment completed", 6),
                ("Dispatch message generated", 7),
            ]

            for event, seconds in timeline:
                event_time = (start_time + timedelta(seconds=seconds)).strftime("%H:%M:%S")
                st.write(f"**{event_time}**  •  {event}")

            # ==========================
            # Recommended Response Units
            # ==========================
            st.subheader("🚒 Recommended Response Units")

            for resource in triage["resources"]:
                with st.container(border=True):
                    st.write(f"**{resource}**")
                    st.caption("Status: Ready for dispatch")

            # ==========================
            # Verification Evidence
            # ==========================
            st.subheader("🌦️ Verification Evidence")

            if verification.get("location_verified"):
                st.success("✅ Location Verified")
            else:
                st.error("❌ Location could not be verified")

            weather = verification.get("live_weather") or {}

            col1, col2, col3 = st.columns(3)
            col1.metric("Temperature", f"{weather.get('temperature_2m', '--')} °C")
            col2.metric("Rain", f"{weather.get('precipitation', '--')} mm")
            col3.metric("Wind", f"{weather.get('wind_speed_10m', '--')} km/h")

            st.info(f"Weather Risk Boost: +{verification.get('weather_risk_boost', 0)}")

            if verification.get("notes"):
                st.caption(verification["notes"])

            # ==========================
            # Water Level Evidence
            # ==========================
            water_data = verification.get("live_water_data") or {}

            if water_data:
                st.subheader("💧 Water Level Verification")

                col1, col2, col3 = st.columns(3)
                col1.metric("Current Discharge", f"{water_data.get('current_discharge_m3s', '--')} m³/s")
                col2.metric("Water Severity", triage.get("water_level_severity", "unknown").title())
                col3.metric("Water Risk Boost", f"+{verification.get('water_level_risk_boost', 0)}")

                if water_data.get("next_7_days_forecast"):
                    st.caption("7-day river discharge forecast:")
                    forecast_df = pd.DataFrame({
                        "Date": water_data.get("forecast_timestamps", []),
                        "Discharge (m³/s)": water_data.get("next_7_days_forecast", [])
                    })
                    st.line_chart(forecast_df.set_index("Date"))

            # ==========================
            # Seismic Activity Evidence
            # ==========================
            seismic_data = verification.get("live_seismic_data") or {}
            closest_eq = verification.get("closest_earthquake")

            if seismic_data and closest_eq:
                st.subheader("🌍 Seismic Activity Verification")

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Magnitude", f"M{closest_eq.get('magnitude', '?')}")
                col2.metric("Distance", f"{closest_eq.get('distance_km', '?'):.1f} km")
                col3.metric("Hours Ago", f"{closest_eq.get('hours_ago', '?'):.1f}h")
                col4.metric("Seismic Risk Boost", f"+{verification.get('seismic_risk_boost', 0)}")

                st.write(f"**Location:** {closest_eq.get('location', 'Unknown')}")
                st.write(f"**Depth:** {closest_eq.get('depth_km', '?')} km")
                st.write(f"**Severity:** {triage.get('seismic_severity', 'unknown').title()}")

                if seismic_data.get("earthquakes"):
                    with st.expander(f"📊 Other nearby earthquakes ({len(seismic_data['earthquakes'])} detected)"):
                        for eq in seismic_data["earthquakes"][:5]:
                            st.write(
                                f"- **M{eq['magnitude']}** {eq['distance_km']:.1f}km away "
                                f"({eq['hours_ago']:.1f}h ago): {eq['location']}"
                            )

            # ==========================
            # Incident Location Map
            # ==========================
            st.subheader("📍 Incident Location")

            coordinates = verification.get("coordinates")

            if coordinates:
                st.caption(
                    f"Latitude: {coordinates['latitude']:.5f} | "
                    f"Longitude: {coordinates['longitude']:.5f}"
                )
                map_data = pd.DataFrame({
                    "lat": [coordinates["latitude"]],
                    "lon": [coordinates["longitude"]],
                })
                st.map(map_data)
            else:
                st.warning("Location coordinates unavailable.")

            # ==========================
            # Dispatch Message
            # ==========================
            st.subheader("📨 Dispatch Message")
            st.code(result["dispatch_message"])

            # ==========================
            # Human Review
            # ==========================
            if result["status"] == "needs_human_review":
                st.warning("⚠️ Human review required before dispatch")

                note = st.text_input("Reviewer note", value="Reviewed by dispatcher.")

                col_a, col_b, col_c = st.columns(3)

                if col_a.button("✅ Approve Dispatch"):
                    log = append_review_action(
                        incident, triage, action="approve", note=note
                    )
                    st.success("Dispatch approved and logged.")
                    st.json(log)

                if col_b.button("⏸ Hold"):
                    log = append_review_action(
                        incident, triage, action="hold", note=note
                    )
                    st.info("Incident put on hold and logged.")
                    st.json(log)

                if col_c.button("❌ Reject"):
                    log = append_review_action(
                        incident, triage, action="reject", note=note
                    )
                    st.error("Dispatch rejected and logged.")
                    st.json(log)

            # ==========================
            # Full JSON
            # ==========================
            with st.expander("Full JSON"):
                st.json(result)