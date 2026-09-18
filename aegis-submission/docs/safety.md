# Safety Model

The SafetyEngine is deterministic and runs independently of the LLM.

Checks include:

- service existence
- observation freshness
- health
- availability
- min/max instance limits
- rising traffic when scaling down
- latency headroom when scaling down
- valid resource size for resize
- idle + stoppable requirements for stop-idle
- worker/batch policy for delay-batch
- current latency target

`no_action` is always permitted because doing nothing is safer than acting without sufficient evidence.
