"""Public connector contracts: fixed host, bounded snapshots and tenant gates."""

import base64
import io
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.message import Message

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_identity import create_org, create_user, csrf_headers, login

from app.core.errors import ApiError
from app.features.enterprise_agent.github_public import PublicDocument, fetch_public_document
from app.features.enterprise_agent.schemas import GitHubDocumentInput
from app.main import app


def _payload(content: bytes, sha: str = "a" * 40) -> bytes:
    return json.dumps({
        "type": "file", "encoding": "base64", "path": "README.md", "sha": sha,
        "content": base64.b64encode(content).decode(),
    }).encode()


def test_github_path_validation_rejects_url_and_traversal() -> None:
    for path in ("https://example.com/a.md", "../README.md", "/README.md", "docs/a.html"):
        with pytest.raises(ValidationError):
            GitHubDocumentInput(owner="picolitios", repo="processmind-ai", path=path,
                                title="Manual", enabled=True)


def test_fixed_github_transport_and_text_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    class Opener:
        def __init__(self, body: bytes) -> None:
            self.body = body

        def open(self, request: urllib.request.Request, timeout: int) -> io.BytesIO:
            assert request.full_url == (
                "https://api.github.com/repos/picolitios/processmind-ai/contents/README.md"
            )
            assert timeout == 10
            assert request.get_header("Authorization") is None
            return io.BytesIO(self.body)

    monkeypatch.setattr(urllib.request, "build_opener", lambda handler: Opener(_payload(b"Manual")))
    result = fetch_public_document("picolitios", "processmind-ai", "README.md")
    assert result.content == "Manual" and result.blob_sha == "a" * 40

    for body, code in (
        (_payload(b"a\x00b"), "github_document_invalid"),
        (_payload(b"x" * 40001), "github_document_too_large"),
        (b"not-json", "github_document_invalid"),
    ):
        monkeypatch.setattr(urllib.request, "build_opener", lambda handler, body=body: Opener(body))
        with pytest.raises(ApiError) as exc:
            fetch_public_document("picolitios", "processmind-ai", "README.md")
        assert exc.value.code == code


def test_github_transport_does_not_follow_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    class Redirecting:
        def open(self, request: urllib.request.Request, timeout: int) -> io.BytesIO:
            raise urllib.error.HTTPError(request.full_url, 302, "moved", Message(), None)

    monkeypatch.setattr(urllib.request, "build_opener", lambda handler: Redirecting())
    with pytest.raises(ApiError) as exc:
        fetch_public_document("picolitios", "processmind-ai", "README.md")
    assert exc.value.status_code == 503


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="PostgreSQL test database required")
def test_github_source_import_refresh_and_revocation(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.enterprise_agent import routes

    current = PublicDocument("Procedimento sintético inicial.", "a" * 40, datetime.now(UTC))
    monkeypatch.setattr(routes, "fetch_public_document", lambda *args: current)
    with TestClient(app) as owner, TestClient(app) as outsider, TestClient(app) as viewer:
        csrf = login(owner, create_user(owner, "github-owner"))
        outsider_csrf = login(outsider, create_user(outsider, "github-outsider"))
        viewer_email = create_user(viewer, "github-viewer")
        viewer_csrf = login(viewer, viewer_email)
        org = create_org(owner, csrf, "github-org")
        base = f"/api/v1/organizations/{org}"
        member = owner.post(f"{base}/users", headers=csrf_headers(csrf),
                            json={"email": viewer_email, "role": "viewer"})
        assert member.status_code == 201
        endpoint = f"{base}/integrations/github-public/documents"
        data = {"owner": "picolitios", "repo": "processmind-ai", "path": "README.md",
                "title": "Manual do produto", "enabled": True}
        assert owner.post(endpoint, json=data).status_code == 403
        assert (
            outsider.post(endpoint, headers=csrf_headers(outsider_csrf), json=data).status_code
            == 404
        )
        assert (
            viewer.post(endpoint, headers=csrf_headers(viewer_csrf), json=data).status_code
            == 403
        )
        created = owner.post(endpoint, headers=csrf_headers(csrf), json=data)
        assert created.status_code == 201, created.text
        source_id = created.json()["id"]
        assert created.json()["type"] == "github_public"
        assert created.json()["github_blob_sha"] == "a" * 40
        assert created.json()["content"] == current.content
        assert owner.post(endpoint, headers=csrf_headers(csrf), json=data).status_code == 409
        assert outsider.get(f"{base}/integrations/knowledge/{source_id}").status_code == 404
        assert viewer.get(f"{base}/integrations/knowledge/{source_id}").status_code == 200
        assert outsider.post(f"{endpoint}/{source_id}/refresh",
                             headers=csrf_headers(outsider_csrf)).status_code == 404
        capabilities = owner.get(f"{base}/agent/capabilities").json()
        assert capabilities["knowledge_available"] is True
        assert {tool["id"]: tool["enabled"] for tool in capabilities["tools"]} == {
            "managed_knowledge": False, "github_public": True, "purchasing_audit": True,
        }
        assert (
            owner.patch(f"{base}/integrations/knowledge/{source_id}",
                        headers=csrf_headers(csrf), json={"content": "forjado"}).status_code
            == 422
        )
        assert owner.post(f"{endpoint}/{source_id}/refresh",
                          headers=csrf_headers(csrf)).json()["revision"] == 1

        current = PublicDocument("Procedimento sintético revisado.", "b" * 40, datetime.now(UTC))
        refreshed = owner.post(f"{endpoint}/{source_id}/refresh", headers=csrf_headers(csrf))
        assert refreshed.status_code == 200
        assert refreshed.json()["revision"] == 2
        assert refreshed.json()["content"] == current.content
        monkeypatch.setattr(routes, "fetch_public_document", lambda *args: (_ for _ in ()).throw(
            ApiError(503, "github_unavailable", "GitHub indisponível")))
        assert owner.post(f"{endpoint}/{source_id}/refresh",
                          headers=csrf_headers(csrf)).status_code == 503
        assert owner.get(f"{base}/integrations/knowledge/{source_id}").json()["revision"] == 2
        disabled = owner.patch(f"{base}/integrations/knowledge/{source_id}",
                               headers=csrf_headers(csrf), json={"enabled": False})
        assert disabled.status_code == 200
        assert owner.get(f"{base}/agent/capabilities").json()["knowledge_available"] is False
        assert viewer.get(f"{base}/integrations/knowledge/{source_id}").status_code == 404
