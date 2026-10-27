# Testing strategy and results

The local test suite covers verified paths, tenant path scoping, CSRF header,
idempotency, invalid input, denied access, 404/409/422/503 responses, malformed
backend data, unverified answers and timeout. It uses an HTTP mock transport,
not a fake business algorithm. The original backend remains the integration
target for manual local demonstration.

Baseline before changes: `apps/api/.venv/Scripts/python.exe -m pytest
tests/test_audit_rules.py tests/test_contract.py -q` from `apps/api`:
**4 passed**. An initial invocation with the global Python failed collection
because it lacked SQLAlchemy and PyYAML; rerunning in the project venv passed.

Variant ordinary suite: 12 passed, 1 optional database test skipped; Ruff and
strict mypy passed. The optional end-to-end test passed against a fresh,
migrated `processmind_power_e2e` PostgreSQL database. It exercised actual
registration, session, CSV import, import worker, audit request, audit worker,
findings, conversation/question routes, citation validation and outsider denial.
Only Ollama inference was replaced by an explicitly labeled deterministic
response. Reproduce with `scripts/test-live.ps1`.

Original regression (`test_identity.py`, `test_audit_api.py`, `test_copilot.py`)
on a separate migrated `processmind_power_demo` database: **16 passed**.
Original `ruff check app` and `mypy app`: passed (66 source files checked by
mypy). The initial no-database run of selected tests had 4 passed and 13 skipped.
Cloud agent/app/flow tests require tenant access and have not been run. The
running Compose application database was not used as a test database.
