from uuid import uuid4
from opportunityos.application.learning import apply_feedback
from opportunityos.domain.enums import FeedbackAction,FeedbackReason,OpportunityType
from opportunityos.domain.models import FeedbackEvent,PersonalProfile
def test_explicit_positive_feedback_increases_engagement_preference(strong_profile:PersonalProfile):
    f=FeedbackEvent(analysis_id=uuid4(),action=FeedbackAction.PURSUE,reasons=[FeedbackReason.STRONG_FIT],explicit=True);updated,changes=apply_feedback(strong_profile,f,opportunity_type=OpportunityType.FRACTIONAL);assert next(p.weight for p in updated.preferences if p.key=='engagement:fractional')>.5;assert changes
def test_implicit_feedback_has_smaller_effect(strong_profile:PersonalProfile):
    e=FeedbackEvent(analysis_id=uuid4(),action=FeedbackAction.REJECT,explicit=True);i=FeedbackEvent(analysis_id=uuid4(),action=FeedbackAction.REJECT,explicit=False);ep,_=apply_feedback(strong_profile,e,opportunity_type=OpportunityType.CONTRACT);ip,_=apply_feedback(strong_profile,i,opportunity_type=OpportunityType.CONTRACT);assert next(p.weight for p in ep.preferences if p.key=='engagement:contract')<next(p.weight for p in ip.preferences if p.key=='engagement:contract')
