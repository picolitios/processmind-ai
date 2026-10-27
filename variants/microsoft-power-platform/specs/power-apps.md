# Power Apps canvas app blueprint

Build a small responsive canvas app inside the same solution as the flows. It
is a manual build plan and Power Fx examples, not a validated `.msapp` package.
The app must use a **per-user delegated connection** after the identity bridge
in [deployment](deployment.md) exists. Do not place ProcessMind credentials,
session cookies or CSRF tokens in formulas or app variables.

| Screen | Controls and state |
| --- | --- |
| Dashboard | Summary cards of bounded recent audits, counts by status; loading, empty and error banners |
| Select audit | Gallery with ID/status; select a completed audit; next-page control |
| Audit detail | Status, finding count, failure limitation and refresh button |
| Findings | Gallery of actual `rule_code`, severity, explanation and evidence IDs; no inferred scores |
| Recommendations | Human review suggestions tied to a selected finding/evidence; label them as proposed actions |
| Request analysis | Import ID selector, required validation, submit and queued confirmation |

Data sources: `ListAudits`, `GetAudit`, `ListFindings`, `RequestAudit` flows.
The backend currently exposes purchases/imports, not a general process catalog.
An audit is the selection unit. An import must already be completed using the
original application's import workflow before it can be audited.

Illustrative Power Fx (flow names/outputs must be aligned in the tenant):

```powerfx
// Audit gallery: refresh with a visible loading state.
Set(varLoading, true);
Set(varAuditResult, ListAudits.Run());
Set(varLoading, false);
If(varAuditResult.ok, ClearCollect(colAudits, varAuditResult.items),
   Notify(varAuditResult.message, NotificationType.Error))

// Request button: validate before starting an asynchronous audit.
If(IsBlank(ddImport.Selected.importId),
   Notify("Selecione uma importação concluída", NotificationType.Error),
   Set(varRequest, RequestAudit.Run(ddImport.Selected.importId, Text(GUID())));
   If(varRequest.ok,
      Notify("Auditoria solicitada: " & varRequest.auditId, NotificationType.Success),
      Notify(varRequest.message, NotificationType.Error)))
```

`GUID()` must be generated once per user request and reused for retries; the
flow passes it as the backend idempotency key. For a page beyond the first,
pass `next_cursor` unchanged. `GetAudit` drives a refresh button/timer with a
reasonable interval. Stop polling when succeeded/failed or on navigation.
Power Apps [connections](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/add-manage-connections)
must be shared/configured per app user. Formula names and separators may require
adjustment for the target locale.
