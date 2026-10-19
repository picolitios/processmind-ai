"""Read-only release gate for the local ProcessMind Compose installation."""

import argparse
import json
import subprocess
from typing import Any

SERVICES = (
    "db", "rabbitmq", "api", "identity", "web", "worker", "model-worker",
    "audit-publisher", "audit-consumer", "audit-monitor", "identity-config-reconciler",
)
HEALTHCHECKS = {"db", "rabbitmq", "api", "identity", "web", "audit-monitor"}
AUDIT_FAILURES = {
    "outbox_pending_age", "audit_queued_age", "audit_expired_lease", "audit_dead_letter"
}


def compose(*args: str) -> tuple[int, str]:
    """Capture only stdout; never print container stderr or credentials."""
    try:
        result = subprocess.run(
            ["docker", "compose", *args], capture_output=True, text=True,
            timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return result.returncode, result.stdout


def service_states(raw: str) -> dict[str, str]:
    """Reduce Compose JSON to stable service health without container metadata."""
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        row = json.loads(line)
        if not isinstance(row, dict):
            raise TypeError("Unexpected Compose row")
        rows.append(row)
    states: dict[str, str] = {}
    for service in SERVICES:
        instances = [row for row in rows if row.get("Service") == service]
        if not instances:
            states[service] = "missing"
        elif any(row.get("State") != "running" for row in instances):
            states[service] = "stopped"
        elif service in HEALTHCHECKS and any(
            row.get("Health") != "healthy" for row in instances
        ):
            states[service] = "unhealthy"
        else:
            states[service] = "healthy" if service in HEALTHCHECKS else "running"
    return states


def audit_result(exit_code: int, raw: str) -> dict[str, Any]:
    """Expose only allowlisted aggregate failure codes from the operator CLI."""
    try:
        result = json.loads(raw)
        codes = result.get("failures", [])
        if not isinstance(codes, list) or any(code not in AUDIT_FAILURES for code in codes):
            raise ValueError("Unexpected audit failure code")
        if exit_code == 0 and result.get("status") == "ok" and not codes:
            return {"ok": True, "failures": []}
        if exit_code == 2 and result.get("status") == "threshold_exceeded" and codes:
            return {"ok": False, "failures": sorted(codes)}
    except (ValueError, TypeError, AttributeError):
        pass
    return {"ok": False, "failures": ["audit_snapshot_unavailable"]}


def collect(max_pending_age_seconds: int) -> dict[str, Any]:
    """Run independent read-only checks and summarize all failed gates."""
    checks: dict[str, Any] = {}
    exit_code, output = compose("ps", "--format", "json")
    try:
        states = service_states(output) if exit_code == 0 else {}
    except (ValueError, TypeError):
        states = {}
    checks["services"] = {
        "ok": bool(states) and all(
            state in {"healthy", "running"} for state in states.values()
        ),
        "states": states,
    }

    exit_code, output = compose(
        "run", "--rm", "--no-deps", "db-admin", "python", "-m",
        "app.db.verify_migration_head",
    )
    try:
        checks["migration"] = {"ok": exit_code == 0 and json.loads(output)["status"] == "ok"}
    except (ValueError, TypeError, KeyError):
        checks["migration"] = {"ok": False}

    for service in ("api", "identity"):
        exit_code, _ = compose(
            "run", "--rm", "--no-deps", service, "python", "-m",
            "app.db.verify_role_boundary",
        )
        checks[f"{service}_role"] = {"ok": exit_code == 0}

    exit_code, output = compose(
        "run", "--rm", "--no-deps", "audit-publisher", "python", "-m",
        "app.features.audit.operations", "--max-pending-age-seconds",
        str(max_pending_age_seconds), "--fail-on-expired-leases", "--fail-on-dead-letter",
    )
    checks["audit_dispatch"] = audit_result(exit_code, output)
    return {
        "status": "ok" if all(check["ok"] for check in checks.values()) else "failed",
        "checks": checks,
    }


def main() -> int:
    """Print one bounded JSON result suitable for a local deployment gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pending-age-seconds", type=int, default=300)
    args = parser.parse_args()
    if args.max_pending_age_seconds < 0:
        parser.error("--max-pending-age-seconds must be nonnegative")
    result = collect(args.max_pending_age_seconds)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
