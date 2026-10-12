# Worker serialization, checkpoint recovery and privacy

The graph engine controls scheduling and persistence. LoopGrid Core supplies signed
policy/review/evidence, not a transactional executor. **There is no automatic global
exactly-once action guarantee.**

## Dispatch across workers

Two workers may read a clean signed decision at the same time. The ordinary Core
`tool_requested` append is a durable, conservative *replay barrier*, but is **not**
a documented cross-worker compare-and-swap lease. A reused idempotency response is
explicitly refused; that alone is not sufficient if two concurrent first writers
both receive an acknowledgement.

`LangGraphBridge(..., dispatch_lease=host_lease,
require_dispatch_lease=True)` accepts a host-provided callable taking the stable,
opaque decision-operation key and returning a context manager. **All competing
workers must use the same lease service**, the same Core workspace, the same
operation ID and a mutually exclusive fence through the external callback and
receipt write. Acquiring a lease must fail closed. When using a time-limited lease,
use a fenced execution protocol with verified renewal/ownership; otherwise a pause
or expiration can allow two callbacks. A shared Postgres row-lock or single-writer
transactional outbox is more appropriate than a short TTL lock.

For **single-machine tests only**, use `LocalSqliteDispatchLease`:

```python
from pathlib import Path
from loopgrid_langgraph import LangGraphBridge, LocalSqliteDispatchLease

lease = LocalSqliteDispatchLease(Path('C:/loopgrid-test/dispatch.sqlite').resolve())
bridge = LangGraphBridge(
    core, agent_id='your-agent', dispatch_lease=lease,
    require_dispatch_lease=True,
)
```

All local workers must use **one shared absolute database file on a reliable local
filesystem**. This SQLite reference implementation uses `BEGIN IMMEDIATE` and
serializes all dispatches, not one row per key. It does not work as a correct
production lease over multiple machines/network filesystems. On restart, the
transaction releases, but the prior Core request event still blocks replay.

## Crash and retry

- **Before** Core writes `tool_requested`: no callback has run; try again only
  after checking the decision and host idempotency constraints.
- **After** `tool_requested`, **before** callback: an execution may or may not
  have happened; halt and reconcile, never retry automatically.
- After callback but before `tool_executed`: the same conservative state applies.
- After `tool_executed`: downstream success is not proven; a trusted host must
  inspect an authoritative external system before posting `outcome_observed`.

Rollback of a local lock is **not** a rollback of a payment, email, or API action.
Downstream systems should expose idempotency keys and authoritative status APIs.

## LangGraph checkpoint privacy

`make_decision_node` now strips its duplicate `tool_arguments` field from the
`loopgrid` checkpoint scope. A signed SHA-256 arguments commitment remains, and
the tool arguments are **re-derived from application state** at dispatch.
`LangGraphBridge.propose` still returns `tool_arguments` to callers using the
lower-level API: treat that dict as sensitive if you serialize it yourself.

**This does not redact the rest of a LangGraph checkpoint.** The host-supplied
application state, authority, context, model metadata and `loopgrid_tool_result`
may contain private data. Apply data minimization, encryption at rest, access
control, retention limits and safe serializer settings to your chosen checkpointer.
Do not store API keys or raw customer payloads in checkpoint/telemetry fields.
See LangGraph's serializer restrictions for compromised databases:
https://reference.langchain.com/python/langgraph.checkpoint.sqlite

The SQLite checkpoint demonstration (`scripts/persistent_langgraph_e2e.py`)
uses `SqliteSaver` for **development validation**. Production workloads should
use a supported durable production backend (for example PostgresSaver) and test
its actual failure/recovery semantics.

## Review trust and asynchronous tools

`Command(resume=...)` is not approval. Application reviewer authentication and
authorization are external to LoopGrid's SDK. A Core signature proves recorded
review provenance under a signer key, **not real-world human identity** unless the
host identity layer is trustworthy.

Guarded callbacks are **synchronous** in v0.1.0. Async callback functions are
rejected before request reservation. Calling async code through an arbitrary
coroutine-returning sync wrapper is also unsupported. Use a host-owned synchronous
dispatcher or design a separately tested async release; do not fire-and-forget
irreversible operations.

## Verification statements

Signed workspace verification validates ledger integrity according to Core's
trusted key. Offline verification must pin the signer key out of band. No part of
this integration turns a callback result into independent external outcome proof.
