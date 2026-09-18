# Judge Questions

**Where does the data come from?**

The supplied KMIT JSON test inputs are included under `data/source_problem/`. The UI also accepts custom JSON.

**Does the AI directly change infrastructure?**

No. The model produces a structured proposal. Deterministic backend code authorizes or blocks the proposal before simulator execution.

**What happens with stale data?**

The agent compares observation timestamps with the latest traffic record, fetches fresh service state and reassesses before taking a consequential action.

**What happens if execution fails?**

The simulator returns the failure. The system records it, fetches fresh state anyway, marks verification failed and does not report success.

**Can you use a different AI provider?**

Yes. The local MockAgent works without a key. Optional provider adapters are included for Anthropic and OpenAI.

**Can you run your own environment?**

Yes. Use Data Studio to upload or paste JSON. The application validates and normalizes the input before activation.
