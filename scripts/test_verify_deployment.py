"""Deployment gate tests that do not start or modify Docker containers."""

import json
import unittest
from unittest.mock import patch

import verify_deployment as preflight


def healthy_compose_rows() -> str:
    """Build the smallest expected Compose status without container details."""
    return "\n".join(
        json.dumps({
            "Service": service,
            "State": "running",
            "Health": "healthy" if service in preflight.HEALTHCHECKS else "",
        })
        for service in preflight.SERVICES
    )


class DeploymentPreflightTests(unittest.TestCase):
    def test_service_health_and_missing_service(self) -> None:
        states = preflight.service_states(healthy_compose_rows())
        self.assertEqual(states["api"], "healthy")
        self.assertEqual(states["model-worker"], "running")
        rows = healthy_compose_rows().splitlines()
        states = preflight.service_states("\n".join(rows[:-1]))
        self.assertEqual(states["identity-config-reconciler"], "missing")

    def test_rejects_unhealthy_and_malformed_compose_output(self) -> None:
        rows = healthy_compose_rows().splitlines()
        rows[0] = json.dumps({"Service": "db", "State": "running", "Health": "unhealthy"})
        self.assertEqual(preflight.service_states("\n".join(rows))["db"], "unhealthy")
        with self.assertRaises(TypeError):
            preflight.service_states("[]")

    def test_audit_snapshot_exposes_only_known_failure_codes(self) -> None:
        self.assertEqual(
            preflight.audit_result(2, '{"status":"threshold_exceeded","failures":["audit_dead_letter"]}'),
            {"ok": False, "failures": ["audit_dead_letter"]},
        )
        self.assertEqual(
            preflight.audit_result(0, '{"status":"ok","failures":[]}'),
            {"ok": True, "failures": []},
        )
        self.assertEqual(
            preflight.audit_result(1, '{"status":"unavailable","failures":["tenant-secret"]}'),
            {"ok": False, "failures": ["audit_snapshot_unavailable"]},
        )

    def test_collect_reports_independent_failure_without_container_output(self) -> None:
        def fake_compose(*args: str) -> tuple[int, str]:
            if args[0] == "ps":
                return 0, healthy_compose_rows()
            if "app.db.verify_migration_head" in args:
                return 0, '{"status":"ok"}'
            if "app.db.verify_role_boundary" in args:
                return (2, "private database error") if "identity" in args else (0, "")
            return 0, '{"status":"ok","failures":[]}'

        with patch.object(preflight, "compose", side_effect=fake_compose):
            result = preflight.collect(300)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["checks"]["identity_role"]["ok"])
        self.assertTrue(result["checks"]["audit_dispatch"]["ok"])
        self.assertNotIn("private database error", json.dumps(result))

    def test_compose_failure_fails_closed(self) -> None:
        with patch.object(preflight, "compose", return_value=(1, "")):
            result = preflight.collect(300)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["checks"]["services"]["ok"])
        self.assertFalse(result["checks"]["migration"]["ok"])
        self.assertFalse(result["checks"]["audit_dispatch"]["ok"])


if __name__ == "__main__":
    unittest.main()
