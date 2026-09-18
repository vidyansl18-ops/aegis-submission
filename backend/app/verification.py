from __future__ import annotations

from .models import LifecycleStatus, SafetyCheck, VerificationResult


class Verifier:
    def __init__(self, sim):
        self.sim = sim

    def verify(self, action_id: str, service_id: str, before: dict, execution: dict):
        after = self.sim.fresh_state(service_id)
        checks = [
            SafetyCheck(name="actual_state_retrieved", passed=True, message="Fresh state retrieved after the action attempt."),
            SafetyCheck(name="health", passed=bool(after.get("healthy")), message="Healthy after action" if after.get("healthy") else "Unhealthy after action"),
            SafetyCheck(name="availability", passed=bool(after.get("available")), message="Available after action" if after.get("available") else "Unavailable after action"),
            SafetyCheck(name="latency", passed=float(after.get("latency_ms", 0)) <= float(after.get("max_latency_ms", 0)), message=f"{after.get('latency_ms', 0)}ms / {after.get('max_latency_ms', 0)}ms"),
            SafetyCheck(
                name="capacity",
                passed=(after.get("instances", 0) >= after.get("min_instances", 0)) or (after.get("instances") == 0 and after.get("stoppable_when_idle", False)),
                message=f"Instances={after.get('instances', 0)}; allowed range {after.get('min_instances', 0)}-{after.get('max_instances', 0)}",
            ),
        ]
        before_cost = float(before.get("cost_per_hour", 0))
        after_cost = float(after.get("cost_per_hour", 0))
        delta = round(after_cost - before_cost, 2)

        if execution.get("status") != "success":
            checks.append(SafetyCheck(name="execution", passed=False, message=f"Execution failed: {execution.get('error', 'unknown error')}"))
            return VerificationResult(
                action_id=action_id,
                status=LifecycleStatus.failed,
                verified=False,
                summary=f"Execution failed: {execution.get('error', 'unknown')}. Fresh state was still checked and no success was claimed.",
                before=before,
                after=after,
                checks=checks,
                cost_delta_per_hour=delta,
            )

        checks.append(SafetyCheck(name="execution", passed=True, message="Execution API reported success."))
        verified = all(check.passed for check in checks)
        status = LifecycleStatus.verified if verified else LifecycleStatus.partial
        summary = "Action executed and verified against fresh state." if verified else "Action executed, but one or more post-action checks did not pass."
        return VerificationResult(
            action_id=action_id,
            status=status,
            verified=verified,
            summary=summary,
            before=before,
            after=after,
            checks=checks,
            cost_delta_per_hour=delta,
        )
