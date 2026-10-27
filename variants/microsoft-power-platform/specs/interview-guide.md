# Interview guide

**Scenario:** an analyst selects a completed import, requests an asynchronous
purchase audit, checks status, reviews deterministic findings and asks for a
helpful evidence-backed explanation. The agent may propose a human review
action but never declares fraud or creates unsupported metrics.

**Why keep the backend?** Existing import, audit rules, jobs, citations and
tenant checks are already implemented. Power Platform adds business surfaces
and orchestration; duplicating the rules would split the source of truth.

**Why no Dataverse copy?** PostgreSQL already stores the operational records.
Dataverse is optional only for future notification metadata.

**Hardest integration point:** the current browser session and CSRF contract
does not equal delegated Entra authorization. A shared connector account risks
cross-user access. The required bridge must verify identity and membership on
the server; agent prompts are never a security boundary.

**Why asynchronous flows?** Audit creation returns 202 and RabbitMQ/worker
finishes later. The flow returns the audit ID immediately, and later reads
status/results. Agent actions have bounded real-time response requirements.

**What is proven?** The isolated Python client and contract/error tests.
**What remains?** Tenant licensing, identity bridge, connector, cloud flows,
canvas app, agent publication and two-user security tests. Do not present the
blueprints as deployed artifacts.
