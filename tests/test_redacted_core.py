"""Regression for actual Core 0.8.1 redacted signed decision_created payloads.

Real Core retains agent.id and action binding but supplies typed SHA-256
commitments for model.name and context.prompt_version. Do not mistakenly
reject these, and never accept a forged or mismatched commitment.
"""
from __future__ import annotations
import hashlib
import pytest

from fakes import FakeCore
from loopgrid_langgraph import LangGraphBridge, EvidenceInvalid, commitment

class RedactedCreateCore(FakeCore):
    def create_decision(self, payload):
        result = super().create_decision(payload)
        if not result.get("idempotent_replay"):
            p = self.decisions[result["decision_id"]]["events"][0]["payload"]
            for container, key in [(p["model"], "name"), (p["context"], "prompt_version")]:
                container[key] = {"redacted": True, "sha256": commitment(container[key]), "type": "str"}
        return result

@pytest.fixture
def prepared():
    core=RedactedCreateCore()
    bridge=LangGraphBridge(core, agent_id="test-agent")
    scope=bridge.propose(thread_id="thread-001",operation_id="refund-001",tool="refund",
                         arguments={"amount": 15},authority={"limit_usd": 1500},
                         model={"name": "synthetic-model"},context={"prompt_version": "v1"},
                         policy_id="refund-policy")
    return core,bridge,scope

def _dispatch(bridge, scope):
    return bridge.dispatch(scope, thread_id="thread-001", tool="refund",
                           arguments={"amount": 15}, callback=lambda args:{"sandbox": "ok"})

def test_actual_core_typed_redacted_strings_permit_bound_execution(prepared):
    core,bridge,scope=prepared
    created=core.get_decision(scope["decision_id"])["events"][0]["payload"]
    assert created["model"]["name"]["sha256"] == hashlib.sha256(b'"synthetic-model"').hexdigest()
    assert _dispatch(bridge,scope)=={"sandbox":"ok"}

def test_idempotent_replay_validates_redacted_model_and_context(prepared):
    core,bridge,scope=prepared
    fresh=bridge.propose(thread_id="thread-001",operation_id="refund-001",tool="refund",
                         arguments={"amount": 15},authority={"limit_usd": 1500},
                         model={"name": "synthetic-model"},context={"prompt_version": "v1"},
                         policy_id="refund-policy")
    assert fresh["decision_id"]==scope["decision_id"]
    with pytest.raises(EvidenceInvalid):
        bridge.propose(thread_id="thread-001",operation_id="refund-001",tool="refund",
                       arguments={"amount":15},authority={"limit_usd":1500},
                       model={"name":"different-model"},context={"prompt_version":"v1"},
                       policy_id="refund-policy")
    with pytest.raises(EvidenceInvalid):
        bridge.propose(thread_id="thread-001",operation_id="refund-001",tool="refund",
                       arguments={"amount":15},authority={"limit_usd":1500},
                       model={"name":"synthetic-model"},context={"prompt_version":"v2"},
                       policy_id="refund-policy")

def test_changed_authority_refused_before_dispatch(prepared):
    core,bridge,scope=prepared
    scope["authority"]={"limit_usd":50}
    with pytest.raises(EvidenceInvalid): _dispatch(bridge,scope)
    assert not any(e["event_type"]=="tool_requested" for e in core.get_decision(scope["decision_id"])["events"])

@pytest.mark.parametrize("tamper",[
    lambda p: p["context"]["prompt_version"].update(sha256="0"*64),
    lambda p: p["agent"].update(id="different-agent"),
    lambda p: p["context"].update(thread_id="different-thread"),
])
def test_changed_signed_dispatch_identity_refused(prepared, tamper):
    core,bridge,scope=prepared
    p=core.decisions[scope["decision_id"]]["events"][0]["payload"]
    tamper(p)
    with pytest.raises(EvidenceInvalid): _dispatch(bridge,scope)
    assert not any(e["event_type"]=="tool_requested" for e in core.get_decision(scope["decision_id"])["events"])

@pytest.mark.parametrize("tamper",[
    lambda p: p["model"]["name"].update(sha256="0"*64),
    lambda p: p["model"]["name"].update(type="int"),
    lambda p: p["model"]["name"].update(sha256="bogus"),
    lambda p: p["model"]["name"].update(extra="permissive"),
])
def test_changed_signed_model_fails_idempotent_proposal_reuse(prepared, tamper):
    core,bridge,scope=prepared
    p=core.decisions[scope["decision_id"]]["events"][0]["payload"]
    tamper(p)
    with pytest.raises(EvidenceInvalid):
        bridge.propose(thread_id="thread-001",operation_id="refund-001",tool="refund",
                       arguments={"amount":15},authority={"limit_usd":1500},
                       model={"name":"synthetic-model"},context={"prompt_version":"v1"},
                       policy_id="refund-policy")
    assert not any(e["event_type"]=="tool_requested" for e in core.get_decision(scope["decision_id"])["events"])
