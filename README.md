# 🛡️ Veritas — AI-Powered Emergency Decision Support System

**Evidence-first emergency triage for citizen incident reports.**
Built for the **Kaggle x Google AI Agents Intensive — Agents for Good** submission.

Veritas takes a raw citizen report ("There is heavy smoke near Central School") and
turns it into a defensible dispatch decision: it verifies the location and live
weather, runs an independent AI reasoning pass, checks whether other nearby
reports corroborate the same hazard, scores severity, and produces a
human-readable **evidence verdict** (Likely Real / Likely Fake / Disputed /
Resolved / Unverified) alongside a recommended response and a ready-to-send
dispatch message — with a human always in the loop for anything uncertain.

It exists to solve a real problem in emergency response: **operators are
flooded with unverified reports and have no fast way to tell a real fire from
a mistaken one, or a genuine flood from a stale/duplicate report.** Veritas
doesn't replace the dispatcher — it does the busywork of cross-checking
evidence so the dispatcher's judgement is spent on the reports that actually
need it.

---

## What makes a decision trustworthy here

Every incident is scored from **five independent signals**, and the system is
explicit about which ones fired and which didn't — nothing is silently assumed:

| Signal | Source | What it catches |
|---|---|---|
| **Keyword / rule-based severity** | `skills/severity_score.py` | Fast, deterministic hazard detection (fire, flood, collapse, explosion, ...) |
| **Location & live weather verification** | `skills/weather_geo_verify.py` (OpenStreetMap + Open-Meteo) | Confirms the place exists and checks real-time conditions (rain, wind) that raise or lower risk |
| **Independent AI reasoning** | `skills/ai_reasoning.py` (Gemini Vision) | A second, LLM-based read of the *same* report and *attached image* — catches negation ("fire is out"), contradictions with the evidence, and nuance keywords miss |
| **Multi-report corroboration** | `skills/corroboration.py` | Scans the audit log for other independent reports of the same hazard nearby and recently — one lone report is treated differently from five |
| **Report credibility** | `skills/incident_credibility.py` | How much detail and independent support the report itself has |

`skills/evidence_engine.py` combines all five into one auditable profile: an
**evidence strength** (Strong/Moderate/Weak/Insufficient), an explicit
**verdict**, and a **recommendation** a dispatcher can act on without reading
raw JSON. A single credible contradiction can never be silently outvoted by
quantity — it either caps the verdict at "Weak" or routes the incident to a
human for review.

Everything fails **closed, not silently**: if Gemini isn't reachable, if the
geocoder times out, if the audit log is missing — the pipeline treats that as
a *missing* piece of evidence (and lowers confidence accordingly), never as
"everything is fine."

---

## Architecture

         Citizen report
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Which engine?        │
                    └──────────┬───────────┘
                 ┌──────────────┴──────────────┐
                 ▼                              ▼
   CUSTOM PIPELINE (deterministic)   ADK AGENT (Gemini decides)
   ┌─────────────────────┐           ┌─────────────────────────┐
   │  Guardrail Agent    │           │  root_agent (Gemini)    │
   │  ── prompt-injection│           │  decides at runtime:    │
   │     detection, PII  │           │ • call full_emergency_  │
   │     redaction       │           │   assessment tool, OR   │
   └─────────┬───────────┘           │ • delegate to Verification│
             ▼                       │    sub-agent, OR        │
   ┌─────────────────────--┐         │ • call MCP tool         │
   │ Verification Agent    │         │ verify_location_weather │
   │ ── geocoding + live   │         └──────────┬──────────────┘
   │     weather           │                      │
   │ ── live river         │                    ▼
   │     discharge (flood) │          ┌─────────────────────────┐
   │ ── live seismic       │          │ MCP Server (subprocess) │
   │     activity (USGS)   │          │ mcp_server/server.py    │
   │ ── independent Gemini │◀──────── │ exposes verify_location_│
   │     reasoning (+ image)│  same   │ weather as an MCP too   │
   │ ── multi-report       │   skill  │ over stdio              │
   │     corroboration     │   module └─────────────────────────┘
   └─────────┬───────────--┘
             ▼
   ┌─────────────────────┐
   │    Triage Agent         │──▶ rule + AI + verification boosts → final score
   │                         │──▶ hazard-specific response unit mapping
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │   Evidence Engine       │──▶ 7-signal verdict + recommendation
   │                         │──▶ report credibility scoring
   └─────────┬───────────┘
             ▼
   ┌─────────────────────┐
   │   Comms Agent           │──▶ dispatch message + optional Gemini translation
   └─────────┬───────────┘
             ▼
     Dispatch decision + full audit trail
```

`agents/orchestrator.py` (`process_incident`) wires all of the above together
and is the single entry point every surface (Streamlit UI, ADK agent, tests)
calls into.

### One app, two engines

The Streamlit form (`app/main.py`) has a **"Processing engine"** choice
right in the incident form:

- **⚙️ Custom pipeline** (default) — calls
  `agents.orchestrator.process_incident` directly: deterministic,
  fastest, and the one exercised by the full evidence-breakdown UI
  (confidence meter, agent activity panel, timeline, map, human-review
  workflow).
- **🤖 ADK Agent** — routes the same incident through the actual Google
  ADK agent (`adk/root_agent.py`) via `app/adk_bridge.py`, which runs it
  through a real ADK `Runner`. Gemini decides on its own whether to call
  `full_emergency_assessment`, delegate to the Verification sub-agent, or
  call the **MCP-exposed** `verify_location_weather` tool
  (`mcp_server/server.py`, launched as a subprocess by the agent's
  `weather_mcp_toolset`) — no code picks the tool, the model does. The
  result panel shows the agent's final response plus which tool(s) it
  actually called.

Both options submit through the same form and render in the same results
area — switching engines is just a radio button, not a different app.

You can also run the ADK agent directly, outside Streamlit, for the full
conversational dev UI:


### Project layout

```
app/            Streamlit UI (main triage form with dual engine choice,
                dashboard, audit log) + adk_bridge.py (runs the real ADK
                agent from the form)
agents/         Orchestration layer (verification, triage, comms agents)
skills/         Independent, individually-testable reasoning/verification units
guardrails/     Prompt-injection detection, PII redaction, human-review policy
adk/            Google ADK agent definitions (root agent + sub-agent + tool)
mcp_server/     Standalone MCP server exposing the weather/geo verification tool
data/           Audit log (incidents.jsonl) + response-unit reference data
scripts/        seed_data.py — populate the dashboard with demo data
tests/          Pytest suite (network-free — verification/AI calls are mocked
                by passing hand-built dicts directly into the functions under test)
```

---

## Setup

**Requirements:** Python 3.11+ and a [Gemini API key](https://aistudio.google.com/apikey)
(optional — the app runs without one, just with the AI-reasoning signal
unavailable, as designed).

```bash
# 1. Clone / unzip and enter the project
cd veritas

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
cp .env.example .env
# then edit .env and set GOOGLE_API_KEY=<your key>

# 5. (Optional) seed some demo incidents so the dashboard isn't empty
python scripts/seed_data.py --reset

# 6. Run the app
streamlit run app/main.py
```

> **Note:** `.env` is git-ignored. Never commit a real API key — use
> `.env.example` as the template. If a key was ever committed to a repo or
> shared in a zip, treat it as compromised and rotate it in
> [Google AI Studio](https://aistudio.google.com/apikey).

Once running, open the sidebar to navigate to **📊 Incident Dashboard** and
**📜 Audit Log** — both read from `data/incidents.jsonl`, the same append-only
log every processed incident (and every human review action) is written to.

### Running the ADK agent standalone

Prefer the in-app option above for a quick check -- use this for the full
conversational dev UI instead:

```bash
adk web adk        # launches the ADK dev UI against adk/agent.py
```

### Running the MCP server standalone

```bash
python mcp_server/server.py
```

### Running tests

```bash
pytest
```

The suite (52 tests across `tests/`) exercises the triage scoring, confidence
logic, evidence engine, and credibility skill in isolation — verification/AI
calls are never actually made over the network in tests; hand-built
`verification`/`triage` dicts are passed directly into the functions under
test, so `pytest` runs deterministically offline.

---

## Design notes / known limitations

- **Human-in-the-loop by policy, not by accident.** `guardrails/policy.yaml`
  sets the human-review threshold, low-confidence threshold, and a list of
  hazard keywords (trapped, injured, collapse, explosion, ...) that always
  force review regardless of score — so a high-consequence report can never
  be silently auto-dispatched purely because the math came out high enough.
- **Corroboration currently only looks at Veritas's own audit log**, not an
  external social-media/911-feed source — in a real deployment this would
  pull from whatever multi-channel intake system feeds Veritas. This could be extended to include real-time social media feeds or official incident reports for richer corroboration.
- **Translation (`skills/translate_dispatch.py`) supports English, Hindi, and
  Spanish** for the demo; extending `LANGUAGE_NAMES` is enough to add more,
  since translation goes through Gemini rather than a fixed phrase table.
- **Sensor readings** (`skills/weather_geo_verify.py: SENSOR_TYPES`) cover six
  types — `smoke`, `flood`, `temp`, `gas`, `seismic`, `structural` — each
  mapped to the hazard(s) it's evidence for (e.g. `seismic` → earthquake/
  tsunami/landslide, `gas` → explosion/fire) with its own threshold and risk
  boost. Every reading is treated as a normalized 0-100 intensity scale for
  that sensor. Adding a new sensor type is a one-line addition to that dict —
  no other code changes needed, since the Streamlit dropdown and the risk
  calculation both read from it directly.
- **The severity keyword list and resource mapping** (`skills/severity_score.py`,
  `skills/resource_mapper.py`) have been expanded to include more granular hazards like chemical spills and medical emergencies, making the system more comprehensive. These are illustrative starting points, not a substitute for a jurisdiction's actual dispatch protocol — they're meant to
  be swapped in for real ones per deployment.
- `data/incidents.jsonl` ships pre-seeded with a handful of synthetic demo
  incidents (via `scripts/seed_data.py`) purely so the dashboard/audit log
  aren't empty on first run; delete it and re-seed for a clean demo.

---

## Credits

Built for the Kaggle x Google AI Agents Intensive (Agents for Good) capstone.
Uses Gemini (`google-genai` / `google-adk`), Streamlit, OpenStreetMap
Nominatim, and Open-Meteo.
