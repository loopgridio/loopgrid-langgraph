"""Opt-in installed LangGraph StateGraph + real disposable LoopGrid Core E2E.

Uses the local Core, provisions an isolated workspace. No model keys or real payments.
"""
from __future__ import annotations
import os, json, uuid
import httpx

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver
from typing import TypedDict
from loopgrid_langgraph import CoreClient, LangGraphBridge, PolicyDenied, ReconciliationRequired

base=os.environ.get('LOOPGRID_BASE_URL','http://127.0.0.1:8000').rstrip('/')
if base not in ('http://127.0.0.1:8000','http://localhost:8000') and os.environ.get('LOOPGRID_ALLOW_TEST_ORIGIN')!='YES':
    raise SystemExit('Run against local Core only; remote test requires explicit LOOPGRID_ALLOW_TEST_ORIGIN=YES')
admin=os.environ.get('LOOPGRID_ADMIN_KEY') or os.environ.get('LOOPGRID_API_KEY')
headers={'X-LoopGrid-Key':admin} if admin else {}
def post(path,data):
    try:
        with httpx.Client(base_url=base,headers=headers,timeout=12,trust_env=False,follow_redirects=False) as h:
            r=h.post(path,json=data);r.raise_for_status();return r.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f'Core test workspace provisioning failed: {type(e).__name__}') from None

ws=post('/api/v1/workspaces',{'name':'LangGraph native test '+uuid.uuid4().hex[:6],
                                 'environment':'development','privacy_mode':'redacted'})['workspace_id']
policy='native-langgraph-policy'
post(f'/api/v1/workspaces/{ws}/policies',{'policy_id':policy,'name':'Native graph sandbox policy',
   'version':'17.3','active':True,'rule':{'type':'amount_threshold','field':'amount',
                                      'auto_approve_max':500,'hard_limit':1500,'currency':'USD'}})
key=post(f'/api/v1/workspaces/{ws}/keys',{'name':'LangGraph native E2E',
                                         'scopes':['ingest','read','review']})['api_key']
client=CoreClient(base_url=base,workspace_id=ws,service_key=key)
bridge=LangGraphBridge(client,agent_id='native-langgraph-sandbox')
class State(TypedDict,total=False):
    amount:int
    operation_id:str
    loopgrid:dict
    loopgrid_tool_result:dict
    loopgrid_verification:dict
calls=[]
def params(state):return {'amount':state['amount'],'currency':'USD'}
proposal=bridge.make_decision_node(tool='refund',policy_id=policy,arguments=params,
     authority=lambda s:{'limit_usd':1500},model=lambda s:{'name':'synthetic-host-model'},
     context=lambda s:{'prompt_version':'sandbox-v1'},operation_id=lambda s:s['operation_id'])
guard=bridge.make_guarded_node(tool='refund',arguments=params,
     callback=lambda args:(calls.append(args),{'sandbox_receipt':True,'amount':args['amount']})[1])
builder=StateGraph(State)
builder.add_node('propose',proposal);builder.add_node('execute',guard)
builder.add_node('verify',bridge.make_verify_node())
builder.add_edge(START,'propose');builder.add_edge('propose','execute')
builder.add_edge('execute','verify');builder.add_edge('verify',END)
graph=builder.compile(checkpointer=InMemorySaver())

# Pure sandbox automatic allow.
a_cfg={'configurable':{'thread_id':'thread-langgraph-allow-'+uuid.uuid4().hex[:8]}}
a=graph.invoke({'amount':15,'operation_id':'allow-'+uuid.uuid4().hex[:8]},a_cfg)
assert a['loopgrid_tool_result']['sandbox_receipt'] is True
bridge.record_outcome(a['loopgrid']['decision_id'],external_reference='sandbox-allow',status='confirmed',
                      source='sandbox-downstream-observer',observed={'no_real_money':True})

# Interrupt must happen BEFORE action; resume is not authority. Actual Core review is.
r_cfg={'configurable':{'thread_id':'thread-langgraph-review-'+uuid.uuid4().hex[:8]}}
paused=graph.invoke({'amount':750,'operation_id':'review-'+uuid.uuid4().hex[:8]},r_cfg)
assert '__interrupt__' in paused and len(calls)==1,paused
s=graph.get_state(r_cfg).values
client.review(s['loopgrid']['decision_id'],'approve','synthetic-host-reviewer','sandbox approval')
resumed=graph.invoke(Command(resume='resume'),r_cfg)
assert resumed['loopgrid_tool_result']['amount']==750 and len(calls)==2
bridge.record_outcome(s['loopgrid']['decision_id'],external_reference='sandbox-review',status='confirmed',
                      source='sandbox-downstream-observer',observed={'no_real_money':True})
# Replaying same scope refuses dispatch.
try:
    bridge.dispatch(s['loopgrid'],thread_id=r_cfg['configurable']['thread_id'],tool='refund',
        arguments=params(s),callback=lambda args:calls.append(args))
    raise AssertionError('Duplicate executed')
except ReconciliationRequired:
    pass

# Blocked policy must never dispatch.
b_cfg={'configurable':{'thread_id':'thread-langgraph-block-'+uuid.uuid4().hex[:8]}}
try:
    graph.invoke({'amount':2500,'operation_id':'block-'+uuid.uuid4().hex[:8]},b_cfg)
    raise AssertionError('Policy denied action dispatched')
except PolicyDenied:
    pass
for recorded_id in (a['loopgrid']['decision_id'], s['loopgrid']['decision_id']):
    detail = client.get_decision(recorded_id)
    assert detail['summary']['lifecycle']['state'] == 'evidence_complete',detail
    assert detail['coverage']['score'] == 100 and detail['coverage']['complete'],detail
proof=client.verify_workspace()
assert proof.get('valid') is True and not proof.get('failures') and len(calls)==2
print('PASS: REAL installed LangGraph StateGraph + local LoopGrid Core, policy, signed human review, interrupt/resume and replay protection')
print(json.dumps({'workspace_id':ws,'allowed_decision_id':a['loopgrid']['decision_id'],
   'approved_decision_id':s['loopgrid']['decision_id'],
   'signed_workspace_verification':proof['valid'],'failures':proof['failures'],
   'sandbox_executions':len(calls),'real_money_moved':False,
   'successful_decisions_lifecycle':'evidence_complete','applicable_coverage':100},indent=2))
client.close()
