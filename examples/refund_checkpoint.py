"""Synthetic local LangGraph refund example. No real payment or refund occurs.

Requires a prepared LoopGrid workspace with active 'refund-policy' and scoped key.
For the self-contained setup and complete end-to-end validation, use
scripts/native_core_langgraph_e2e.py instead.
"""
from __future__ import annotations
import os,uuid
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from loopgrid_langgraph import CoreClient, LangGraphBridge

class State(TypedDict,total=False):
    amount:int
    operation_id:str
    loopgrid:dict
    loopgrid_tool_result:dict
    loopgrid_verification:dict

core=CoreClient(base_url=os.environ.get('LOOPGRID_BASE_URL','http://127.0.0.1:8000'),
    workspace_id=os.environ['LOOPGRID_WORKSPACE_ID'],
    service_key=os.environ['LOOPGRID_SERVICE_KEY'])
bridge=LangGraphBridge(core,agent_id='langgraph-refund-demo')
args=lambda state:{'amount':state['amount'],'currency':'USD'}
proposal=bridge.make_decision_node(tool='refund',policy_id='refund-policy',arguments=args,
    authority=lambda state:{'limit_usd':1500,'scope':['synthetic-refund']},
    model=lambda state:{'name':'deterministic-example-no-llm'},
    context=lambda state:{'prompt_version':'refund-demo-v1'},
    operation_id=lambda state:state['operation_id'])
execution=bridge.make_guarded_node(tool='refund',arguments=args,
    callback=lambda args:{'sandbox':True,'amount':args['amount'],'real_money_moved':False})
workflow=StateGraph(State)
workflow.add_node('propose',proposal);workflow.add_node('execute',execution)
workflow.add_node('verify',bridge.make_verify_node())
workflow.add_edge(START,'propose');workflow.add_edge('propose','execute');workflow.add_edge('execute','verify');workflow.add_edge('verify',END)
graph=workflow.compile(checkpointer=InMemorySaver())
conf={'configurable':{'thread_id':'demo-'+uuid.uuid4().hex[:12]}}
result=graph.invoke({'amount':15,'operation_id':'demo-'+uuid.uuid4().hex[:12]},conf)
assert 'loopgrid_tool_result' in result
print('Decision ID:',result['loopgrid']['decision_id'])
print('Tool result:',result['loopgrid_tool_result'])
print('Verified Core chain:',result['loopgrid_verification']['valid'])
print('Observed external business outcome: NOT RECORDED (no real business action)')
