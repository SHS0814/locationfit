from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import settings


def _database_url() -> str:
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL이 설정되지 않았습니다. 금융지원 카탈로그 DB를 사용할 때만 설정해주세요."
        )
    return settings.database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(_database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Generator[Session, None, None]:
    with session_scope() as session:
        yield session
