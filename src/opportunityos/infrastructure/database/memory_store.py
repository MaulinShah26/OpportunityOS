from opportunityos.domain.enums import MemoryCategory
from opportunityos.domain.taxonomy import canonicalise_preference_key, canonicalise_problem_area
from opportunityos.infrastructure.database.memory_controls import MemoryControlMixin
from opportunityos.infrastructure.database.memory_errors import (
    MemoryConflictError,
    MemoryNotFoundError,
)
from opportunityos.infrastructure.database.memory_profile import ProfileMemoryMixin
from opportunityos.infrastructure.database.store import SqlAlchemyStore as BaseSqlAlchemyStore


class UserControlledStore(ProfileMemoryMixin, MemoryControlMixin, BaseSqlAlchemyStore):
    """Adds durable, user-controlled memory to the v0.2 persistence store."""

    def _validate_memory_value(
        self,
        category: MemoryCategory,
        requested_key: str | None,
        value: dict[str, object],
    ) -> tuple[str, dict, float]:
        key, validated, confidence = super()._validate_memory_value(category, requested_key, value)
        if category == MemoryCategory.PREFERENCE:
            canonical = canonicalise_preference_key(key)
            validated["key"] = canonical
            return canonical, validated, confidence
        if category == MemoryCategory.PROBLEM_AREA:
            canonical = canonicalise_problem_area(key)
            if canonical is None:
                raise MemoryConflictError(
                    "Problem areas must describe a business problem rather than a capability"
                )
            validated["name"] = canonical
            return canonical, validated, confidence
        return key, validated, confidence


__all__ = [
    "MemoryConflictError",
    "MemoryNotFoundError",
    "UserControlledStore",
]
