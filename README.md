# 🤖 Devin AutoFix — Event-Driven Vulnerability Remediation

An event-driven automation system that uses [Devin](https://devin.ai) to automatically remediate security vulnerabilities, dependency upgrades, and code quality issues in [Apache Superset](https://github.com/apache/superset).

## Problem

Engineering teams accumulate security and maintenance debt faster than they can fix it. Vulnerability scanners flag dozens of issues, but remediation competes with feature work for developer time. Most findings sit untouched for weeks or months.

**AutoFix** closes that gap. When an issue is created and labeled, Devin automatically picks it up, writes the fix, and opens a PR — with a dashboard that lets engineering leadership track throughput in real time.

## Architecture

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│  GitHub Actions   │       │  AutoFix Server   │       │    Devin API     │
│  (issue.labeled   │──────▶│  FastAPI + Poller  │──────▶│   Sessions       │
│   or CI scan)     │       └────────┬─────────┘       └────────┬─────────┘
└──────────────────┘                │                           │
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

**Three trigger modes:**

1. **GitHub Action (primary):** An issue is labeled `devin-autofix` → GitHub Action calls the Devin API directly → Devin creates a PR
2. **Manual API trigger:** Call `/api/trigger` endpoint → creates a Devin session → tracked on the dashboard
3. **CI scan simulation:** Run `simulate_ci_scan.py` → scans dependencies for CVEs → dispatches Devin sessions for each finding

## Quick Start

### Prerequisites

- Docker & Docker Compose
- A [Devin](https://devin.ai) account with API access
- A GitHub Personal Access Token with `repo` and `workflow` scope

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
GITHUB_TOKEN=ghp_...         # GitHub PAT with repo + workflow scope
GITHUB_REPO=MadCoder200OK/superset
```

### 2. Start the server

```bash
docker compose up --build
```

The dashboard will be available at **http://localhost:8000**.

### 3. Seed issues on your fork

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests

export GITHUB_TOKEN=ghp_...
python scripts/seed_issues.py
```

This creates 6 issues across three categories:

- **Frontend bugs:** missing button spacing, dead UI controls, input validation, collapse state bugs
- **Chart warnings:** histogram deprecation warnings
- **Code quality:** deprecated `datetime.utcnow()` calls (32 occurrences)

### 4. Trigger remediation

**Option A — GitHub Actions (event-driven, recommended):**

The Superset fork includes two GitHub Actions workflows:

- `issue-autofix.yml` — triggers when an issue is labeled `devin-autofix`
- `security-scan.yml` — triggers on push to master when requirements change, or manually via workflow_dispatch

To set up: add `DEVIN_API_KEY` and `DEVIN_ORG_ID` as repository secrets on the Superset fork under Settings → Secrets → Actions.

**Option B — Manual trigger (for demo/testing):**

```bash
curl -X POST http://localhost:8000/api/trigger \
  -H "Content-Type: application/json" \
  -d '{"issue_number": 1, "issue_title": "A space is missing for the + SQL Query button", "issue_body": "Fix the missing space in the button label."}'
```

**Option C — CI scan simulation (Level 2 demo):**

```bash
source .venv/bin/activate
python scripts/simulate_ci_scan.py
```

### 5. Monitor

- **Dashboard:** http://localhost:8000
- **JSON API:** http://localhost:8000/api/status
- **Health check:** http://localhost:8000/api/health

## API Endpoints

| Method | Path           | Description                      |
| ------ | -------------- | -------------------------------- |
| `GET`  | `/`            | Observability dashboard          |
| `GET`  | `/api/status`  | JSON status + all tasks          |
| `GET`  | `/api/health`  | Health check                     |
| `POST` | `/api/trigger` | Manually trigger a Devin session |

## Issue Categories

| Category           | Example                                 | Devin Complexity             |
| ------------------ | --------------------------------------- | ---------------------------- |
| Frontend bug       | Missing button spacing, dead UI control | Easy–Medium                  |
| Chart rendering    | Histogram warning, collapse state bug   | Medium                       |
| Code quality       | Replace deprecated `datetime.utcnow()`  | Medium — multi-file refactor |
| Security (CI scan) | CVE in dependency, version bump         | Easy                         |

## Observability

The dashboard provides engineering leadership with:

- **Total / Running / Completed / Failed** counters
- **Success rate** percentage
- **Average fix time** in minutes
- Per-issue status with links to Devin sessions and resulting PRs

## Project Structure

```
devin-superset-autofix/
├── app.py                          # FastAPI server — trigger API + dashboard
├── devin_client.py                 # Devin API v3 client wrapper
├── tracker.py                      # SQLite persistence for task tracking
├── poller.py                       # Background session status poller
├── templates/
│   └── dashboard.html              # Observability dashboard
├── scripts/
│   ├── seed_issues.py              # Creates test issues on your fork
│   └── simulate_ci_scan.py         # CI pipeline scan simulator (Level 2)
├── .github/
│   └── workflows/
│       ├── issue-autofix.yml       # GitHub Action: issue label → Devin
│       └── security-scan.yml       # GitHub Action: push → scan → Devin
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Extending This

In a real customer engagement, this system would be extended with:

- **Snyk / Dependabot / Trivy integration** — trigger from real scan results
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
- **GitHub Actions** for event-driven triggers
- **GitHub API** for issue management
