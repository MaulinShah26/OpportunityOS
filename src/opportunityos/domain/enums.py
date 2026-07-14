from enum import Enum


class OpportunityType(str, Enum):
    CONSULTING = "consulting"
    FRACTIONAL = "fractional"
    CONTRACT = "contract"
    FULL_TIME = "full_time"
    ADVISORY = "advisory"
    PARTNERSHIP = "partnership"
    UNKNOWN = "unknown"


class Decision(str, Enum):
    PURSUE = "pursue"
    HOLD = "hold"
    REJECT = "reject"


class ConstraintKind(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class EvidenceType(str, Enum):
    OBSERVED_FACT = "observed_fact"
    SUPPORTED_INFERENCE = "supported_inference"
    SPECULATIVE_HYPOTHESIS = "speculative_hypothesis"


class FeedbackAction(str, Enum):
    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    SAVE = "save"
    PURSUE = "pursue"
    REJECT = "reject"
    MAYBE_LATER = "maybe_later"


class FeedbackReason(str, Enum):
    STRONG_FIT = "strong_fit"
    WRONG_ROLE = "wrong_role"
    WRONG_COMPANY = "wrong_company"
    WRONG_ENGAGEMENT = "wrong_engagement"
    COMPENSATION_MISMATCH = "compensation_mismatch"
    LOCATION_MISMATCH = "location_mismatch"
    TOO_JUNIOR = "too_junior"
    TOO_EXECUTION_HEAVY = "too_execution_heavy"
    INTERESTING_COMPANY_WRONG_OPPORTUNITY = "interesting_company_wrong_opportunity"


class MemoryCategory(str, Enum):
    CAPABILITY = "capability"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    ASPIRATION = "aspiration"
    PROBLEM_AREA = "problem_area"


class MemorySource(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DELETED = "deleted"


class MemoryAction(str, Enum):
    CONFIRM = "confirm"
    UPDATE = "update"
    REJECT = "reject"


class CriticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"
