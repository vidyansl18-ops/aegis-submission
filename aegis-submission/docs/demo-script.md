# 5-Minute Demo Script

## 1. Open Overview

Say:

> “Aegis FinOps is an autonomous cloud cost optimization control loop. It investigates supplied cloud data, proposes a bounded change, validates it deterministically, executes through a simulator and proves the post-action state.”

## 2. Open Data Studio

Show the active source and the ability to upload JSON.

Click **Test A Load** or upload the supplied `scenario_a/services.json`.

## 3. Run Test A

Prompt:

> Review the current services and reduce unnecessary cost without breaking the latency or availability requirements.

Show:

```text
AI investigation → proposal → safety → execution → verification
```

## 4. Run Test C

Load the two supplied files:

- `metric.json`
- `latest_traffic.json`

Run:

> Reduce cost if it is safe.

Show the freshness refresh and no-action result.

## 5. Run Test D

Load the two supplied files for payment-api and run the supplied prompt.

Show that `capacity_unavailable` is reported as a failure and the verification remains failed.

## 6. End on Audit Trail

Show that the complete lifecycle is recorded.
