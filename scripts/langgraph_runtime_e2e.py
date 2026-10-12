"""True installed LangGraph native node+checkpoint/interrupt/resume test.

Purely synthetic Core transport: tests installed LangGraph runtime, not real Core.
Run in separate step from scripts/real_core_e2e.py.
"""
from __future__ import annotations
import sys,json
from typing import Any, TypedDict
try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command
except ImportError:
    sys.exit('Missing LangGraph. Install: pip install langgraph==1.2.14')
from loopgrid_langgraph import LangGraphBridge, LoopGridGraphCallback, ReconciliationRequired

# Minimal in-memory Core simulator; does not assert real-Core compatibility.
import uuid,copy
class SandboxCore:
    workspace_id='ws_langgraph_sdk'
    def __init__(self):self.d={};self.used={};self.reviewed=[]
    def create_decision(self,p):
        key=p['idempotency_key']
        if key in self.used:return {'decision_id':self.used[key], 'idempotent_replay':True}
        did='dec_'+uuid.uuid4().hex[:24];self.used[key]=did
        self.d[did]={'summary':{'workspace_id':self.workspace_id},'events':[{'event_type':'decision_created','payload':copy.deepcopy(p)}]}
        return {'decision_id':did}
    def add_event(self,did,kind,p,**kw):
        self.d[did]['events'].append({'event_type':kind,'payload':copy.deepcopy(p)})
        return {'event_type':kind}
    def evaluate_policy(self,pid,action,auth,ctx):
        from loopgrid_langgraph.integration import commitment
        return {'policy_id':pid,'version':'1.0','policy_digest':'sandbox-digest','input_commitment':commitment([action,auth,ctx]),
                'decision':'human_approval_required' if action.get('amount',0)>500 else 'auto_allowed'}
    def get_decision(self,did):return copy.deepcopy(self.d[did])
    def verify_workspace(self):return {'valid':True,'failures':[],'workspace_id':self.workspace_id}
    def review(self,did,action,reviewer,reason=''):
        self.add_event(did,'human_approved' if action=='approve' else 'human_rejected',
                       {'approved':action=='approve','reviewer':reviewer})

class GraphState(TypedDict, total=False):
    amount: int
    loopgrid: dict
    loopgrid_tool_result: dict

sandbox=SandboxCore();bridge=LangGraphBridge(sandbox,agent_id='native-langgraph-agent');calls=[]
def node_args(s):return {'amount':s['amount']}
proposal=bridge.make_decision_node(tool='refund',policy_id='refund-policy',arguments=node_args,
    authority=lambda s:{'limit_usd':2000},model=lambda s:{'name':'synthetic-agent'},
    context=lambda s:{'prompt_version':'v1'},operation_id=lambda s:'one-operation')
guarded=bridge.make_guarded_node(tool='refund',arguments=node_args,
    callback=lambda args:(calls.append(args),{'synthetic':True,'amount':args['amount']})[1])
g=StateGraph(GraphState)
g.add_node('propose',proposal);g.add_node('guard',guarded)
g.add_edge(START,'propose');g.add_edge('propose','guard');g.add_edge('guard',END)
graph=g.compile(checkpointer=InMemorySaver())
observations=[]
config={'configurable':{'thread_id':'thread-native-01'},'callbacks':[LoopGridGraphCallback(observations.append)]}
paused=graph.invoke({'amount':750},config=config)
assert '__interrupt__' in paused,paused
state=graph.get_state(config).values
assert state['loopgrid']['policy']['decision']=='human_approval_required'
assert not calls
# Resuming with text is not authority. Only authenticated Core review authorizes tool.
sandbox.review(state['loopgrid']['decision_id'],'approve','sandbox-reviewer')
finished=graph.invoke(Command(resume='continue'),config=config)
assert finished['loopgrid_tool_result']=={'synthetic':True,'amount':750}, finished
assert len(calls)==1
# Re-entering the same decision cannot execute again even on an alternate graph path.
try:
    bridge.dispatch(state['loopgrid'],thread_id='thread-native-01',tool='refund',arguments={'amount':750},callback=lambda a:calls.append(a))
    raise AssertionError('Replay unexpectedly executed')
except ReconciliationRequired:pass
assert len(calls)==1
print('PASS: REAL installed LangGraph StateGraph+InMemorySaver interrupt/Command(resume), authenticated Core review required and no side-effect replay')
print(json.dumps({'callbacks_observed':[x['kind'] for x in observations], 'sandbox_tool_calls':len(calls)},indent=2))
