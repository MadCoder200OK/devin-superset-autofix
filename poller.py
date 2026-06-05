"""
Poller — background worker that polls Devin sessions and updates the tracker.
Runs as an asyncio task inside the FastAPI app.
"""

import asyncio
import logging
import re
from devin_client import DevinClient
from tracker import Tracker

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30  # seconds
TERMINAL_STATUSES = {"exit", "error", "suspended", "stopped"}

# Devin status → our simplified status
STATUS_MAP = {
    "running": "running",
    "blocked": "running",      # waiting for input, still active
    "exit": "completed",
    "error": "error",
    "suspended": "failed",
    "stopped": "failed",
}


def _extract_pr_url(session_data: dict) -> str | None:
    """Try to extract a PR URL from session data or structured output."""
    # Check structured_output first
    structured = session_data.get("structured_output")
    if structured and isinstance(structured, dict):
        pr = structured.get("pr_url") or structured.get("pull_request_url")
        if pr:
            return pr

    # Check the session URL — sometimes Devin links PRs in the result
    # Also scan last messages for github PR URLs
    result = session_data.get("result", "") or ""
    pr_match = re.search(r"https://github\.com/[^/]+/[^/]+/pull/\d+", result)
    if pr_match:
        return pr_match.group(0)

    return None


async def poll_sessions(tracker: Tracker, devin: DevinClient):
    """
    Continuously poll active Devin sessions and update the tracker.
    Designed to run as a long-lived asyncio background task.
    """
    logger.info("Poller started — checking every %ds", POLL_INTERVAL)

    while True:
        try:
            active = tracker.get_active_sessions()
            if active:
                logger.info(f"Polling {len(active)} active session(s)")

            for task in active:
                session_id = task.get("session_id")
                if not session_id:
                    continue  # pending task, no session yet

                try:
                    data = devin.get_session(session_id)
                    raw_status = data.get("status", "unknown")
                    mapped = STATUS_MAP.get(raw_status, raw_status)

                    pr_url = _extract_pr_url(data)

                    error_msg = None
                    if mapped in ("error", "failed"):
                        error_msg = data.get("status_info", raw_status)

                    if mapped != task["status"] or pr_url:
                        tracker.update_status(
                            session_id=session_id,
                            status=mapped,
                            pr_url=pr_url,
                            error_message=error_msg,
                        )
                        logger.info(
                            f"Session {session_id}: {task['status']} → {mapped}"
                            + (f" PR: {pr_url}" if pr_url else "")
                        )

                except Exception as e:
                    logger.error(f"Error polling session {session_id}: {e}")

        except Exception as e:
            logger.error(f"Poller loop error: {e}")

        await asyncio.sleep(POLL_INTERVAL)
