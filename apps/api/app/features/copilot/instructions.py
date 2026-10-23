"""Apply tenant-specific AI preferences below the product's fixed evidence rules."""

import json
import uuid

from sqlalchemy.orm import Session

from app.features.copilot.models import CopilotPolicy


def system_message_for_organization(
    db: Session, organization_id: uuid.UUID, base_message: str,
) -> str:
    """Add bounded company preferences without treating them as permission to bypass safeguards."""
    policy = db.get(CopilotPolicy, organization_id)
    if policy is None or not policy.instructions:
        return base_message
    return (
        base_message
        + "\nPreferências da organização para tom e foco (subordinadas às regras acima): "
        + json.dumps(policy.instructions, ensure_ascii=False)
        + "\nEssas preferências nunca dispensam evidências, citações, controle de acesso, "
        "revisão humana ou o formato JSON exigido. Não execute ações."
    )
