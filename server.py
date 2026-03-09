#!/usr/bin/env python3
"""
Java ITS Reviewer — Flask server with Supabase
Serves index.html/admin.html and saves exam scores to Supabase.

Usage:
    pip install -r requirements.txt
    python3 server.py
"""

import os
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory, Response
import requests as http_requests

# Load .env file if present (for local development)
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

app = Flask(__name__, static_folder=os.path.dirname(__file__))

# ── Supabase config (set these in Render environment variables) ──
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")          # e.g. https://xxxx.supabase.co
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")  # service_role key (not anon)
TABLE = "scores"

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "teacher2024")


def supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


# ── Routes ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/admin")
def admin():
    return send_from_directory(app.static_folder, "admin.html")


@app.route("/batch1")
def batch1():
    return send_from_directory(app.static_folder, "index-batch1.html")


@app.route("/batch2")
def batch2():
    return send_from_directory(app.static_folder, "index-batch2.html")


@app.route("/batch3")
def batch3():
    return send_from_directory(app.static_folder, "index-batch3.html")


@app.route("/batch4")
def batch4():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/submit", methods=["POST", "OPTIONS"])
def submit():
    if request.method == "OPTIONS":
        return _cors_preflight()

    data = request.get_json(force=True, silent=True) or {}
    name       = str(data.get("name", "")).strip() or "Unknown"
    score      = int(data.get("score", 0))
    total      = int(data.get("total", 0))
    percent    = str(data.get("percent", "0%"))
    violations = int(data.get("violations", 0))
    batch      = str(data.get("batch", "Unknown"))
    flagged    = violations >= 3
    timestamp  = datetime.now(timezone.utc).isoformat()

    row = {
        "timestamp":  timestamp,
        "name":       name,
        "score":      score,
        "total":      total,
        "percent":    percent,
        "violations": violations,
        "flagged":    flagged,
        "batch":      batch,
    }

    try:
        resp = http_requests.post(
            f"{SUPABASE_URL}/rest/v1/{TABLE}",
            headers=supabase_headers(),
            json=row,
            timeout=10,
        )
        resp.raise_for_status()
        flag_note = " ⚠ FLAGGED" if flagged else ""
        print(f"  Saved: {name} [{batch}] — {score}/{total} ({percent}) | violations: {violations}{flag_note}")
        return jsonify({"ok": True}), 200
    except Exception as e:
        print(f"  ERROR saving score: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/scores-data")
def scores_data():
    try:
        resp = http_requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}?select=*&order=timestamp.desc",
            headers={**supabase_headers(), "Prefer": ""},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        # Normalise keys to match what admin.html expects (capitalised)
        normalised = [
            {
                "Timestamp":  r.get("timestamp", ""),
                "Name":       r.get("name", ""),
                "Batch":      r.get("batch", ""),
                "Score":      r.get("score", 0),
                "Total":      r.get("total", 0),
                "Percent":    r.get("percent", "0%"),
                "Violations": r.get("violations", 0),
                "Flagged":    "YES" if r.get("flagged") else "no",
            }
            for r in rows
        ]
        return jsonify(normalised), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/scores-download")
def scores_download():
    try:
        batch_filter = request.args.get("batch", "")
        resp = http_requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}?select=*&order=timestamp.desc",
            headers={**supabase_headers(), "Prefer": ""},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()

        if batch_filter:
            rows = [r for r in rows if r.get("batch", "") == batch_filter]

        filename = f"scores_{batch_filter.replace(' ', '_')}.csv" if batch_filter else "scores.csv"
        lines = ["Timestamp,Name,Batch,Score,Total,Percent,Violations,Flagged"]
        for r in rows:
            lines.append(",".join([
                r.get("timestamp", ""),
                f'"{r.get("name","")}"',
                r.get("batch", ""),
                str(r.get("score", 0)),
                str(r.get("total", 0)),
                r.get("percent", "0%"),
                str(r.get("violations", 0)),
                "YES" if r.get("flagged") else "no",
            ]))

        csv_text = "\n".join(lines)
        return Response(
            csv_text,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _cors_preflight():
    r = app.make_response("")
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r, 200


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


# ── Static files (css, images, etc.) ─────────────────────────────

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8082))
    print(f"Java ITS Reviewer running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
