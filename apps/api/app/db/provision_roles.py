"""Enable schema-scoped runtime logins after the migration has created them."""

import os

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import settings

ROLES = (
    ("processmind_identity", "IDENTITY_DB_PASSWORD"),
    ("processmind_business", "BUSINESS_DB_PASSWORD"),
)


def main() -> int:
    """Read secrets only from the environment and never print connection details."""
    passwords = [os.environ.get(variable, "") for _, variable in ROLES]
    if any(len(password) < 32 for password in passwords) or passwords[0] == passwords[1]:
        print("role provisioning requires distinct passwords of at least 32 characters")
        return 2
    url = make_url(settings.database_url)
    try:
        with psycopg.connect(
            host=url.host, port=url.port, dbname=url.database,
            user=url.username, password=url.password,
        ) as connection:
            with connection.cursor() as cursor:
                for (role, _), password in zip(ROLES, passwords, strict=True):
                    cursor.execute(
                        sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                            sql.Identifier(role), sql.Literal(password)
                        )
                    )
    except psycopg.Error:
        print("role provisioning failed; check migration and admin connection")
        return 1
    print("runtime roles provisioned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
