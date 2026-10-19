"""Compare an isolated restored upload volume with its backup archive and database keys."""

import argparse
import hashlib
import re
import tarfile
from pathlib import Path, PurePosixPath
from typing import IO

KEY_PATTERN = re.compile(r"[0-9a-f]{32}\Z")


def hash_stream(source: IO[bytes]) -> str:
    """Hash files and tar members with bounded memory."""
    checksum = hashlib.sha256()
    while chunk := source.read(1024 * 1024):
        checksum.update(chunk)
    return checksum.hexdigest()


def verify(archive_path: Path, root: Path, keys_path: Path) -> int:
    """Require an exact byte-for-byte volume restore and every referenced upload."""
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Restored upload volume is unavailable")
    root = root.resolve()
    keys = set(keys_path.read_text(encoding="utf-8").splitlines())
    if not keys or any(not KEY_PATTERN.fullmatch(key) for key in keys):
        raise RuntimeError("Invalid restored upload references")

    expected: set[str] = set()
    with tarfile.open(archive_path, "r:") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
                raise RuntimeError("Unsafe upload archive member")
            if not member.isfile():
                continue
            relative = name.as_posix().removeprefix("./")
            if relative in expected:
                raise RuntimeError("Duplicate upload archive member")
            expected.add(relative)
            restored = root.joinpath(*name.parts)
            if restored.is_symlink() or not restored.is_file() or not restored.resolve().is_relative_to(root):
                raise RuntimeError("Restored upload file is missing or unsafe")
            archived = archive.extractfile(member)
            if archived is None:
                raise RuntimeError("Upload archive member could not be read")
            with archived, restored.open("rb") as restored_file:
                matches = hash_stream(archived) == hash_stream(restored_file)
            if not matches:
                raise RuntimeError("Restored upload checksum mismatch")

    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise RuntimeError("Unsafe restored upload entry")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != expected or not keys <= actual:
        raise RuntimeError("Restored upload set differs from archive or database")
    return len(actual)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("volume", type=Path)
    parser.add_argument("database_keys", type=Path)
    args = parser.parse_args()
    print(f"Verified {verify(args.archive, args.volume, args.database_keys)} restored uploads")


if __name__ == "__main__":
    main()
