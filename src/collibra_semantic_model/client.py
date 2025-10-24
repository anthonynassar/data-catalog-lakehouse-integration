"""HTTP clients for the Collibra Knowledge Graph API."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CollibraGraphQLClient:
    """Thin wrapper around Collibra's Knowledge Graph GraphQL endpoint."""

    base_url: str
    auth_token: str
    timeout: int = 30
    verify_ssl: bool = True

    def __post_init__(self) -> None:
        if self.base_url.endswith("/"):
            self.base_url = self.base_url.rstrip("/")

    @property
    def _url(self) -> str:
        return f"{self.base_url}/graphql/knowledgeGraph/v1"

    def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute ``query`` and return the parsed JSON payload."""

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": self.auth_token,
            "Content-Type": "application/json",
        }

        request = urllib.request.Request(self._url, data=data, headers=headers)
        context = None
        if not self.verify_ssl:
            context = ssl._create_unverified_context()

        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=context) as response:  # type: ignore[arg-type]
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # pragma: no cover - network failure path
            logger.error("Collibra GraphQL HTTP error: %s", exc)
            raise CollibraHTTPError(exc.code, exc.reason) from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network failure path
            logger.error("Collibra GraphQL URL error: %s", exc)
            raise CollibraHTTPError(None, str(exc)) from exc

        parsed = json.loads(body or "{}")
        if "errors" in parsed:
            logger.error("Collibra GraphQL query failed: %s", parsed["errors"])
            raise CollibraGraphQLError(parsed["errors"])
        return parsed.get("data", {})


class CollibraGraphQLError(RuntimeError):
    """Raised when Collibra GraphQL responds with errors."""

    def __init__(self, errors: Any):
        super().__init__("Collibra GraphQL query failed")
        self.errors = errors


class CollibraHTTPError(RuntimeError):
    """Raised when the HTTP layer encounters an error."""

    def __init__(self, status: Optional[int], message: str):
        super().__init__(f"Collibra GraphQL HTTP error: {status} {message}")
        self.status = status
        self.message = message
