import json

from backend.app.data_loader import DataValidationError, normalize_documents
from backend.app.simulator import CloudSimulator


def test_load_source_style_documents_and_detect_stale_state():
    env = normalize_documents([
        {
            "filename": "metric.json",
            "content": json.dumps({
                "service_id": "checkout-api",
                "cpu_percent": 24,
                "memory_percent": 39,
                "requests_per_minute": 900,
                "latency_ms": 170,
                "instances": 5,
                "cost_per_hour": 20.0,
                "min_instances": 2,
                "max_instances": 8,
                "max_latency_ms": 250,
                "healthy": True,
                "timestamp": "2026-09-17T08:00:00Z",
            }),
        },
        {
            "filename": "latest_traffic.json",
            "content": json.dumps({"service_id": "checkout-api", "requests_per_minute": 5200, "timestamp": "2026-09-17T10:30:00Z"}),
        },
    ])
    sim = CloudSimulator()
    sim.load_environment(env, source_name="test_input")
    assert sim.service("checkout-api")["timestamp"] == "2026-09-17T08:00:00Z"
    assert sim.traffic("checkout-api")["requests_per_minute"] == 5200
    fresh = sim.fresh_state("checkout-api")
    assert fresh["timestamp"] == "2026-09-17T10:30:00Z"
    assert fresh["requests_per_minute"] == 5200


def test_rejects_invalid_json_and_missing_service_id():
    try:
        normalize_documents([{"filename": "bad.json", "content": "{not-json"}])
        assert False, "Expected validation error"
    except DataValidationError as exc:
        assert "invalid JSON" in str(exc)

    try:
        normalize_documents([{"filename": "bad.json", "content": json.dumps({"cpu_percent": 5})}])
        assert False, "Expected validation error"
    except DataValidationError as exc:
        assert "unrecognized JSON structure" in str(exc)
