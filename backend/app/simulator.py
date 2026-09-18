from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json

from .data_loader import NormalizedEnvironment, normalize_documents


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "data" / "source_problem"

PROMPTS = {
    "scenario_a_cost_optimization": (SOURCE_ROOT / "scenario_a" / "prompt.txt").read_text(encoding="utf-8").strip(),
    "scenario_b_rising_traffic": (SOURCE_ROOT / "scenario_b" / "prompt.txt").read_text(encoding="utf-8").strip(),
    "scenario_c_stale_observation": (SOURCE_ROOT / "scenario_c" / "prompt.txt").read_text(encoding="utf-8").strip(),
    "scenario_d_failed_action": (SOURCE_ROOT / "scenario_d" / "prompt.txt").read_text(encoding="utf-8").strip(),
}


def _read(path: Path) -> dict[str, Any] | list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_documents(scenario_id: str) -> list[dict[str, str]]:
    mapping = {
        "scenario_a_cost_optimization": [SOURCE_ROOT / "scenario_a" / "services.json"],
        "scenario_b_rising_traffic": [SOURCE_ROOT / "scenario_b" / "service.json"],
        "scenario_c_stale_observation": [SOURCE_ROOT / "scenario_c" / "metric.json", SOURCE_ROOT / "scenario_c" / "latest_traffic.json"],
        "scenario_d_failed_action": [SOURCE_ROOT / "scenario_d" / "service.json", SOURCE_ROOT / "scenario_d" / "action_result.json"],
    }
    return [{"filename": path.name, "content": path.read_text(encoding="utf-8")} for path in mapping[scenario_id]]


class CloudSimulator:
    """Deterministic cloud-control-plane simulator.

    It consumes normalized JSON input so the same application can run the KMIT samples or
    arbitrary user-supplied service/environment data without touching real infrastructure.
    """

    def __init__(self):
        self._scenario = "baseline"
        self.source_files: list[str] = []
        self.diagnostics: list[str] = []
        self.clock = datetime.now(timezone.utc)
        self.reset()
        self.load_demo_environment()

    def reset(self) -> None:
        self.state = {
            "services": {},
            "traffic": {},
            "events": [],
            "pricing": {"currency": "USD", "hourly_total": 0.0},
            "action_results": [],
            "metadata": {"source_files": [], "diagnostics": []},
        }
        self.action_failures: dict[str, str] = {}
        self._scenario = "baseline"
        self.clock = datetime.now(timezone.utc)

    def load_environment(self, environment: NormalizedEnvironment, *, source_name: str = "uploaded_data") -> None:
        self.state = deepcopy(environment.as_state())
        self.source_files = list(environment.source_files)
        self.diagnostics = list(environment.diagnostics)
        self.state["metadata"]["source_name"] = source_name
        self._scenario = source_name
        timestamps: list[datetime] = []
        for svc in self.state["services"].values():
            dt = datetime.fromisoformat(svc["timestamp"].replace("Z", "+00:00"))
            timestamps.append(dt)
        for t in self.state["traffic"].values():
            if t.get("timestamp"):
                timestamps.append(datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00")))
        # Set the simulator clock shortly after the latest supplied observation. This keeps
        # fresh user data fresh while still making older service snapshots demonstrably stale
        # when a newer traffic snapshot is supplied (KMIT Test C).
        self.clock = (max(timestamps) + timedelta(seconds=60)) if timestamps else datetime.now(timezone.utc)

        self.action_failures = {}
        for result in self.state.get("action_results", []):
            if str(result.get("status", "")).lower() == "failed":
                service_id = result.get("service_id") or self._infer_failure_service()
                action = result.get("action")
                target = result.get("requested_instances", "")
                if service_id and action:
                    self.action_failures[f"{service_id}:{action}:{target}"] = str(result.get("error") or "action_failed")

        # Source Test D gives action_result without service_id, and the only supplied service is
        # payment-api. Associate such a failure with the single available service.
        if not self.action_failures:
            self._register_implicit_action_failure()

    def _infer_failure_service(self) -> str | None:
        if len(self.state["services"]) == 1:
            return next(iter(self.state["services"]))
        return None

    def _register_implicit_action_failure(self) -> None:
        for result in self.state.get("action_results", []):
            if str(result.get("status", "")).lower() == "failed" and result.get("action"):
                sid = self._infer_failure_service()
                if sid:
                    target = result.get("requested_instances", "")
                    self.action_failures[f"{sid}:{result['action']}:{target}"] = str(result.get("error") or "action_failed")

    def _normalized_source_environment(self, scenario_id: str) -> NormalizedEnvironment:
        return normalize_documents(_source_documents(scenario_id))

    def load_demo_environment(self) -> None:
        docs = []
        for sid in ("scenario_a_cost_optimization", "scenario_b_rising_traffic", "scenario_c_stale_observation", "scenario_d_failed_action"):
            docs.extend(_source_documents(sid))
        env = normalize_documents(docs)
        self.load_environment(env, source_name="kmit_demo_environment")
        if "reports-worker" in self.state["services"]:
            self.state["services"]["reports-worker"]["service_type"] = "worker"
            self.state["services"]["reports-worker"]["stoppable_when_idle"] = True
        self._scenario = "baseline"

    def reset_to_default(self) -> None:
        self.reset()
        env = normalize_documents([{
            "filename": "services.json",
            "content": (SOURCE_ROOT / "scenario_a" / "services.json").read_text(encoding="utf-8"),
        }])
        self.load_environment(env, source_name="baseline_from_kmit_test_a")
        # Make the source's reports-worker eligible for the stop-idle action. The problem statement
        # explicitly lists that action, but does not supply a separate boolean flag in services.json.
        if "reports-worker" in self.state["services"]:
            self.state["services"]["reports-worker"]["stoppable_when_idle"] = True
            self.state["services"]["reports-worker"]["service_type"] = "worker"
        self._scenario = "baseline"

    def services(self) -> list[dict[str, Any]]:
        return [deepcopy(x) for x in self.state["services"].values()]

    def service(self, service_id: str) -> dict[str, Any]:
        if service_id not in self.state["services"]:
            raise KeyError(service_id)
        return deepcopy(self.state["services"][service_id])

    def traffic(self, service_id: str) -> dict[str, Any]:
        if service_id in self.state["traffic"]:
            return deepcopy(self.state["traffic"][service_id])
        service = self.service(service_id)
        return {
            "service_id": service_id,
            "requests_per_minute": service.get("requests_per_minute", 0),
            "previous_requests_per_minute": service.get("previous_requests_per_minute"),
            "timestamp": service["timestamp"],
        }

    def events(self, service_id: str | None = None) -> list[dict[str, Any]]:
        items = self.state["events"]
        if service_id:
            items = [x for x in items if x.get("service_id") == service_id]
        return deepcopy(items)

    def pricing(self) -> dict[str, Any]:
        total = round(sum(float(s.get("cost_per_hour", 0)) for s in self.state["services"].values()), 2)
        p = deepcopy(self.state.get("pricing", {}))
        p["hourly_total"] = total
        p["daily_total"] = round(total * 24, 2)
        p["monthly_total"] = round(total * 24 * 30, 2)
        return p

    def fresh_state(self, service_id: str) -> dict[str, Any]:
        service = self.service(service_id)
        latest_traffic = self.traffic(service_id)
        service_ts = datetime.fromisoformat(service["timestamp"].replace("Z", "+00:00"))
        traffic_ts = datetime.fromisoformat(latest_traffic["timestamp"].replace("Z", "+00:00"))
        if traffic_ts > service_ts:
            service["requests_per_minute"] = latest_traffic.get("requests_per_minute", service["requests_per_minute"])
            service["previous_requests_per_minute"] = latest_traffic.get("previous_requests_per_minute", service.get("previous_requests_per_minute"))
            service["timestamp"] = latest_traffic["timestamp"]
        return service

    def reset_scenario(self, scenario_id: str) -> str:
        env = self._normalized_source_environment(scenario_id)
        self.load_environment(env, source_name=scenario_id)
        self._scenario = scenario_id
        if scenario_id == "scenario_a_cost_optimization":
            # Simulator policy metadata needed for the advertised stop-idle action.
            s = self.state["services"].get("reports-worker")
            if s:
                s["service_type"] = "worker"
                s["stoppable_when_idle"] = True
        return self._scenario

    def execute(self, service_id: str, action: str, target_instances: int | None = None, target_size: str | None = None) -> dict[str, Any]:
        service = self.service(service_id)
        self.clock += timedelta(seconds=1)
        now = self.clock.isoformat().replace("+00:00", "Z")
        key = f"{service_id}:{action}:{target_instances if target_instances is not None else ''}"
        if key in self.action_failures:
            return {"status": "failed", "error": self.action_failures[key], "timestamp": now}

        if action in ("scale_up", "scale_down"):
            if target_instances is None:
                raise ValueError("target_instances required")
            if target_instances < service["min_instances"] or target_instances > service["max_instances"]:
                return {"status": "failed", "error": "capacity_out_of_bounds", "timestamp": now}
            old_instances = service["instances"]
            service["instances"] = target_instances
            per_instance = float(service["cost_per_hour"]) / max(old_instances, 1)
            service["cost_per_hour"] = round(per_instance * target_instances, 2)
            service["timestamp"] = now
            self.state["services"][service_id] = service
            return {"status": "success", "timestamp": now, "before_instances": old_instances, "after_instances": target_instances}

        if action == "stop_idle_service":
            if not service.get("stoppable_when_idle"):
                return {"status": "failed", "error": "service_not_stoppable", "timestamp": now}
            if service.get("requests_per_minute", 0) != 0:
                return {"status": "failed", "error": "service_not_idle", "timestamp": now}
            old_instances = service["instances"]
            service["instances"] = 0
            service["cost_per_hour"] = 0
            service["timestamp"] = now
            self.state["services"][service_id] = service
            return {"status": "success", "timestamp": now, "before_instances": old_instances, "after_instances": 0}

        if action == "resize":
            sizes = {"small": 0.6, "standard": 1.0, "large": 1.8}
            if target_size not in sizes:
                return {"status": "failed", "error": "unsupported_size", "timestamp": now}
            current_multiplier = sizes.get(service.get("resource_size", "standard"), 1.0)
            base = float(service["cost_per_hour"]) / max(current_multiplier, 0.01)
            service["resource_size"] = target_size
            service["cost_per_hour"] = round(base * sizes[target_size], 2)
            service["timestamp"] = now
            self.state["services"][service_id] = service
            return {"status": "success", "timestamp": now, "resource_size": target_size}

        if action == "delay_batch":
            return {"status": "success", "timestamp": now, "message": "Batch workload delayed in simulator."}

        return {"status": "success", "timestamp": now}
