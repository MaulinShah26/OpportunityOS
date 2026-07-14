from opportunityos.infrastructure.database.memory_controls import MemoryControlMixin
from opportunityos.infrastructure.database.memory_errors import (
    MemoryConflictError,
    MemoryNotFoundError,
)
from opportunityos.infrastructure.database.memory_profile import ProfileMemoryMixin
from opportunityos.infrastructure.database.store import SqlAlchemyStore as BaseSqlAlchemyStore


class UserControlledStore(ProfileMemoryMixin, MemoryControlMixin, BaseSqlAlchemyStore):
    """Adds durable, user-controlled memory to the v0.2 persistence store."""


__all__ = [
    "MemoryConflictError",
    "MemoryNotFoundError",
    "UserControlledStore",
]
