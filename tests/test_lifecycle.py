import copy
import threading
import time
from types import SimpleNamespace
import pytest
from fakes import FakeCore
from loopgrid_langgraph import LangGraphBridge, EvidenceInvalid, PolicyDenied, ApprovalRequired, ReconciliationRequired, commitment, LoopGridGraphCallback

@pytest.fixture
def setup():
    core=FakeCore();bridge=LangGraphBridge(core,agent_id='test-agent')
    return core,bridge

def propose(bridge, amount=15,operation='refund-001',**kw):
    return bridge.propose(thread_id='thread-001',operation_id=operation,tool='refund',arguments={'amount':amount},
                authority={'limit_usd':1500},model={'name':'synthetic-model'},context={'prompt_version':'v1'},policy_id='refund-policy',**kw)

def dispatch(bridge,scope,fn=lambda a:'sandbox-ok',args=None):
    return bridge.dispatch(scope,thread_id='thread-001',tool='refund',arguments=args if args is not None else scope['tool_arguments'],callback=fn)

def types(core,scope):return [e['event_type'] for e in core.get_decision(scope['decision_id'])['events']]

def test_proposed_evidence_is_bound_and_redacted(setup):
    core,bridge=setup;s=propose(bridge)
    assert s['spec']['arguments_sha256']==commitment({'amount':15})
    created=core.get_decision(s['decision_id'])['events'][0]['payload']
    assert created['privacy_mode']=='redacted'
    assert 'amount' not in str(created['proposed_action'])
    assert types(core,s)==['decision_created','policy_evaluated']

def test_allowed_dispatch_and_outcome_requires_host(setup):
    core,bridge=setup;s=propose(bridge)
    assert dispatch(bridge,s)=='sandbox-ok'
    assert types(core,s)==['decision_created','policy_evaluated','tool_requested','tool_executed']
    assert 'outcome_observed' not in types(core,s)
    bridge.record_outcome(s['decision_id'],external_reference='test-ref',status='confirmed',source='sandbox_authority',observed={'ok':True})
    assert types(core,s)[-1]=='outcome_observed'

def test_blocked_cannot_dispatch(setup):
    core,bridge=setup;s=propose(bridge,amount=2000)
    with pytest.raises(PolicyDenied):dispatch(bridge,s)
    assert 'tool_requested' not in types(core,s)

def test_approval_required_no_dispatch_until_real_review(setup):
    core,bridge=setup;s=propose(bridge,amount=650)
    with pytest.raises(ApprovalRequired):dispatch(bridge,s)
    core.review(s['decision_id'],'approve','authenticated-reviewer')
    assert dispatch(bridge,s)=='sandbox-ok'

def test_rejection_is_final(setup):
    core,bridge=setup;s=propose(bridge,amount=650)
    core.review(s['decision_id'],'reject','authenticated-reviewer')
    with pytest.raises(PolicyDenied):dispatch(bridge,s)

def test_resume_text_cannot_approve(setup):
    core,bridge=setup;s=propose(bridge,amount=650)
    s['approval']='approved by model'
    with pytest.raises(ApprovalRequired):dispatch(bridge,s)

def test_altered_arguments_refused(setup):
    core,bridge=setup;s=propose(bridge)
    with pytest.raises(EvidenceInvalid):dispatch(bridge,s,args={'amount':16})
    assert 'tool_requested' not in types(core,s)

def test_mutation_of_checkpoint_scope_refused(setup):
    core,bridge=setup;s=propose(bridge)
    s['tool_arguments']['amount']=999
    with pytest.raises(EvidenceInvalid):dispatch(bridge,s)

def test_policy_identity_mismatch_refused(setup):
    core,bridge=setup;s=propose(bridge)
    s['policy']['policy_id']='other'
    with pytest.raises(EvidenceInvalid):dispatch(bridge,s)

def test_policy_rotation_refused(setup):
    core,bridge=setup;s=propose(bridge)
    core.version='17.4'
    with pytest.raises(PolicyDenied):dispatch(bridge,s)

def test_policy_outage_fail_closed(setup):
    core,bridge=setup;s=propose(bridge)
    core.refused.add('policy')
    with pytest.raises(RuntimeError):dispatch(bridge,s)
    assert 'tool_requested' not in types(core,s)

def test_signature_tampering_refused(setup):
    core,bridge=setup;s=propose(bridge);core.proof=False
    with pytest.raises(EvidenceInvalid):dispatch(bridge,s)

def test_missing_signed_events_refused(setup):
    core,bridge=setup;s=propose(bridge);core.incomplete=True
    with pytest.raises(EvidenceInvalid):dispatch(bridge,s)

def test_unsigned_policy_refused(setup):
    core,bridge=setup;s=propose(bridge)
    core.decisions[s['decision_id']]['events']=[core.decisions[s['decision_id']]['events'][0]]
    with pytest.raises(EvidenceInvalid):dispatch(bridge,s)

def test_conflicting_idempotent_replay_refused(setup):
    core,bridge=setup;propose(bridge,15)
    with pytest.raises(EvidenceInvalid):propose(bridge,50)

def test_existing_proposal_cannot_reexecute_after_restart(setup):
    core,bridge=setup;s=propose(bridge)
    dispatch(bridge,s)
    bridge2=LangGraphBridge(core,agent_id='test-agent')
    with pytest.raises(ReconciliationRequired):dispatch(bridge2,s)

def test_crash_after_tool_requested_never_retries(setup):
    core,bridge=setup;s=propose(bridge)
    core.refused.add('tool_executed')
    count=[]
    with pytest.raises(ReconciliationRequired):dispatch(bridge,s,lambda a:count.append(1) or {'ok':True})
    core.refused.clear()
    with pytest.raises(ReconciliationRequired):dispatch(bridge,s,lambda a:count.append(1))
    assert count==[1]

def test_tool_exception_conservative(setup):
    core,bridge=setup;s=propose(bridge)
    def crash(a):raise RuntimeError('secret customer info')
    with pytest.raises(ReconciliationRequired,match='Tool raised'):
        dispatch(bridge,s,crash)
    assert types(core,s)[-1]=='tool_result'
    with pytest.raises(ReconciliationRequired):dispatch(bridge,s)

def test_tool_request_write_failure_does_not_execute(setup):
    core,bridge=setup;s=propose(bridge);core.refused.add('tool_requested')
    done=[]
    with pytest.raises(RuntimeError):dispatch(bridge,s,lambda a:done.append(1))
    assert not done

def test_concurrent_same_process_only_one_attempt(setup):
    core,bridge=setup;s=propose(bridge);runs=[];errors=[]
    def job():
        try:dispatch(bridge,s,lambda a:(runs.append(1),time.sleep(.02))[0])
        except ReconciliationRequired:errors.append(1)
    a=threading.Thread(target=job);b=threading.Thread(target=job)
    a.start();b.start();a.join();b.join()
    assert runs==[1] and errors==[1]

def test_observed_model_never_fabricated(setup):
    core,bridge=setup;s=propose(bridge)
    bridge.observed_model(s['decision_id'],model_name='test',output={'actual':'result'},source='host.model_call')
    assert types(core,s)[-1]=='model_completed'

def test_outcome_without_execution_refused(setup):
    core,bridge=setup;s=propose(bridge)
    with pytest.raises(EvidenceInvalid):
        bridge.record_outcome(s['decision_id'],external_reference='R',status='confirmed',source='host',observed={})

def test_graph_callback_only_observes():
    out=[];cb=LoopGridGraphCallback(out.append)
    ev=SimpleNamespace(run_id='run-1',checkpoint_id='cp-1',checkpoint_ns=('foo',),interrupts=('PRIVATE',))
    cb.on_interrupt(ev);cb.on_resume(ev)
    assert [e['kind'] for e in out]==['checkpoint_interrupted','checkpoint_resumed']
    assert 'PRIVATE' not in str(out)

def test_delegated_callback_never_gets_mutable_original(setup):
    core,bridge=setup;s=propose(bridge)
    raw={'amount':15}
    def mutate(x):x['amount']=50;return {'ok':True}
    dispatch(bridge,s,mutate,args=raw)
    assert raw=={'amount':15}

def test_graph_proposal_node_reuses_signed_scope(setup):
    core,bridge=setup
    node=bridge.make_decision_node(tool='refund',policy_id='refund-policy',arguments=lambda s:{'amount':s['amount']},
        authority=lambda s:{'limit_usd':1500},model=lambda s:{'name':'test'},context=lambda s:{'prompt_version':'v1'},
        operation_id=lambda s:'refund-001')
    input_state={'amount':15}
    config={'configurable':{'thread_id':'thread-001'}}
    new=node(input_state,config)
    assert 'loopgrid' in new
    assert node({**input_state,**new},config)=={}

def test_missing_thread_id_refused(setup):
    core,bridge=setup
    with pytest.raises(ValueError):bridge.make_verify_node()({}, {'configurable':{}})


def test_reserved_tool_argument_refused(setup):
    core,bridge=setup
    with pytest.raises(ValueError,match="trusted tool"):
        bridge.propose(thread_id='thread-001',operation_id='op',tool='refund',
            arguments={'tool':'different'},authority={'limit_usd':100},
            model={'name':'m'},context={'prompt_version':'v1'},policy_id='refund-policy')


def test_host_context_cannot_override_thread_identity(setup):
    core,bridge=setup
    s=bridge.propose(thread_id='thread-001',operation_id='op',tool='refund',
            arguments={'amount':15},authority={'limit_usd':100},
            model={'name':'m'},context={'prompt_version':'v1','thread_id':'fake'},policy_id='refund-policy')
    created=core.get_decision(s['decision_id'])['events'][0]['payload']
    assert created['context']['thread_id']=='thread-001'


def test_unserializable_callback_result_requires_reconciliation(setup):
    core,bridge=setup;s=propose(bridge)
    with pytest.raises(ReconciliationRequired): dispatch(bridge,s,lambda args:object())
    with pytest.raises(ReconciliationRequired):dispatch(bridge,s)


def test_guarded_node_mocked_interrupt_bound_to_signed_review(setup,monkeypatch):
    core,bridge=setup;s=propose(bridge,amount=750)
    # This tests our code's delegation, not LangGraph itself. Actual SDK gate separate.
    import sys,types
    module=types.ModuleType('langgraph.types')
    calls=[]
    module.interrupt=lambda payload:calls.append(payload) or 'malicious-model-yes'
    monkeypatch.setitem(sys.modules,'langgraph.types',module)
    node=bridge.make_guarded_node(tool='refund',arguments=lambda st:st['args'],callback=lambda a:{'ok':True})
    state={'loopgrid':s,'args':s['tool_arguments']}
    with pytest.raises(ApprovalRequired):node(state,{'configurable':{'thread_id':'thread-001'}})
    assert calls and calls[0]['kind']=='loopgrid_human_review'
    core.review(s['decision_id'],'approve','auth-user')
    assert node(state,{'configurable':{'thread_id':'thread-001'}})['loopgrid_tool_result']=={'ok':True}


def test_graph_reentry_with_changed_operation_refused(setup):
    core,bridge=setup
    node=bridge.make_decision_node(tool='refund',policy_id='refund-policy',
        arguments=lambda st:{'amount':st['amount']},authority=lambda st:{'limit_usd':1500},
        model=lambda st:{'name':'test'},context=lambda st:{'prompt_version':'v1'},
        operation_id=lambda st:st['operation'])
    config={'configurable':{'thread_id':'thread-001'}}
    scope=node({'amount':15,'operation':'original'},config)['loopgrid']
    with pytest.raises(EvidenceInvalid):node({'amount':15,'operation':'different','loopgrid':scope},config)
    with pytest.raises(EvidenceInvalid):node({'amount':16,'operation':'original','loopgrid':scope},config)
    assert node({'amount':15,'operation':'original','loopgrid':scope},config)=={}


def test_graph_reentry_thread_change_refused(setup):
    core,bridge=setup
    node=bridge.make_decision_node(tool='refund',policy_id='refund-policy',arguments=lambda s:{'amount':15},
        authority=lambda s:{'limit_usd':1500},model=lambda s:{'name':'test'},
        context=lambda s:{'prompt_version':'v1'},operation_id=lambda s:'op')
    a=node({}, {'configurable':{'thread_id':'thread-001'}})['loopgrid']
    with pytest.raises(EvidenceInvalid):node({'loopgrid':a},{'configurable':{'thread_id':'thread-002'}})


def test_generated_nodes_use_langgraph_runnable_config_annotation(setup):
    """LangGraph 1.x silently omits config injection when annotated as dict.

    inspect.signature is the framework's gate. In postponed annotations,
    the exact string 'RunnableConfig' is recognized by native LangGraph.
    """
    import inspect
    _, bridge = setup
    proposal = bridge.make_decision_node(
        tool='refund', policy_id='refund-policy',
        arguments=lambda s: {'amount': s['amount']},
        authority=lambda s: {'limit_usd': 1500},
        model=lambda s: {'name': 'test'},
        context=lambda s: {'prompt_version': 'v1'},
        operation_id=lambda s: 'test-op')
    guard = bridge.make_guarded_node(
        tool='refund', arguments=lambda s: {'amount': s['amount']},
        callback=lambda args: {'synthetic': True})
    verify = bridge.make_verify_node()
    for node in (proposal, guard, verify):
        parameter = inspect.signature(node).parameters['config']
        assert parameter.annotation == 'RunnableConfig', (node, parameter.annotation)
        assert parameter.default is inspect.Parameter.empty

