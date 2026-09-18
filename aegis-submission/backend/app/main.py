from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .agent_orchestrator import AgentOrchestrator
from .audit import ActionAudit
from .config import settings
from .data_loader import DataValidationError, normalize_documents
from .db import Database
from .models import ActionRequest, AgentRunRequest, DataLoadRequest
from .safety import SafetyEngine
from .simulator import CloudSimulator, PROMPTS
from .tools import ToolRegistry
from .verification import Verifier

app = FastAPI(
    title="Aegis FinOps API",
    version="2.0.0",
    description="Autonomous cloud cost optimization simulator with user-supplied JSON input, deterministic safety and fresh verification.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = Database(settings.database_path)
sim = CloudSimulator()
sim.load_demo_environment()
safety = SafetyEngine(sim)
verifier = Verifier(sim)
audit = ActionAudit(sim, safety, verifier, db)
tools = ToolRegistry(sim, audit)
agent = AgentOrchestrator(tools, audit, db)


def _state_summary():
    pricing = sim.pricing()
    return {
        "source_name": sim.state.get("metadata", {}).get("source_name", sim._scenario),
        "files": sim.source_files,
        "services": len(sim.state.get("services", {})),
        "traffic_records": len(sim.state.get("traffic", {})),
        "events": len(sim.state.get("events", [])),
        "action_results": len(sim.state.get("action_results", [])),
        "hourly_total": pricing.get("hourly_total", 0),
        "currency": pricing.get("currency", "USD"),
        "diagnostics": sim.diagnostics,
    }


@app.get("/api/system/health")
def system_health():
    return {"status": "ok", "provider": agent.provider_name, "scenario": sim._scenario, "input": _state_summary()}


@app.get("/api/services")
def services():
    return sim.services()


@app.get("/api/services/{service_id}")
def service(service_id: str):
    try:
        return sim.service(service_id)
    except KeyError:
        raise HTTPException(404, "Service not found") from None


@app.get("/api/services/{service_id}/metrics")
def metrics(service_id: str):
    return tools.get_service_metrics(service_id)


@app.get("/api/services/{service_id}/traffic")
def traffic(service_id: str):
    return tools.get_service_traffic(service_id)


@app.get("/api/services/{service_id}/events")
def events(service_id: str):
    return tools.get_recent_events(service_id)


@app.get("/api/services/{service_id}/health")
def health(service_id: str):
    return tools.get_service_health(service_id)


@app.get("/api/pricing")
def pricing():
    return tools.get_pricing()


@app.get("/api/audit")
def audit_log(limit: int = Query(100, ge=1, le=500)):
    return db.recent_audit(limit)


@app.get("/api/actions/{action_id}")
def action_status(action_id: str):
    action = db.get_action(action_id)
    if not action:
        raise HTTPException(404, "Action not found")
    verification = db.get_verification(action_id)
    return {"action": action, "verification": verification}


@app.get("/api/verifications/{action_id}")
def verification_status(action_id: str):
    verification = db.get_verification(action_id)
    if not verification:
        raise HTTPException(404, "Verification not found")
    return verification


@app.post("/api/actions/scale")
def scale_action(req: ActionRequest):
    if req.target_instances is None:
        raise HTTPException(400, "target_instances is required")
    try:
        before = sim.service(req.service_id)
    except KeyError:
        raise HTTPException(404, "Service not found") from None
    action = "scale_up" if req.target_instances > before["instances"] else "scale_down"
    result = audit.execute_action(req.service_id, action, target_instances=req.target_instances)
    return {"action": result, "execution": audit.last_execution, "verification": audit.last_verification}


@app.post("/api/actions/resize")
def resize_action(req: ActionRequest):
    if not req.target_size:
        raise HTTPException(400, "target_size is required")
    result = audit.execute_action(req.service_id, "resize", target_size=req.target_size)
    return {"action": result, "execution": audit.last_execution, "verification": audit.last_verification}


@app.post("/api/actions/stop")
def stop_action(req: ActionRequest):
    result = audit.execute_action(req.service_id, "stop_idle_service")
    return {"action": result, "execution": audit.last_execution, "verification": audit.last_verification}


@app.post("/api/actions/delay-batch")
def delay_batch_action(req: ActionRequest):
    result = audit.execute_action(req.service_id, "delay_batch")
    return {"action": result, "execution": audit.last_execution, "verification": audit.last_verification}


@app.post("/api/simulator/reset")
def simulator_reset():
    sim.load_demo_environment()
    return {"status": "ok", "input": _state_summary()}


@app.get("/api/input/current")
def input_current():
    return {"summary": _state_summary(), "environment": sim.state}


@app.get("/api/input/template")
def input_template():
    return {
        "services": [
            {
                "service_id": "example-api",
                "cpu_percent": 35,
                "memory_percent": 52,
                "requests_per_minute": 2500,
                "previous_requests_per_minute": 1800,
                "latency_ms": 225,
                "instances": 4,
                "cost_per_hour": 18.5,
                "min_instances": 2,
                "max_instances": 8,
                "max_latency_ms": 300,
                "healthy": True,
                "available": True,
                "timestamp": "2026-09-17T10:30:00Z",
            }
        ],
        "traffic": [],
        "events": [],
        "pricing": {"currency": "USD"},
        "action_results": [],
    }


@app.post("/api/input/validate")
def input_validate(req: DataLoadRequest):
    try:
        env = normalize_documents([doc.model_dump() for doc in req.documents])
        return {"valid": True, "summary": {"services": len(env.services), "traffic": len(env.traffic), "events": len(env.events), "action_results": len(env.action_results), "currency": env.pricing.get("currency", "USD")}, "diagnostics": env.diagnostics, "source_files": env.source_files}
    except DataValidationError as exc:
        return JSONResponse(status_code=422, content={"valid": False, "error": str(exc)})


@app.post("/api/input/load")
def input_load(req: DataLoadRequest):
    try:
        env = normalize_documents([doc.model_dump() for doc in req.documents])
    except DataValidationError as exc:
        raise HTTPException(422, str(exc)) from None
    if req.activate:
        sim.load_environment(env, source_name="user_import")
    return {"status": "loaded" if req.activate else "validated", "summary": _state_summary() if req.activate else {"services": len(env.services), "traffic": len(env.traffic), "events": len(env.events), "action_results": len(env.action_results), "currency": env.pricing.get("currency", "USD")}, "diagnostics": env.diagnostics, "source_files": env.source_files}


@app.post("/api/input/load-kmit/{scenario_id}")
def input_load_kmit(scenario_id: str):
    try:
        sim.reset_scenario(scenario_id)
    except KeyError:
        raise HTTPException(404, "Unknown KMIT scenario") from None
    return {"status": "loaded", "scenario_id": scenario_id, "prompt": PROMPTS.get(scenario_id, ""), "summary": _state_summary()}


@app.post("/api/input/load-demo")
def input_load_demo():
    sim.load_demo_environment()
    return {"status": "loaded", "summary": _state_summary()}


@app.get("/api/input/export")
def input_export():
    return JSONResponse(content=sim.state)


@app.get("/api/scenarios")
def scenarios():
    return [
        {"id": "scenario_a_cost_optimization", "name": "Test A — Cost Optimization", "prompt": PROMPTS["scenario_a_cost_optimization"], "focus": "Idle capacity and safe cost reduction"},
        {"id": "scenario_b_rising_traffic", "name": "Test B — Rising Traffic", "prompt": PROMPTS["scenario_b_rising_traffic"], "focus": "Traffic trend and latency headroom"},
        {"id": "scenario_c_stale_observation", "name": "Test C — Stale Observation", "prompt": PROMPTS["scenario_c_stale_observation"], "focus": "Freshness and contradiction detection"},
        {"id": "scenario_d_failed_action", "name": "Test D — Failed Action", "prompt": PROMPTS["scenario_d_failed_action"], "focus": "Action failure and verification truthfulness"},
    ]


@app.post("/api/scenarios/{scenario_id}/run")
def run_scenario(scenario_id: str):
    mapping = {x["id"]: x for x in scenarios()}
    if scenario_id not in mapping:
        raise HTTPException(404, "Scenario not found")
    return agent.run(mapping[scenario_id]["prompt"], scenario_id)


@app.post("/api/agent/run")
def run_agent(req: AgentRunRequest):
    try:
        return agent.run(req.prompt, req.scenario_id)
    except KeyError as exc:
        raise HTTPException(404, f"Unknown service: {exc.args[0]}") from None
    except Exception as exc:
        raise HTTPException(500, str(exc)) from None


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str):
    result = db.get_run(run_id)
    if not result:
        raise HTTPException(404, "Run not found")
    return result


@app.get("/api/runs/{run_id}/report")
def run_report(run_id: str):
    result = db.get_run(run_id)
    if not result or not result.get("result_json"):
        raise HTTPException(404, "Run result not found")
    data = result["result_json"]
    proposal = data.get("proposal", {})
    safety_data = data.get("safety", {})
    execution = data.get("execution") or {}
    verification = data.get("verification") or {}
    lines = [
        "# Aegis FinOps Run Report",
        "",
        f"**Run ID:** `{run_id}`",
        f"**Provider:** {data.get('provider', 'mock')}",
        f"**Summary:** {data.get('summary', '')}",
        "",
        "## Input Source",
        f"- Source: {data.get('input_source', {}).get('source_name', '')}",
        f"- Files: {', '.join(data.get('input_source', {}).get('files', []))}",
        "",
        "## Proposal",
        f"- Service: `{proposal.get('service_id')}`",
        f"- Action: `{proposal.get('action')}`",
        f"- Target instances: `{proposal.get('requested_instances')}`",
        f"- Target size: `{proposal.get('requested_size')}`",
        f"- Reason: {proposal.get('reason', '')}",
        "- Evidence:",
    ]
    lines.extend([f"  - {item}" for item in proposal.get("evidence", [])])
    lines += [
        "",
        "## Safety",
        f"- Allowed: `{safety_data.get('allowed')}`",
        f"- Reason code: `{safety_data.get('reason_code')}`",
        "",
        "## Execution",
        f"- Status: `{execution.get('status', 'NO_ACTION')}`",
        f"- Action ID: `{execution.get('action_id', '')}`",
        f"- Error: `{execution.get('error', '')}`",
        "",
        "## Verification",
        f"- Status: `{verification.get('status', 'NOT_APPLICABLE')}`",
        f"- Verified: `{verification.get('verified', False)}`",
        f"- Summary: {verification.get('summary', 'No action required.')}",
        f"- Cost delta/hour: `{verification.get('cost_delta_per_hour', 0)}`",
        "",
        "## Tool Trace",
    ]
    for item in data.get("tool_trace", []):
        lines.append(f"- `{item.get('tool')}` → {json.dumps(item.get('result'), default=str)[:500]}")
    lines.append("")
    lines.append("Generated by Aegis FinOps.")
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


frontend = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/assets", StaticFiles(directory=frontend), name="assets")


@app.get("/")
def index():
    return FileResponse(frontend / "index.html")
