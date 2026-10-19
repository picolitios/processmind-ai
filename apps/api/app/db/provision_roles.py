"""Provision schema-scoped runtime logins after migration or isolated restore."""

import os

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import settings

ROLES = (
    ("processmind_identity", "IDENTITY_DB_PASSWORD", "identity"),
    ("processmind_business", "BUSINESS_DB_PASSWORD", "business"),
)


def main() -> int:
    """Read secrets only from the environment and never print connection details."""
    passwords = [os.environ.get(variable, "") for _, variable, _ in ROLES]
    if any(len(password) < 32 for password in passwords) or passwords[0] == passwords[1]:
        print("role provisioning requires distinct passwords of at least 32 characters")
        return 2
    url = make_url(settings.database_url)
    if url.database is None:
        print("role provisioning requires a database name")
        return 2
    try:
        with psycopg.connect(
            host=url.host, port=url.port, dbname=url.database,
            user=url.username, password=url.password,
        ) as connection:
            with connection.cursor() as cursor:
                for (role, _, schema), password in zip(ROLES, passwords, strict=True):
                    # A pg_dump restore does not include cluster roles or database grants.
                    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                    if cursor.fetchone() is None:
                        cursor.execute(
                            sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role))
                        )
                    cursor.execute(
                        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                            sql.Identifier(schema), sql.Identifier(role)
                        )
                    )
                    cursor.execute(
                        sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                                "IN SCHEMA {} TO {}").format(
                            sql.Identifier(schema), sql.Identifier(role)
                        )
                    )
                    cursor.execute(
                        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES "
                                "IN SCHEMA {} TO {}").format(
                            sql.Identifier(schema), sql.Identifier(role)
                        )
                    )
                    cursor.execute(
                        sql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path = {}, public").format(
                            sql.Identifier(role),
                            sql.Identifier(url.database),
                            sql.Identifier(schema),
                        )
                    )
                    cursor.execute(
                        sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                            sql.Identifier(role), sql.Literal(password)
                        )
                    )
                cursor.execute(
                    sql.SQL(
                        "ALTER DATABASE {} SET search_path = public, business, identity"
                    ).format(
                        sql.Identifier(url.database)
                    )
                )
    except psycopg.Error:
        print("role provisioning failed; check migration and admin connection")
        return 1
    print("runtime roles provisioned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
