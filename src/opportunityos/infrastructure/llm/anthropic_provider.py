from __future__ import annotations
import json
from anthropic import Anthropic
from opportunityos.domain.models import BusinessHypothesis,OpportunityProfile,OutreachDraft,PersonalProfile
def _text_from_message(message):return ''.join(getattr(b,'text','') for b in getattr(message,'content',[]) if getattr(b,'type','')=='text')
class AnthropicBusinessAnalyst:
    def __init__(self,api_key:str,model:str):self.client=Anthropic(api_key=api_key);self.model=model
    def analyse(self,profile,opportunity):
        prompt={'instruction':'Identify at most three credible business hypotheses. Separate facts, supported inferences, and speculation. Return only JSON. Never claim internal knowledge.','profile':profile.model_dump(mode='json'),'opportunity':opportunity.model_dump(mode='json'),'schema':{'type':'array','items':BusinessHypothesis.model_json_schema()}}
        m=self.client.messages.create(model=self.model,max_tokens=1800,messages=[{'role':'user','content':json.dumps(prompt)}]);return [BusinessHypothesis.model_validate(i) for i in json.loads(_text_from_message(m))]
class AnthropicOutreachWriter:
    def __init__(self,api_key:str,model:str):self.client=Anthropic(api_key=api_key);self.model=model
    def draft(self,profile,opportunity,hypotheses):
        prompt={'instruction':'Draft direct, natural, operator-like outreach. Use only grounded claims. Avoid generic networking language and exaggerated certainty. Return only JSON.','profile':profile.model_dump(mode='json'),'opportunity':opportunity.model_dump(mode='json'),'hypotheses':[i.model_dump(mode='json') for i in hypotheses],'schema':OutreachDraft.model_json_schema()}
        m=self.client.messages.create(model=self.model,max_tokens=1200,messages=[{'role':'user','content':json.dumps(prompt)}]);return OutreachDraft.model_validate_json(_text_from_message(m))
