import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.audit.models import AuditFinding, AuditRun, FindingEvidence
from app.features.audit.rules import RULE_VERSION, SEVERITY, evaluate
from app.features.audit_trail.events import append_business_event
from app.features.ingestion.models import ImportBatch, ImportRow, Job, Purchase


def process_audit_job(db: Session, job_id: uuid.UUID) -> None:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.type == "audit").with_for_update())
    if job is None or job.status != "running":
        return
    run = db.scalar(
        select(AuditRun)
        .where(
            AuditRun.organization_id == job.organization_id,
            AuditRun.id == uuid.UUID(job.payload_json["audit_id"]),
        )
        .with_for_update()
    )
    if run is None or run.job_id != job.id or run.rule_set_version != RULE_VERSION:
        raise ValueError("invalid_audit_job")
    if run.status == "succeeded":
        job.status = "succeeded"
        job.lease_until = None
        db.commit()
        return
    run.status = "running"
    run.started_at = datetime.now(UTC)
    imports = [uuid.UUID(value) for value in run.import_ids]
    mappings = {
        batch.id: batch.mapping["columns"]
        for batch in db.scalars(
            select(ImportBatch).where(
                ImportBatch.organization_id == run.organization_id,
                ImportBatch.id.in_(imports),
                ImportBatch.status == "succeeded",
            )
        )
        if batch.mapping is not None
    }
    if len(mappings) != len(imports):
        raise ValueError("audit_imports_unavailable")
    purchases = db.scalars(
        select(Purchase).where(
            Purchase.organization_id == run.organization_id, Purchase.batch_id.in_(imports)
        )
    ).all()
    rejected = db.scalars(
        select(ImportRow).where(
            ImportRow.organization_id == run.organization_id,
            ImportRow.batch_id.in_(imports),
            ImportRow.errors != [],
        )
    ).all()
    drafts, limitation = evaluate(list(purchases), list(rejected), run.config_snapshot, mappings)
    for draft in drafts:
        finding = AuditFinding(
            organization_id=run.organization_id,
            run_id=run.id,
            rule_code=draft.code,
            rule_version=RULE_VERSION,
            severity=SEVERITY[draft.code],
            review_state="unreviewed",
            explanation=draft.explanation,
            fingerprint=draft.fingerprint,
        )
        db.add(finding)
        db.flush()
        for source in draft.evidence:
            db.add(
                FindingEvidence(
                    organization_id=run.organization_id,
                    finding_id=finding.id,
                    purchase_id=source.purchase_id,
                    import_row_id=source.import_row_id,
                    evidence_json=source.data,
                )
            )
    run.finding_count = len(drafts)
    run.limitation = limitation
    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    job.status = "succeeded"
    job.lease_until = None
    append_business_event(
        db,
        run.organization_id,
        None,
        "audit.completed",
        "audit",
        run.id,
        {"finding_count": len(drafts), "rule_set_version": RULE_VERSION},
    )
    db.commit()
