# Co-op Job Tracker

A small Flask app for tracking co-op and internship applications, with a dashboard,
CSV export, and an automated import from WaterlooWorks.

## What it does

- Dashboard: interviews, offers, response rate, and Chart.js pipeline and velocity charts.
- Applications: add, edit, and delete entries (company, role, status, dates, notes, source, URL).
- SQLite persistence. The first run creates `jobtracker.db` and seeds a few sample rows so the UI is not empty.
- CSV export of the full pipeline from the UI.
- Status normalization: `unfilled`, `filled`, `closed`, and `rejected` are treated as Rejected; `ranked` and `shortlist` collapse into Ranked.
- Import from WaterlooWorks: a headless Playwright browser logs in with your credentials, pulls your applications, normalizes the status labels, and upserts by company and role, so re-running the import never creates duplicates.

## Run it

```bash
python3 -m venv venv
source venv/bin/activate              # Windows: venv\\Scripts\\activate
pip install -r requirements.txt
python -m playwright install chromium # one-time browser download for the importer
python app.py                         # http://localhost:5050
```

## Import from WaterlooWorks

1. Open `Import` in the nav and enter your WaterlooWorks username and password.
2. Click Import. The crawler runs in a subprocess, so credentials are never written to logs or the database.
3. Rows are matched on company and role and upserted; statuses are normalized as above.

The importer can also be run directly against other job boards by passing CSS selectors:

```bash
python crawler.py \\
  --login-url "https://example.com/login" \\
  --target-url "https://example.com/applications" \\
  --username "$WW_USERNAME" --password "$WW_PASSWORD" \\
  --row-selector "table#jobs tr" \\
  --company-selector "td:nth-child(1)" \\
  --role-selector "td:nth-child(2)" \\
  --status-selector "td:nth-child(3)"
```

## Files

- `app.py`: Flask routes, SQLite schema, dashboard queries, seeding.
- `crawler.py`: Playwright importer with the WaterlooWorks preset and status normalization.
- `templates/`: dashboard, list, and form views (Bootstrap 5).
- `static/js/app.js`: chart rendering. `static/css/main.css`: styling and status badges.

## Ideas

- Multi-user accounts.
- Follow-up reminders.
- Tags and filters by industry and location.
