"""
iperf_runner.py – iperf3 CLI Wrapper mit Live-Streaming über SocketIO
"""
import json
import subprocess
import threading
import time
from datetime import datetime

# Globaler Test-State (Thread-safe via Lock)
test_lock = threading.Lock()
current_run_type = "none"      # "manual" | "auto" | "none"
current_run_info = {}          # Live-Infos für Status-Endpoint
_socketio_ref = None           # wird von app.py gesetzt


def set_socketio(sio):
    global _socketio_ref
    _socketio_ref = sio


def _emit(event, data):
    if _socketio_ref:
        _socketio_ref.emit(event, data)


def is_locked():
    return test_lock.locked()


def get_status():
    return {
        "running": test_lock.locked(),
        "run_type": current_run_type if test_lock.locked() else "none",
        "info": current_run_info if test_lock.locked() else {},
    }


def run_iperf3(target_ip: str, target_port: int, run_type: str, duration: int = 10, on_complete=None):
    """
    Startet iperf3 als Client gegen target_ip:target_port.
    Gibt (success: bool, result: dict) zurück.
    on_complete(success, result) wird nach Abschluss im Thread aufgerufen.
    """
    global current_run_type, current_run_info

    acquired = test_lock.acquire(blocking=False)
    if not acquired:
        return False, {"error": f"Ein Test läuft bereits ({current_run_type})"}

    try:
        current_run_type = run_type
        current_run_info = {
            "target_ip": target_ip,
            "target_port": target_port,
            "started_at": datetime.utcnow().isoformat(),
            "run_type": run_type,
        }
        _emit("test_started", {"run_type": run_type, "target": f"{target_ip}:{target_port}"})

        # ------ Download-Test (Normal) ------
        dl_result = _run_single(target_ip, target_port, duration, reverse=False)
        # ------ Upload-Test (Reverse) ------
        ul_result = _run_single(target_ip, target_port, duration, reverse=True)

        success = dl_result["success"] or ul_result["success"]
        result = {
            "target_ip": target_ip,
            "target_port": target_port,
            "run_type": run_type,
            "download_mbps": dl_result.get("bandwidth_mbps"),
            "upload_mbps": ul_result.get("bandwidth_mbps"),
            "jitter_ms": dl_result.get("jitter_ms"),
            "packet_loss_pct": dl_result.get("packet_loss_pct"),
            "duration_s": dl_result.get("duration_s"),
            "retransmits": dl_result.get("retransmits"),
            "raw_json": json.dumps({"download": dl_result.get("raw"), "upload": ul_result.get("raw")}),
            "status": "success" if success else "error",
            "error_msg": dl_result.get("error") if not success else None,
        }
        _emit("test_finished", result)
        if on_complete:
            on_complete(success, result)
        return success, result

    finally:
        current_run_type = "none"
        current_run_info = {}
        test_lock.release()


def _run_single(target_ip, target_port, duration, reverse=False):
    """Führt einen iperf3-Run aus und parst das JSON-Ergebnis."""
    cmd = [
        "iperf3",
        "-c", target_ip,
        "-p", str(target_port),
        "-t", str(duration),
        "--json",
        "--connect-timeout", "5000",
    ]
    if reverse:
        cmd.append("-R")

    direction = "upload" if reverse else "download"

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=duration + 30
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            _emit("live_data", {"direction": direction, "error": err})
            return {"success": False, "error": err}

        data = json.loads(proc.stdout)
        end = data.get("end", {})
        streams = end.get("sum_received") or end.get("sum_sent") or {}

        bps = streams.get("bits_per_second", 0)
        mbps = round(bps / 1_000_000, 2)
        jitter = streams.get("jitter_ms")
        loss = streams.get("lost_percent")
        duration_s = streams.get("seconds")
        retransmits = end.get("sum_sent", {}).get("retransmits")

        payload = {
            "direction": direction,
            "bandwidth_mbps": mbps,
            "jitter_ms": jitter,
            "packet_loss_pct": loss,
            "duration_s": duration_s,
            "retransmits": retransmits,
        }
        _emit("live_data", payload)

        return {
            "success": True,
            "bandwidth_mbps": mbps,
            "jitter_ms": jitter,
            "packet_loss_pct": loss,
            "duration_s": duration_s,
            "retransmits": retransmits,
            "raw": data,
        }

    except subprocess.TimeoutExpired:
        _emit("live_data", {"direction": direction, "error": "Timeout"})
        return {"success": False, "error": "iperf3 Timeout"}
    except json.JSONDecodeError as e:
        _emit("live_data", {"direction": direction, "error": f"JSON Parse Fehler: {e}"})
        return {"success": False, "error": f"JSON Parse Fehler: {e}"}
    except FileNotFoundError:
        _emit("live_data", {"direction": direction, "error": "iperf3 nicht gefunden"})
        return {"success": False, "error": "iperf3 ist nicht installiert"}
    except Exception as e:
        _emit("live_data", {"direction": direction, "error": str(e)})
        return {"success": False, "error": str(e)}
