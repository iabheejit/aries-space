from sqlmodel import Session, SQLModel, create_engine

from app import config

engine = create_engine(config.DB_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
