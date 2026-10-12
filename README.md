# LoopGrid LangGraph Integration

**Native LangGraph StateGraph decision evidence, policy gates, human-review checkpoints and tamper-evident verification.**

LoopGrid preserves evidence for consequential agent decisions; **your application still owns the real action, its authority, the authenticated reviewer and authoritative observed outcomes.** This is a community-built integration, not an official LangChain/LangGraph product or certified badge.

## Release status

`v0.1.0` remains **unpublished**. The hardened RC3 source passed **77/77 tests** on Windows Python 3.12 against installed LangGraph 1.2.14. Both native runtime and persistent SQLite checkpoint/restart tests passed; both real LoopGrid Core `0.8.1-design-partner` E2Es passed with signed workspace verification valid, zero failures, `evidence_complete`, 100% applicable coverage and two synthetic executions (no real money). The Core redaction-metadata fix is thus confirmed end-to-end. Local reproducible wheel/sdist + Twine audit, non-editable clean wheel consumer install, hosted cross-platform CI, and PyPI publication are the outstanding release gates. See [VALIDATION.md](VALIDATION.md).

## Install for development

Python 3.10+ and LangGraph 1.2.12+ are supported by the declared dependency range. The reference native runtime test targets **LangGraph 1.2.14** (released Oct 6, 2026).

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e '.[test,persistence-test]'
python -m pytest -v
python scripts/langgraph_runtime_e2e.py
python scripts/persistent_langgraph_e2e.py
```

The package name `loopgrid-langgraph` and public repository URL are **proposed** until the owner confirms availability and creates them. No PyPI release is assumed yet.

## Native StateGraph usage

The following example uses LangGraph's native `node(state, config: RunnableConfig)` injection signature and its checkpoint/interrupt/resume mechanism. The external callback is **only synthetic**. You must run your own LoopGrid Core, create a workspace and active policy, and supply the correct scoped service credential. The production application must implement authenticated human review independently.

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from loopgrid_langgraph import CoreClient, LangGraphBridge

class State(TypedDict, total=False):
    amount: int
    operation_id: str
    loopgrid: dict
    loopgrid_tool_result: dict
    loopgrid_verification: dict

core = CoreClient(
    base_url="http://127.0.0.1:8000", # Loopback-only HTTP; remote Core must use HTTPS
    workspace_id="YOUR_DISPOSABLE_WORKSPACE",
    service_key=__import__("os").environ["LOOPGRID_SERVICE_KEY"], # host secret manager
)
bridge = LangGraphBridge(core, agent_id="refund-agent")

arguments = lambda s: {"amount": s["amount"], "currency": "USD"}
propose = bridge.make_decision_node(
    tool="refund", policy_id="refund-policy", arguments=arguments,
    authority=lambda s: {"limit_usd": 1500, "scope": ["refund:create"]},
    model=lambda s: {"name": "host-supplied-model-identity"},
    context=lambda s: {"prompt_version": "refund-v1"},
    operation_id=lambda s: s["operation_id"],
)
# Callback actually returns only synthetic data. This is NOT a real refund.
execute = bridge.make_guarded_node(
    tool="refund", arguments=arguments,
    callback=lambda args: {"sandbox": True, "amount": args["amount"]},
)
graph_builder = StateGraph(State)
graph_builder.add_node("propose", propose)
graph_builder.add_node("execute", execute)
graph_builder.add_node("verify", bridge.make_verify_node())
graph_builder.add_edge(START, "propose")
graph_builder.add_edge("propose", "execute")
graph_builder.add_edge("execute", "verify")
graph_builder.add_edge("verify", END)
graph = graph_builder.compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "thread-unique-refund-01"}}
response = graph.invoke({"amount": 750, "operation_id": "refund-unique-01"}, config)
# Approval-required => response contains __interrupt__.
# Authentic reviewer is verified OUTSIDE the graph, using Core review API.
# Only an authenticated, authorized host performs this next call:
# core.review(response_decision_id, "approve", real_reviewer_id)
# After that, resume the SAME thread:
# response = graph.invoke(Command(resume="continue"), config)
```

**Do not copy the key placeholder into a real deployment.** Use your environment/secret manager to create `CoreClient` in the host, not agent-controllable state. `InMemorySaver` is suitable for local tests; use a durable supported LangGraph checkpointer and an external atomic dispatch lease for production multi-worker tools. The node omits duplicate raw tool arguments from the `loopgrid` scope, but **all other application state and callback results remain the host's checkpoint-privacy responsibility**.

## Why the graph is split into nodes

1. **Proposal node**: application-owned operation/thread ID, delegated authority, model/context metadata and exact tool args are committed to **one** Core decision, with redacted SHA-256 argument commitment.
2. **Core policy gate**: the active versioned policy is evaluated and recorded with its exact version, digest and input commitment. No model can assert authority.
3. **Review/interrupt**: a policy requiring approval leads to a native LangGraph `interrupt`. Resuming with `Command(resume=...)` is a UI/graph action, **never approval**. A scoped, authenticated Core review must independently exist.
4. **Guarded execution node**: checks the signed decision, exact proposal binding, policy provenance, current active policy, review, and any previous dispatch attempt *before* dispatching the callback.
5. **Receipt**: `tool_requested` is durably written **before** executing, `tool_executed` **only if the callback returns**. The callback return alone is not an externally verified business outcome.
6. **Outcome + verification**: host attaches real downstream observation separately using `bridge.record_outcome`; signed workspace integrity is verified through Core and may also be checked with the independent verifier.

The decision chain follows `decision_created → [model_completed when actually observed] → policy_evaluated → [human_approved / human_rejected if required] → tool_requested → tool_executed/tool_result → outcome_observed → evidence_complete → verify`. Ordering of model completion and policy is not fixed; events reflect real observations.

## More API surfaces

```python
# Only after a real host-observed model result exists:
bridge.observed_model(decision_id, model_name="actual-model", output=actual_result, source="host.model_call")

# Only after a trusted downstream observer verifies an outcome:
bridge.record_outcome(decision_id, external_reference="sandbox-order-123",
                      status="confirmed", source="trusted-host-observer", observed={"settled": True})

# Optional, purely observational LangGraph interrupt/resume callback:
from loopgrid_langgraph import LoopGridGraphCallback
observer = LoopGridGraphCallback(on_observation=print)
config = {"configurable": {"thread_id": "thread-01"}, "callbacks": [observer]}
```

Callbacks intentionally **do not unlock policy gates, fabricate signed evidence, or interpret user resume strings as human approval**. For parallel multi-decision graphs use a separate `operation_id` per consequential action and store each returned scope in its own state channel.

## Operational safety notes

- Workspace-scoped key passed explicitly; no ambient credential read by the adapter. Redirects disabled; TLS for remote Core; bounded response size; errors do not print response bodies or tokens.
- `proof_only` cannot provide inspectable replay guards; action decisions require redacted evidence. Privacy redaction commitments protect tool arguments, but the Core must be configured with appropriate retention and tenant isolation.
- A pre-dispatch `tool_requested` record conservatively **blocks automatic retry**, even if a crash happened before the real action. Reconcile using the downstream system. The package deliberately does **not** promise globally exactly-once effects across independent hosts.
- Concurrent/multi-worker dispatch must be serialized with a durable distributed lock or outbox reservation controlled by the host. Configure `LangGraphBridge(..., dispatch_lease=host_lease, require_dispatch_lease=True)` in multi-worker deployments. The included `LocalSqliteDispatchLease` is only a single-host test/reference. The built-in `RLock` serializes one bridge instance, **not multiple processes**.
- Tool callbacks are synchronous in v0.1.0. Async callbacks are rejected. `make_decision_node` avoids persisting a duplicate raw argument map inside `loopgrid`, but your own graph state/result/checkpoint may still contain private data.
- See [Worker recovery and privacy](docs/WORKER-RECOVERY-AND-PRIVACY.md) for contention, host leases, recovery, privacy, and serializer considerations.
- Signed evidence proves integrity and order under the trusted signing key, not factual truth, legal compliance, or correctness of a business decision. Verify signer identity out of band for offline proof.

See [INTEGRATION-CONTRACT.md](INTEGRATION-CONTRACT.md), [SECURITY.md](SECURITY.md), [VALIDATION.md](VALIDATION.md), and [WINDOWS-TEST-STEPS.md](WINDOWS-TEST-STEPS.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
