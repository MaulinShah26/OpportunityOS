from __future__ import annotations
import json
from openai import OpenAI
from opportunityos.domain.models import EvidenceClaim,OpportunityInput,OpportunityProfile
class OpenAIOpportunityExtractor:
    def __init__(self,api_key:str,model:str):self.client=OpenAI(api_key=api_key);self.model=model
    def extract(self,source:OpportunityInput,evidence:list[EvidenceClaim])->OpportunityProfile:
        prompt={'instruction':'Extract a factual opportunity profile. Return only JSON matching the supplied schema. Do not infer missing compensation, location, or company facts.','source':source.model_dump(mode='json'),'evidence':[i.model_dump(mode='json') for i in evidence],'schema':OpportunityProfile.model_json_schema()}
        response=self.client.responses.create(model=self.model,input=json.dumps(prompt));payload=json.loads(response.output_text);payload['evidence']=[i.model_dump(mode='json') for i in evidence];return OpportunityProfile.model_validate(payload)
