"""Real LangGraph SQLite checkpoint survives graph/checkpointer re-creation.

Synthetic Core only: this is a persistent SDK/runtime test, not a real-Core E2E.
Run `pip install -e '.[test,persistence-test]'` first.
"""
from __future__ import annotations

import copy
import json
import tempfile
import uuid
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langgraph.checkpoint.sqlite import SqliteSaver
from loopgrid_langgraph import LangGraphBridge, ReconciliationRequired, LocalSqliteDispatchLease
from loopgrid_langgraph.integration import commitment


class SyntheticCore:
    workspace_id = 'ws_persistent_sandbox'

    def __init__(self):
        self.events = {}
        self.by_key = {}

    def create_decision(self, payload):
        key = payload['idempotency_key']
        if key in self.by_key:
            return {'decision_id': self.by_key[key], 'idempotent_replay': True}
        did = 'dec_' + uuid.uuid4().hex[:24]
        self.by_key[key] = did
        self.events[did] = [
            {'event_type':'decision_created','payload':copy.deepcopy(payload)}]
        return {'decision_id': did}

    def add_event(self, did, kind, payload, **kwargs):
        self.events[did].append({'event_type': kind, 'payload': copy.deepcopy(payload)})
        return {'event_type': kind}

    def evaluate_policy(self, policy_id, action, authority, context):
        return {'policy_id':policy_id,'version':'sandbox-v1',
                'policy_digest':'sandbox-digest',
                'input_commitment':commitment([action,authority,context]),
                'decision':'human_approval_required'}

    def get_decision(self, did):
        return {'summary':{'workspace_id':self.workspace_id},
                'events':copy.deepcopy(self.events[did])}

    def verify_workspace(self):
        return {'valid':True,'workspace_id':self.workspace_id,'failures':[]}

    def approve(self, did):
        self.add_event(did, 'human_approved', {'approved':True, 'reviewer':'synthetic-host'})


class State(TypedDict, total=False):
    amount: int
    operation_id: str
    loopgrid: dict
    loopgrid_tool_result: dict


def compiled(core, lock, calls, saver):
    # Mimic a process restart by rebuilding the whole bridge and graph.
    bridge = LangGraphBridge(core, agent_id='persistent-test',
                             dispatch_lease=lock, require_dispatch_lease=True)
    def args(s): return {'amount':s['amount']}
    def callback(arg):
        calls.append(arg['amount'])
        return {'synthetic_refund':True, 'amount':arg['amount']}
    graph = StateGraph(State)
    graph.add_node('propose', bridge.make_decision_node(
        tool='refund', policy_id='refund-policy', arguments=args,
        authority=lambda s:{'limit_usd':1500},model=lambda s:{'name':'synthetic'},
        context=lambda s:{'prompt_version':'v1'},operation_id=lambda s:s['operation_id']))
    graph.add_node('execute', bridge.make_guarded_node(
        tool='refund', arguments=args, callback=callback))
    graph.add_edge(START,'propose')
    graph.add_edge('propose','execute')
    graph.add_edge('execute',END)
    return graph.compile(checkpointer=saver), bridge


def main():
    core = SyntheticCore()
    calls = []
    config = {'configurable':{'thread_id':'thread-persistent-' + uuid.uuid4().hex[:8]}}
    with tempfile.TemporaryDirectory(prefix='loopgrid-lg-persistent-') as root:
        checkpoint_file = str(Path(root, 'checkpoint.sqlite'))
        lock = LocalSqliteDispatchLease(Path(root,'worker-dispatch.sqlite').resolve())
        with SqliteSaver.from_conn_string(checkpoint_file) as saver:
            graph, _ = compiled(core, lock, calls, saver)
            interrupted = graph.invoke({'amount':750,'operation_id':'op-persistent'}, config=config)
            assert '__interrupt__' in interrupted
            state = graph.get_state(config).values
            assert state['loopgrid']['policy']['decision'] == 'human_approval_required'
            assert 'tool_arguments' not in state['loopgrid']
            assert not calls
            did = state['loopgrid']['decision_id']
        # The checkpoint database has been closed; construct a new saver and graph.
        # `Command(resume=...)` is not approval; signed Core review must exist.
        core.approve(did)
        with SqliteSaver.from_conn_string(checkpoint_file) as saver:
            graph, bridge = compiled(core, lock, calls, saver)
            final = graph.invoke(Command(resume='untrusted-continue'), config=config)
            assert final['loopgrid_tool_result']['amount'] == 750
            assert calls == [750]
        # After another graph restart, replaying the same signed scope must fail.
        with SqliteSaver.from_conn_string(checkpoint_file) as saver:
            graph, bridge = compiled(core, lock, calls, saver)
            recovered = graph.get_state(config).values
            assert recovered['loopgrid']['decision_id'] == did
            try:
                bridge.dispatch(recovered['loopgrid'], thread_id=config['configurable']['thread_id'],
                                tool='refund',arguments={'amount':750},
                                callback=lambda a:calls.append(a['amount']))
            except ReconciliationRequired:
                pass
            else:
                raise AssertionError('External action replayed after persisted restart')
            assert calls == [750]
    print('PASS: REAL LangGraph SqliteSaver persisted interrupt/restart/resume, signed synthetic review and no replay')
    print(json.dumps({'synthetic_core':True, 'restarts':2, 'sandbox_tool_calls':len(calls),
                      'checkpoint_duplicated_arguments':False},indent=2))


if __name__ == '__main__': main()
