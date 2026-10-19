# Local backup and isolated restore v1

Status: approved operational increment for the existing single-host Compose deployment.
The PostgreSQL database and private upload volume together hold the durable
business record. RabbitMQ is a dispatch mechanism, not the recovery source.

## Contract

1. The operator first blocks new requests and drains audit dispatch. The backup
   command refuses to run while any application writer is running, an outbox
   event is unpublished, or an audit queue contains messages. It never stops
   services or changes business data on its own.
2. With PostgreSQL and RabbitMQ still running, the command writes a custom
   `pg_dump` archive, a tar archive of the upload volume, and a JSON manifest
   with SHA-256 checksums. It uses a new output directory; an incomplete backup
   is never named as a completed backup. Backup contents are sensitive and must
   remain outside Git with host permissions and encryption appropriate to the
   deployment.
3. Restore uses a fresh, isolated environment and empty volumes. Validate the
   manifest and restore the database and upload archive before starting any
   application process. Do not merge this backup into a live database. A fresh
   RabbitMQ starts empty only because the preflight proved all audit queues and
   unpublished outbox records empty.
4. This local procedure has downtime. It does not establish a production
   recovery time objective, offsite retention, automated scheduling, or high
   availability.

## Acceptance

- Tests cover writer/queue/pending-outbox rejection, archive verification and
  output-directory safety.
- An isolated Compose CI stack creates real data, exports both archives,
  restores the database into a new database, reprovisions runtime grants, and
  compares counts. The upload archive is inspected, checksummed and extracted
  in an isolated temporary directory.
- No customer data, archive or credential is uploaded as a CI artifact.
