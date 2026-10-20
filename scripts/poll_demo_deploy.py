"""Deploy the latest CI-approved main commit from an outbound-only VM timer."""

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

REPOSITORY = "picolitios/processmind-ai"
WORKFLOW_RUNS = (
    f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/ci.yml/runs"
    "?branch=main&event=push&per_page=1"
)
CHECKOUT = Path("/opt/processmind")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
HOST_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]\Z")


def approved_commit(run: object, main_sha: str) -> str | None:
    """Accept only a successful push CI run for the exact current main head."""
    if not isinstance(run, dict):
        return None
    repository = run.get("head_repository")
    sha = run.get("head_sha")
    if not isinstance(repository, dict) or not isinstance(sha, str):
        return None
    if not SHA_PATTERN.fullmatch(sha) or sha != main_sha:
        return None
    if (
        repository.get("full_name") != REPOSITORY
        or run.get("head_branch") != "main"
        or run.get("event") != "push"
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
    ):
        return None
    return sha


def current_main_sha() -> str:
    """Read the public Git remote directly before trusting the CI response."""
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "origin", "refs/heads/main"],
        cwd=CHECKOUT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    sha = result.stdout.split("\t", 1)[0]
    if not SHA_PATTERN.fullmatch(sha):
        raise ValueError("Git returned an invalid main commit")
    return sha


def latest_ci_run() -> object:
    """Query the public GitHub API without creating a token on the VM."""
    request = Request(
        WORKFLOW_RUNS,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "processmind-demo-deploy-poller",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=30) as response:
        runs = json.load(response).get("workflow_runs", [])
    return runs[0] if runs else None


def main() -> None:
    """Run the existing guarded deploy only when CI and Git agree on main."""
    host = os.environ.get("DEMO_HOST", "")
    if not HOST_PATTERN.fullmatch(host):
        raise SystemExit("DEMO_HOST must be a public DNS hostname")
    if not (CHECKOUT / ".env").is_file():
        raise SystemExit("Initial bootstrap and private .env are required")
    sha = approved_commit(latest_ci_run(), current_main_sha())
    if sha is None:
        print("No successful CI run for the current main head; deploy skipped")
        return
    subprocess.run(
        ["bash", "scripts/deploy_demo.sh", sha, host],
        cwd=CHECKOUT,
        check=True,
        timeout=7200,
    )


if __name__ == "__main__":
    main()
