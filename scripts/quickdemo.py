"""Run an isolated, synthetic ProcessMind demo behind a temporary HTTPS tunnel."""

import argparse
import csv
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.quickdemo"
PROJECT = "processmind_quickdemo"
WEB_PORT = 5174
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com(?![.\w-])")
SECRET_KEYS = (
    "POSTGRES_PASSWORD", "IDENTITY_DB_PASSWORD", "BUSINESS_DB_PASSWORD",
    "AUTH_HASH_KEY", "RABBITMQ_PASSWORD",
)


def parse_env(path: Path) -> dict[str, str]:
    """Read only the private demo settings; never echo their values."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def write_env(values: dict[str, str]) -> None:
    """Atomically replace the env file with access limited to the current user."""
    temporary = ENV_FILE.with_suffix(".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            for key, value in values.items():
                output.write(f"{key}={value}\n")
        if os.name == "nt":
            # Windows files inherit directory ACLs unless explicitly restricted.
            identity = subprocess.run(
                ["whoami", "/user", "/fo", "csv", "/nh"],
                capture_output=True, text=True, check=True,
            )
            sid = next(csv.reader(identity.stdout.splitlines()))[1]
            if not re.fullmatch(r"S-1-[0-9-]+", sid):
                raise RuntimeError("Cannot determine current Windows user")
            subprocess.run(
                ["icacls", str(temporary), "/inheritance:r", "/grant:r", f"*{sid}:(F)"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            )
        else:
            temporary.chmod(0o600)
        temporary.replace(ENV_FILE)
    finally:
        temporary.unlink(missing_ok=True)


def prepare() -> dict[str, str]:
    """Create a separate local environment once and preserve it on later runs."""
    if not ENV_FILE.exists():
        values = {
            "COMPOSE_PROJECT_NAME": PROJECT,
            "WEB_ORIGIN": "https://demo.invalid",
            "APP_ENV": "demo",
            "POSTGRES_DB": "processmind",
            "POSTGRES_USER": "processmind",
            "RABBITMQ_USER": "processmind",
            "OLLAMA_BASE_URL": "http://127.0.0.1:1",
        }
        values.update({key: secrets.token_hex(32) for key in SECRET_KEYS})
        write_env(values)
    values = parse_env(ENV_FILE)
    if (
        values.get("COMPOSE_PROJECT_NAME") != PROJECT
        or values.get("APP_ENV") != "demo"
        or values.get("OLLAMA_BASE_URL") != "http://127.0.0.1:1"
        or any(not re.fullmatch(r"[0-9a-f]{64}", values.get(key, "")) for key in SECRET_KEYS)
        or len({values.get(key) for key in SECRET_KEYS}) != len(SECRET_KEYS)
    ):
        raise RuntimeError("Invalid quick demo settings or reused/weak secrets")
    # Reapply the restrictive file ACL when an operator supplied the env file.
    write_env(values)
    return values


def compose_args(*args: str) -> list[str]:
    """Pin every Compose call to the isolated project and private env file."""
    return [
        "docker", "compose", "--project-name", PROJECT, "--env-file", str(ENV_FILE),
        "-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "compose.quickdemo.yaml"),
        *args,
    ]


def run_compose(*args: str) -> None:
    """Execute a reviewed Compose operation without printing secrets."""
    subprocess.run(compose_args(*args), cwd=ROOT, check=True)


def existing_database() -> bool:
    """Avoid applying initial migrations to a preexisting named volume."""
    result = subprocess.run(
        ["docker", "volume", "inspect", f"{PROJECT}_postgres_data"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    return result.returncode == 0


def gate_environment(values: dict[str, str]) -> dict[str, str]:
    """Pass the same Compose context to the existing read-only release gate."""
    environment = os.environ.copy()
    environment.update(values)
    environment["COMPOSE_PROJECT_NAME"] = PROJECT
    environment["COMPOSE_FILE"] = os.pathsep.join((
        str(ROOT / "compose.yaml"), str(ROOT / "compose.quickdemo.yaml"),
    ))
    return environment


def start_stack(values: dict[str, str]) -> None:
    """Build and initialize only a new demo database, then gate all services."""
    run_compose("config", "--quiet")
    prior_database = existing_database()
    run_compose("build")
    run_compose("up", "-d", "--wait", "db", "rabbitmq")
    if not prior_database:
        run_compose("run", "--rm", "--no-deps", "db-admin", "alembic", "upgrade", "head")
        run_compose("run", "--rm", "--no-deps", "db-admin", "python", "-m", "app.db.provision_roles")
    run_compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "180")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_deployment.py")],
        cwd=ROOT, env=gate_environment(values), check=True,
    )


def read_tunnel(stream: TextIO | None, messages: queue.Queue[str]) -> None:
    """Extract only the generated hostname from cloudflared diagnostic output."""
    if stream is None:
        return
    for line in stream:
        match = TUNNEL_URL.search(line)
        if match:
            messages.put(match.group())


def open_tunnel(binary: str) -> tuple[subprocess.Popen[str], str]:
    """Start a free ephemeral tunnel and wait for its validated HTTPS URL."""
    process = subprocess.Popen(
        [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{WEB_PORT}"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    messages: queue.Queue[str] = queue.Queue()
    threading.Thread(target=read_tunnel, args=(process.stderr, messages), daemon=True).start()
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and process.poll() is None:
        try:
            return process, messages.get(timeout=1)
        except queue.Empty:
            continue
    process.terminate()
    raise RuntimeError("Quick Tunnel did not provide a URL within 90 seconds")


def check_public_health(origin: str) -> None:
    """Require a valid TLS response from the external readiness endpoint."""
    with urllib.request.urlopen(f"{origin}/api/v1/health/ready", timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("Public readiness endpoint failed")


def serve() -> None:
    """Expose the isolated stack while this process remains in the foreground."""
    binary = os.environ.get("CLOUDFLARED_BIN", "cloudflared")
    if shutil.which(binary) is None:
        raise RuntimeError("Install the official cloudflared binary before serving")
    values = prepare()
    # The public hostname changes every launch, so bind the app to it before startup.
    tunnel, origin = open_tunnel(binary)
    try:
        values["WEB_ORIGIN"] = origin
        write_env(values)
        start_stack(values)
        check_public_health(origin)
        print(f"Demonstração pública: {origin}", flush=True)
        print("Use somente dados sintéticos. Ctrl+C encerra o túnel; volumes permanecem.", flush=True)
        while tunnel.poll() is None:
            time.sleep(1)
        raise RuntimeError("Quick Tunnel disconnected")
    finally:
        if tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()


def main() -> int:
    """Offer a safe preparation command and an explicit public serve command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "serve"))
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            prepare()
            run_compose("config", "--quiet")
            print("Ambiente isolado preparado; nenhum túnel foi iniciado.")
        else:
            serve()
    except KeyboardInterrupt:
        print("Túnel encerrado; os dados locais foram preservados.")
    except (OSError, RuntimeError, subprocess.CalledProcessError, urllib.error.URLError) as error:
        print(f"Falha na demonstração: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
