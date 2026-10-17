"""Probe the effective runtime credential without exposing connection details."""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.engine import make_engine


def main() -> int:
    """Require own-schema access and reject all cross-owner table operations."""
    try:
        with make_engine().connect() as connection:
            role = connection.scalar(text("SELECT current_user"))
            domains = {
                "processmind_identity": ("identity.users", "business.audit_runs"),
                "processmind_business": ("business.audit_runs", "identity.users"),
            }
            if role not in domains:
                print("unexpected runtime role")
                return 2
            owned, other = domains[role]
            connection.scalar(text(f"SELECT count(*) FROM {owned}"))
            for query in (
                f"SELECT * FROM {other} LIMIT 0",
                f"INSERT INTO {other} DEFAULT VALUES",
                f"UPDATE {other} SET id = id WHERE false",
                f"DELETE FROM {other} WHERE false",
                "SELECT * FROM public.alembic_version LIMIT 0",
            ):
                with connection.begin_nested() as savepoint:
                    try:
                        connection.execute(text(query))
                    except DBAPIError as error:
                        if getattr(error.orig, "sqlstate", None) != "42501":
                            raise
                    else:
                        print("cross-domain access unexpectedly permitted")
                        return 2
                    finally:
                        savepoint.rollback()
            connection.rollback()
    except DBAPIError:
        print("runtime credential or privilege probe failed")
        return 1
    print(f"{role}: own access allowed, cross-domain access denied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
