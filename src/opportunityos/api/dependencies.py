from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.config import get_settings
from opportunityos.infrastructure.database import Database, SqlAlchemyStore
from opportunityos.infrastructure.llm.mock import MockBusinessAnalyst, MockOpportunityExtractor, MockOutreachWriter
from opportunityos.infrastructure.research import InputOnlyResearchProvider, PublicSourceResearchProvider


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
    settings = get_settings()
    if settings.llm_mode == "mock":
        return AnalyseOpportunityService(research=InputOnlyResearchProvider(), extractor=MockOpportunityExtractor(), analyst=MockBusinessAnalyst(), outreach_writer=MockOutreachWriter(), orchestrator_name=settings.orchestrator, model_metadata={"mode": "mock"})
    from opportunityos.infrastructure.llm.anthropic_provider import AnthropicBusinessAnalyst, AnthropicOutreachWriter
    from opportunityos.infrastructure.llm.openai_provider import OpenAIOpportunityExtractor
    return AnalyseOpportunityService(research=PublicSourceResearchProvider(timeout_seconds=settings.http_timeout_seconds, max_source_bytes=settings.max_source_bytes), extractor=OpenAIOpportunityExtractor(api_key=settings.openai_api_key or "", model=settings.openai_model or ""), analyst=AnthropicBusinessAnalyst(api_key=settings.anthropic_api_key or "", model=settings.anthropic_model or ""), outreach_writer=AnthropicOutreachWriter(api_key=settings.anthropic_api_key or "", model=settings.anthropic_model or ""), orchestrator_name=settings.orchestrator, model_metadata={"openai_model": settings.openai_model or "", "anthropic_model": settings.anthropic_model or ""})
