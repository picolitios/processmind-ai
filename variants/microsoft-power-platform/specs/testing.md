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

Variant checks: 12 tests passed; Ruff and strict mypy passed. Original
regression (`test_audit_rules.py`, `test_contract.py`, `test_audit_api.py`,
`test_copilot.py`): 4 passed, 13 skipped because `RUN_DB_TESTS` was unset.
Original `ruff check app` and `mypy app`: passed (66 source files checked by
mypy). Database-backed regression and a live CLI journey were not executed;
the running Compose database was not repurposed as an isolated test database.
Cloud agent/app/flow tests require tenant access and have not been run. The mock
contract suite alone does not prove live service connectivity.
