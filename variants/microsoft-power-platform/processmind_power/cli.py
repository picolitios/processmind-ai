"""Read and exercise real ProcessMind flows without Microsoft credentials."""

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any

from processmind_power.client import IntegrationError, ProcessMindClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Local ProcessMind Power Platform scenario")
    parser.add_argument("command", choices=["audits", "findings", "request-audit", "ask"])
    parser.add_argument("--audit-id", type=uuid.UUID)
    parser.add_argument("--import-id", type=uuid.UUID, action="append", default=[])
    parser.add_argument("--question")
    args = parser.parse_args()
    try:
        org = uuid.UUID(os.environ["PM_ORGANIZATION_ID"])
        with ProcessMindClient(os.environ.get("PM_BASE_URL", "http://localhost:5173"), org) as api:
            api.login(os.environ["PM_EMAIL"], os.environ["PM_PASSWORD"])
            result: Any
            if args.command == "audits":
                result = [item.model_dump(mode="json") for item in api.audits()]
            elif args.command == "findings":
                if not args.audit_id:
                    parser.error("--audit-id is required")
                audit = api.audit(args.audit_id)
                result = {"audit": audit.model_dump(mode="json"), "findings": [
                    item.model_dump(mode="json") for item in api.findings(args.audit_id)
                ] if audit.status == "succeeded" else []}
            elif args.command == "request-audit":
                if not args.import_id:
                    parser.error("--import-id is required")
                created = api.request_audit(args.import_id, str(uuid.uuid4()))
                result = created.model_dump(mode="json")
            else:
                if not args.audit_id or not args.question:
                    parser.error("--audit-id and --question are required")
                audit = api.audit(args.audit_id)
                if audit.status != "succeeded":
                    raise IntegrationError("audit_not_completed")
                conversation = api.create_conversation(args.audit_id)
                question_id = api.ask(conversation, args.question, str(uuid.uuid4()))
                deadline = time.monotonic() + 30
                while True:
                    answer = api.question(question_id)
                    if answer.status in ("succeeded", "failed") or time.monotonic() >= deadline:
                        result = answer.model_dump(mode="json")
                        break
                    time.sleep(2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError) as exc:
        print(f"configuration_error: {type(exc).__name__}", file=sys.stderr)
        return 2
    except IntegrationError as exc:
        print(exc.code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
