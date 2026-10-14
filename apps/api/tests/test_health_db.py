import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL not configured for test")
def test_readiness_with_database() -> None:
    response = TestClient(app).get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
