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
        print(f"  Saved: {name} — {score}/{total} ({percent}) | violations: {violations}{flag_note}")
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
        resp = http_requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLE}?select=*&order=timestamp.desc",
            headers={**supabase_headers(), "Prefer": ""},
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()

        lines = ["Timestamp,Name,Score,Total,Percent,Violations,Flagged"]
        for r in rows:
            lines.append(",".join([
                r.get("timestamp", ""),
                f'"{r.get("name","")}"',
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
            headers={"Content-Disposition": "attachment; filename=scores.csv"},
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
