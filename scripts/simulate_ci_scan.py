#!/usr/bin/env python3
"""
simulate_ci_scan.py — Simulates a CI pipeline security scan + auto-remediation.

This demonstrates "Level 2" automation: scanner finds issues → Devin fixes them.
The system discovers issues and remediates autonomously.

Two modes:
  --live     Actually runs pip-audit against Superset's requirements (needs pip-audit installed)
  --demo     Uses pre-scanned realistic findings (default, works everywhere)

Usage:
    # Demo mode (default) — uses realistic pre-scanned findings
    python scripts/simulate_ci_scan.py

    # Live mode — actually scans the requirements file
    pip install pip-audit
    python scripts/simulate_ci_scan.py --live --requirements ../superset/requirements/base.txt

    # Point to a running AutoFix server
    python scripts/simulate_ci_scan.py --server http://localhost:8000
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

# ── Server config ────────────────────────────────────────────
AUTOFIX_SERVER = os.environ.get("AUTOFIX_SERVER", "http://localhost:8000")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "MadCoder200OK/superset")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ── Pre-scanned findings (demo mode) ────────────────────────
# These are REAL vulnerabilities that have existed in Superset's
# dependency tree at various points. Used for demo when pip-audit
# isn't available.
DEMO_FINDINGS = [
    {
        "package": "werkzeug",
        "installed_version": "3.0.1",
        "fixed_version": "3.0.6",
        "vulnerability_id": "CVE-2024-49767",
        "severity": "HIGH",
        "description": "Werkzeug resource consumption vulnerability via crafted multipart form data. An attacker could send specially crafted requests to cause high resource consumption.",
        "fix_guidance": "Update werkzeug version constraint in requirements/base.in from the current pin to >=3.0.6. Then regenerate requirements/base.txt.",
    },
    {
        "package": "flask-cors",
        "installed_version": "4.0.0",
        "fixed_version": "5.0.1",
        "severity": "MEDIUM",
        "vulnerability_id": "CVE-2024-6221",
        "description": "Flask-CORS allows regex-based origin matching that can be bypassed. Overly permissive CORS configuration could allow unauthorized cross-origin requests.",
        "fix_guidance": "Update flask-cors in requirements/base.in to >=5.0.0. Verify CORS settings in superset/config.py are not affected.",
    },
    {
        "package": "gunicorn",
        "installed_version": "22.0.0",
        "fixed_version": "23.0.0",
        "severity": "HIGH",
        "vulnerability_id": "CVE-2024-1135",
        "description": "Gunicorn HTTP Request Smuggling vulnerability. Gunicorn fails to properly validate Transfer-Encoding headers, leading to HTTP request smuggling.",
        "fix_guidance": "Update gunicorn version in requirements/base.in to >=23.0.0. This is a drop-in upgrade with no breaking changes.",
    },
]


def banner(text: str):
    width = 60
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def run_live_scan(requirements_path: str) -> list[dict]:
    """Run pip-audit against a requirements file and parse results."""
    banner("RUNNING LIVE SCAN: pip-audit")
    print(f"  Target: {requirements_path}")

    try:
        result = subprocess.run(
            [
                "pip-audit",
                "-r", requirements_path,
                "--format", "json",
                "--output", "/tmp/audit-results.json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        print("  ERROR: pip-audit not installed. Run: pip install pip-audit")
        print("  Falling back to demo mode.\n")
        return DEMO_FINDINGS

    # pip-audit returns exit code 1 when vulnerabilities found
    try:
        with open("/tmp/audit-results.json") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"  pip-audit stderr: {result.stderr[:500]}")
        print("  Falling back to demo mode.\n")
        return DEMO_FINDINGS

    findings = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            findings.append({
                "package": dep["name"],
                "installed_version": dep["version"],
                "fixed_version": vuln.get("fix_versions", ["latest"])[0] if vuln.get("fix_versions") else "latest",
                "vulnerability_id": vuln.get("id", "UNKNOWN"),
                "severity": "HIGH",
                "description": vuln.get("description", "No description available."),
                "fix_guidance": f"Update {dep['name']} in requirements/base.in to >={vuln.get('fix_versions', ['latest'])[0] if vuln.get('fix_versions') else 'latest'}.",
            })

    print(f"  Found {len(findings)} vulnerabilities")
    return findings


def display_findings(findings: list[dict]):
    """Print scan results in a CI-like format."""
    banner(f"SCAN RESULTS: {len(findings)} vulnerabilities found")

    for i, f in enumerate(findings, 1):
        severity_icon = "🔴" if f["severity"] == "HIGH" else "🟡"
        print(f"\n  {severity_icon} [{f['severity']}] {f['vulnerability_id']}")
        print(f"     Package:   {f['package']} {f['installed_version']} → {f['fixed_version']}")
        print(f"     Issue:     {f['description'][:100]}...")

    print()


def create_github_issue(finding: dict) -> dict | None:
    """Create a GitHub issue for a scan finding (optional, for traceability)."""
    if not GITHUB_TOKEN:
        return None

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    issue_body = f"""## Automated Security Finding

**Scanner:** pip-audit (CI pipeline simulation)
**Scan time:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

### Vulnerability Details

| Field | Value |
|-------|-------|
| Package | `{finding['package']}` |
| Installed | `{finding['installed_version']}` |
| Fixed in | `{finding['fixed_version']}` |
| CVE | {finding['vulnerability_id']} |
| Severity | **{finding['severity']}** |

### Description
{finding['description']}

### Remediation
{finding['fix_guidance']}

---
*This issue was automatically created by the CI scan pipeline. Devin will auto-remediate.*
"""

    resp = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        headers=headers,
        json={
            "title": f"[Security] Upgrade {finding['package']} to fix {finding['vulnerability_id']}",
            "body": issue_body,
            "labels": ["devin-autofix", "security"],
        },
    )

    if resp.status_code == 201:
        data = resp.json()
        print(f"     GitHub Issue: #{data['number']} — {data['html_url']}")
        return data
    else:
        print(f"     (Could not create GitHub issue: {resp.status_code})")
        return None


def trigger_devin_session(finding: dict, issue_number: int | None = None, server: str = AUTOFIX_SERVER):
    """Send the finding to the AutoFix server to trigger a Devin session."""
    issue_num = issue_number or 0

    title = f"Upgrade {finding['package']} to fix {finding['vulnerability_id']}"

    body = f"""## Automated Security Remediation

A CI security scan found a vulnerability in the `{finding['package']}` package.

**Vulnerability:** {finding['vulnerability_id']}
**Severity:** {finding['severity']}
**Current version:** {finding['installed_version']}
**Fixed version:** {finding['fixed_version']}

### What to fix
{finding['description']}

### How to fix
{finding['fix_guidance']}

### Files to check
- `requirements/base.in` — update the version constraint
- `requirements/base.txt` — regenerate or manually update the pinned version
- `setup.py` or `pyproject.toml` — update if the package is listed there too
"""

    try:
        resp = requests.post(
            f"{server}/api/trigger",
            json={
                "issue_number": issue_num,
                "issue_title": title,
                "issue_body": body,
                "category": "security",
            },
            timeout=10,
        )

        if resp.status_code == 200:
            data = resp.json()
            print(f"     ✓ Devin session triggered (task_id: {data.get('task_id')})")
        else:
            print(f"     ✗ Server returned {resp.status_code}: {resp.text[:100]}")

    except requests.exceptions.ConnectionError:
        print(f"     ✗ Cannot reach AutoFix server at {server}")
        print(f"       Make sure it's running: docker compose up")


def main():
    parser = argparse.ArgumentParser(description="CI Scan Simulator for Devin AutoFix")
    parser.add_argument("--live", action="store_true", help="Run real pip-audit scan")
    parser.add_argument("--demo", action="store_true", default=True, help="Use pre-scanned findings (default)")
    parser.add_argument("--requirements", default=None, help="Path to requirements file (for --live)")
    parser.add_argument("--server", default=AUTOFIX_SERVER, help="AutoFix server URL")
    parser.add_argument("--create-issues", action="store_true", help="Also create GitHub issues for traceability")
    args = parser.parse_args()

    server = args.server

    # ── Scan phase ───────────────────────────────────────────
    banner("CI SECURITY SCAN PIPELINE")
    print(f"  Repository:  {GITHUB_REPO}")
    print(f"  AutoFix:     {server}")
    print(f"  Mode:        {'LIVE (pip-audit)' if args.live else 'DEMO (pre-scanned)'}")
    print(f"  Time:        {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    if args.live and args.requirements:
        findings = run_live_scan(args.requirements)
    else:
        findings = DEMO_FINDINGS

    if not findings:
        print("\n  ✓ No vulnerabilities found. Clean build!")
        return

    display_findings(findings)

    # ── Remediation phase ────────────────────────────────────
    banner("AUTO-REMEDIATION: Dispatching to Devin")

    for i, finding in enumerate(findings, 1):
        print(f"\n  [{i}/{len(findings)}] {finding['package']} ({finding['vulnerability_id']})")

        # Optionally create a GitHub issue for audit trail
        issue = None
        if args.create_issues:
            issue = create_github_issue(finding)
            time.sleep(1)

        issue_number = issue["number"] if issue else 100 + i
        trigger_devin_session(finding, issue_number, server=server)
        time.sleep(1)

    # ── Summary ──────────────────────────────────────────────
    banner("PIPELINE COMPLETE")
    print(f"  Findings:     {len(findings)}")
    print(f"  Dispatched:   {len(findings)} Devin sessions")
    print(f"  Dashboard:    {server}")
    print(f"\n  Devin is now working on fixes. Monitor at the dashboard.\n")


if __name__ == "__main__":
    main()
