from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.engine import make_engine


def get_db() -> Iterator[Session]:
    with Session(make_engine()) as db:
        yield db
