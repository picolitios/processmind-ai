import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.engine import make_engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


@pytest.mark.parametrize(
    ("role", "owned", "private"),
    [
        ("processmind_identity", "identity.users", "business.audit_runs"),
        ("processmind_business", "business.audit_runs", "identity.users"),
    ],
)
def test_runtime_roles_cannot_access_other_owner(
    role: str, owned: str, private: str,
) -> None:
    engine = make_engine()
    with engine.connect() as connection:
        connection.execute(text(f"SET LOCAL ROLE {role}"))
        assert connection.scalar(text(f"SELECT count(*) FROM {owned}")) is not None
        for statement in (
            f"SELECT * FROM {private} LIMIT 0",
            f"INSERT INTO {private} DEFAULT VALUES",
            f"UPDATE {private} SET id = id WHERE false",
            f"DELETE FROM {private} WHERE false",
            "SELECT * FROM public.alembic_version LIMIT 0",
        ):
            with connection.begin_nested() as savepoint:
                with pytest.raises(DBAPIError) as error:
                    connection.execute(text(statement))
                assert error.value.orig.sqlstate == "42501"
                savepoint.rollback()
        with connection.begin_nested() as savepoint:
            with pytest.raises(DBAPIError) as error:
                connection.execute(
                    text(f"CREATE TABLE {owned.split('.')[0]}.forbidden (id integer)")
                )
            assert error.value.orig.sqlstate == "42501"
            savepoint.rollback()
        connection.rollback()
