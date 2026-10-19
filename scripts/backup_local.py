"""Create a quiesced, local Compose backup without touching a running writer."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

WRITERS = (
    "web", "api", "identity", "identity-config-reconciler", "worker",
    "model-worker", "audit-publisher", "audit-consumer",
)
AUDIT_QUEUES = {
    "processmind.audit.requested.v1", "processmind.audit.retry.5s",
    "processmind.audit.retry.15s", "processmind.audit.dead",
}
DATABASE_QUERY = (
    "SELECT (SELECT count(*) FROM business.outbox_events WHERE published_at IS NULL) "
    "+ (SELECT count(*) FROM business.jobs WHERE type = 'audit' "
    "AND status IN ('queued', 'running'))"
)


def compose(*args: str, input_file: Path | None = None) -> bytes:
    """Call Compose without a shell or surfacing potentially sensitive stderr."""
    source = input_file.open("rb") if input_file else None
    try:
        result = subprocess.run(
            ["docker", "compose", *args], stdin=source,
            capture_output=True, check=False,
        )
    finally:
        if source:
            source.close()
    if result.returncode:
        raise RuntimeError("Docker Compose command failed; inspect local container health")
    return result.stdout


def preflight() -> None:
    """Require a drained audit path and stopped application writers."""
    for service in WRITERS:
        if compose("ps", "-q", service).strip():
            raise RuntimeError(f"Stop application writer {service} before backup")
    pending = compose(
        "exec", "-T", "db", "sh", "-c",
        'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "$1"',
        "sh", DATABASE_QUERY,
    ).strip()
    if pending != b"0":
        raise RuntimeError("Drain unpublished events and queued/running audit jobs first")
    lines = compose("exec", "-T", "rabbitmq", "rabbitmqctl", "list_queues", "-q", "name", "messages")
    counts = parse_queue_counts(lines.decode("utf-8"))
    if any(counts.get(queue, 0) for queue in AUDIT_QUEUES):
        raise RuntimeError("Drain all audit queues, including dead letters, first")


def parse_queue_counts(raw: str) -> dict[str, int]:
    """Reject malformed broker output rather than assuming the queues are empty."""
    counts: dict[str, int] = {}
    for line in raw.splitlines():
        fields = line.split()
        if fields == ["name", "messages"]:
            continue
        if len(fields) != 2 or not fields[1].isdigit():
            raise RuntimeError("Unexpected RabbitMQ queue response")
        counts[fields[0]] = int(fields[1])
    return counts


def write_stream(command: tuple[str, ...], path: Path) -> None:
    """Stream an archive directly to a private file without printing its bytes."""
    with path.open("xb") as output:
        result = subprocess.run(
            ["docker", "compose", *command], stdout=output,
            stderr=subprocess.PIPE, check=False,
        )
    if result.returncode:
        raise RuntimeError("Docker Compose archive command failed")


def digest(path: Path) -> str:
    """Hash a potentially large archive with bounded memory."""
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def verify(directory: Path) -> None:
    """Check the manifest and both archives without extracting sensitive data."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or set(manifest.get("sha256", {})) != {
        "database.dump", "uploads.tar"
    }:
        raise RuntimeError("Invalid backup manifest")
    for name, expected in manifest["sha256"].items():
        if digest(directory / name) != expected:
            raise RuntimeError(f"Backup checksum mismatch: {name}")
    with tarfile.open(directory / "uploads.tar", "r:") as archive:
        for member in archive:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or not member.isfile() and not member.isdir():
                raise RuntimeError("Unsafe upload archive member")
    compose("exec", "-T", "db", "pg_restore", "--list", input_file=directory / "database.dump")


def backup(directory: Path) -> None:
    """Create a new complete directory; preserve partial output for diagnosis."""
    if directory.exists():
        raise RuntimeError("Backup destination already exists")
    preflight()
    staging = directory.with_name(f"{directory.name}.incomplete-{uuid.uuid4().hex[:8]}")
    staging.mkdir(mode=0o700, parents=True)
    write_stream(
        ("exec", "-T", "db", "sh", "-c",
         'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl'),
        staging / "database.dump",
    )
    write_stream(
        ("run", "--rm", "--no-deps", "-T", "--entrypoint", "tar", "worker",
         "-C", "/data/uploads", "-cf", "-", "."),
        staging / "uploads.tar",
    )
    manifest = {
        "format": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "sha256": {name: digest(staging / name) for name in ("database.dump", "uploads.tar")},
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verify(staging)
    os.replace(staging, directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "verify"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "backup":
            backup(args.directory.resolve())
        else:
            verify(args.directory.resolve())
    except (OSError, RuntimeError, ValueError, tarfile.TarError, json.JSONDecodeError) as error:
        print(f"Backup {args.action} failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(f"Backup {args.action} verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
