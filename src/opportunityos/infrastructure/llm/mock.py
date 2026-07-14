from __future__ import annotations
import re
from opportunityos.domain.enums import EvidenceType,OpportunityType
from opportunityos.domain.models import BusinessHypothesis,EvidenceClaim,OpportunityInput,OpportunityProfile,OutreachDraft,PersonalProfile
class MockOpportunityExtractor:
    def extract(self,source,evidence):
        text=(source.raw_text or '').strip();lowered=text.lower();tm=re.search(r'(?:role|title)\s*:\s*([^\n]+)',text,re.I);cm=re.search(r'(?:company)\s*:\s*([^\n]+)',text,re.I)
        title=tm.group(1).strip() if tm else 'Unspecified opportunity';company=cm.group(1).strip() if cm else source.company_hint or 'Unknown company'
        kind=OpportunityType.FRACTIONAL if 'fractional' in lowered else OpportunityType.CONSULTING if 'consult' in lowered else OpportunityType.CONTRACT if 'contract' in lowered else OpportunityType.FULL_TIME if 'full-time' in lowered or 'full time' in lowered else OpportunityType.UNKNOWN
        skills=[s for s in ['data science','analytics','product analytics','retention','growth','ai','machine learning','forecasting','experimentation','python'] if s in lowered];problems=[s for s in ['retention','growth','forecasting','analytics','ai'] if s in lowered];remote=True if 'remote' in lowered else False if 'onsite' in lowered else None;lm=re.search(r'location\s*:\s*([^\n]+)',text,re.I)
        return OpportunityProfile(company_name=company,title=title,opportunity_type=kind,location=lm.group(1).strip() if lm else None,remote_allowed=remote,required_skills=skills,responsibilities=problems,problem_areas=problems,evidence=evidence,extraction_confidence=.75 if text else .4)
class MockBusinessAnalyst:
    def analyse(self,profile,opportunity):
        if opportunity.problem_areas:return [BusinessHypothesis(statement=f"{opportunity.company_name} may need stronger decision systems around {', '.join(opportunity.problem_areas[:3])}.",claim_type=EvidenceType.SUPPORTED_INFERENCE,rationale='The opportunity explicitly references these problem areas.',evidence_ids=[i.id for i in opportunity.evidence],confidence=.65)]
        return [BusinessHypothesis(statement='The business need is not sufficiently specified.',claim_type=EvidenceType.SPECULATIVE_HYPOTHESIS,rationale='The source lacks concrete problem or responsibility information.',evidence_ids=[i.id for i in opportunity.evidence],confidence=.35)]
class MockOutreachWriter:
    def draft(self,profile,opportunity,hypotheses):
        caps=', '.join(c.name for c in profile.capabilities[:3]);problem=opportunity.problem_areas[0] if opportunity.problem_areas else "the role's core problem"
        return OutreachDraft(subject=f'Regarding {opportunity.title} at {opportunity.company_name}',body=f'Hi, I reviewed the {opportunity.title} opportunity at {opportunity.company_name}. My background in {caps} is directly relevant to {problem}. I would be interested in discussing the specific outcomes you need and whether a focused engagement is the right fit.',grounded_claims=[h.statement for h in hypotheses if h.confidence>=.6],claims_to_avoid=['Claims about internal company problems not supported by public evidence.'])
