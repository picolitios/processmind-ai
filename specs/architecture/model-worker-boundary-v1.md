# Model worker process boundary v1

Status: approved incremental extraction after the audit broker recovery gate.
The business API and `jobs` table remain unchanged. This is process isolation
for slow local model calls, not independent AI data ownership.

## Contract

1. `WORKER_JOB_GROUP=import` claims only import jobs.
   `WORKER_JOB_GROUP=model` claims AI explanation and copilot jobs, including
   expired leases for those types, and purges expired temporary chats.
   Both use the existing transactional `FOR UPDATE SKIP LOCKED` claim.
2. The default `auto` retains the preexisting behavior: import, explanation
   and copilot in broker dispatch mode; those plus audit in database rollback
   mode. Invalid group values fail configuration validation. An explicit
   `all` group retains the same set as `auto` for local debugging.
3. Compose runs one import worker and one model worker. The model worker owns
   Ollama connection settings; the import worker owns the upload volume.
   Neither changes the public API, job payload or schema.
4. Both processes retain current three-attempt/lease recovery. Model outages
   cannot claim import jobs, and import work cannot claim model jobs. Database
   audit fallback remains available in `auto` or `all` mode outside the
   standard Compose broker deployment.

## Acceptance

- Unit tests cover all group/dispatch combinations, invalid configuration,
  and which process runs temporary-chat cleanup.
- The existing API regression and copilot tests pass; lint and types pass.
- Compose configuration validates and both worker processes start. A normal
  import still completes with the model worker running separately.

## Limits

These workers still share the business schema and Python image. A future AI
service with exclusive data ownership requires versioned contracts for audit
evidence, job state and copilot memory, plus a separate migration. No claim
of completed AI microservice extraction is made here.
