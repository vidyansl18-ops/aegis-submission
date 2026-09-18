from __future__ import annotations

from datetime import datetime, timezone

from .config import settings
from .models import ActionProposal, ActionType, SafetyCheck, SafetyDecision


class SafetyEngine:
    """Deterministic policy engine. The model cannot bypass these checks."""

    def __init__(self, sim):
        self.sim = sim

    def _age_seconds(self, timestamp: str) -> float:
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now = getattr(self.sim, "clock", datetime.now(timezone.utc))
        return max(0.0, (now - ts).total_seconds())

    def validate(self, p: ActionProposal) -> SafetyDecision:
        try:
            s = self.sim.service(p.service_id)
        except KeyError:
            return SafetyDecision(
                allowed=False,
                reason_code="service_not_found",
                checks=[SafetyCheck(name="service_exists", passed=False, message="Service does not exist")],
            )

        checks: list[SafetyCheck] = []
        age = self._age_seconds(s["timestamp"])
        fresh = age <= settings.max_observation_age_seconds
        checks.append(SafetyCheck(name="freshness", passed=fresh, message=f"Observation age {age:.0f}s; limit {settings.max_observation_age_seconds}s"))
        healthy = bool(s.get("healthy", False))
        available = bool(s.get("available", False))
        checks.append(SafetyCheck(name="health", passed=healthy, message="Service is healthy" if healthy else "Service is unhealthy"))
        checks.append(SafetyCheck(name="availability", passed=available, message="Service is available" if available else "Service is unavailable"))

        if p.action == ActionType.no_action:
            reason = "stale_observation_requires_refresh" if not fresh else None
            return SafetyDecision(allowed=True, reason_code=reason, checks=checks)

        if not fresh:
            return SafetyDecision(allowed=False, reason_code="stale_observation", checks=checks)
        if not healthy:
            return SafetyDecision(allowed=False, reason_code="unhealthy_service", checks=checks)
        if not available:
            return SafetyDecision(allowed=False, reason_code="availability_risk", checks=checks)

        if p.action in (ActionType.scale_up, ActionType.scale_down):
            if p.requested_instances is None:
                checks.append(SafetyCheck(name="target_instances", passed=False, message="A target instance count is required"))
                return SafetyDecision(allowed=False, reason_code="invalid_target", checks=checks)
            ok_min = p.requested_instances >= s["min_instances"]
            ok_max = p.requested_instances <= s["max_instances"]
            checks.append(SafetyCheck(name="min_capacity", passed=ok_min, message=f"Target {p.requested_instances} >= min {s['min_instances']}"))
            checks.append(SafetyCheck(name="max_capacity", passed=ok_max, message=f"Target {p.requested_instances} <= max {s['max_instances']}"))
            if not ok_min:
                return SafetyDecision(allowed=False, reason_code="below_min_capacity", checks=checks)
            if not ok_max:
                return SafetyDecision(allowed=False, reason_code="above_max_capacity", checks=checks)

            if p.requested_instances < s["instances"]:
                traffic = self.sim.traffic(p.service_id)
                current = float(traffic.get("requests_per_minute", 0))
                previous = traffic.get("previous_requests_per_minute")
                if previous is None:
                    previous = s.get("previous_requests_per_minute")
                rising = previous is not None and current > float(previous) * 1.2
                latency_risk = float(s.get("latency_ms", 0)) >= float(s.get("max_latency_ms", 0)) * 0.85
                checks.append(SafetyCheck(name="traffic_trend", passed=not rising, message="Traffic is stable/non-rising" if not rising else f"Traffic is rising ({current:g} > {float(previous):g} baseline)"))
                checks.append(SafetyCheck(name="latency_headroom", passed=not latency_risk, message="Latency headroom acceptable" if not latency_risk else "Latency is close to its limit"))
                if rising:
                    return SafetyDecision(allowed=False, reason_code="traffic_risk", checks=checks)
                if latency_risk:
                    return SafetyDecision(allowed=False, reason_code="latency_risk", checks=checks)

        if p.action == ActionType.resize:
            if p.requested_size not in {"small", "standard", "large"}:
                checks.append(SafetyCheck(name="resource_size", passed=False, message="Supported sizes: small, standard, large"))
                return SafetyDecision(allowed=False, reason_code="unsupported_size", checks=checks)
            checks.append(SafetyCheck(name="resource_size", passed=True, message=f"Requested size {p.requested_size} is supported"))

        if p.action == ActionType.stop_idle_service:
            idle = float(s.get("requests_per_minute", 0)) == 0 and bool(s.get("stoppable_when_idle", False))
            checks.append(SafetyCheck(name="idle_and_stoppable", passed=idle, message="Idle and marked stoppable" if idle else "Service is not safely stoppable while active"))
            if not idle:
                return SafetyDecision(allowed=False, reason_code="service_not_idle", checks=checks)

        if p.action == ActionType.delay_batch:
            worker_like = str(s.get("service_type", "")).lower() == "worker" or "worker" in p.service_id.lower()
            checks.append(SafetyCheck(name="batch_workload", passed=worker_like, message="Service is batch/worker-like" if worker_like else "Service is not clearly a batch workload"))
            if not worker_like:
                return SafetyDecision(allowed=False, reason_code="not_batch_workload", checks=checks)

        within_latency = float(s.get("latency_ms", 0)) <= float(s.get("max_latency_ms", 0))
        checks.append(SafetyCheck(name="latency_target", passed=within_latency, message=f"Latency {s.get('latency_ms', 0)}ms / max {s.get('max_latency_ms', 0)}ms"))
        if not within_latency and p.action in (ActionType.scale_down, ActionType.stop_idle_service, ActionType.resize):
            return SafetyDecision(allowed=False, reason_code="latency_risk", checks=checks)

        return SafetyDecision(allowed=True, checks=checks)
