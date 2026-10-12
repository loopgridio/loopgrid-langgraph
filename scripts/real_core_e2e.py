"""Opt-in disposable-workspace LoopGrid Core E2E (no live business actions).

Run against LOCAL Core only. Requires admin rights to create the disposable workspace
and issue a scoped test service key. Tested on Core 0.8.1-design-partner.
"""
from __future__ import annotations
import os, json, sys, uuid
from urllib.parse import urlsplit
import httpx

from loopgrid_langgraph import CoreClient, LangGraphBridge, PolicyDenied, ApprovalRequired, ReconciliationRequired

base=os.environ.get('LOOPGRID_BASE_URL','http://127.0.0.1:8000').rstrip('/')
if base not in ('http://127.0.0.1:8000','http://localhost:8000') and os.environ.get('LOOPGRID_ALLOW_TEST_ORIGIN')!='YES':
    raise SystemExit('E2E runs on localhost:8000 by default; other origins require explicit LOOPGRID_ALLOW_TEST_ORIGIN=YES')
admin=os.environ.get('LOOPGRID_ADMIN_KEY') or os.environ.get('LOOPGRID_API_KEY')
headers={'X-LoopGrid-Key':admin} if admin else {}

def request(method, path, body=None):
    try:
        with httpx.Client(base_url=base,headers=headers,timeout=12,follow_redirects=False,trust_env=False) as http:
            r=http.request(method,path,json=body)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f'Core sandbox setup failed (no response contents): {type(e).__name__}') from None

ready=request('GET','/ready')
if ready.get('ready') is not True:
    raise SystemExit('Core not ready')
workspace=request('POST','/api/v1/workspaces',{'name':'LangGraph isolated e2e '+uuid.uuid4().hex[:8], 'environment':'development','privacy_mode':'redacted'})
wid=workspace['workspace_id']
policy_id='langgraph-refund-test'
policy=request('POST',f'/api/v1/workspaces/{wid}/policies',{
    'policy_id':policy_id,'name':'Synthetic refund policy', 'version':'17.3', 'active':True,
    'rule':{'type':'amount_threshold','field':'amount','auto_approve_max':500,'hard_limit':1500,'currency':'USD'}})
issued=request('POST',f'/api/v1/workspaces/{wid}/keys',{'name':'LangGraph isolated E2E', 'scopes':['ingest','read','review']})
client=CoreClient(base_url=base,workspace_id=wid,service_key=issued['api_key'])
bridge=LangGraphBridge(client,agent_id='synthetic-langgraph-agent')
executions=[]

def start(amount,operation):
    return bridge.propose(thread_id='thread-test-'+operation,operation_id=operation,tool='refund',
        arguments={'amount':amount,'currency':'USD'},authority={'limit_usd':1500},
        model={'name':'synthetic-rule-agent'},context={'prompt_version':'synthetic-v1'},policy_id=policy_id)

def execute(s,operation):
    def callback(args):
        executions.append({'operation':operation,'arguments':args})
        return {'kind':'synthetic_receipt','operation':operation}
    return bridge.dispatch(s,thread_id='thread-test-'+operation,tool='refund',arguments=s['tool_arguments'],callback=callback)

allowed=start(15,'allow')
bridge.observed_model(allowed['decision_id'],model_name='synthetic-rule-agent',output={'proposed_amount':15},source='sandbox.simulated_model')
execute(allowed,'allow')
bridge.record_outcome(allowed['decision_id'],external_reference='sandbox-allow',status='confirmed',source='sandbox-authoritative-observer',observed={'no_money_moved':True})
blocked=start(2001,'block')
try:execute(blocked,'block');raise AssertionError('Blocked decision dispatched')
except PolicyDenied:pass
reviewed=start(750,'review')
try:execute(reviewed,'review');raise AssertionError('Unapproved decision dispatched')
except ApprovalRequired:pass
client.review(reviewed['decision_id'],'approve','isolated-sandbox-reviewer','sandbox authorization only')
execute(reviewed,'review')
bridge.record_outcome(reviewed['decision_id'],external_reference='sandbox-review',status='confirmed',source='sandbox-authoritative-observer',observed={'no_money_moved':True})
rejected=start(800,'reject')
client.review(rejected['decision_id'],'reject','isolated-sandbox-reviewer','sandbox reject')
try:execute(rejected,'reject');raise AssertionError('Rejected decision dispatched')
except PolicyDenied:pass
try:execute(allowed,'allow');raise AssertionError('Already completed decision replayed')
except ReconciliationRequired:pass
proof=client.verify_workspace()
assert proof['valid'] is True and not proof.get('failures')
assert [e['operation'] for e in executions]==['allow','review']
for recorded in (allowed, reviewed):
    detail = client.get_decision(recorded['decision_id'])
    assert detail['summary']['lifecycle']['state'] == 'evidence_complete',detail
    assert detail['coverage']['score'] == 100 and detail['coverage']['complete'],detail
assert all(e['arguments']['amount'] in (15,750) for e in executions)
result={
    'profile':'LoopGrid LangGraph v0.1.0 adapter (no real LangGraph SDK invoked)',
    'core_version':ready.get('version'), 'workspace_id':wid,
    'decisions':{name:obj['decision_id'] for name,obj in [('allowed',allowed),('blocked',blocked),('human_approved',reviewed),('rejected',rejected)]},
    'signed_workspace_verification':proof.get('valid'), 'failures':proof.get('failures'),
    'sandbox_executions':len(executions),'real_money_moved':False,
    'successful_decisions_lifecycle':'evidence_complete', 'applicable_coverage':100,
    'framework_runtime_test':'separate scripts/langgraph_runtime_e2e.py required'}
print(json.dumps(result,indent=2))
client.close()
