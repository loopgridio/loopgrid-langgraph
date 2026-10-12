import copy
import uuid
from loopgrid_langgraph.integration import commitment

class FakeCore:
    workspace_id='ws_test'
    def __init__(self):
        self.decisions={};self.keys={};self.proof=True;self.refused=set();self.version='17.3';self.digest='policy-digest';self.calls=[];self.outage=False
        self.incomplete=False
    def _fail(self,operation):
        if self.outage or operation in self.refused: raise RuntimeError('core unavailable')
    def create_decision(self,payload):
        self._fail('create')
        key=payload['idempotency_key']
        if key in self.keys:
            return {'decision_id':self.keys[key],'idempotent_replay':True}
        did='dec_'+uuid.uuid4().hex[:24]
        self.keys[key]=did
        self.decisions[did]={'summary':{'workspace_id':self.workspace_id}, 'events':[{'event_type':'decision_created','payload':copy.deepcopy(payload)}]}
        self.calls.append(('decision',did))
        return {'decision_id':did}
    def add_event(self,did,kind,payload,**kw):
        self._fail(kind)
        if did not in self.decisions:raise RuntimeError('missing decision')
        entry={'event_type':kind,'payload':copy.deepcopy(payload)}
        self.decisions[did]['events'].append(entry)
        self.calls.append((kind,did))
        return entry
    def evaluate_policy(self,policy_id,action,authority,context):
        self._fail('policy')
        amt=action.get('amount',0)
        decision='blocked' if amt>1500 else ('human_approval_required' if amt>500 else 'auto_allowed')
        return {'policy_id':policy_id,'version':self.version,'policy_digest':self.digest,
                'input_commitment':commitment({'action':action,'authority':authority,'context':context}),
                'decision':decision,'reason':'synthetic'}
    def get_decision(self,did):
        self._fail('get')
        if self.incomplete:return {'summary':{'workspace_id':self.workspace_id},'events':[]}
        return copy.deepcopy(self.decisions[did])
    def verify_workspace(self):
        self._fail('verify')
        return {'valid':self.proof,'workspace_id':self.workspace_id,'failures':[] if self.proof else [{'seq':1}]}
    def review(self,did,action,reviewer,reason=''):
        self._fail('review')
        self.add_event(did,'human_approved' if action=='approve' else 'human_rejected',{'approved':action=='approve','reviewer':reviewer})
