"""
Poller — background worker that polls Devin sessions and updates the tracker.
"""
import asyncio
import json
import logging
import re
from devin_client import DevinClient
from tracker import Tracker

logger = logging.getLogger(__name__)
POLL_INTERVAL = 30
STATUS_MAP = {
    "running": "running",
    "blocked": "running",
    "exit": "completed",
    "error": "error",
    "suspended": "completed",
    "stopped": "completed",
}

def _extract_pr_url(session_data: dict) -> str | None:
    prs = session_data.get("pull_requests", [])
    if prs and isinstance(prs, list) and len(prs) > 0:
        pr_url = prs[0].get("pr_url")
        if pr_url:
            return pr_url
    structured = session_data.get("structured_output")
    if structured and isinstance(structured, dict):
        pr = structured.get("pr_url") or structured.get("pull_request_url")
        if pr:
            return pr
    for key, val in session_data.items():
        if isinstance(val, str) and "/pull/" in val:
            pr_match = re.search(r"https://github\.com/[^/]+/[^/]+/pull/\d+", val)
            if pr_match:
                return pr_match.group(0)
    return None

async def poll_sessions(tracker: Tracker, devin: DevinClient):
    logger.info("Poller started — checking every %ds", POLL_INTERVAL)
    while True:
        try:
            active = tracker.get_active_sessions()
            if active:
                logger.info(f"Polling {len(active)} active session(s)")
            for task in active:
                session_id = task.get("session_id")
                if not session_id:
                    continue
                try:
                    data = devin.get_session(session_id)
                    raw_status = data.get("status", "unknown")
                    mapped = STATUS_MAP.get(raw_status, raw_status)
                    pr_url = _extract_pr_url(data)
                    if pr_url:
                        mapped = "completed"

                    # ── ACU LOGGING ──────────────────────────
                    acus = 0.0
                    if mapped == "completed":
                        logger.info(f"[ACU DEBUG] Session {session_id[:12]} completed, fetching ACUs...")
                        try:
                            acu_data = devin.get_session_acus(session_id)
                            logger.info(f"[ACU DEBUG] Raw consumption response: {acu_data}")
                            logger.info(f"[ACU DEBUG] Type: {type(acu_data)}")
                            if isinstance(acu_data, dict):
                                acus = float(acu_data.get("total_acus", 0.0))
                            elif isinstance(acu_data, (int, float)):
                                acus = float(acu_data)
                            else:
                                acus = 0.0
                            logger.info(f"[ACU DEBUG] Final ACU value: {acus}")
                        except Exception as e:
                            logger.error(f"[ACU DEBUG] Error fetching ACUs: {e}")
                            acus = 0.0

                    # Also log what session API returns for acus_consumed
                    session_acus = data.get("acus_consumed")
                    logger.info(f"[ACU DEBUG] session.acus_consumed = {session_acus} (type: {type(session_acus).__name__})")
                    # ── END ACU LOGGING ──────────────────────

                    error_msg = None
                    if mapped in ("error", "failed") and not pr_url:
                        error_msg = data.get("status_info", raw_status)

                    if mapped != task["status"] or (pr_url and not task.get("pr_url")):
                        logger.info(f"[UPDATE] session={session_id[:12]} status={mapped} pr={pr_url} acus={acus}")
                        tracker.update_status(
                            session_id=session_id, status=mapped, pr_url=pr_url,
                            error_message=error_msg, acus_consumed=acus,
                        )
                        logger.info(f"Session {session_id}: {task['status']} -> {mapped}"
                            + (f" PR: {pr_url}" if pr_url else "")
                            + (f" ACUs: {acus}" if acus else ""))
                except Exception as e:
                    logger.error(f"Error polling session {session_id}: {e}")
        except Exception as e:
            logger.error(f"Poller loop error: {e}")
        await asyncio.sleep(POLL_INTERVAL)
