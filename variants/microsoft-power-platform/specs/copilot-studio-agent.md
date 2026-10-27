# Copilot Studio agent blueprint

**Purpose:** help an authorized business user understand ProcessMind purchase
audits and their evidence. Language: Portuguese. This is a manual blueprint,
not an importable agent package.

## Instructions to configure

> Answer questions using only data returned by the ProcessMind actions for the
> active user and organization. Distinguish a queued or failed audit from a
> completed one. Never invent a metric, finding, bottleneck, recommendation,
> evidence ID or citation. For each recommendation, identify the finding and
> evidence that supports it; describe an action for human review, not a fraud
> verdict. If no evidence or action result is available, say so and suggest
> checking the audit status. Do not request passwords or tokens in chat.

These instructions guide wording only. Backend authorization and citation
validation remain mandatory.

## Intents and actions

| Intent | Inputs | Action / output |
| --- | --- | --- |
| List recent audits | Active organization | `ListAudits` returns bounded IDs/status |
| Check status | Audit ID | `GetAudit` returns queued/running/succeeded/failed |
| Explain findings | Completed audit ID | `ListFindings`, with evidence IDs and severity |
| Request analysis | Completed import IDs, explicit user request | `RequestAudit`; reply with audit ID and queued state |
| Ask about an audit | Completed audit ID, question | `CreateTemporaryConversation`, `AskQuestion`, then later `GetQuestion` |

Tool descriptions must say they read or request **actual** ProcessMind data.
Require explicit audit selection when more than one is plausible. Do not pass a
user-typed organization ID as an authorization claim; the connector/backend
identity mapping must determine membership. Use a bounded result with next-page
indicator. A missing result, 403, 404, timeout or invalid citation produces a
clear limitation without extrapolating findings.

For an agent flow, configure **When an agent calls the flow**, **Respond to the
agent**, and real-time response in the same solution/environment. Return audit
request acknowledgment immediately; never hold the flow open until the audit
worker completes. Microsoft's [agent-flow requirements](https://learn.microsoft.com/microsoft-copilot-studio/flow-modify-use-with-agent)
state the real-time action has a 100-second response limit. Add the published
flow as a tool through the agent's Tools page as described by
[Microsoft](https://learn.microsoft.com/en-us/microsoft-copilot-studio/advanced-use-flow).

The existing model is local Ollama. If unavailable, the agent may summarize
deterministic findings with citations, but must not present a model answer as
if it had been generated and validated.
