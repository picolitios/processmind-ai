"""Check links and local OpenAPI references in Phase 0 documentation."""

from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "specs" / "architecture" / "openapi.yaml"


def main() -> None:
    document = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    assert document["openapi"] == "3.1.0"
    assert document["servers"][0]["url"] == "/api/v1"

    references: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "$ref":
                    assert isinstance(child, str) and child.startswith("#/"), child
                    references.add(child)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    for reference in references:
        target: object = document
        for part in reference.removeprefix("#/").split("/"):
            assert isinstance(target, dict) and part in target, reference
            target = target[part]

    for path, operations in document["paths"].items():
        path_parameters = set(re.findall(r"\{([^}]+)\}", path))
        for method, operation in operations.items():
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            defined = {
                item.get("name")
                if "$ref" not in item
                else item["$ref"].rsplit("/", 1)[-1]
                for item in operation.get("parameters", [])
            }
            for parameter in path_parameters:
                assert parameter in defined or "".join(
                    word.capitalize() for word in parameter.split("_")
                ) in defined, f"{method.upper()} {path}: {parameter} missing"
            assert operation.get("responses"), f"{method.upper()} {path}: responses missing"

    for document_path in [ROOT / "README.md", *ROOT.glob("specs/**/*.md")]:
        text = document_path.read_text(encoding="utf-8")
        for destination in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text):
            if "://" in destination:
                continue
            assert (document_path.parent / destination).exists(), (
                document_path,
                destination,
            )

    print(f"Validated {len(document['paths'])} API paths and {len(references)} references")


if __name__ == "__main__":
    main()
