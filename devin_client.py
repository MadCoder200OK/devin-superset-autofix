"""
Devin API Client — wraps the v3 Organization API for session management.
"""

import os
import time
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

API_BASE = "https://api.devin.ai/v3"


class DevinClient:
    def __init__(self, api_key: str = None, org_id: str = None):
        self.api_key = api_key or os.environ["DEVIN_API_KEY"]
        self.org_id = org_id or os.environ["DEVIN_ORG_ID"]
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{API_BASE}/organizations/{self.org_id}/{path}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = self._url(path)
        resp = requests.request(method, url, headers=self.headers, **kwargs)
        try:
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error(f"Devin API error {resp.status_code}: {resp.text}")
            raise
        return resp.json()

    # ── Sessions ─────────────────────────────────────────────

    def create_session(
        self,
        prompt: str,
        tags: list[str] = None,
        title: str = None,
        playbook_id: str = None,
        idempotent: bool = False,
        max_acu_limit: int = None,
    ) -> dict:
        """Create a new Devin session. Returns {session_id, url, status}."""
        payload = {"prompt": prompt, "idempotent": idempotent}
        if tags:
            payload["tags"] = tags
        if title:
            payload["title"] = title
        if playbook_id:
            payload["playbook_id"] = playbook_id
        if max_acu_limit:
            payload["max_acu_limit"] = max_acu_limit

        result = self._request("POST", "sessions", json=payload)
        logger.info(f"Created session {result['session_id']} → {result['url']}")
        return result

    def get_session(self, session_id: str) -> dict:
        """Get full session details including status and structured output."""
        return self._request("GET", f"sessions/{session_id}")

    def get_session_status(self, session_id: str) -> str:
        """Get just the status string for a session."""
        data = self.get_session(session_id)
        return data.get("status", "unknown")

    def send_message(self, session_id: str, message: str) -> dict:
        """Send a follow-up message to a running session."""
        return self._request(
            "POST",
            f"sessions/{session_id}/messages",
            json={"message": message},
        )

    def list_sessions(self, limit: int = 50, offset: int = 0) -> dict:
        """List sessions for this org."""
        return self._request(
            "GET", "sessions", params={"limit": limit, "offset": offset}
        )

    def terminate_session(self, session_id: str) -> dict:
        """Terminate a running session."""
        return self._request("POST", f"sessions/{session_id}/terminate")

    def update_tags(self, session_id: str, tags: list[str]) -> dict:
        """Update tags on a session."""
        return self._request(
            "PUT", f"sessions/{session_id}/tags", json={"tags": tags}
        )

    # ── Messages / Events ────────────────────────────────────

    def get_messages(self, session_id: str) -> dict:
        """Get all messages/events from a session."""
        return self._request("GET", f"sessions/{session_id}/messages")

    # ── Convenience ──────────────────────────────────────────

    def wait_for_completion(
        self, session_id: str, poll_interval: int = 15, timeout: int = 1800
    ) -> dict:
        """Block until session exits. Returns final session data."""
        terminal = {"exit", "error", "suspended", "stopped"}
        start = time.time()
        while time.time() - start < timeout:
            data = self.get_session(session_id)
            status = data.get("status", "unknown")
            logger.info(f"Session {session_id}: {status}")
            if status in terminal:
                return data
            time.sleep(poll_interval)
        raise TimeoutError(
            f"Session {session_id} did not complete within {timeout}s"
        )

    # ── Self check ───────────────────────────────────────────

    def whoami(self) -> dict:
        """Verify API credentials."""
        resp = requests.get(
            f"{API_BASE}/self", headers=self.headers
        )
        resp.raise_for_status()
        return resp.json()
