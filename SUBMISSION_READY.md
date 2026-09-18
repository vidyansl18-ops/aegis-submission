# Aegis FinOps — Submission Ready

## What to submit

You can submit the entire project folder/ZIP. The repository contains the application, source-aligned KMIT test JSON, documentation, tests and run scripts.

## First run

```powershell
.\run.ps1
```

Then open:

`http://127.0.0.1:8000`

## Judge demo

1. Overview
2. Data Studio
3. Load a KMIT Test A/B/C/D dataset or upload your own JSON
4. AI Agent
5. Scenario Lab
6. Verification Center
7. Audit Trail

## Main proof points

- Custom data can be loaded without editing source code.
- The agent investigates before proposing.
- Deterministic safety blocks unsafe actions.
- Stale observations trigger refresh/reassessment.
- Failed actions remain failed in the final result.
- Post-action state is fetched fresh and verified.
- Every run is auditable.

## Final local verification

Run:

```powershell
python -m pytest -q
```

The maintained test suite covers safety, scenarios, input normalization and adversarial behavior.
