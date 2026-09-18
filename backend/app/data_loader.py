from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


class DataValidationError(ValueError):
    pass


SERVICE_FIELDS = {
    "service_id", "cpu_percent", "memory_percent", "requests_per_minute", "latency_ms",
    "instances", "cost_per_hour", "min_instances", "max_instances", "max_latency_ms", "healthy",
    "available", "timestamp", "display_name", "service_type", "stoppable_when_idle", "resource_size",
    "previous_requests_per_minute",
}


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_number(value: Any, field: str, *, integer: bool = False) -> int | float:
    if isinstance(value, bool):
        raise DataValidationError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise DataValidationError(f"{field} must be numeric") from None
    if integer:
        if int(number) != number:
            raise DataValidationError(f"{field} must be an integer")
        return int(number)
    return number


def normalize_service(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw.get("service_id"):
        raise DataValidationError("Each service must be an object containing service_id")

    service_id = str(raw["service_id"])
    timestamp = raw.get("timestamp")
    if _parse_timestamp(timestamp) is None:
        raise DataValidationError(f"{service_id}: timestamp must be an ISO-8601 string")

    out = dict(raw)
    defaults = {
        "display_name": service_id.replace("-", " ").title(),
        "service_type": "worker" if "worker" in service_id.lower() else "api",
        "cpu_percent": 0,
        "memory_percent": 0,
        "requests_per_minute": 0,
        "latency_ms": 0,
        "instances": 1,
        "cost_per_hour": 0,
        "min_instances": 1,
        "max_instances": 10,
        "max_latency_ms": 1000,
        "healthy": True,
        "available": True,
        "stoppable_when_idle": False,
        "resource_size": "standard",
    }
    for key, default in defaults.items():
        out.setdefault(key, default)

    for key in ("cpu_percent", "memory_percent", "requests_per_minute", "latency_ms", "cost_per_hour", "max_latency_ms"):
        out[key] = _as_number(out[key], key)
    for key in ("instances", "min_instances", "max_instances"):
        out[key] = _as_number(out[key], key, integer=True)
    if out.get("previous_requests_per_minute") is not None:
        out["previous_requests_per_minute"] = _as_number(out["previous_requests_per_minute"], "previous_requests_per_minute")

    if out["min_instances"] < 0 or out["max_instances"] < out["min_instances"]:
        raise DataValidationError(f"{service_id}: invalid min/max instance constraints")
    if out["instances"] < 0:
        raise DataValidationError(f"{service_id}: instances cannot be negative")
    if out["cost_per_hour"] < 0:
        raise DataValidationError(f"{service_id}: cost_per_hour cannot be negative")

    # The source problem exposes a worker named reports-worker. The stop-idle action is an
    # available action, but the source JSON does not provide a separate stoppable flag. We
    # infer stoppability only for explicitly worker-like services with zero traffic and document
    # that policy in the UI/import report.
    if "stoppable_when_idle" not in raw and out["service_type"].lower() == "worker" and out["requests_per_minute"] == 0:
        out["stoppable_when_idle"] = True

    return out


def _looks_like_service(obj: dict[str, Any]) -> bool:
    return "service_id" in obj and any(key in obj for key in ("cpu_percent", "instances", "cost_per_hour", "latency_ms"))


def _looks_like_traffic(obj: dict[str, Any]) -> bool:
    return "service_id" in obj and "requests_per_minute" in obj and "timestamp" in obj and not any(
        key in obj for key in ("cpu_percent", "memory_percent", "instances", "cost_per_hour", "healthy")
    )


def _merge_service(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return dict(incoming)
    merged = dict(existing)
    merged.update(incoming)
    return merged


@dataclass
class NormalizedEnvironment:
    services: dict[str, dict[str, Any]]
    traffic: dict[str, dict[str, Any]]
    events: list[dict[str, Any]]
    pricing: dict[str, Any]
    action_results: list[dict[str, Any]]
    source_files: list[str]
    diagnostics: list[str]

    def as_state(self) -> dict[str, Any]:
        return {
            "services": self.services,
            "traffic": self.traffic,
            "events": self.events,
            "pricing": self.pricing,
            "action_results": self.action_results,
            "metadata": {
                "source_files": self.source_files,
                "diagnostics": self.diagnostics,
            },
        }


def normalize_documents(documents: Iterable[dict[str, str]]) -> NormalizedEnvironment:
    services: dict[str, dict[str, Any]] = {}
    traffic: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    pricing: dict[str, Any] = {"currency": "USD"}
    action_results: list[dict[str, Any]] = []
    source_files: list[str] = []
    diagnostics: list[str] = []

    docs = list(documents)
    if not docs:
        raise DataValidationError("Provide at least one JSON document")

    def ingest_obj(filename: str, obj: Any) -> None:
        lower = filename.lower()
        if isinstance(obj, list):
            # A list may be services, events, or action results.
            for item in obj:
                if isinstance(item, dict) and _looks_like_service(item):
                    s = normalize_service(item)
                    services[s["service_id"]] = _merge_service(services.get(s["service_id"]), s)
                elif isinstance(item, dict) and "type" in item and "message" in item and "service_id" in item:
                    events.append(dict(item))
                elif isinstance(item, dict) and "action" in item and "status" in item:
                    action_results.append(dict(item))
                elif isinstance(item, dict) and "service_id" in item and "requests_per_minute" in item:
                    t = dict(item)
                    traffic[t["service_id"]] = t
                else:
                    raise DataValidationError(f"{filename}: unsupported list item shape")
            return

        if not isinstance(obj, dict):
            raise DataValidationError(f"{filename}: JSON root must be an object or array")

        # Combined environment file.
        if any(k in obj for k in ("services", "traffic", "events", "pricing", "action_results", "action_result")):
            if "services" in obj:
                raw_services = obj["services"]
                if isinstance(raw_services, dict):
                    raw_services = list(raw_services.values())
                for item in raw_services or []:
                    s = normalize_service(item)
                    services[s["service_id"]] = _merge_service(services.get(s["service_id"]), s)
            if "traffic" in obj:
                raw_traffic = obj["traffic"]
                if isinstance(raw_traffic, dict):
                    raw_traffic = list(raw_traffic.values())
                for item in raw_traffic or []:
                    if not isinstance(item, dict) or "service_id" not in item:
                        raise DataValidationError(f"{filename}: invalid traffic entry")
                    traffic[item["service_id"]] = dict(item)
            events.extend(obj.get("events") or [])
            if isinstance(obj.get("pricing"), dict):
                pricing.update(obj["pricing"])
            if obj.get("action_result"):
                action_results.append(dict(obj["action_result"]))
            if obj.get("action_results"):
                action_results.extend(obj["action_results"])
            return

        if _looks_like_service(obj):
            s = normalize_service(obj)
            services[s["service_id"]] = _merge_service(services.get(s["service_id"]), s)
            return
        if _looks_like_traffic(obj):
            traffic[obj["service_id"]] = dict(obj)
            return
        if "action" in obj and "status" in obj:
            action_results.append(dict(obj))
            return
        if "currency" in obj or any(k in obj for k in ("hourly_total", "hourly_cost", "monthly_total")):
            pricing.update(obj)
            return
        if "type" in obj and "message" in obj and "service_id" in obj:
            events.append(dict(obj))
            return

        # Filename-aware fallback for common problem-statement names.
        if "pricing" in lower:
            pricing.update(obj)
            return
        if "event" in lower:
            if isinstance(obj, dict): events.append(obj)
            return
        raise DataValidationError(f"{filename}: unrecognized JSON structure")

    for doc in docs:
        filename = str(doc.get("filename") or "input.json")
        content = doc.get("content")
        if not isinstance(content, str):
            raise DataValidationError(f"{filename}: content must be text")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise DataValidationError(f"{filename}: invalid JSON at line {exc.lineno}, column {exc.colno}") from None
        source_files.append(filename)
        ingest_obj(filename, parsed)

    # Attach latest traffic/trend to services and fill pricing total from service data if absent.
    for service_id, traffic_doc in traffic.items():
        if service_id not in services:
            diagnostics.append(f"Traffic supplied for unknown service '{service_id}' was retained but not attached to service state.")
            continue
        svc = services[service_id]
        if "previous_requests_per_minute" in traffic_doc:
            svc["previous_requests_per_minute"] = traffic_doc["previous_requests_per_minute"]

    hourly_total = sum(float(s.get("cost_per_hour", 0)) for s in services.values())
    pricing.setdefault("hourly_total", round(hourly_total, 2))
    pricing.setdefault("daily_total", round(float(pricing["hourly_total"]) * 24, 2))
    pricing.setdefault("monthly_total", round(float(pricing["hourly_total"]) * 24 * 30, 2))

    if not services:
        raise DataValidationError("No service records were found in the supplied JSON")

    # Update traffic with service-level metrics where no separate traffic document exists.
    for service_id, service in services.items():
        if service_id not in traffic:
            traffic[service_id] = {
                "service_id": service_id,
                "requests_per_minute": service.get("requests_per_minute", 0),
                "previous_requests_per_minute": service.get("previous_requests_per_minute"),
                "timestamp": service["timestamp"],
            }

    return NormalizedEnvironment(services, traffic, events, pricing, action_results, source_files, diagnostics)
