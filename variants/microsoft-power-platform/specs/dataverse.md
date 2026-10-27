# Dataverse decision

Dataverse is **not used** for this variant's audit, finding or evidence data.
PostgreSQL in ProcessMind already owns these records, including tenant isolation,
relationships, versions and citations. A second business copy would introduce
freshness, deletion and authorization problems without improving the demo.

If the tenant later needs integration metadata, a solution-owned table could
track only `AuditId`, `OrganizationId`, `RequesterEntraObjectId`, `NotificationState`
and timestamps. It would need organization-scoped ownership, restricted security
roles, retention, duplicate prevention and a reconciliation policy. This table
is a proposal, not an implemented or necessary component. No user business data
is stored in Dataverse by the local implementation.
