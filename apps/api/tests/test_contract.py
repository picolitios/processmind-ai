from pathlib import Path

import yaml

from app.main import app


def test_implemented_routes_are_in_mvp_contract() -> None:
    contract_path = Path(__file__).resolve().parents[3] / "specs/architecture/openapi.yaml"
    planned = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    implemented = app.openapi()
    for path, operations in implemented["paths"].items():
        planned_path = path.removeprefix("/api/v1")
        assert planned_path in planned["paths"], path
        for method in operations:
            assert method in planned["paths"][planned_path], (method, path)
    assert "APIKeyCookie" in implemented["components"]["securitySchemes"]
