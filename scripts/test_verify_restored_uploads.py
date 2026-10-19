"""Check byte integrity and reference coverage for restored upload volumes."""

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

import verify_restored_uploads

KEY = "a" * 32


class RestoredUploadTests(unittest.TestCase):
    def test_exact_restore_and_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            volume = directory / "volume"
            volume.mkdir()
            (volume / KEY).write_bytes(b"synthetic private upload")
            keys = directory / "keys.txt"
            keys.write_text(f"{KEY}\n", encoding="utf-8")
            archive_path = directory / "uploads.tar"
            with tarfile.open(archive_path, "w") as archive:
                data = b"synthetic private upload"
                member = tarfile.TarInfo(f"./{KEY}")
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            self.assertEqual(verify_restored_uploads.verify(archive_path, volume, keys), 1)
            (volume / KEY).write_bytes(b"corrupted")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                verify_restored_uploads.verify(archive_path, volume, keys)
            (volume / KEY).write_bytes(data)
            (volume / "unexpected").write_bytes(b"x")
            with self.assertRaisesRegex(RuntimeError, "set differs"):
                verify_restored_uploads.verify(archive_path, volume, keys)

    def test_missing_database_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            volume = directory / "volume"
            volume.mkdir()
            keys = directory / "keys.txt"
            keys.write_text(f"{KEY}\n", encoding="utf-8")
            archive_path = directory / "uploads.tar"
            with tarfile.open(archive_path, "w"):
                pass
            with self.assertRaisesRegex(RuntimeError, "set differs"):
                verify_restored_uploads.verify(archive_path, volume, keys)


if __name__ == "__main__":
    unittest.main()
