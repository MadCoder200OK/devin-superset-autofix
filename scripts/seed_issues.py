#!/usr/bin/env python3
"""
seed_issues.py — Create remediation issues on your Superset fork.

These are REAL issues sourced from the upstream apache/superset repo,
plus one verified codebase-wide issue (datetime.utcnow deprecation).

Usage:
    export GITHUB_TOKEN=ghp_...
    python scripts/seed_issues.py
"""

import os
import sys
import requests
import time

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPO", "MadCoder200OK/superset")
LABEL = "devin-autofix"
API = "https://api.github.com"

ISSUES = [
    # ── 1. Cosmetic bug — Missing space (upstream #32773) ────────────
    {
        "title": "A space is missing for the '+ SQL Query' button on the Welcome screen",
        "labels": [LABEL, "bug", "frontend"],
        "body": """## Summary
On the Welcome/Home screen, a space is missing in the "+ SQL Query" button text. Other buttons ("+ Dashboard", "+ Chart") display correctly with a space after the "+".

**Upstream reference:** apache/superset#32773

## Steps to Reproduce
1. Navigate to the Superset Welcome/Home page
2. Look at the action buttons row
3. The "+ SQL Query" button has no space between "+" and "SQL"

## Expected
`+ SQL Query` (with space after +)

## Actual
`+SQL Query` (no space)

## Fix
Find the button label string in the frontend source (likely in `superset-frontend/src/pages/Home/` or a related component) and add the missing space. Other buttons in the same row can be used as reference for the correct format.

## Acceptance Criteria
- The "+ SQL Query" button displays with correct spacing matching other buttons
""",
    },
    # ── 2. Dead UI control (upstream #32776) ─────────────────────────
    {
        "title": "Subheader Size control on Big Number with Trendline does nothing",
        "labels": [LABEL, "bug", "frontend"],
        "body": """## Summary
The "Subheader Size" control in the Big Number with Trendline chart's customize panel has no effect on the rendered chart. The control exists in the UI but is not wired up to the chart rendering logic.

**Upstream reference:** apache/superset#32776

## Expected Behavior
The Subheader Size control should either:
- (Option A) Be removed from the customize panel since it has no function, OR
- (Option B) Be wired up to actually control the subheader font size

## Suggested Fix
Option A is the simplest: locate the chart plugin for Big Number with Trendline in `superset-frontend/plugins/plugin-chart-echarts/src/BigNumber/` or `superset-frontend/plugins/legacy-plugin-chart-big-number/`, find the Subheader Size control definition in the control panel configuration, and remove it.

## Acceptance Criteria
- The non-functional Subheader Size control is removed from the Big Number with Trendline chart customization panel
""",
    },
    # ── 3. Histogram warning (upstream #36530) ───────────────────────
    {
        "title": "Histogram chart throws warning in logs in 6.0.0+",
        "labels": [LABEL, "bug", "frontend"],
        "body": """## Summary
The Histogram chart generates warnings in the browser console / server logs. This is a low-priority but noisy issue that clutters logging output.

**Upstream reference:** apache/superset#36530

## Fix Guidance
1. Look at the Histogram chart plugin in `superset-frontend/plugins/plugin-chart-echarts/src/Histogram/` or `superset-frontend/plugins/legacy-preset-chart-nvd3/src/Histogram/`
2. Identify the deprecated API call or missing property causing the warning
3. Update to the correct API or add the missing prop

## Acceptance Criteria
- The Histogram chart renders without producing warnings in the console or server logs
""",
    },
    # ── 4. UI collapse bug (upstream #37444) ─────────────────────────
    {
        "title": "Hiding 'Metrics' section also collapses 'Columns' section unexpectedly",
        "labels": [LABEL, "bug", "frontend"],
        "body": """## Summary
In the Explore view chart editor, when the "Metrics" section is hidden/collapsed, the "Columns" section also collapses unexpectedly. These two sections should have independent expand/collapse states.

**Upstream reference:** apache/superset#37444

## Steps to Reproduce
1. Open any chart in the Explore view
2. In the left panel, collapse the "Metrics" section
3. Observe that the "Columns" section also collapses

## Expected
Only the "Metrics" section collapses. "Columns" remains in its current state.

## Root Cause (likely)
The two sections probably share a React state variable for their collapsed/expanded state, or there's a parent container whose visibility toggle affects both children.

## Fix Guidance
Look in `superset-frontend/src/explore/components/controls/` for the panel component that renders Metrics and Columns sections. Each section should maintain its own independent collapsed state (e.g., separate `useState` hooks or separate keys in a state object).

## Acceptance Criteria
- Collapsing "Metrics" does NOT affect the "Columns" section
- Collapsing "Columns" does NOT affect the "Metrics" section
""",
    },
    # ── 5. Input validation bug (upstream #37038) ────────────────────
    {
        "title": "Not able to type comma (,) in D3 format field for Table chart",
        "labels": [LABEL, "bug", "frontend"],
        "body": """## Summary
In the Table chart configuration, users cannot type a comma `,` in the D3 format input field. This prevents using common number formats like `,.2f` (comma as thousands separator with 2 decimal places).

**Upstream reference:** apache/superset#37038

## Steps to Reproduce
1. Create or edit a Table chart
2. Go to the Customize tab
3. Try to type `,.2f` in the D3 Format field
4. The comma is not registered / gets stripped

## Expected
The field should accept commas since they are valid D3 format specifiers.

## Root Cause (likely)
The input field likely has an `onChange` handler or validation regex that strips or blocks comma characters, possibly because commas are used as delimiters elsewhere in the form.

## Fix Guidance
Look in `superset-frontend/src/explore/components/controls/` for the D3 format input component. The fix is to allow comma characters in the input validation.

## Acceptance Criteria
- Users can type comma in the D3 format field
- Format strings like `,.2f` and `$,.0f` work correctly
""",
    },
    # ── 6. Python deprecation — verified 32 occurrences ──────────────
    {
        "title": "Replace deprecated datetime.utcnow() with timezone-aware alternative",
        "labels": [LABEL, "code-quality", "backend"],
        "body": """## Summary
`datetime.utcnow()` is deprecated as of Python 3.12 (see https://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow). It returns a naive datetime which can cause timezone-related bugs. The codebase currently has **32 occurrences** across 8+ files.

## Affected Files (verified by grep)
The heaviest offender is `superset/commands/report/execute.py` with ~20 uses. Other affected files:
- `superset/models/core.py` (2 uses — as SQLAlchemy column defaults)
- `superset/models/sql_lab.py` (1 use — column default + onupdate)
- `superset/models/helpers.py` (1 use — `utcfromtimestamp`)
- `superset/daos/query.py` (1 use — `utcfromtimestamp`)
- `superset/daos/log.py` (1 use)
- `superset/utils/dates.py` (1 use)
- `superset/utils/cache.py` (2 uses)

## Required Change
Replace:
```python
# Before
from datetime import datetime
datetime.utcnow()
datetime.utcfromtimestamp(ts)

# After
from datetime import datetime, timezone
datetime.now(timezone.utc)
datetime.fromtimestamp(ts, tz=timezone.utc)
```

## Scope
**Focus on `superset/commands/report/execute.py` only** to keep the change reviewable. This single file has ~20 occurrences and is self-contained.

Do NOT modify SQLAlchemy column defaults (in `models/core.py` and `models/sql_lab.py`) as those require separate consideration for ORM compatibility.

## Acceptance Criteria
- All `datetime.utcnow()` calls in `superset/commands/report/execute.py` are replaced with `datetime.now(timezone.utc)`
- All `datetime.utcfromtimestamp()` calls in the same file are replaced with `datetime.fromtimestamp(ts, tz=timezone.utc)`
- `from datetime import timezone` is added to imports
- No other files are modified in this PR
""",
    },
]


def main():
    if not GITHUB_TOKEN:
        print("ERROR: Set GITHUB_TOKEN environment variable")
        sys.exit(1)

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Ensure labels exist
    for label_name, color in [
        (LABEL, "7057ff"),
        ("bug", "d73a4a"),
        ("frontend", "0075ca"),
        ("backend", "e4e669"),
        ("code-quality", "fbca04"),
    ]:
        requests.post(
            f"{API}/repos/{REPO}/labels",
            headers=headers,
            json={
                "name": label_name,
                "color": color,
            },
        )  # 422 if exists, that's fine

    created = []
    for issue in ISSUES:
        print(f"Creating: {issue['title'][:70]}...")
        resp = requests.post(
            f"{API}/repos/{REPO}/issues",
            headers=headers,
            json=issue,
        )
        if resp.status_code == 201:
            data = resp.json()
            created.append(data)
            print(f"  ✓ #{data['number']}: {data['html_url']}")
        else:
            print(f"  ✗ {resp.status_code}: {resp.text[:200]}")

        time.sleep(1)  # rate limit courtesy

    print(f"\nDone — created {len(created)} issues on {REPO}")
    print("\nTo manually trigger without webhooks:")
    for c in created:
        print(f'  curl -X POST http://localhost:8000/api/trigger \\')
        print(f'    -H "Content-Type: application/json" \\')
        print(f"    -d '{{\"issue_number\": {c['number']}, \"issue_title\": \"{c['title'][:60]}...\"}}'")
        print()


if __name__ == "__main__":
    main()
