"""Session-scoped client for a local, authenticated ProcessMind demonstration."""

from __future__ import annotations

import uuid
from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError

Model = TypeVar("Model", bound=BaseModel)


class IntegrationError(Exception):
    """Safe failure category for callers; never contains credentials or response bodies."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class Page(BaseModel):
    items: list[dict[str, Any]]
    next_cursor: str | None


class Audit(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    finding_count: int = Field(ge=0)
    limitation: str | None = None
    import_ids: list[uuid.UUID]


class Evidence(BaseModel):
    id: uuid.UUID
    type: Literal["purchase", "import_row"]
    data: dict[str, Any]


class Finding(BaseModel):
    id: uuid.UUID
    audit_id: uuid.UUID
    rule_code: str
    severity: Literal["low", "medium", "high", "critical"]
    explanation: str
    evidence: list[Evidence]


class Citation(BaseModel):
    evidence_id: uuid.UUID
    finding_id: uuid.UUID
    audit_id: uuid.UUID


class Question(BaseModel):
    id: uuid.UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    limitation: str | None = None


class ProcessMindClient:
    """Preserves the user's own session, CSRF token, and tenant boundary."""

    def __init__(
        self, base_url: str, organization_id: uuid.UUID, *, client: httpx.Client | None = None
    ) -> None:
        if not base_url.startswith(("http://127.0.0.1:", "http://localhost:", "https://")):
            raise ValueError("Use HTTPS or a loopback address")
        self.organization_id = organization_id
        self.http = client or httpx.Client(
            base_url=base_url.rstrip("/"), timeout=10.0, trust_env=False
        )
        self.origin = base_url.rstrip("/")
        self.csrf: str | None = None

    def __enter__(self) -> ProcessMindClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.http.close()

    def _request(self, method: str, path: str, *, json: object = None,
                 idempotency_key: str | None = None) -> dict[str, Any]:
        headers = {"Origin": self.origin}
        if method != "GET":
            if not self.csrf and path != "/api/v1/auth/login":
                raise IntegrationError("session_required")
            if self.csrf:
                headers["X-CSRF-Token"] = self.csrf
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = self.http.request(method, path, json=json, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise IntegrationError("backend_unavailable") from exc
        if response.status_code in (401, 403):
            raise IntegrationError("access_denied")
        if response.status_code == 404:
            raise IntegrationError("not_found")
        if response.status_code == 409:
            raise IntegrationError("conflict")
        if response.status_code == 422:
            raise IntegrationError("invalid_input")
        if response.status_code >= 400:
            raise IntegrationError("backend_failure")
        try:
            payload = response.json()
        except ValueError as exc:
            raise IntegrationError("invalid_response") from exc
        if not isinstance(payload, dict):
            raise IntegrationError("invalid_response")
        return payload

    def _parse(self, model: type[Model], payload: dict[str, Any]) -> Model:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise IntegrationError("invalid_response") from exc

    def login(self, email: str, password: str) -> None:
        """Acquire a real ProcessMind session for local use; secrets stay in memory."""
        if not email or not password:
            raise IntegrationError("invalid_input")
        payload = self._request("POST", "/api/v1/auth/login",
                                json={"email": email, "password": password})
        token = payload.get("csrf_token")
        if not isinstance(token, str) or not token:
            raise IntegrationError("invalid_response")
        self.csrf = token

    def _org_path(self, suffix: str) -> str:
        return f"/api/v1/organizations/{self.organization_id}{suffix}"

    def audits(self) -> list[Audit]:
        """List the first bounded page; callers must not assume it is exhaustive."""
        payload = self._request("GET", self._org_path("/audits?limit=50"))
        page = self._parse(Page, payload)
        return [self._parse(Audit, item) for item in page.items]

    def audit(self, audit_id: uuid.UUID) -> Audit:
        return self._parse(Audit, self._request("GET", self._org_path(f"/audits/{audit_id}")))

    def findings(self, audit_id: uuid.UUID) -> list[Finding]:
        payload = self._request("GET", self._org_path(f"/findings?audit_id={audit_id}&limit=50"))
        page = self._parse(Page, payload)
        return [self._parse(Finding, item) for item in page.items]

    def request_audit(self, import_ids: list[uuid.UUID], key: str) -> Audit:
        if not 1 <= len(import_ids) <= 50 or len(set(import_ids)) != len(import_ids):
            raise IntegrationError("invalid_input")
        if not 8 <= len(key) <= 128:
            raise IntegrationError("invalid_input")
        payload = self._request("POST", self._org_path("/audits"),
                                json={"import_ids": [str(item) for item in import_ids]},
                                idempotency_key=key)
        return self._parse(Audit, payload)

    def create_conversation(self, audit_id: uuid.UUID) -> uuid.UUID:
        payload = self._request("POST", self._org_path("/ai/copilot/conversations"),
                                json={"audit_id": str(audit_id), "mode": "temporary"})
        if payload.get("status") != "active":
            raise IntegrationError("conversation_pending")
        try:
            return uuid.UUID(str(payload["id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise IntegrationError("invalid_response") from exc

    def ask(self, conversation_id: uuid.UUID, question: str, key: str) -> uuid.UUID:
        if not 1 <= len(question.strip()) <= 1000 or not 8 <= len(key) <= 128:
            raise IntegrationError("invalid_input")
        payload = self._request("POST", self._org_path(
            f"/ai/copilot/conversations/{conversation_id}/questions"),
            json={"question": question}, idempotency_key=key)
        try:
            return uuid.UUID(str(payload["question_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise IntegrationError("invalid_response") from exc

    def question(self, question_id: uuid.UUID) -> Question:
        payload = self._request("GET", self._org_path(f"/ai/copilot/questions/{question_id}"))
        result = self._parse(Question, payload)
        if result.status == "succeeded" and (not result.answer or not result.citations):
            raise IntegrationError("unverified_answer")
        return result
