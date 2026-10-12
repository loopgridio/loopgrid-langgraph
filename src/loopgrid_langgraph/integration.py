"""LangGraph-native decision nodes. Guard actual tool dispatch; callbacks are observation only."""
from __future__ import annotations
from contextlib import nullcontext
import hashlib
import inspect
import json
import threading
from typing import Any, Callable, ContextManager, Mapping, TYPE_CHECKING

# Keep LangGraph node annotations compatible with runtime config injection.
# LangGraph accepts the postponed string annotation "RunnableConfig", not "dict".
if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

from .core import LoopGridError, require_id

FRAMEWORK = "langgraph"
VERSION = "0.1.0"

class PolicyDenied(RuntimeError): pass
class ApprovalRequired(RuntimeError): pass
class ReconciliationRequired(RuntimeError): pass
class EvidenceInvalid(RuntimeError): pass

def canonical_json(value: Any) -> bytes:
    # Reject non-JSON content rather than serialize arbitrary repr(), which could diverge.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")

def commitment(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()

def snapshot(obj: Any) -> Any:
    return json.loads(canonical_json(obj).decode("utf-8"))

def idem(*parts: Any) -> str:
    return "lg-langgraph-" + commitment(parts)

def _valid_map(value: Any, label: str) -> dict:
    if not isinstance(value, Mapping): raise ValueError(f"{label} must be a mapping")
    return snapshot(dict(value))

def _get_thread(config: Mapping) -> str:
    thread = (config or {}).get("configurable", {}).get("thread_id")
    return require_id(thread)

def _events(detail: dict) -> list[dict]:
    events = detail.get("events")
    if not isinstance(events, list) or not events:
        raise EvidenceInvalid("Signed decision event history unavailable")
    return events

def _payload(event: dict) -> dict:
    p = event.get("payload")
    if not isinstance(p, dict): raise EvidenceInvalid("Signed evidence payload not inspectable")
    return p

def _signed_value_matches(signed: Any, expected: Any) -> bool:
    """Compare signed Core evidence with the host-owned original JSON value.

    Core `privacy_mode=redacted` can return typed commitment envelopes for
    individual fields (for example `model.name` or `context.prompt_version`).
    Compare their SHA-256 hashes over canonical JSON, without treating a
    redacted commitment as a wildcard or trusting any unsigned placeholder.
    The caller MUST first verify the Core workspace's signed evidence chain.
    """
    if isinstance(signed, dict) and signed.get("redacted") is True:
        if set(signed) != {"redacted", "sha256", "type"}:
            return False
        if not isinstance(signed["sha256"], str) or len(signed["sha256"]) != 64:
            return False
        if signed["type"] != type(expected).__name__:
            return False
        try:
            return signed["sha256"] == commitment(expected)
        except (TypeError, ValueError):
            return False
    if type(signed) is not type(expected):
        return False
    if isinstance(signed, dict):
        return (signed.keys() == expected.keys() and
                all(_signed_value_matches(signed[k], expected[k]) for k in signed))
    if isinstance(signed, list):
        return len(signed) == len(expected) and all(
            _signed_value_matches(s, e) for s, e in zip(signed, expected))
    return signed == expected

def _assert_chain(client: Any, decision_id: str) -> list[dict]:
    proof = client.verify_workspace()
    if proof.get("valid") is not True or proof.get("failures") or proof.get("workspace_id") not in (None, client.workspace_id):
        raise EvidenceInvalid("Signed workspace verification failed")
    detail = client.get_decision(decision_id)
    summary = detail.get("summary") or {}
    if summary.get("workspace_id") != client.workspace_id:
        raise EvidenceInvalid("Decision belongs to a different workspace")
    return _events(detail)

class LangGraphBridge:
    """Native graph nodes and explicit authority boundary; scope held in checkpointed state.

    A non-transactional API cannot guarantee global exactly-once side effects across workers.
    For multi-worker deployment provide a shared durable dispatch_lease; the built-in
    lock protects only one bridge instance. No distributed exactly-once guarantee.
    """
    def __init__(self, client: Any, *, agent_id: str, lock: Any = None,
                 dispatch_lease: Callable[[str], ContextManager[Any]] | None = None,
                 require_dispatch_lease: bool = False):
        require_id(agent_id)
        if require_dispatch_lease and dispatch_lease is None:
            raise ValueError("A shared durable dispatch lease is required for multi-worker execution")
        if dispatch_lease is not None and not callable(dispatch_lease):
            raise TypeError("dispatch_lease must be a context-manager factory")
        self.client = client
        self.agent_id = agent_id
        self._lock = lock if lock is not None else threading.RLock()
        self._dispatch_lease = dispatch_lease

    def propose(self, *, thread_id: str, operation_id: str, tool: str, arguments: Mapping,
                authority: Mapping, model: Mapping, context: Mapping, policy_id: str,
                decision_type: str = "agent_tool_action") -> dict:
        """Application calls in its proposal node; returns checkpointable redacted scope."""
        for v in (thread_id, operation_id, tool, policy_id): require_id(v)
        args = _valid_map(arguments,"arguments")
        if "tool" in args: raise ValueError("arguments cannot override the trusted tool identity")
        auth = _valid_map(authority,"authority")
        mod = _valid_map(model,"model")
        ctx = _valid_map(context,"context")
        if not mod.get("name") or not auth or not ctx: raise ValueError("Model, authority and context must be explicit")
        spec = {"tool":tool,"arguments_sha256":commitment(args), "thread_id":thread_id,
                "operation_id":operation_id, "policy_id":policy_id}
        # Redacted: no raw arguments. Policy itself requires actual fields for evaluation.
        created = self.client.create_decision({
            "decision_type":decision_type,"service_name":"loopgrid-langgraph",
            "privacy_mode":"redacted", "agent":{"id":self.agent_id},
            "authority":auth, "model":mod, "context":{**ctx,"thread_id":thread_id,"operation_id":operation_id},
            "proposed_action":spec,
            "metadata":{"framework":FRAMEWORK,"integration_version":VERSION},
            "idempotency_key":idem("create", self.client.workspace_id, thread_id, operation_id),
        })
        decision_id = require_id(created["decision_id"])
        if created.get("idempotent_replay"):
            # A replay may not silently switch agent, authority, model or context.
            events = self._check_binding(decision_id, spec)
            self._check_created_metadata(events, spec, auth, ctx, model=mod)
        policy_input = {"tool":tool, **args}
        policy = self.client.evaluate_policy(policy_id, policy_input, auth, ctx)
        if policy.get("policy_id") != policy_id or policy.get("decision") not in {
                "auto_allowed", "human_approval_required", "blocked", "manual_review_required"}:
            raise EvidenceInvalid("Policy response failed provenance validation")
        if not all(policy.get(f) for f in ("version", "policy_digest", "input_commitment")):
            raise EvidenceInvalid("Policy response missing signed provenance fields")
        # On idempotent create replay, avoid writing duplicate policy evidence.
        if not created.get("idempotent_replay"):
            self.client.add_event(decision_id,"policy_evaluated",policy,actor_type="policy",actor_id=policy_id,
                                  idempotency_key=idem("policy",self.client.workspace_id,decision_id))
        return {"decision_id":decision_id,"spec":spec,"policy":policy,
                "authority":auth,"context":ctx,"tool_arguments":args}

    def _check_binding(self, decision_id: str, spec: dict) -> list[dict]:
        events = _assert_chain(self.client, decision_id)
        created = next((e for e in events if e.get("event_type")=="decision_created"),None)
        if not created or _payload(created).get("proposed_action") != spec:
            raise EvidenceInvalid("Decision action binding mismatch")
        return events

    def _check_created_metadata(self, events: list[dict], spec: dict,
                                auth: dict, ctx: dict, *, model: dict | None = None) -> None:
        created = next((e for e in events if e.get("event_type") == "decision_created"), None)
        if created is None:
            raise EvidenceInvalid("Missing signed decision creation metadata")
        payload = _payload(created)
        signed_context = {**ctx, "thread_id": spec["thread_id"],
                          "operation_id": spec["operation_id"]}
        if (not _signed_value_matches(payload.get("agent"), {"id": self.agent_id})
                or not _signed_value_matches(payload.get("authority"), auth)
                or not _signed_value_matches(payload.get("context"), signed_context)
                or (model is not None and not _signed_value_matches(payload.get("model"), model))):
            raise EvidenceInvalid("Signed decision identity, authority or context changed")

    def dispatch(self, scope: Mapping, *, thread_id: str, tool: str, arguments: Mapping,
                 callback: Callable[[dict], Any]) -> Any:
        """Fail closed before calling callback. A tool_requested event permanently reserves attempt."""
        if inspect.iscoroutinefunction(callback) or inspect.iscoroutinefunction(getattr(callback, "__call__", None)):
            raise TypeError("Async tool callbacks are not supported; use a synchronous host dispatcher")
        saved = _valid_map(scope, "scope")
        decision_id = require_id(saved.get("decision_id"))
        lease_key = idem("dispatch-lease", self.client.workspace_id, decision_id)
        # The supplied host lease MUST be shared across workers and held through
        # the callback. Acquiring it before reading Core evidence closes the
        # usual check-then-write race between collaborating workers.
        lease = self._dispatch_lease(lease_key) if self._dispatch_lease else nullcontext()
        with lease, self._lock:
            saved = _valid_map(scope,"scope")
            spec = saved.get("spec")
            args = _valid_map(arguments,"arguments")
            if (spec is None or spec.get("thread_id") != thread_id or spec.get("tool") != tool
                    or spec.get("arguments_sha256") != commitment(args)
                    or ("tool_arguments" in saved and saved["tool_arguments"] != args)):
                raise EvidenceInvalid("Action changed from original checkpointed proposal")
            events = self._check_binding(decision_id, spec)
            self._check_created_metadata(events, spec, saved["authority"], saved["context"])
            if any(e.get("event_type") in ("tool_requested","tool_executed","tool_result","outcome_observed") for e in events):
                raise ReconciliationRequired("Prior dispatch attempt detected; reconcile before retry")
            recorded_policy = next((e for e in events if e.get("event_type")=="policy_evaluated"),None)
            if recorded_policy is None: raise EvidenceInvalid("No signed policy evidence")
            prev = _payload(recorded_policy)
            expected = saved.get("policy") or {}
            keys=("policy_id","version","policy_digest","input_commitment","decision")
            if any(prev.get(k)!=expected.get(k) or not prev.get(k) for k in keys):
                raise EvidenceInvalid("Signed policy provenance mismatch")
            if spec.get("policy_id") != expected.get("policy_id"):
                raise EvidenceInvalid("Decision policy identity mismatch")
            # Fresh evaluation detects policy rotations/revocation before any side effect.
            current = self.client.evaluate_policy(spec["policy_id"], {"tool":tool,**args},
                                                  saved["authority"],saved["context"])
            if any(current.get(k)!=expected.get(k) for k in keys):
                raise PolicyDenied("Current policy differs; new decision required")
            verdict = expected["decision"]
            if verdict in ("blocked", "manual_review_required"):
                raise PolicyDenied("Core policy did not authorize execution")
            # Rejection is terminal for this action, including after policy changes.
            if any(e.get("event_type") == "human_rejected" for e in events):
                raise PolicyDenied("Signed human rejection is final for this decision")
            if verdict == "human_approval_required":
                approvals=[e for e in events if e.get("event_type") in ("human_approved","human_rejected")]
                if not approvals: raise ApprovalRequired("Authenticated signed review required")
                if approvals[-1]["event_type"] != "human_approved" or _payload(approvals[-1]).get("approved") is not True:
                    raise PolicyDenied("Human reviewer rejected action")
            # A signed receipt of request is a durable conservative barrier: no automatic replay.
            reservation = self.client.add_event(decision_id,"tool_requested",{
                "framework":FRAMEWORK,"tool":tool,"arguments_sha256":commitment(args),
                "thread_id":thread_id,"operation_id":spec["operation_id"]},
                actor_type="tool",actor_id=tool,
                idempotency_key=idem("tool-request",self.client.workspace_id,decision_id))
            # A duplicate idempotency response is NOT permission to execute.
            # Multi-worker deployments still require a shared external lease.
            if isinstance(reservation, Mapping) and reservation.get("idempotent_replay") is True:
                raise ReconciliationRequired("Tool request already reserved; never re-execute")
            try:
                result = callback(snapshot(args))
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()  # avoid leaking an unawaited coroutine
                    raise TypeError("Async callback result is unsupported")
            except Exception:
                try: self.client.add_event(decision_id,"tool_result",{
                    "status":"error","framework":FRAMEWORK,"tool":tool,
                    "external_outcome_verified":False},actor_type="tool",actor_id=tool)
                except Exception: pass
                raise ReconciliationRequired("Tool raised after dispatch; reconcile external state") from None
            try:
                result_hash = commitment(result)
                self.client.add_event(decision_id,"tool_executed",{
                    "framework":FRAMEWORK,"tool":tool,"status":"returned",
                    "result_sha256":result_hash,"external_outcome_verified":False},
                    actor_type="tool",actor_id=tool)
            except Exception:
                raise ReconciliationRequired("Result evidence failed after dispatch; reconcile") from None
            return result

    def observed_model(self, decision_id: str, *, model_name: str, output: Any, source: str) -> dict:
        if not model_name or not source: raise ValueError("Observed model source required")
        _assert_chain(self.client, require_id(decision_id))
        return self.client.add_event(decision_id,"model_completed",{
            "source":source,"model":model_name,"output_sha256":commitment(output),"framework":FRAMEWORK},
            actor_type="agent",actor_id=self.agent_id,
            idempotency_key=idem("model",self.client.workspace_id,decision_id,commitment(output)))

    def record_outcome(self, decision_id: str, *, external_reference: str, status: str,
                       source: str, observed: Mapping) -> dict:
        if not external_reference or not source or not status: raise ValueError("Authoritative outcome source and reference required")
        events = _assert_chain(self.client,require_id(decision_id))
        if not any(e.get("event_type")=="tool_executed" for e in events):
            raise EvidenceInvalid("Cannot claim outcome before signed tool execution receipt")
        return self.client.add_event(decision_id,"outcome_observed",{
            "status":status,"external_reference":external_reference,"source":source,
            "observed_sha256":commitment(dict(observed)),"verified_source":True},
            actor_type="integration",actor_id="host-outcome-observer",
            idempotency_key=idem("outcome",self.client.workspace_id,decision_id,external_reference))

    def make_decision_node(self, *, tool: str, policy_id: str, arguments: Callable[[dict],dict],
                           authority: Callable[[dict],dict], model: Callable[[dict],dict],
                           context: Callable[[dict],dict], operation_id: Callable[[dict],str]):
        """Return an ordinary LangGraph StateGraph node with (state, config) signature."""
        def node(state: dict, config: RunnableConfig) -> dict:
            thread = _get_thread(config)
            if state.get("loopgrid"):
                # Graph loops/restarts must not reuse the previous operation for a new action.
                stored = _valid_map(state["loopgrid"], "loopgrid")
                spec = stored.get("spec") or {}
                args = _valid_map(arguments(state), "arguments")
                if (spec.get("thread_id") != thread or spec.get("operation_id") != operation_id(state)
                        or spec.get("tool") != tool or spec.get("policy_id") != policy_id
                        or spec.get("arguments_sha256") != commitment(args)
                        or stored.get("authority") != _valid_map(authority(state), "authority")
                        or stored.get("context") != _valid_map(context(state), "context")):
                    raise EvidenceInvalid("Checkpoint scope is bound to a different action or graph operation")
                events = self._check_binding(stored["decision_id"], spec)
                self._check_created_metadata(events, spec, stored["authority"], stored["context"],
                                             model=_valid_map(model(state), "model"))
                return {}
            scope = self.propose(thread_id=thread,operation_id=operation_id(state),
                    tool=tool, arguments=arguments(state),authority=authority(state),
                    model=model(state),context=context(state),policy_id=policy_id)
            # The state must already supply arguments via the application's
            # `arguments(state)` callback. Do not duplicate raw args inside our
            # checkpoint scope; retain their signed SHA-256 commitment instead.
            scope.pop("tool_arguments", None)
            return {"loopgrid":scope}
        return node

    def make_guarded_node(self, *, tool: str, arguments: Callable[[dict], dict],
                          callback: Callable[[dict],Any], interrupt_for_review: bool = True):
        """Native StateGraph node. interrupt() is advisory only; signed Core review is authority."""
        def node(state: dict, config: RunnableConfig) -> dict:
            from langgraph.types import interrupt  # defer optional framework import
            thread = _get_thread(config)
            scope = _valid_map(state["loopgrid"],"loopgrid")
            if scope["policy"]["decision"] == "human_approval_required" and interrupt_for_review:
                # Even if model/user sends resume='approved', signed authenticated Core review is required.
                interrupt({"kind":"loopgrid_human_review","decision_id":scope["decision_id"],
                           "tool":tool,"message":"Review through authorized LoopGrid Core review API"})
            result = self.dispatch(scope,thread_id=thread,tool=tool,
                                   arguments=arguments(state),callback=callback)
            return {"loopgrid_tool_result":result}
        return node

    def make_verify_node(self):
        def node(state: dict, config: RunnableConfig) -> dict:
            _get_thread(config)
            proof = self.client.verify_workspace()
            if proof.get("valid") is not True or proof.get("failures"):
                raise EvidenceInvalid("Workspace signature verification failed")
            return {"loopgrid_verification":snapshot(proof)}
        return node
