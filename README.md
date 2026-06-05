# 🤖 Devin AutoFix — Event-Driven Vulnerability Remediation

An event-driven automation system that uses [Devin](https://devin.ai) to automatically remediate security vulnerabilities, dependency upgrades, and code quality issues in [Apache Superset](https://github.com/apache/superset).

## Problem

Engineering teams accumulate security and maintenance debt faster than they can fix it. Vulnerability scanners flag dozens of issues, but remediation competes with feature work for developer time. Most findings sit untouched for weeks or months.

**AutoFix** closes that gap. When an issue is created and labeled, Devin automatically picks it up, writes the fix, and opens a PR — with a dashboard that lets engineering leadership track throughput in real time.

## Architecture

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│  GitHub Webhook   │       │  AutoFix Server   │       │    Devin API     │
│  (issue.labeled)  │──────▶│  FastAPI + Poller  │──────▶│   Sessions       │
└──────────────────┘       └────────┬─────────┘       └────────┬─────────┘
                                    │                           │
                             ┌──────▼──────┐            ┌──────▼──────┐
                             │  SQLite DB   │            │  Pull Reqs   │
                             │  (tracking)  │            │  on GitHub   │
                             └──────┬──────┘            └─────────────┘
                                    │
                             ┌──────▼──────┐
                             │  Dashboard   │
                             │  /           │
                             └─────────────┘
```

**Flow:**
1. An issue is created on the Superset fork with the `devin-autofix` label
2. GitHub sends a webhook to the AutoFix server
3. The server creates a Devin session with a targeted prompt
4. A background poller monitors the session until completion
5. Devin clones the repo, writes the fix, and opens a PR
6. The dashboard shows real-time status, success rates, and PR links

## Quick Start

### Prerequisites

- Docker & Docker Compose
- A [Devin](https://devin.ai) account with API access
- A GitHub Personal Access Token with `repo` scope

### 1. Clone and configure

```bash
git clone https://github.com/MadCoder200OK/devin-superset-autofix.git
cd devin-superset-autofix
cp .env.example .env
```

Edit `.env` with your credentials:

```
DEVIN_API_KEY=cog_...        # From Devin Settings → Service Users
DEVIN_ORG_ID=...             # From Devin Settings → Service Users
GITHUB_TOKEN=ghp_...         # GitHub PAT with repo scope
GITHUB_REPO=MadCoder200OK/superset
```

### 2. Start the server

```bash
docker compose up --build
```

The dashboard will be available at **http://localhost:8000**.

### 3. Seed issues on your fork

```bash
# From your host machine (or inside the container)
export GITHUB_TOKEN=ghp_...
python scripts/seed_issues.py
```

This creates 6 pre-written issues across three categories:
- **Dependency upgrades:** PyJWT, cryptography, Pillow
- **Code quality:** deprecated `datetime.utcnow()`, bare `except` clauses
- **Security hardening:** HTTP security headers

### 4. Trigger remediation

**Option A — Webhook (production flow):**
Set up a GitHub webhook on your fork pointing to `http://YOUR_HOST:8000/webhook` with content type `application/json` and the `Issues` event. Use ngrok for local testing:

```bash
ngrok http 8000
# Copy the https URL → GitHub repo → Settings → Webhooks → Add
```

**Option B — Manual trigger (demo/testing):**

```bash
curl -X POST http://localhost:8000/api/trigger \
  -H "Content-Type: application/json" \
  -d '{"issue_number": 1, "issue_title": "Upgrade PyJWT", "issue_body": "Update PyJWT to latest stable."}'
```

### 5. Monitor

- **Dashboard:** http://localhost:8000
- **JSON API:** http://localhost:8000/api/status
- **Health check:** http://localhost:8000/api/health

### 6. CI Scan Simulation (Level 2 Demo)

This simulates what a production CI pipeline would do: scan for vulnerabilities, then auto-dispatch Devin to fix each one.

```bash
# Demo mode — uses realistic pre-scanned vulnerability findings
python scripts/simulate_ci_scan.py

# With GitHub issue creation for audit trail
python scripts/simulate_ci_scan.py --create-issues

# Live mode — actually runs pip-audit against Superset's requirements
pip install pip-audit
python scripts/simulate_ci_scan.py --live --requirements ../superset/requirements/base.txt
```

This demonstrates the progression from manual issue-driven remediation (Level 1) to fully automated scanner-driven remediation (Level 2).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook` | GitHub webhook receiver |
| `GET` | `/` | Observability dashboard |
| `GET` | `/api/status` | JSON status + all tasks |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/trigger` | Manually trigger a session |

## Issue Categories

| Category | Example | Devin Complexity |
|----------|---------|-----------------|
| Dependency upgrade | Bump PyJWT to latest | Low — version change + test |
| Code quality | Replace `datetime.utcnow()` | Medium — multi-file refactor |
| Security hardening | Add HTTP security headers | Medium — config understanding |

## Observability

The dashboard provides engineering leadership with:

- **Total / Running / Completed / Failed** counters
- **Success rate** percentage
- **Average fix time** in minutes
- Per-issue status with links to Devin sessions and resulting PRs

## Project Structure

```
devin-superset-autofix/
├── app.py              # FastAPI server — webhook + dashboard + API
├── devin_client.py     # Devin API v3 client wrapper
├── tracker.py          # SQLite persistence for task tracking
├── poller.py           # Background session status poller
├── templates/
│   └── dashboard.html  # Observability dashboard
├── scripts/
│   ├── seed_issues.py          # Creates test issues on your fork
│   └── simulate_ci_scan.py     # CI pipeline scan simulator (Level 2 demo)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Extending This

In a real customer engagement, this system would be extended with:

- **Snyk / Dependabot / Trivy webhook integration** — trigger from real scan results, not manual issues
- **Slack / Teams notifications** — alert channels when PRs are ready for review
- **Auto-merge with CI gates** — if tests pass, merge the PR automatically
- **Batch scheduling** — run a nightly sweep of the entire vulnerability backlog
- **Cost tracking** — monitor Devin ACU consumption per issue category
- **Multi-repo support** — single dashboard across an org's repositories

## Tech Stack

- **Python 3.12** + FastAPI
- **Devin API v3** for session management
- **SQLite** for lightweight persistence
- **Docker** for deployment
- **GitHub API** for issue management and webhook events
