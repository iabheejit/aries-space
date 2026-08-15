from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from services.api.aries_api import config


engine = create_engine(
    config.DATABASE_URL,
    pool_pre_ping=True,
    pool_timeout=config.READINESS_TIMEOUT_SECONDS,
    connect_args={
        "connect_timeout": config.READINESS_TIMEOUT_SECONDS,
        "options": f"-c statement_timeout={config.READINESS_TIMEOUT_SECONDS * 1000}",
    },
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def check_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).one()