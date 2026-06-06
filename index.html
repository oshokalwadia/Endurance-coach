"""
Web service for the Endurance Coach PWA.

Serves the installable mobile dashboard (web/static) and a small JSON API the
front-end calls:

    GET /api/data?days=14   -> recent daily rows (for charts + today's card)

Data source:
  * LIVE  (DRY_RUN=false): reads your Google Sheet (the cron job populates it).
  * DRY_RUN=true:          computes mock days so you can preview the PWA with
                           no keys at all.

Run locally:
    python web/app.py            # http://localhost:8000

Deploy: see README "Put it on your phone (PWA)".
"""
import os
import sys

# allow `import config`, `pipeline`, etc. when run from repo root or /web
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request, send_from_directory

from config import config

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app = Flask(__name__, static_folder=STATIC, static_url_path="")


@app.route("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.route("/api/data")
def data():
    days = int(request.args.get("days", 14))
    if config.DRY_RUN:
        from pipeline import build_recent
        rows = build_recent(days)
    else:
        from clients.sheets import SheetStore
        rows = SheetStore().read_recent(days)
    return jsonify({
        "athlete": config.athlete.name,
        "goal": config.athlete.goal,
        "mode": "dry_run" if config.DRY_RUN else "live",
        "rows": rows,
    })


# service worker must be served from root scope to control the whole app
@app.route("/service-worker.js")
def sw():
    return send_from_directory(STATIC, "service-worker.js", mimetype="application/javascript")


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(STATIC, "manifest.webmanifest",
                               mimetype="application/manifest+json")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
