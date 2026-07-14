from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from opportunityos.infrastructure.database.models import Base


class Database:
    def __init__(self, database_url: str) -> None:
        engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
        if database_url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if database_url.endswith(":memory:"):
                engine_kwargs["poolclass"] = StaticPool
        self.engine: Engine = create_engine(database_url, **engine_kwargs)
        self._session_factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False, class_=Session)
        self._schema_lock = Lock()
        self._schema_ready = False

    def create_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if not self._schema_ready:
                Base.metadata.create_all(self.engine)
                self._schema_ready = True

    @contextmanager
    def session(self) -> Iterator[Session]:
        db_session = self._session_factory()
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()
