# Aegis FinOps — Autonomous Cloud Cost Optimization Agent

**A submission-ready, local-first implementation of the KMIT problem statement “The Cloud Bill That Wouldn’t Stop Growing”.**

Aegis FinOps turns supplied cloud JSON into a reproducible simulated environment, investigates it with explicit agent tools, proposes a bounded action, runs the proposal through deterministic safety policy, executes through a simulator, fetches fresh state, verifies what actually happened, and records an audit trail.

> **AI investigates. Deterministic code authorizes. APIs execute. Fresh state verifies. The system explains reality.**

## What makes this version submission-ready

- Accepts **your own JSON input** from the Data Studio UI.
- Supports one or many JSON files, including `services.json`, service/metric objects, traffic records, pricing, events and action results.
- Includes the exact structured KMIT Test A/B/C/D inputs as source files under `data/source_problem/`.
- Includes a reproducible KMIT scenario runner.
- Includes a no-key local MockAgent that genuinely investigates the supplied data with read/verification tools.
- Includes optional Anthropic/OpenAI adapters without requiring an API key.
- Keeps mutation tools out of the model-facing tool surface; final actions go through deterministic backend policy.
- Handles stale observations, changing traffic, capacity limits, health/availability, failed actions and post-action verification.
- Provides a polished cloud-operations command center UI with Data Studio, Services, AI Agent, Scenario Lab, Verification Center and Audit Trail.
- Generates a downloadable Markdown report for every completed agent run.
- Includes automated unit, scenario, import and adversarial tests.

## Architecture

```text
JSON / natural-language request
           │
           ▼
     Data Normalizer
           │
           ▼
     Simulated Cloud
           │
           ▼
       Agent Layer
     ┌─────┴─────┐
     │           │
   Mock       optional
   Agent      Claude/OpenAI
     │           │
     └─────┬─────┘
           ▼
   Structured Proposal
           │
           ▼
   Deterministic Safety Gate
           │
      ┌────┴────┐
      │         │
    BLOCK     ALLOW
      │         │
      │         ▼
      │     Controlled API
      │         │
      │         ▼
      │   Fresh-State Verify
      │         │
      └────┬────┘
           ▼
       Audit Trail
```

## Run on Windows

### PowerShell

```powershell
.\run.ps1
```

### Command Prompt

```cmd
run.bat
```

### Manual

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**.

API docs: **http://127.0.0.1:8000/docs**

## How to use your own data

1. Open **Data Studio**.
2. Drag one or more `.json` files into the upload area, or paste JSON into the editor.
3. Click **Validate**.
4. Click **Load & Activate**.
5. Open **AI Agent** and enter a natural-language request.
6. Run it and inspect the tool trace, proposal, safety checks, execution result and verification.
7. Open **Verification Center** or **Audit Trail** for proof.
8. Download the Markdown run report when needed.

The importer understands these common shapes:

```text
services.json        → array of service objects
service.json         → one service object
metric.json          → one service/metric object
latest_traffic.json  → one traffic object
pricing.json         → pricing object
events.json          → event list
action_result.json   → action outcome
combined.json        → services / traffic / events / pricing / action_results
```

## KMIT source data

The original problem statement supplies the structured Test A/B/C/D records. Those are reproduced under:

```text
data/source_problem/
├── scenario_a/services.json
├── scenario_b/service.json
├── scenario_c/metric.json
├── scenario_c/latest_traffic.json
├── scenario_d/service.json
└── scenario_d/action_result.json
```

The supplied source also specifies the required behavior: accept natural-language requests with structured environment data, inspect metrics/traffic/health/instances/pricing/constraints/events, choose safe actions, handle stale/changing/failed state, and verify the result afterwards. The project implements that workflow through the simulator and safety/verification layers.

### Source-alignment note

The Test A `services.json` does not contain a separate `stoppable_when_idle` field, even though the challenge lists “stop an idle service” as an available action. Aegis therefore applies a small simulator policy: a service is eligible for the stop-idle action only when it is worker-like and has zero traffic. This policy is visible in the UI and keeps the supplied test reproducible without changing the source JSON.

## KMIT Scenario Lab

### Test A — Cost optimization

Expected flow:

```text
reports-worker → stop_idle_service
→ Safety ALLOW
→ EXECUTED
→ VERIFIED
→ about -$11/hour
```

### Test B — Rising traffic

```text
orders-api: 2100 → 4200 RPM
→ latency 260 / 300 ms
→ scale_up 4 → 5
→ VERIFIED
```

### Test C — Stale observation

```text
checkout-api metric: 08:00
traffic: 10:30
→ detect stale observation
→ fetch fresh state
→ no unsafe cost action
```

### Test D — Failed action

```text
payment-api: high CPU + high latency
→ propose scale_up to 5
→ safety ALLOW
→ simulator returns capacity_unavailable
→ execution FAILED
→ verification FAILED
```

The system never converts a failed infrastructure action into a fake success.

## Testing

```bash
python -m pytest -q
```

The final build includes unit, scenario, input-validation and adversarial tests.

## Optional real LLM provider

By default:

```env
AGENT_PROVIDER=mock
```

For an optional Anthropic adapter:

```env
AGENT_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key
ANTHROPIC_MODEL=your_supported_model
```

For an optional OpenAI adapter:

```env
AGENT_PROVIDER=openai
OPENAI_API_KEY=your_key
OPENAI_MODEL=your_supported_model
```

The deterministic safety and controlled execution layers remain in the backend regardless of provider.

## Submission checklist

- Run `pytest -q` and confirm all tests pass.
- Start the application with `run.ps1` or `run.bat`.
- Open Data Studio and confirm custom JSON imports correctly.
- Run KMIT Test A/B/C/D once from Scenario Lab.
- Show the Safety Gate and Verification Center during the demo.
- Keep `.env` and API keys out of the repository.

## Known scope

This submission uses a local simulator rather than a live AWS/Azure/GCP control plane. That is deliberate: it gives judges deterministic, safe and reproducible demonstrations while keeping the application ready for future real-cloud adapters.
