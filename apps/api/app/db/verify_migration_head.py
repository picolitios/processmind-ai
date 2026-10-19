"""Read-only check that the connected database is at this image's Alembic head."""

import json

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy.exc import SQLAlchemyError

from app.db.engine import make_engine


def revision_state() -> tuple[set[str], set[str]]:
    """Read both revision sets without running an upgrade or exposing a URL."""
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    expected = set(script.get_heads())
    with make_engine().connect() as connection:
        current = set(MigrationContext.configure(connection).get_current_heads())
    return current, expected


def main() -> int:
    """Emit stable revision state for an operator-only release gate."""
    try:
        current, expected = revision_state()
    except (SQLAlchemyError, CommandError, OSError, ValueError):
        print(json.dumps({"status": "unavailable"}))
        return 1
    ok = bool(expected) and current == expected
    print(json.dumps({
        "status": "ok" if ok else "mismatch",
        "current": sorted(current),
        "expected": sorted(expected),
    }, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
