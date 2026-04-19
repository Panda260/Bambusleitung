"""
app.py – Flask + SocketIO Haupt-Anwendung für Bambusleitung
"""
import io
import json
import os
import secrets
import threading
from datetime import datetime
from functools import wraps

import eventlet
eventlet.monkey_patch()

from flask import Flask, jsonify, request, send_file, send_from_directory, session
from flask_cors import CORS
from flask_socketio import SocketIO, disconnect

from db import init_db, get_session, SpeedTestResult
from exporter import export_to_excel
import iperf_runner
import scheduler

# ─── App Setup ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet", logger=False, engineio_logger=False)

# iperf_runner mit SocketIO-Referenz versorgen
iperf_runner.set_socketio(socketio)

# ─── Auth ─────────────────────────────────────────────────────────────────────
# Wenn UI_PASSWORD nicht gesetzt oder leer → kein Login erforderlich
UI_PASSWORD = os.environ.get("UI_PASSWORD", "").strip()
AUTH_REQUIRED = bool(UI_PASSWORD)


def is_authenticated():
    if not AUTH_REQUIRED:
        return True
    return session.get("authenticated") is True


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return jsonify({"error": "Nicht autorisiert", "auth_required": True}), 401
        return f(*args, **kwargs)
    return decorated


# ─── Konfiguration (in-memory, persistent über /data/config.json) ─────────────
DATA_DIR = os.environ.get("DATA_DIR", "/data")
os.makedirs(DATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

# Defaults können per Docker-ENV überschrieben werden
DEFAULT_CONFIG = {
    "target_ip":        os.environ.get("IPERF_TARGET_IP", ""),
    "target_port":      int(os.environ.get("IPERF_TARGET_PORT", 5201)),
    "interval_minutes": int(os.environ.get("IPERF_INTERVAL_MINUTES", 15)),
    "test_duration":    int(os.environ.get("IPERF_TEST_DURATION", 10)),
    "enabled":          os.environ.get("IPERF_ENABLED", "false").lower() == "true",
    "iperf_params":     os.environ.get("IPERF_EXTRA_PARAMS", ""),
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
                return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ─── DB Result speichern ──────────────────────────────────────────────────────
def save_result(success: bool, result: dict):
    db_session = get_session()
    try:
        entry = SpeedTestResult(
            timestamp=datetime.utcnow(),
            target_ip=result.get("target_ip", ""),
            target_port=result.get("target_port", 0),
            run_type=result.get("run_type", "manual"),
            download_mbps=result.get("download_mbps"),
            upload_mbps=result.get("upload_mbps"),
            jitter_ms=result.get("jitter_ms"),
            packet_loss_pct=result.get("packet_loss_pct"),
            duration_s=result.get("duration_s"),
            retransmits=result.get("retransmits"),
            status=result.get("status", "error"),
            error_msg=result.get("error_msg"),
            raw_json=result.get("raw_json"),
        )
        db_session.add(entry)
        db_session.commit()
        socketio.emit("history_update", entry.to_dict())
    finally:
        db_session.close()


# ─── Scheduler initialisieren ─────────────────────────────────────────────────
scheduler.set_references(load_config, save_result)
scheduler.start_scheduler()


def apply_scheduler():
    cfg = load_config()
    scheduler.update_job(cfg.get("interval_minutes", 15), cfg.get("enabled", False))


apply_scheduler()

# ─── REST API ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ── Auth-Endpunkte ────────────────────────────────────────────

@app.route("/api/auth/status", methods=["GET"])
def auth_status():
    """Gibt zurück ob Auth nötig und ob der aktuelle User eingeloggt ist."""
    return jsonify({
        "auth_required": AUTH_REQUIRED,
        "authenticated": is_authenticated(),
    })


@app.route("/api/auth/login", methods=["POST"])
def login():
    if not AUTH_REQUIRED:
        return jsonify({"success": True, "message": "Kein Passwort konfiguriert."})

    data = request.get_json(force=True) or {}
    password = data.get("password", "")

    if secrets.compare_digest(password, UI_PASSWORD):
        session.permanent = True
        session["authenticated"] = True
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": "Falsches Passwort"}), 401


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


# ── Geschützte Endpunkte ──────────────────────────────────────

@app.route("/api/config", methods=["GET"])
@login_required
def get_config():
    cfg = load_config()
    cfg["next_run"] = scheduler.get_next_run()
    return jsonify(cfg)


@app.route("/api/config", methods=["POST"])
@login_required
def set_config():
    data = request.get_json(force=True)
    cfg = load_config()
    for key in ("target_ip", "target_port", "interval_minutes", "test_duration", "enabled", "iperf_params"):
        if key in data:
            cfg[key] = data[key]
    save_config(cfg)
    apply_scheduler()
    cfg["next_run"] = scheduler.get_next_run()
    socketio.emit("config_update", cfg)
    return jsonify(cfg)


@app.route("/api/status", methods=["GET"])
def get_status():
    # Status ist immer öffentlich (braucht Healthcheck ohne Auth)
    status = iperf_runner.get_status()
    status["next_run"] = scheduler.get_next_run()
    return jsonify(status)


@app.route("/api/run", methods=["POST"])
@login_required
def manual_run():
    """Manuellen Test starten."""
    if iperf_runner.is_locked():
        run_type = iperf_runner.current_run_type
        return jsonify({
            "success": False,
            "error": f"Ein {run_type}er Test läuft bereits. Bitte warten."
        }), 409

    cfg = load_config()
    target_ip = cfg.get("target_ip", "").strip()
    target_port = cfg.get("target_port", 5201)
    duration = cfg.get("test_duration", 10)
    iperf_params = cfg.get("iperf_params", "")

    if not target_ip:
        return jsonify({"success": False, "error": "Keine Ziel-IP konfiguriert."}), 400

    def run():
        iperf_runner.run_iperf3(
            target_ip, target_port, run_type="manual", duration=duration,
            iperf_params=iperf_params,
            on_complete=save_result
        )

    t = threading.Thread(target=run, daemon=True)
    t.start()

    return jsonify({"success": True, "message": f"Manueller Test gestartet → {target_ip}:{target_port}"}), 202


@app.route("/api/history", methods=["GET"])
@login_required
def get_history():
    limit = request.args.get("limit", 200, type=int)
    db_session = get_session()
    try:
        results = (
            db_session.query(SpeedTestResult)
            .order_by(SpeedTestResult.timestamp.desc())
            .limit(limit)
            .all()
        )
        return jsonify([r.to_dict() for r in results])
    finally:
        db_session.close()


@app.route("/api/export", methods=["GET"])
@login_required
def export_excel():
    db_session = get_session()
    try:
        results = (
            db_session.query(SpeedTestResult)
            .order_by(SpeedTestResult.timestamp.asc())
            .all()
        )
        data = [r.to_dict() for r in results]
    finally:
        db_session.close()

    excel_bytes = export_to_excel(data)
    filename = f"bambusleitung_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        io.BytesIO(excel_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


# ─── SocketIO Events ──────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    # Socket-Verbindung nur wenn authentifiziert (oder kein Auth nötig)
    if AUTH_REQUIRED and not is_authenticated():
        disconnect()
        return False

    status = iperf_runner.get_status()
    status["next_run"] = scheduler.get_next_run()
    socketio.emit("status", status, room=request.sid)


# ─── Start ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    auth_info = f"🔒 Passwort-Schutz aktiv" if AUTH_REQUIRED else "🔓 Kein Passwort-Schutz"
    print(f"🎋 Bambusleitung startet auf Port {port} ... ({auth_info})")
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)
