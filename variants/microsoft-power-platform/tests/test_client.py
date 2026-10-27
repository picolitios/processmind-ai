"""Contract and failure tests for the isolated HTTP integration."""

import uuid

import httpx
import pytest

from processmind_power.client import IntegrationError, ProcessMindClient

ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
AUDIT = uuid.UUID("22222222-2222-2222-2222-222222222222")
EVIDENCE = uuid.UUID("33333333-3333-3333-3333-333333333333")


def make_client(handler: httpx.MockTransport) -> ProcessMindClient:
    return ProcessMindClient("http://127.0.0.1:5173", ORG, client=httpx.Client(
        transport=handler, base_url="http://127.0.0.1:5173"))


def test_real_paths_session_csrf_tenant_and_idempotency() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(200, json={"csrf_token": "csrf-value"})
        return httpx.Response(202, json={"id": str(AUDIT), "status": "queued",
                                         "finding_count": 0, "import_ids": [str(EVIDENCE)]})

    with make_client(httpx.MockTransport(respond)) as api:
        api.login("analyst@example.test", "secret")
        audit = api.request_audit([EVIDENCE], "same-request-key")
    assert audit.status == "queued"
    assert seen[1].url.path == f"/api/v1/organizations/{ORG}/audits"
    assert seen[1].headers["X-CSRF-Token"] == "csrf-value"
    assert seen[1].headers["Idempotency-Key"] == "same-request-key"
    assert seen[1].headers["Origin"] == "http://127.0.0.1:5173"


def test_invalid_inputs_never_reach_backend() -> None:
    def unexpected(_request: httpx.Request) -> httpx.Response:
        pytest.fail("backend must not be called")

    with make_client(httpx.MockTransport(unexpected)) as api:
        with pytest.raises(IntegrationError, match="invalid_input"):
            api.request_audit([AUDIT, AUDIT], "reused-key")
        with pytest.raises(IntegrationError, match="invalid_input"):
            api.ask(AUDIT, " ", "question-key")


@pytest.mark.parametrize("status,code", [(403, "access_denied"), (404, "not_found"),
                                          (409, "conflict"), (422, "invalid_input"),
                                          (503, "backend_failure")])
def test_http_failures_are_safe(status: int, code: str) -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="private server details")

    with make_client(httpx.MockTransport(respond)) as api:
        with pytest.raises(IntegrationError, match=code) as error:
            api.audit(AUDIT)
    assert "private" not in str(error.value)


def test_invalid_backend_payload_rejected() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"id": str(AUDIT)}))
    with make_client(transport) as api:
        with pytest.raises(IntegrationError, match="invalid_response"):
            api.audit(AUDIT)


def test_unverified_answer_is_never_shown_as_success() -> None:
    payload = {"id": str(AUDIT), "status": "succeeded", "answer": "Invented result",
               "citations": []}
    with make_client(httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as api:
        with pytest.raises(IntegrationError, match="unverified_answer"):
            api.question(AUDIT)


def test_findings_preserve_only_real_evidence_data() -> None:
    payload = {"items": [{"id": str(EVIDENCE), "audit_id": str(AUDIT),
                          "rule_code": "DUPLICATE", "severity": "medium",
                          "explanation": "Review repeated purchase",
                          "evidence": [{"id": str(EVIDENCE), "type": "purchase",
                                        "data": {"purchase_id": str(AUDIT)}}]}],
               "next_cursor": None}
    with make_client(httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as api:
        findings = api.findings(AUDIT)
    assert findings[0].evidence[0].data == {"purchase_id": str(AUDIT)}


def test_malformed_citation_is_rejected() -> None:
    payload = {"id": str(AUDIT), "status": "succeeded", "answer": "Check evidence",
               "citations": [{"evidence_id": str(EVIDENCE)}]}
    with make_client(httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as api:
        with pytest.raises(IntegrationError, match="invalid_response"):
            api.question(AUDIT)


def test_network_timeout_is_bounded() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret URL")

    with make_client(httpx.MockTransport(timeout)) as api:
        with pytest.raises(IntegrationError, match="backend_unavailable"):
            api.audits()
