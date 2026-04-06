"""SQLAlchemy engine, session factory, and Base."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from tsunami.config import get_settings


class Base(DeclarativeBase):
    pass


def get_sync_engine():
    url = get_settings().database_url.replace("sqlite+aiosqlite", "sqlite")
    return create_engine(url)


def get_async_engine():
    return create_async_engine(get_settings().database_url)


def get_async_session_factory():
    return async_sessionmaker(get_async_engine(), expire_on_commit=False)
