from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .agent import AnthropicAgent, MockAgent, OpenAIAgent
from .config import settings
from .models import AgentRunResponse


class AgentOrchestrator:
    def __init__(self, tools, audit, db):
        self.tools = tools
        self.audit = audit
        self.db = db
        self.provider_name = self._provider_name()
        if self.provider_name == "anthropic" and settings.anthropic_api_key:
            self.agent = AnthropicAgent(tools, audit, settings.anthropic_api_key, settings.anthropic_model)
        elif self.provider_name == "openai" and settings.openai_api_key:
            self.agent = OpenAIAgent(tools, audit, settings.openai_api_key, settings.openai_model)
        else:
            self.provider_name = "mock"
            self.agent = MockAgent(tools, audit)

    def _provider_name(self) -> str:
        return settings.provider

    def run(self, prompt: str, scenario_id: str | None = None):
        run_id = "run-" + uuid4().hex[:10]
        self.audit.run_id = run_id
        self.db.save_run(run_id, self.provider_name, prompt, "RUNNING", "", self._now(), input_source=self.input_source())
        self.db.log_event(run_id, "request_received", {"prompt": prompt, "scenario_id": scenario_id}, self._now())

        if scenario_id:
            self.tools.sim.reset_scenario(scenario_id)
            self.db.log_event(run_id, "scenario_loaded", {"scenario_id": scenario_id}, self._now())

        try:
            result = self.agent.run(prompt, scenario_id)
            proposal = result["proposal"]
            self.db.log_event(run_id, "agent_proposal", proposal.model_dump(mode="json"), self._now())

            if proposal.requires_fresh_check and proposal.action.value != "no_action":
                refreshed = self.tools.call("get_fresh_service_state", {"service_id": proposal.service_id})
                self.db.log_event(run_id, "freshness_refresh", {"service_id": proposal.service_id, "result": refreshed}, self._now())

            safety = self.audit.safety.validate(proposal)
            self.db.log_event(run_id, "final_safety", safety.model_dump(mode="json"), self._now())
            execution = None
            verification = None

            if proposal.action.value != "no_action":
                kwargs = {}
                if proposal.requested_instances is not None:
                    kwargs["target_instances"] = proposal.requested_instances
                if proposal.requested_size is not None:
                    kwargs["target_size"] = proposal.requested_size
                self.audit.execute_action(proposal.service_id, proposal.action.value, **kwargs)
                execution = self.audit.last_execution
                verification = self.audit.last_verification

            input_source = self.input_source()
            response = AgentRunResponse(
                run_id=run_id,
                provider=self.provider_name,
                summary=result.get("summary", ""),
                proposal=proposal,
                safety=safety,
                execution=execution,
                verification=verification,
                tool_trace=result.get("trace", []),
                input_source=input_source,
            )
            payload = response.model_dump(mode="json")
            self.db.save_run(run_id, self.provider_name, prompt, "COMPLETED", response.summary, self._now(), result=payload, input_source=input_source)
            self.db.log_event(run_id, "final_response", payload, self._now())
            return response
        except Exception as exc:
            self.db.save_run(run_id, self.provider_name, prompt, "FAILED", str(exc), self._now(), input_source=self.input_source())
            self.db.log_event(run_id, "agent_error", {"error": str(exc)}, self._now())
            raise

    def input_source(self):
        metadata = self.tools.sim.state.get("metadata", {})
        return {
            "source_name": metadata.get("source_name", self.tools.sim._scenario),
            "files": list(self.tools.sim.source_files),
            "diagnostics": list(self.tools.sim.diagnostics),
            "service_count": len(self.tools.sim.state.get("services", {})),
            "traffic_count": len(self.tools.sim.state.get("traffic", {})),
            "event_count": len(self.tools.sim.state.get("events", [])),
            "action_result_count": len(self.tools.sim.state.get("action_results", [])),
        }

    def _now(self):
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
