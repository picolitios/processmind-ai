"""Safety checks for the local backup command without touching Docker data."""

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backup_local


class BackupLocalTests(unittest.TestCase):
    def test_rejects_running_writer(self) -> None:
        with (
            patch.object(backup_local, "compose", return_value=b"container-id\n"),
            self.assertRaisesRegex(RuntimeError, "Stop application writer web"),
        ):
            backup_local.preflight()

    def test_rejects_pending_work_and_nonempty_queue(self) -> None:
        def pending(*args: str, **_: object) -> bytes:
            return b"2\n" if args[0] == "exec" else b""

        with (
            patch.object(backup_local, "compose", side_effect=pending),
            self.assertRaisesRegex(RuntimeError, "Drain unpublished"),
        ):
            backup_local.preflight()

        def queued(*args: str, **_: object) -> bytes:
            if args[0] == "ps":
                return b""
            if args[2] == "db":
                return b"0\n"
            return b"processmind.audit.dead\t1\n"

        with (
            patch.object(backup_local, "compose", side_effect=queued),
            self.assertRaisesRegex(RuntimeError, "Drain all audit queues"),
        ):
            backup_local.preflight()

    def test_rejects_malformed_queue_output(self) -> None:
        self.assertEqual(
            backup_local.parse_queue_counts("name\tmessages\nprocessmind.audit.dead\t0\n"),
            {"processmind.audit.dead": 0},
        )
        with self.assertRaisesRegex(RuntimeError, "Unexpected RabbitMQ"):
            backup_local.parse_queue_counts("processmind.audit.dead not-a-count")

    def test_complete_manifest_and_archive_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "database.dump").write_bytes(b"placeholder pg dump")
            with tarfile.open(directory / "uploads.tar", "w") as archive:
                data = b"synthetic"
                member = tarfile.TarInfo("./file")
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            manifest = {
                "format": 1,
                "sha256": {
                    name: backup_local.digest(directory / name)
                    for name in ("database.dump", "uploads.tar")
                },
            }
            (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(backup_local, "compose", return_value=b"archive listing"):
                backup_local.verify(directory)
                (directory / "database.dump").write_bytes(b"tampered")
                with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                    backup_local.verify(directory)

    def test_existing_destination_is_not_modified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(backup_local, "preflight") as preflight:
                with self.assertRaisesRegex(RuntimeError, "already exists"):
                    backup_local.backup(directory)
                preflight.assert_not_called()

    def test_rejects_unsafe_upload_archive_member(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "database.dump").write_bytes(b"placeholder")
            with tarfile.open(directory / "uploads.tar", "w") as archive:
                member = tarfile.TarInfo("../outside")
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))
            (directory / "manifest.json").write_text(
                json.dumps({
                    "format": 1,
                    "sha256": {
                        name: backup_local.digest(directory / name)
                        for name in ("database.dump", "uploads.tar")
                    },
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "Unsafe upload"):
                backup_local.verify(directory)


if __name__ == "__main__":
    unittest.main()
