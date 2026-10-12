"""Security and local worker-recovery regressions introduced during final hardening."""
from __future__ import annotations

import multiprocessing as mp
import os
import threading
import time
from pathlib import Path

import pytest

from fakes import FakeCore
from loopgrid_langgraph import (
    LangGraphBridge, EvidenceInvalid, PolicyDenied, ReconciliationRequired,
    LocalSqliteDispatchLease, LeaseUnavailable,
)


def make_scope(bridge, operation_id='hardening-op', amount=15):
    return bridge.propose(
        thread_id='thread-hardening', operation_id=operation_id, tool='refund',
        arguments={'amount': amount}, authority={'limit_usd': 1500},
        model={'name': 'synthetic'}, context={'version': 'v1'}, policy_id='refund-policy')


def run_dispatch(bridge, scope, cb):
    return bridge.dispatch(scope, thread_id='thread-hardening', tool='refund',
                           arguments={'amount': 15}, callback=cb)


def _sqlite_lock_worker(dbpath: str, marker: str, hold: float):
    """Top-level for Windows spawn. Records enter/exit with a shared local file."""
    lease = LocalSqliteDispatchLease(dbpath, timeout=10)
    with lease('lg-langgraph-shared-test-operation'):
        with open(marker, 'a', encoding='ascii') as f:
            f.write('enter\n')
        time.sleep(hold)
        with open(marker, 'a', encoding='ascii') as f:
            f.write('exit\n')


def test_shared_sqlite_lease_serializes_separate_bridge_instances(tmp_path):
    core = FakeCore()
    lease = LocalSqliteDispatchLease((tmp_path / 'dispatch.db').resolve())
    a = LangGraphBridge(core, agent_id='test', dispatch_lease=lease,
                        require_dispatch_lease=True)
    b = LangGraphBridge(core, agent_id='test', dispatch_lease=lease,
                        require_dispatch_lease=True)
    scope = make_scope(a)
    executions, failures = [], []

    def worker(bridge):
        try:
            run_dispatch(bridge, scope, lambda args: (executions.append(1),time.sleep(.03),{'ok':True})[-1])
        except ReconciliationRequired:
            failures.append('replayed')

    t1 = threading.Thread(target=worker, args=(a,))
    t2 = threading.Thread(target=worker, args=(b,))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert executions == [1]
    assert failures == ['replayed']


def test_sqlite_lease_is_exclusive_across_spawned_processes(tmp_path):
    ctx = mp.get_context('spawn')  # same cross-platform isolation on Windows/macOS/Linux
    db = str((tmp_path / 'worker-lease.db').resolve())
    marker = str((tmp_path / 'events.log').resolve())
    jobs = [ctx.Process(target=_sqlite_lock_worker, args=(db, marker, .08)) for _ in range(2)]
    for job in jobs: job.start()
    for job in jobs: job.join(timeout=12)
    try:
        assert all(job.exitcode == 0 for job in jobs), [job.exitcode for job in jobs]
        assert Path(marker).read_text().splitlines() == ['enter','exit','enter','exit']
    finally:
        for job in jobs:
            if job.is_alive(): job.terminate(); job.join()


def test_enforced_lease_cannot_be_skipped():
    with pytest.raises(ValueError, match='durable dispatch lease'):
        LangGraphBridge(FakeCore(), agent_id='test', require_dispatch_lease=True)
    with pytest.raises(ValueError):
        LocalSqliteDispatchLease(':memory:')


def test_lease_acquisition_failure_does_not_execute():
    core = FakeCore()
    def fail_lease(key):
        raise LeaseUnavailable('sandbox lease unavailable')
    bridge = LangGraphBridge(core, agent_id='test', dispatch_lease=fail_lease)
    scope = make_scope(bridge)
    calls = []
    with pytest.raises(LeaseUnavailable): run_dispatch(bridge, scope, lambda a: calls.append(a))
    assert not calls
    assert [e['event_type'] for e in core.get_decision(scope['decision_id'])['events']] == [
        'decision_created','policy_evaluated']


def test_duplicate_tool_reservation_refused_even_if_first_history_looked_clear():
    core = FakeCore()
    bridge = LangGraphBridge(core, agent_id='test')
    scope = make_scope(bridge)
    orig = core.add_event
    def replay(did, kind, payload, **kw):
        if kind == 'tool_requested': return {'idempotent_replay': True}
        return orig(did, kind, payload, **kw)
    core.add_event = replay
    calls = []
    with pytest.raises(ReconciliationRequired, match='already reserved'):
        run_dispatch(bridge, scope, lambda a: calls.append(a))
    assert calls == []


def test_rejection_remains_terminal_even_after_later_approval():
    core = FakeCore()
    bridge = LangGraphBridge(core, agent_id='test')
    scope = make_scope(bridge, amount=750)
    core.review(scope['decision_id'], 'reject', 'host-reviewer')
    core.review(scope['decision_id'], 'approve', 'host-reviewer')
    with pytest.raises(PolicyDenied, match='rejection is final'):
        bridge.dispatch(scope, thread_id='thread-hardening', tool='refund',
                        arguments={'amount':750}, callback=lambda a: True)


def test_native_node_checkpoint_scope_does_not_duplicate_raw_arguments():
    core = FakeCore()
    bridge = LangGraphBridge(core, agent_id='test')
    node = bridge.make_decision_node(
        tool='refund', policy_id='refund-policy',
        arguments=lambda s: {'amount': s['amount'], 'secret': s['private_value']},
        authority=lambda s: {'limit_usd': 1500},
        model=lambda s: {'name': 'synthetic'},
        context=lambda s: {'version': 'v1'}, operation_id=lambda s: 'redacted-op')
    state = {'amount': 15, 'private_value': 'do-not-repeat-in-loopgrid-scope'}
    scope = node(state, {'configurable': {'thread_id':'thread-hardening'}})['loopgrid']
    assert 'tool_arguments' not in scope
    assert 'private_value' not in str(scope)
    assert bridge.dispatch(scope, thread_id='thread-hardening', tool='refund',
        arguments={'amount':15,'secret':'do-not-repeat-in-loopgrid-scope'},
        callback=lambda a:{'ok':True}) == {'ok': True}


def test_async_callback_is_refused_before_tool_reservation():
    core = FakeCore()
    bridge = LangGraphBridge(core, agent_id='test')
    scope = make_scope(bridge)
    async def async_callback(a): return {'ok':True}
    with pytest.raises(TypeError, match='Async tool callbacks'):
        run_dispatch(bridge, scope, async_callback)
    assert not any(e['event_type']=='tool_requested'
                   for e in core.get_decision(scope['decision_id'])['events'])


def test_dispatch_refuses_modified_authority_even_with_same_action_hash():
    core = FakeCore()
    bridge = LangGraphBridge(core, agent_id='test')
    scope = make_scope(bridge)
    scope['authority']['limit_usd'] = 5000
    with pytest.raises(EvidenceInvalid, match='identity, authority or context changed'):
        run_dispatch(bridge, scope, lambda a: True)


def test_dispatch_refuses_cross_agent_scope_hijacking():
    core = FakeCore()
    original = LangGraphBridge(core, agent_id='original-agent')
    scope = make_scope(original)
    other = LangGraphBridge(core, agent_id='different-agent')
    with pytest.raises(EvidenceInvalid, match='identity, authority or context changed'):
        run_dispatch(other, scope, lambda a: True)


def test_same_operation_replay_cannot_swap_signed_model():
    core = FakeCore()
    bridge = LangGraphBridge(core, agent_id='test')
    original = make_scope(bridge)
    with pytest.raises(EvidenceInvalid, match='identity, authority or context changed'):
        bridge.propose(thread_id='thread-hardening', operation_id='hardening-op',
                       tool='refund',arguments={'amount':15},
                       authority={'limit_usd':1500},model={'name':'different-model'},
                       context={'version':'v1'},policy_id='refund-policy')


def test_native_graph_reentry_refuses_model_identity_swap():
    core = FakeCore()
    bridge = LangGraphBridge(core, agent_id='test')
    node = bridge.make_decision_node(
        tool='refund', policy_id='refund-policy',arguments=lambda s:{'amount':15},
        authority=lambda s:{'limit_usd':1500},model=lambda s:{'name':s['model_name']},
        context=lambda s:{'version':'v1'}, operation_id=lambda s:'same')
    config={'configurable':{'thread_id':'thread-hardening'}}
    scope=node({'model_name':'model-A'},config)['loopgrid']
    with pytest.raises(EvidenceInvalid, match='identity, authority or context changed'):
        node({'model_name':'model-B','loopgrid':scope}, config)
