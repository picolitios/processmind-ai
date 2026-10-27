# Feature specification and Definition of Done

Scope: a separate Microsoft Power Platform demonstration of the existing purchase
audit and evidence-backed copilot. The original implementation is the source of
truth. This variant must never generate unsupported findings or silently imply
that a cloud integration has been deployed.

Acceptance: (1) local client calls real tenant-scoped routes with session, CSRF
and idempotency; (2) bounded audit and finding reads map actual response contracts;
(3) a request returns a job/audit status without waiting for completion; (4)
copilot answers appear as verified only with server citations; (5) errors and
timeouts have predictable safe codes; (6) cloud assets describe supported build
steps and the missing identity boundary; (7) original code is unchanged and
tests/lint/types pass. Cloud deployment and licensing are explicit prerequisites,
not acceptance claims for the local variant.

Edge cases: no audits or findings; queued/failed audits; no local model;
cross-organization access; viewer role; invalid import IDs; duplicate request
key; timed-out backend; malformed response; missing or unverified citations.

The client deliberately limits lists to 50 items. Pagination is part of the
backend contract and must be implemented in the cloud connector before a
production business UI claims exhaustive results.
