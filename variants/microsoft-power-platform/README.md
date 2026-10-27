# ProcessMind AI · Microsoft Power Platform variant

This isolated portfolio variant demonstrates the integration contract for a business
help copilot. The **local layer is executable** and uses the existing ProcessMind API.
The **Microsoft layer is a configuration blueprint**; no tenant, license, cloud flow,
connector, or published agent was available for validation. The original application
and its database schema are unchanged.

## What exists

| Component | State |
| --- | --- |
| Session-scoped Python API client and CLI | Implemented and tested locally |
| Audit list, status, findings, request, evidence-backed question | Uses verified backend routes |
| Copilot Studio agent, Power Apps canvas app, Power Automate flows | Documented build instructions; cloud setup required |
| Dataverse | Deliberately omitted as a data store |
| Direct Microsoft-to-backend authentication | Architecture gap; requires delegated identity integration |

## Local setup

Run the original stack per the root README. Use a **test organization and synthetic
imports**; the audit request command creates a real audit. Python 3.12 is required.

```powershell
cd variants/microsoft-power-platform
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:PM_BASE_URL = "http://localhost:5173"
$env:PM_ORGANIZATION_ID = "<organization UUID>"
$env:PM_EMAIL = "<existing user email>"
$env:PM_PASSWORD = "<password>"
.\.venv\Scripts\python.exe -m processmind_power.cli audits
.\.venv\Scripts\python.exe -m processmind_power.cli request-audit --import-id "<completed import UUID>"
.\.venv\Scripts\python.exe -m processmind_power.cli findings --audit-id "<audit UUID>"
.\.venv\Scripts\python.exe -m processmind_power.cli ask --audit-id "<succeeded audit UUID>" --question "Quais achados exigem revisão?"
```

Use the nginx gateway at port 5173 so login, business API, cookie and expected
`Origin` share one origin. The root `.env.example` sets `WEB_ORIGIN` to
`http://localhost:5173`; use that exact host or adjust both settings together.
Environment values remain local to the shell. Never
commit them. The `ask` command waits up to 30 seconds; if still queued, rerun
the existing application's UI or use the API to retrieve the returned question ID.
The local Ollama worker must be enabled to produce a model answer. Without it,
the backend returns an explicit limitation.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy processmind_power
```

The suite uses `httpx.MockTransport`; it never needs Microsoft credentials or
mutates the original application. See [testing](specs/testing.md) for actual results.
Synthetic contract payloads are in `examples/`; they are explicitly not real findings.

## Architecture and setup

Start with [architecture](specs/architecture.md), then the [deployment sequence](specs/deployment.md).
Build instructions: [agent](specs/copilot-studio-agent.md), [app](specs/power-apps.md),
[flows](specs/power-automate.md), [Dataverse decision](specs/dataverse.md).
The [interview guide](specs/interview-guide.md) summarizes design decisions.

## Troubleshooting

| Result | Action |
| --- | --- |
| `access_denied` | Check session, organization membership and role. |
| `backend_unavailable` | Check Docker services and gateway address. |
| `invalid_response` | Check API version against the verified contracts below. |
| `audit_not_completed` | Wait for the audit worker/consumer and inspect status. |
| `unverified_answer` | Do not show the text; inspect server evidence validation. |
| Failed/empty AI answer | Enable the optional local model or report the limitation. |

The cloud configuration cannot securely reuse a shared ProcessMind cookie for
multiple users. The required identity bridge is specified in deployment; until
implemented, do not connect production Power Apps or Copilot Studio to this API.
