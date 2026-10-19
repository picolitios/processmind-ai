# Isolated upload-volume restore proof v1

Status: approved extension of `local-backup-restore-v1.md` for the disposable CI stack.
The backup archive, manifest and operator restore procedure do not change.

## Contract and acceptance

1. After the quiesced backup and isolated database restore, CI creates a new
   Docker upload volume. It extracts the archive into that volume, without
   mounting or modifying the source application's upload volume.
2. A separate verifier reads the archive and restored volume, compares every
   file byte-for-byte by streaming SHA-256, rejects missing/extra files and
   unsafe paths, and requires each import key from the restored database.
   At least one synthetic import must be present so an empty proof cannot pass.
3. CI removes the temporary volume after the check. No upload content or
   archive is attached to the workflow. Unit tests cover corruption, extra
   files and a missing database reference.
4. The proof establishes a local, isolated volume restore. It does not provide
   production backup scheduling, offsite retention or a measured RPO/RTO.
