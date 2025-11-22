import csv
import io
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Tuple

from flask import Flask, Response, flash, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "jobtracker.db"

STATUS_KEYWORDS = {
    "rejected": [
        "unfilled",
        "filled",
        "cancelled",
        "canceled",
        "closed",
        "not selected",
        "rejected",
        "unsuccessful",
        "declined",
        "did not proceed",
    ],
    "offer": ["offer", "accepted", "accept"],
    "onsite": ["onsite", "final round"],
    "interview": ["interview", "phone screen", "screen", "assessment"],
    "ranked": ["ranked", "alternate", "shortlist", "pool"],
    "applied": ["applied", "submitted", "received", "under review", "in progress"],
}

# Mapping presets to a display label for UI
PRESETS = {"waterlooworks": "WaterlooWorks"}


def normalize_status(raw_status: str) -> str:
    """Map messy labels like 'unfilled'/'filled' into canonical statuses."""
    text = (raw_status or "").strip()
    lowered = text.lower()
    for target, keywords in STATUS_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return {
                "rejected": "Rejected",
                "offer": "Offer",
                "onsite": "Onsite",
                "interview": "Interview",
                "ranked": "Ranked",
                "applied": "Applied",
            }[target]
    return text.title() if text else "Applied"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "dev-key-change-me"

    ensure_database()

    @app.route("/")
    def dashboard():
        conn = get_db()
        stats = fetch_stats(conn)
        stage_breakdown = fetch_stage_breakdown(conn)
        monthly_velocity = fetch_monthly_velocity(conn)
        recent = conn.execute(
            "SELECT * FROM applications ORDER BY applied_date DESC LIMIT 5"
        ).fetchall()
        return render_template(
            "dashboard.html",
            stats=stats,
            recent=recent,
            stage_breakdown=stage_breakdown,
            monthly_velocity=monthly_velocity,
        )

    @app.route("/applications")
    def applications():
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY applied_date DESC, id DESC"
        ).fetchall()
        return render_template("applications.html", applications=rows)

    @app.route("/applications/export")
    def export_applications():
        conn = get_db()
        rows = conn.execute(
            "SELECT company, role, location, status, applied_date, follow_up_date, source, notes, url FROM applications ORDER BY applied_date DESC"
        ).fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "company",
                "role",
                "location",
                "status",
                "applied_date",
                "follow_up_date",
                "source",
                "notes",
                "url",
            ]
        )
        writer.writerows(rows)
        output.seek(0)
        return Response(
            output.read(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=applications.csv"},
        )

    @app.route("/import", methods=["GET", "POST"])
    def import_applications():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            if not username or not password:
                flash("Username and password are required.", "danger")
                return redirect(url_for("import_applications"))
            try:
                # Run crawler in a subprocess to avoid blocking the Flask app and to keep credentials out of logs.
                env = {**os.environ, "WW_USERNAME": username, "WW_PASSWORD": password}
                result = subprocess.run(
                    [sys.executable, "crawler.py", "--preset", "waterlooworks"],
                    capture_output=True,
                    text=True,
                    env=env,
                    cwd=BASE_DIR,
                    check=True,
                )
                flash(result.stdout.strip() or "Imported applications.", "success")
            except subprocess.CalledProcessError as err:
                message = err.stderr.strip() or err.stdout.strip() or str(err)
                flash(f"Import failed: {message}", "danger")
            return redirect(url_for("applications"))
        return render_template("import.html")

    @app.route("/applications/new", methods=["GET", "POST"])
    def add_application():
        if request.method == "POST":
            conn = get_db()
            data = form_to_application(request.form)
            conn.execute(
                """
                INSERT INTO applications
                (company, role, location, status, applied_date, follow_up_date, source, notes, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                data_to_tuple(data),
            )
            conn.commit()
            flash("Application added.", "success")
            return redirect(url_for("applications"))
        return render_template("form.html", application=None, action="Add")

    @app.route("/applications/<int:app_id>/edit", methods=["GET", "POST"])
    def edit_application(app_id: int):
        conn = get_db()
        existing = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (app_id,)
        ).fetchone()
        if not existing:
            flash("Application not found.", "danger")
            return redirect(url_for("applications"))

        if request.method == "POST":
            data = form_to_application(request.form)
            conn.execute(
                """
                UPDATE applications
                SET company = ?, role = ?, location = ?, status = ?, applied_date = ?,
                    follow_up_date = ?, source = ?, notes = ?, url = ?
                WHERE id = ?
                """,
                (*data_to_tuple(data), app_id),
            )
            conn.commit()
            flash("Application updated.", "success")
            return redirect(url_for("applications"))

        return render_template("form.html", application=existing, action="Edit")

    @app.route("/applications/<int:app_id>/delete", methods=["POST"])
    def delete_application(app_id: int):
        conn = get_db()
        conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        conn.commit()
        flash("Application deleted.", "info")
        return redirect(url_for("applications"))

    return app


def ensure_database() -> None:
    init_db()
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    if count == 0:
        seed_sample_data(conn)
        conn.commit()


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            location TEXT,
            status TEXT NOT NULL,
            applied_date TEXT NOT NULL,
            follow_up_date TEXT,
            source TEXT,
            notes TEXT,
            url TEXT
        )
        """
    )
    conn.commit()


def seed_sample_data(conn: sqlite3.Connection) -> None:
    today = date.today()
    sample_rows = [
        (
            "DeepPixel AI",
            "ML Intern",
            "Toronto, ON",
            "Phone Screen",
            str(today.replace(day=max(1, today.day - 18))),
            None,
            "LinkedIn",
            "Reached out to recruiter on LinkedIn. Prep system design.",
            "https://example.com/deeppixel",
        ),
        (
            "Volt Robotics",
            "Firmware Co-op",
            "Waterloo, ON",
            "Applied",
            str(today.replace(day=max(1, today.day - 9))),
            None,
            "WaterlooWorks",
            "",
            "",
        ),
        (
            "Aurora Cloud",
            "Backend Intern",
            "Remote (Canada)",
            "Interview",
            str(today.replace(day=max(1, today.day - 30))),
            str(today.replace(day=max(1, today.day - 15))),
            "Company Careers",
            "Take-home API design sent.",
            "https://example.com/aurora",
        ),
        (
            "Quark Labs",
            "Platform Engineering Co-op",
            "Montreal, QC",
            "Offer",
            str(today.replace(day=max(1, today.day - 45))),
            str(today.replace(day=max(1, today.day - 10))),
            "Referral",
            "Offer pending negotiation.",
            "",
        ),
        (
            "Northwind Energy",
            "Data Intern",
            "Calgary, AB",
            "Rejected",
            str(today.replace(day=max(1, today.day - 60))),
            str(today.replace(day=max(1, today.day - 25))),
            "Indeed",
            "Need more SQL practice.",
            "",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO applications
        (company, role, location, status, applied_date, follow_up_date, source, notes, url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sample_rows,
    )


def form_to_application(form) -> dict:
    applied = form.get("applied_date", "")
    follow_up = form.get("follow_up_date", "") or None
    if not applied:
        applied = date.today().isoformat()
    status = normalize_status(form.get("status", "Applied"))
    return {
        "company": form.get("company", "").strip(),
        "role": form.get("role", "").strip(),
        "location": form.get("location", "").strip(),
        "status": status,
        "applied_date": applied,
        "follow_up_date": follow_up,
        "source": form.get("source", "").strip(),
        "notes": form.get("notes", "").strip(),
        "url": form.get("url", "").strip(),
    }


def data_to_tuple(data: dict) -> Tuple[str, ...]:
    return (
        data["company"],
        data["role"],
        data["location"],
        data["status"],
        data["applied_date"],
        data["follow_up_date"],
        data["source"],
        data["notes"],
        data["url"],
    )


def upsert_application(conn: sqlite3.Connection, data: Dict[str, str]) -> None:
    """Insert or update an application keyed by company + role."""
    normalized = {**data}
    normalized["status"] = normalize_status(data.get("status", "Applied"))
    existing = conn.execute(
        "SELECT id FROM applications WHERE company = ? AND role = ?",
        (normalized["company"], normalized["role"]),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE applications
            SET company = ?, role = ?, location = ?, status = ?, applied_date = ?,
                follow_up_date = ?, source = ?, notes = ?, url = ?
            WHERE id = ?
            """,
            (*data_to_tuple(normalized), existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO applications
            (company, role, location, status, applied_date, follow_up_date, source, notes, url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data_to_tuple(normalized),
        )
    conn.commit()


def fetch_stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    interviews = conn.execute(
        """
        SELECT COUNT(*) FROM applications
        WHERE status IN ('Phone Screen', 'Interview', 'Onsite', 'Offer', 'Ranked')
        """
    ).fetchone()[0]
    offers = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE status = 'Offer'"
    ).fetchone()[0]
    responded = conn.execute(
        "SELECT COUNT(*) FROM applications WHERE status != 'Applied'"
    ).fetchone()[0]
    response_rate = round((responded / total) * 100, 1) if total else 0
    return {
        "total": total,
        "interviews": interviews,
        "offers": offers,
        "response_rate": response_rate,
    }


def fetch_stage_breakdown(conn: sqlite3.Connection) -> List[Tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT status, COUNT(*) as count
        FROM applications
        GROUP BY status
        ORDER BY count DESC
        """
    ).fetchall()
    return [(row["status"], row["count"]) for row in rows]


def fetch_monthly_velocity(conn: sqlite3.Connection) -> List[Tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT strftime('%Y-%m', applied_date) as month, COUNT(*) as count
        FROM applications
        GROUP BY month
        ORDER BY month
        """
    ).fetchall()
    return [(row["month"], row["count"]) for row in rows]


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=True, port=port)
