"""
Devin Superset AutoFix — Event-driven automation server.

Listens for GitHub issue webhooks, spins up Devin sessions to remediate them,
and provides an observability dashboard for engineering leadership.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from devin_client import DevinClient
from tracker import Tracker
from poller import poll_sessions

# ── Config ───────────────────────────────────────────────────

GITHUB_REPO = os.environ.get("GITHUB_REPO", "MadCoder200OK/superset")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
TRIGGER_LABEL = os.environ.get("TRIGGER_LABEL", "devin-autofix")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("autofix")

# ── Shared instances ─────────────────────────────────────────

tracker = Tracker()
devin = DevinClient()
templates = Jinja2Templates(directory="templates")


# ── Lifespan: start poller on boot ──────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(poll_sessions(tracker, devin))
    logger.info("🚀 AutoFix server started — poller running")
    yield
    task.cancel()
    logger.info("Server shutting down")


app = FastAPI(
    title="Devin Superset AutoFix",
    description="Event-driven vulnerability remediation powered by Devin",
    lifespan=lifespan,
)


# ── Helpers ──────────────────────────────────────────────────

def verify_github_signature(payload_body: bytes, signature: str) -> bool:
    """Verify the GitHub webhook HMAC signature."""
    if not GITHUB_WEBHOOK_SECRET:
        return True  # skip verification in dev
    expected = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def _is_frontend_issue(labels: list[str], title: str, body: str) -> bool:
    """Detect whether this is a frontend (React/TS) or backend (Python) issue."""
    text = f"{title} {body} {' '.join(labels)}".lower()
    frontend_signals = [
        "frontend", "react", "typescript", "echarts", "chart",
        "button", "ui ", "css", "component", "panel", "control",
        "d3 format", "collapse", "render", "plugin-chart",
        "superset-frontend", "cosmetic", "label", "display",
    ]
    return any(signal in text for signal in frontend_signals)


def build_devin_prompt(issue: dict) -> str:
    """Craft the Devin session prompt from a GitHub issue."""
    labels = [l.get("name", "") for l in issue.get("labels", [])]
    body = issue.get("body", "No description provided.")
    is_fe = _is_frontend_issue(labels, issue["title"], body)

    if is_fe:
        stack_guidance = """
## Tech Stack Context
This is a FRONTEND issue. The frontend lives in `superset-frontend/`.
- Framework: React 18 + TypeScript
- Charts use ECharts (plugins in `superset-frontend/plugins/plugin-chart-echarts/`)
- Legacy charts in `superset-frontend/plugins/legacy-plugin-chart-*` and `legacy-preset-chart-*`
- Explore controls in `superset-frontend/src/explore/components/controls/`
- Pages (Home, etc.) in `superset-frontend/src/pages/`
- To verify: `cd superset-frontend && npm ci && npm run lint`
- Do NOT run the full backend test suite — just verify the frontend builds.
"""
    else:
        stack_guidance = """
## Tech Stack Context
This is a BACKEND issue. The Python backend lives in `superset/`.
- Framework: Flask + SQLAlchemy
- Python 3.10+
- To verify: run any relevant unit tests with `pytest superset/tests/... -x` if applicable.
- Do NOT modify database migration files unless the issue explicitly asks for it.
"""

    return f"""You are an expert software engineer fixing an issue in the Apache Superset repository.

Repository: https://github.com/{GITHUB_REPO}
Issue #{issue['number']}: {issue['title']}

Issue description:
{body}
{stack_guidance}
## Instructions

1. Clone the repository: `git clone https://github.com/{GITHUB_REPO}.git`
2. Create a new branch: `git checkout -b fix/issue-{issue['number']}`
3. Read and understand the relevant code before making changes.
4. Implement the minimal, targeted fix described in the issue.
5. If there are existing tests related to the change, run them to verify nothing breaks.
6. Commit your changes with a clear message referencing #{issue['number']}.
7. Push the branch and open a Pull Request against the `master` branch.
   - PR title: "fix: {issue['title']}"
   - PR body: "Closes #{issue['number']}\\n\\n<describe what you changed and why>"

## Constraints
- Keep changes minimal and focused — do NOT refactor unrelated code.
- Follow the existing code style of the repository.
- If unsure about something, err on the side of a smaller, safer change.
"""


def categorize_issue(labels: list[str], title: str) -> str:
    """Infer category from issue labels or title."""
    lower_title = title.lower()
    label_set = {l.lower() for l in labels}
    if "dependency" in label_set or "upgrade" in lower_title or "bump" in lower_title:
        return "dependency"
    if "security" in label_set or "cve" in lower_title or "vulnerability" in lower_title:
        return "security"
    if "code-quality" in label_set or "deprecated" in lower_title or "lint" in lower_title:
        return "code-quality"
    if "frontend" in label_set or "chart" in lower_title or "button" in lower_title:
        return "frontend"
    if "backend" in label_set or "python" in lower_title:
        return "backend"
    return "general"


# ── Routes ───────────────────────────────────────────────────

@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    GitHub webhook endpoint.
    Triggered when an issue is opened or labeled with TRIGGER_LABEL.
    """
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    payload = json.loads(body)

    if event == "issues":
        action = payload.get("action")
        issue = payload.get("issue", {})
        labels = [l.get("name", "") for l in issue.get("labels", [])]

        # Trigger on: issue opened with label, or label added to existing issue
        should_trigger = (
            TRIGGER_LABEL in labels
            and action in ("opened", "labeled")
        )

        if not should_trigger:
            return {"status": "ignored", "reason": f"action={action}, missing label"}

        # Check for duplicate
        existing = tracker.get_task_by_issue(issue["number"])
        if existing and existing["status"] in ("pending", "running"):
            return {"status": "skipped", "reason": "already processing"}

        # Create tracking entry and dispatch Devin session
        category = categorize_issue(labels, issue.get("title", ""))
        task_id = tracker.create_task(
            issue_number=issue["number"],
            issue_title=issue["title"],
            issue_url=issue.get("html_url"),
            issue_labels=",".join(labels),
            category=category,
        )

        background_tasks.add_task(dispatch_devin_session, task_id, issue)

        logger.info(f"Queued issue #{issue['number']}: {issue['title']}")
        return {"status": "queued", "task_id": task_id, "issue": issue["number"]}

    # Also handle ping for webhook setup verification
    if event == "ping":
        return {"status": "pong"}

    return {"status": "ignored", "event": event}


async def dispatch_devin_session(task_id: int, issue: dict):
    """Create a Devin session for the given issue (runs in background)."""
    try:
        prompt = build_devin_prompt(issue)
        labels = [l.get("name", "") for l in issue.get("labels", [])]

        result = devin.create_session(
            prompt=prompt,
            tags=["autofix", f"issue-{issue['number']}", GITHUB_REPO],
            title=f"AutoFix: {issue['title']}",
        )

        tracker.update_session(
            task_id=task_id,
            session_id=result["session_id"],
            session_url=result["url"],
        )

        logger.info(
            f"Devin session created for issue #{issue['number']}: {result['url']}"
        )

    except Exception as e:
        logger.error(f"Failed to create Devin session for task {task_id}: {e}")
        tracker.update_status(
            session_id=None,
            status="error",
            error_message=str(e),
        )


# ── Dashboard & API ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Observability dashboard — the VP of Engineering view."""
    tasks = tracker.get_all_tasks()
    stats = tracker.get_stats()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tasks": tasks,
            "stats": stats,
            "repo": GITHUB_REPO,
            "now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        },
    )


@app.get("/api/status")
async def api_status():
    """JSON status endpoint for programmatic access."""
    return JSONResponse(
        {
            "stats": tracker.get_stats(),
            "tasks": tracker.get_all_tasks(),
        }
    )


@app.get("/api/health")
async def health():
    """Health check."""
    return {"status": "ok", "repo": GITHUB_REPO}


# ── Manual trigger (for demo / testing) ──────────────────────

@app.post("/api/trigger")
async def manual_trigger(request: Request, background_tasks: BackgroundTasks):
    """
    Manually trigger a Devin session for a given issue number.
    Body: {"issue_number": 1, "issue_title": "...", "issue_body": "..."}
    """
    data = await request.json()
    issue_number = data.get("issue_number")
    issue_title = data.get("issue_title", f"Issue #{issue_number}")
    issue_body = data.get("issue_body", "")

    if not issue_number:
        raise HTTPException(400, "issue_number is required")

    issue = {
        "number": issue_number,
        "title": issue_title,
        "body": issue_body,
        "html_url": f"https://github.com/{GITHUB_REPO}/issues/{issue_number}",
        "labels": [],
    }

    task_id = tracker.create_task(
        issue_number=issue_number,
        issue_title=issue_title,
        issue_url=issue["html_url"],
        category=data.get("category", "general"),
    )
    background_tasks.add_task(dispatch_devin_session, task_id, issue)

    return {"status": "queued", "task_id": task_id}
