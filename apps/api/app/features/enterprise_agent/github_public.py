"""Read one bounded public GitHub text file without accepting arbitrary URLs."""

import base64
import binascii
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.errors import ApiError

MAX_RESPONSE_BYTES = 64 * 1024
MAX_CONTENT_BYTES = 40 * 1024
MAX_CONTENT_CHARS = 20000


@dataclass(frozen=True)
class PublicDocument:
    content: str
    blob_sha: str
    checked_at: datetime


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A moved repository cannot silently change the authorized target."""

    def redirect_request(self, request: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def fetch_public_document(owner: str, repo: str, path: str) -> PublicDocument:
    """Fetch a small UTF-8 snapshot from the fixed GitHub Contents API host."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ProcessMindAI-public-document-connector",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ApiError(
                422, "github_document_missing", "Arquivo público não encontrado"
            ) from exc
        if exc.code in {403, 429}:
            raise ApiError(
                503, "github_rate_limited", "GitHub temporariamente indisponível"
            ) from exc
        raise ApiError(503, "github_unavailable", "Não foi possível consultar o GitHub") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ApiError(503, "github_unavailable", "Não foi possível consultar o GitHub") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise ApiError(422, "github_document_too_large", "Documento excede o limite")
    try:
        payload = json.loads(body)
        if (
            not isinstance(payload, dict)
            or payload.get("type") != "file"
            or payload.get("encoding") != "base64"
            or not isinstance(payload.get("content"), str)
            or not isinstance(payload.get("sha"), str)
            or re.fullmatch(r"[0-9a-f]{40}", payload["sha"]) is None
            or payload.get("path") != path
        ):
            raise ValueError("invalid_github_response")
        raw = base64.b64decode("".join(payload["content"].split()), validate=True)
        if len(raw) > MAX_CONTENT_BYTES:
            raise ApiError(422, "github_document_too_large", "Documento excede o limite")
        content = raw.decode("utf-8")
        if len(content) > MAX_CONTENT_CHARS:
            raise ApiError(422, "github_document_too_large", "Documento excede o limite")
        if not content.strip() or any(
            ord(char) < 32 and char not in "\n\t\r" for char in content
        ):
            raise ValueError("invalid_text")
    except ApiError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, binascii.Error) as exc:
        raise ApiError(422, "github_document_invalid", "Arquivo não é texto válido") from exc
    return PublicDocument(content=content, blob_sha=payload["sha"], checked_at=datetime.now(UTC))
