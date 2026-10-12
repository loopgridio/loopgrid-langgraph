# Security — LoopGrid LangGraph Integration

**Trust boundary:** the model must never choose a service key, reviewer identity, application authority, policy verdict, signed action scope or external observed result. The host supplies the explicit LoopGrid Core client, validated inputs, privileged reviewer and approved tool callback.

**Fail-closed paths:** unavailable Core, missing or corrupt decision history, invalid signature chain, missing versioned policy evidence, rotated/differing policy, denied or unreviewed action, mismatched arguments, replayed request and missing outcome provenance all fail without silently authorizing a tool. The library does not execute any other tools outside the guarded node.

**Graph restart:** `interrupt()` restarts its node on resume. A persisted signed `tool_requested` event must be inspected before an attempted replay. A crash after request but before external effect is conservatively indistinguishable from a crash after an effect: stop and reconcile rather than retry.

**Multi-process risk:** the SDK's in-process `RLock` is not a distributed lock. The Core append API is not assumed to expose an atomic compare-and-swap/once-only cross-worker reservation; duplicate reservation responses fail closed. A host serving multiple runners must supply a shared durable, fenced transactional lock or single-writer outbox, with `require_dispatch_lease=True`. The included `LocalSqliteDispatchLease` serializes processes only on one reliable local disk and is not distributed-production infrastructure. Do not claim exactly-once financial effects solely from this adapter.

**Credentials/privacy:** remote Core requires HTTPS; HTTP is permitted only for loopback. Explicit keys are transmitted only to the validated Core origin. HTTP redirects and proxy environment inheritance are disabled; maximum Core JSON response is bounded. Error messages intentionally omit secret-bearing response bodies. Record hashed arguments with redacted decision mode. Native decision nodes strip a duplicate raw argument map from the `loopgrid` checkpoint scope; all other application state, authority/context, and result payloads remain the host's checkpoint privacy responsibility. Configure checkpoint encryption, safe serializer settings, access control and retention. Do not put raw arguments or credentials in graph logs, telemetry or screenshots.

**Reviewer identity:** the sample's service-key review is synthetic and cannot substantiate a real person's authorization. Production human-review hosts must authenticate and authorize the human, then submit the signed review to Core. Never take an LLM response or `Command(resume=True)` as signed approval.

**Proof semantics:** Ed25519 validates integrity under the signer key; independently pin the key for signer identity. Integrity is not a compliance attestation, model correctness verdict or verification that a business action really succeeded. Preserve any legacy bundle-attestation warning rather than upgrading it to a full attestation claim.

**Dependency and deployment:** inspect pinned LangGraph/Core releases, GitHub alerts and security advisories; use production-grade store, checkpointer, backend authentication and threat model. InMemorySaver is for local demos only.

**Callback mode:** v0.1.0 guarded dispatch is synchronous only. Coroutine callbacks are rejected rather than silently launched. Signed rejection is terminal, and `Command(resume)` cannot supersede it.

See [worker recovery and privacy](docs/WORKER-RECOVERY-AND-PRIVACY.md).
