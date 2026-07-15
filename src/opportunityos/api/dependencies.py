from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from opportunityos.application.factory import build_analysis_service
from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.config import get_settings
from opportunityos.infrastructure.database import Database, SqlAlchemyStore


@lru_cache
def get_database() -> Database:
    settings = get_settings()
    database = Database(settings.database_url)
    if settings.auto_create_schema:
        database.create_schema()
    return database


def get_session() -> Iterator[Session]:
    with get_database().session() as session:
        yield session


def get_store(session: Session = Depends(get_session)) -> SqlAlchemyStore:
    return SqlAlchemyStore(session)


@lru_cache
def get_analysis_service() -> AnalyseOpportunityService:
    return build_analysis_service(get_settings())
