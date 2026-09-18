# Data Input Guide

## Supported input patterns

Aegis accepts multiple JSON documents in one load operation. It normalizes them into a single environment containing services, traffic, events, pricing and action results.

### Service object

```json
{
  "service_id": "example-api",
  "cpu_percent": 30,
  "memory_percent": 40,
  "requests_per_minute": 2200,
  "latency_ms": 180,
  "instances": 4,
  "cost_per_hour": 18.5,
  "min_instances": 2,
  "max_instances": 8,
  "max_latency_ms": 300,
  "healthy": true,
  "available": true,
  "timestamp": "2026-09-17T10:30:00Z"
}
```

### Combined environment

```json
{
  "services": [],
  "traffic": [],
  "events": [],
  "pricing": {"currency": "USD"},
  "action_results": []
}
```

## Validation

The importer rejects invalid JSON, missing `service_id`, malformed timestamps, invalid instance bounds and negative cost values. It returns diagnostics before the data becomes active.

## Freshness

The simulator clock is placed shortly after the newest supplied observation. This means the importer can work with arbitrary timestamps while preserving the challenge's stale-observation behavior whenever a newer traffic record conflicts with an older service snapshot.
