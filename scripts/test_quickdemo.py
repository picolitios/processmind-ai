"""Focused safety tests for the isolated demonstration launcher."""

import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import quickdemo


class QuickDemoTests(unittest.TestCase):
    def test_prepare_keeps_unique_secrets_and_does_not_recreate_file(self) -> None:
        """A second preparation must preserve the database's existing secrets."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.quickdemo"
            with patch.object(quickdemo, "ENV_FILE", path):
                first = quickdemo.prepare()
                second = quickdemo.prepare()
                self.assertEqual(first, second)
                self.assertEqual(len({first[key] for key in quickdemo.SECRET_KEYS}), 5)
                self.assertTrue(all(len(first[key]) == 64 for key in quickdemo.SECRET_KEYS))
                self.assertEqual(first["COMPOSE_PROJECT_NAME"], quickdemo.PROJECT)

    def test_rejects_weak_or_reused_secret(self) -> None:
        """Reject edited demo env files that could expose a weak installation."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env.quickdemo"
            with patch.object(quickdemo, "ENV_FILE", path):
                values = quickdemo.prepare()
                values["POSTGRES_PASSWORD"] = values["RABBITMQ_PASSWORD"]
                quickdemo.write_env(values)
                with self.assertRaisesRegex(RuntimeError, "reused/weak"):
                    quickdemo.prepare()

    def test_tunnel_url_accepts_only_generated_cloudflare_host(self) -> None:
        """Do not set the trusted web origin from arbitrary diagnostic text."""
        messages: quickdemo.queue.Queue[str] = quickdemo.queue.Queue()
        quickdemo.read_tunnel(StringIO(
            "warning https://other.example.com\n"
            "ready https://careful-dawn-123.trycloudflare.com\n"
            "ignore https://foo.trycloudflare.com.evil.example\n"
        ), messages)
        self.assertEqual(messages.get_nowait(), "https://careful-dawn-123.trycloudflare.com")
        self.assertTrue(messages.empty())

    def test_gate_context_targets_quickdemo_only(self) -> None:
        """The release gate must not inspect the default Compose installation."""
        values = {"POSTGRES_PASSWORD": "a" * 64}
        environment = quickdemo.gate_environment(values)
        self.assertEqual(environment["COMPOSE_PROJECT_NAME"], quickdemo.PROJECT)
        self.assertEqual(environment["POSTGRES_PASSWORD"], values["POSTGRES_PASSWORD"])
        self.assertEqual(len(environment["COMPOSE_FILE"].split(os.pathsep)), 2)
        self.assertIn("--env-file", quickdemo.compose_args("config", "--quiet"))

    def test_start_builds_the_migration_runner(self) -> None:
        """A fresh or upgraded demo must not migrate with an old db-admin image."""
        with (
            patch.object(quickdemo, "run_compose") as compose,
            patch.object(quickdemo, "existing_database", return_value=True),
            patch.object(quickdemo.subprocess, "run"),
        ):
            quickdemo.start_stack({})
        compose.assert_any_call("--profile", "tools", "build")

    def test_model_activation_requires_local_worker_probe(self) -> None:
        """A missing model cannot silently switch the demo to another endpoint."""
        values = {"OLLAMA_BASE_URL": quickdemo.FALLBACK_MODEL_URL}
        with (
            patch.object(quickdemo, "prepare", return_value=values),
            patch.object(quickdemo, "model_available_in_worker", return_value=False),
            patch.object(quickdemo, "write_env") as writer,
            patch.object(quickdemo, "run_compose") as compose,
            self.assertRaisesRegex(RuntimeError, "missing or unreachable"),
        ):
            quickdemo.configure_model(True)
        writer.assert_not_called()
        compose.assert_not_called()

    def test_model_activation_changes_only_private_demo_worker(self) -> None:
        """Keep the project and credentials while recreating only model-worker."""
        values = {"COMPOSE_PROJECT_NAME": quickdemo.PROJECT}
        with (
            patch.object(quickdemo, "prepare", return_value=values),
            patch.object(quickdemo, "model_available_in_worker", return_value=True),
            patch.object(quickdemo, "write_env") as writer,
            patch.object(quickdemo, "run_compose") as compose,
        ):
            quickdemo.configure_model(True)
        self.assertEqual(values["OLLAMA_BASE_URL"], quickdemo.LOCAL_MODEL_URL)
        self.assertEqual(values["OLLAMA_TIMEOUT_SECONDS"], "120")
        writer.assert_called_once_with(values)
        compose.assert_called_once_with(
            "up", "-d", "--no-build", "--force-recreate", "--wait", "model-worker"
        )


if __name__ == "__main__":
    unittest.main()
