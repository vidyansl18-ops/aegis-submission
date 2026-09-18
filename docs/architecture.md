# Architecture

## Layers

1. **Data ingestion** — parses and validates user JSON into a normalized environment.
2. **Simulator** — stores service state and exposes deterministic read/execute behavior.
3. **Tool registry** — explicit inspection and verification tools available to agent providers.
4. **Agent** — MockAgent locally, optional Claude/OpenAI adapters.
5. **Safety engine** — deterministic policy independent of the model.
6. **Audit layer** — records safety decisions, action attempts and verification.
7. **Verifier** — retrieves fresh state and checks health, availability, latency and capacity.
8. **FastAPI/UI** — product interface, API endpoints and demo workflow.

## Trust boundary

```text
Model output
   ↓
Pydantic proposal validation
   ↓
Deterministic SafetyEngine
   ↓
ActionAudit
   ↓
CloudSimulator
   ↓
Verifier
```

The model-facing tools are read/verification tools only. Mutation calls are backend-controlled.
