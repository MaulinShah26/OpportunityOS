from enum import StrEnum

class OpportunityType(StrEnum):
    CONSULTING='consulting'; FRACTIONAL='fractional'; CONTRACT='contract'; FULL_TIME='full_time'; ADVISORY='advisory'; PARTNERSHIP='partnership'; UNKNOWN='unknown'
class Decision(StrEnum):
    PURSUE='pursue'; HOLD='hold'; REJECT='reject'
class ConstraintKind(StrEnum):
    HARD='hard'; SOFT='soft'
class EvidenceType(StrEnum):
    OBSERVED_FACT='observed_fact'; SUPPORTED_INFERENCE='supported_inference'; SPECULATIVE_HYPOTHESIS='speculative_hypothesis'
class FeedbackAction(StrEnum):
    RELEVANT='relevant'; NOT_RELEVANT='not_relevant'; SAVE='save'; PURSUE='pursue'; REJECT='reject'; MAYBE_LATER='maybe_later'
class FeedbackReason(StrEnum):
    STRONG_FIT='strong_fit'; WRONG_ROLE='wrong_role'; WRONG_COMPANY='wrong_company'; WRONG_ENGAGEMENT='wrong_engagement'; COMPENSATION_MISMATCH='compensation_mismatch'; LOCATION_MISMATCH='location_mismatch'; TOO_JUNIOR='too_junior'; TOO_EXECUTION_HEAVY='too_execution_heavy'; INTERESTING_COMPANY_WRONG_OPPORTUNITY='interesting_company_wrong_opportunity'
