from __future__ import annotations

from typing import Any, Callable

from .simulator import CloudSimulator


class ToolRegistry:
    """Explicit, inspectable tools exposed to the agent layer."""

    def __init__(self, sim: CloudSimulator, audit):
        self.sim = sim
        self.audit = audit
        self.tools: dict[str, Callable[..., Any]] = {
            "get_all_services": self.get_all_services,
            "get_service": self.get_service,
            "get_service_metrics": self.get_service_metrics,
            "get_service_traffic": self.get_service_traffic,
            "get_recent_events": self.get_recent_events,
            "get_pricing": self.get_pricing,
            "get_service_health": self.get_service_health,
            "get_current_service_state": self.get_current_service_state,
            "get_fresh_service_state": self.get_fresh_service_state,
            "calculate_cost_impact": self.calculate_cost_impact,
            "get_action_result": self.get_action_result,
            "verify_service_health": self.verify_service_health,
            "verify_latency": self.verify_latency,
            "verify_capacity": self.verify_capacity,
        }

    def call(self, name: str, args: dict[str, Any]) -> Any:
        if name not in self.tools:
            raise KeyError(name)
        return self.tools[name](**args)

    def get_all_services(self):
        return self.sim.services()

    def get_service(self, service_id: str):
        return self.sim.service(service_id)

    def get_service_metrics(self, service_id: str):
        s = self.sim.service(service_id)
        return {k: s.get(k) for k in ["cpu_percent", "memory_percent", "requests_per_minute", "latency_ms", "instances", "timestamp"]}

    def get_service_traffic(self, service_id: str):
        return self.sim.traffic(service_id)

    def get_recent_events(self, service_id: str):
        return self.sim.events(service_id)

    def get_pricing(self):
        return self.sim.pricing()

    def get_service_health(self, service_id: str):
        s = self.sim.service(service_id)
        return {"healthy": s.get("healthy"), "available": s.get("available"), "timestamp": s.get("timestamp")}

    def get_current_service_state(self, service_id: str):
        return self.sim.service(service_id)

    def get_fresh_service_state(self, service_id: str):
        return self.sim.fresh_state(service_id)

    def calculate_cost_impact(self, service_id: str):
        s = self.sim.service(service_id)
        hourly = float(s.get("cost_per_hour", 0))
        return {"hourly_cost": hourly, "daily_cost": round(hourly * 24, 2), "monthly_cost": round(hourly * 24 * 30, 2)}

    def get_action_result(self, action_id: str):
        for result in self.sim.state.get("action_results", []):
            if str(result.get("action_id")) == action_id:
                return result
        stored = self.audit.db.get_action(action_id) if self.audit and self.audit.db else None
        return stored or {"action_id": action_id, "status": "not_found"}

    def verify_service_health(self, service_id: str):
        s = self.sim.fresh_state(service_id)
        return {"healthy": s.get("healthy"), "available": s.get("available")}

    def verify_latency(self, service_id: str):
        s = self.sim.fresh_state(service_id)
        return {
            "latency_ms": s.get("latency_ms", 0),
            "max_latency_ms": s.get("max_latency_ms", 0),
            "within_target": s.get("latency_ms", 0) <= s.get("max_latency_ms", 0),
        }

    def verify_capacity(self, service_id: str):
        s = self.sim.fresh_state(service_id)
        return {"instances": s.get("instances"), "min_instances": s.get("min_instances"), "max_instances": s.get("max_instances")}
