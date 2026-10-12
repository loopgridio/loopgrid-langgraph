# LoopGrid LangGraph v0.1.0 — Integration Contract

## Invariants

LoopGrid is a **decision evidence plane**, not the framework's LLM runtime or the external business action executor.

| Source | Signed evidence | Constraint |
| --- | --- | --- |
| App-provided `operation_id` + `thread_id`, tool args, delegated identity | `decision_created` | One consequential decision; redacted args SHA-256; stable operation ID for retries |
| Actual app-observed model output (explicit API) | `model_completed` | Never synthesized from prompt/model identifier |
| Core's actual active deterministic policy response | `policy_evaluated` | Must include policy ID, version, digest and input commitment |
| Authenticated Core review by real external host | `human_approved` or `human_rejected` | Resume payload, graph checkpoint and tool text are not approval |
| Native guarded `StateGraph` node immediately before callback | `tool_requested` | Signed, conservative no-replay barrier; exact tool+args binding |
| Wrapped callback returns / raises | `tool_executed` / `tool_result` | Return does not establish external success |
| Trusted host checks actual downstream system | `outcome_observed` | Require external reference, status, source; never invent result |
| Core and independent offline verifier | Workspace hash-chain/signature verification | Data integrity only; no business correctness claims |

## Native extension points

- `LangGraphBridge.make_decision_node()`, `make_guarded_node()`, `make_verify_node()` return **StateGraph-native `(state, config)` nodes**.
- `langgraph.types.interrupt` + `Command(resume=...)` provide checkpoint-backed human-in-the-loop UX. The interrupt happens before the action; code before it may be re-executed on resume.
- `LoopGridGraphCallback` inherits `langgraph.callbacks.GraphCallbackHandler` (when installed) and observes `on_interrupt(event)` and `on_resume(event)`; this is **telemetry only**.
- Application supplies `CoreClient` with explicit workspace/key, durable checkpointer and production-level external dispatch serialization. The bridge accepts `dispatch_lease=` and a `require_dispatch_lease=True` gate; a local SQLite reference lease is limited to same-host testing.

## Security state machine

**proposal → real Core policy → signed approval where required → verified unattempted decision → signed tool-request reservation → callback → signed callback receipt → optional downstream outcome → verify**.

Any ambiguity after request reservation (callback error, Core receipt outage, interrupted process) leads to **ReconciliationRequired** and no automatic replay. A signed approval for a different decision, identity, action or policy is not authority.

A signed rejection is terminal for the decision, even if a later event says approved. A duplicate Core reservation acknowledgement must never permit a callback.

A new attempt for the same consequence requires a deliberate host reconciliation and, if needed, a separate decision/operation identifier. This adapter does not implement a distributed atomic conditional write; a correctly configured host must prevent multi-process races.

Native graph proposal nodes do not duplicate the raw arguments inside the `loopgrid` checkpoint scope; the host state may still contain private data. Only synchronous guarded callbacks are supported. See [worker recovery and privacy](docs/WORKER-RECOVERY-AND-PRIVACY.md).

## E2E release gates

1. Unit/security matrix passing with semantics and fail-closed tests.
2. Installed LangGraph 1.2.14 test of real `StateGraph`, `InMemorySaver`, `interrupt`, `Command(resume)` (not merely import), plus optional `SqliteSaver` persistent restart.
3. Isolated Core 0.8.1 full allow/block/approve/reject signed E2E.
4. Offline verification with out-of-band public key; distinguish signed ledger from legacy file-level attestation.
5. Built wheel and sdist, metadata validation, clean installation, cross-platform CI.
6. After all gates, create public GitHub tag/Release and PyPI Trusted Publishing; then fresh public PyPI install and website/discovery.
