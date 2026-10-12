"""Cross-platform regressions for Core REST routing, fail-closed leases and graph verification.

These deliberately exercise security-relevant paths not covered by the standard
success-path E2Es; CI coverage must not depend on the Python/OS version.
"""
from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from fakes import FakeCore
from loopgrid_langgraph import (
    CoreClient, EvidenceInvalid, LangGraphBridge,
    LeaseUnavailable, LocalSqliteDispatchLease, validate_origin,
)


def test_core_origin_rejects_non_string_input():
    with pytest.raises(ValueError, match="must be a string"):
        validate_origin(None)


def test_core_client_signed_evidence_routes_and_payloads():
    """Ensure review/policy/evidence requests use the intended endpoints and scope."""
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.method, request.url.path, request.url.query.decode(),
                         json.loads(request.content) if request.content else None))
        return httpx.Response(200, json={"valid": True})

    client = CoreClient(base_url="https://core.example.invalid", workspace_id="ws_test",
                        transport=httpx.MockTransport(handler))
    try:
        client.add_event("dec_test", "model_completed", {"sha256": "test"},
                         idempotency_key="idem_test")
        client.evaluate_policy("policy_test", {"tool": "refund", "amount": 15},
                               {"role": "operator"}, {"environment": "test"})
        client.get_decision("dec_test")
        client.verify_workspace()
        client.review("dec_test", "approve", "authenticated-reviewer", "test approved")
    finally:
        client.close()

    assert [(method, path) for method, path, _, _ in captured] == [
        ("POST", "/api/v1/decisions/dec_test/events"),
        ("POST", "/api/v1/workspaces/ws_test/policies/evaluate"),
        ("GET", "/api/v1/decisions/dec_test"),
        ("GET", "/api/v1/integrity/verify"),
        ("POST", "/api/v1/decisions/dec_test/review"),
    ]
    assert captured[0][3]["idempotency_key"] == "idem_test"
    assert captured[1][3]["policy_id"] == "policy_test"
    assert captured[3][2] == "workspace_id=ws_test"
    assert captured[4][3] == {"action": "approve", "reviewer": "authenticated-reviewer",
                              "reason": "test approved"}


@pytest.mark.parametrize("action, reviewer", [
    ("delete", "authenticated-reviewer"),
    ("approve", ""),
    ("reject", ""),
])
def test_core_client_never_sends_unapproved_review_action(action, reviewer):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json={"ok": True})

    client = CoreClient(base_url="https://core.example.invalid", workspace_id="ws_test",
                        transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="Explicit authenticated review required"):
            client.review("dec_test", action, reviewer)
        assert sent == []
    finally:
        client.close()


def test_lease_rejects_bad_timeout_and_operation_key(tmp_path):
    db = (tmp_path / "leases.db").resolve()
    for timeout in (0, -1, 61):
        with pytest.raises(ValueError, match="Invalid SQLite lock timeout"):
            LocalSqliteDispatchLease(db, timeout=timeout)
    lease = LocalSqliteDispatchLease(db)
    with pytest.raises(ValueError, match="Invalid dispatch operation key"):
        with lease("not-a-langgraph-operation"):
            pytest.fail("Lease should never be entered")


def test_locked_sqlite_dispatch_lease_fails_closed(tmp_path):
    """A second worker cannot enter while an independent writer holds the lock."""
    db = str((tmp_path / "shared-lease.db").resolve())
    owner = sqlite3.connect(db, isolation_level=None)
    try:
        owner.execute("BEGIN IMMEDIATE")
        contender = LocalSqliteDispatchLease(db, timeout=0.05)
        with pytest.raises(LeaseUnavailable, match="lease unavailable"):
            with contender("lg-langgraph-lock-contention"):
                pytest.fail("An already-held write lock must not permit dispatch")
    finally:
        owner.rollback()
        owner.close()
    # A released lock is usable again; the failure must not leave it poisoned.
    with LocalSqliteDispatchLease(db)("lg-langgraph-lock-contention"):
        pass


def test_bridge_rejects_noncallable_dispatch_lease():
    with pytest.raises(TypeError, match="context-manager factory"):
        LangGraphBridge(FakeCore(), agent_id="test-agent", dispatch_lease=object())


def test_signed_decision_must_match_workspace_before_tool_dispatch():
    core = FakeCore()
    bridge = LangGraphBridge(core, agent_id="test-agent")
    scope = bridge.propose(thread_id="thread-001", operation_id="op-001", tool="refund",
                           arguments={"amount": 15}, authority={"limit_usd": 1500},
                           model={"name": "synthetic"}, context={"version": "v1"},
                           policy_id="refund-policy")
    core.decisions[scope["decision_id"]]["summary"]["workspace_id"] = "ws_other"
    side_effects = []
    with pytest.raises(EvidenceInvalid, match="different workspace"):
        bridge.dispatch(scope, thread_id="thread-001", tool="refund",
                        arguments={"amount": 15}, callback=lambda args: side_effects.append(args))
    assert not side_effects


def test_native_verify_node_refuses_invalid_signed_workspace():
    core = FakeCore()
    bridge = LangGraphBridge(core, agent_id="test-agent")
    verify_node = bridge.make_verify_node()
    config = {"configurable": {"thread_id": "thread-001"}}
    good = verify_node({}, config)["loopgrid_verification"]
    assert good["valid"] is True
    core.proof = False
    with pytest.raises(EvidenceInvalid, match="signature verification failed"):
        verify_node({}, config)


def test_proposal_refuses_missing_policy_provenance_before_dispatch():
    core = FakeCore()
    original = core.evaluate_policy

    def bad_policy(*args):
        response = original(*args)
        response.pop("policy_digest")
        return response

    core.evaluate_policy = bad_policy
    bridge = LangGraphBridge(core, agent_id="test-agent")
    with pytest.raises(EvidenceInvalid, match="missing signed provenance"):
        bridge.propose(thread_id="thread-001", operation_id="op-001", tool="refund",
                       arguments={"amount": 15}, authority={"limit_usd": 1500},
                       model={"name": "synthetic"}, context={"version": "v1"},
                       policy_id="refund-policy")
    assert all(kind != "tool_requested" for kind, _ in core.calls)


def test_proposal_refuses_untrusted_policy_identity():
    core = FakeCore()
    original = core.evaluate_policy

    def wrong_policy(*args):
        response = original(*args)
        response["policy_id"] = "wrong-policy"
        return response

    core.evaluate_policy = wrong_policy
    bridge = LangGraphBridge(core, agent_id="test-agent")
    with pytest.raises(EvidenceInvalid, match="Policy response failed provenance"):
        bridge.propose(thread_id="thread-001", operation_id="op-001", tool="refund",
                       arguments={"amount": 15}, authority={"limit_usd": 1500},
                       model={"name": "synthetic"}, context={"version": "v1"},
                       policy_id="refund-policy")
    assert all(kind != "tool_requested" for kind, _ in core.calls)
