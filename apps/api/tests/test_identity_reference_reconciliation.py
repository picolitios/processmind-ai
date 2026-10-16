import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.db import reconcile_identity
from app.db.engine import make_engine
from app.features.audit_trail.models import BusinessAuditEvent

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required"
)


def test_reconciliation_reports_orphans_without_persisting_them() -> None:
    with make_engine().connect() as connection:
        transaction = connection.begin()
        try:
            # This table intentionally lacks a cross-domain FK, so the probe can be rolled back.
            connection.execute(
                BusinessAuditEvent.__table__.insert().values(
                    id=uuid.uuid4(),
                    organization_id=uuid.uuid4(),
                    actor_user_id=uuid.uuid4(),
                    action="case.test_reference",
                    subject_type="case",
                    subject_id=uuid.uuid4(),
                    metadata_json={},
                    occurred_at=datetime.now(UTC),
                )
            )
            report = reconcile_identity.collect_report(connection)
            checks = {
                (item["source"], item["column"]): item
                for item in report["checks"]
            }
            assert report["status"] == "inconsistent"
            assert checks[("business_audit_events", "organization_id")]["missing"] == 1
            assert checks[("business_audit_events", "actor_user_id")]["missing"] == 1
        finally:
            transaction.rollback()


def test_reconciliation_rejects_unclassified_tenant_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        reconcile_identity,
        "BUSINESS_TENANT_TABLES",
        tuple(name for name in reconcile_identity.BUSINESS_TENANT_TABLES if name != "suppliers"),
    )
    with make_engine().connect() as connection:
        report = reconcile_identity.collect_report(connection)
    assert report["status"] == "inconsistent"
    assert "unclassified_tenant_table:suppliers" in report["schema_errors"]


def test_reconciliation_fails_closed_on_connection_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unavailable_engine() -> None:
        raise SQLAlchemyError("private connection detail")

    monkeypatch.setattr(reconcile_identity, "open_engine", unavailable_engine)
    assert reconcile_identity.main() == 1
    output = capsys.readouterr().out
    assert '"status": "error"' in output
    assert "private connection detail" not in output
