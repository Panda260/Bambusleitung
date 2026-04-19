"""
scheduler.py – APScheduler für automatische Intervall-Tests
"""
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


_scheduler = BackgroundScheduler(timezone="UTC")
_job = None
_config_ref = None
_save_result_fn = None


def set_references(config_getter, save_result_fn):
    """Wird von app.py aufgerufen um Zugriff auf Config + DB zu geben."""
    global _config_ref, _save_result_fn
    _config_ref = config_getter
    _save_result_fn = save_result_fn


def _auto_run():
    """Job der vom Scheduler aufgerufen wird."""
    from iperf_runner import run_iperf3, is_locked, current_run_type

    if _config_ref is None:
        return

    cfg = _config_ref()
    if not cfg.get("enabled", False):
        return

    target_ip = cfg.get("target_ip", "")
    target_port = cfg.get("target_port", 5201)
    duration = cfg.get("test_duration", 10)

    if not target_ip:
        return

    # Wenn manuell läuft → skip (warten bis nächster Slot)
    if is_locked():
        from iperf_runner import _emit
        _emit("scheduler_skip", {
            "reason": f"Test läuft bereits ({current_run_type}), überspringe automatischen Run"
        })
        return

    # Test starten (non-blocking via Thread)
    def run():
        success, result = run_iperf3(
            target_ip, target_port, run_type="auto", duration=duration,
            on_complete=_save_result_fn
        )

    t = threading.Thread(target=run, daemon=True)
    t.start()


def start_scheduler():
    if not _scheduler.running:
        _scheduler.start()


def update_job(interval_minutes: int, enabled: bool):
    """Aktualisiert den Scheduler-Job mit neuem Intervall."""
    global _job

    if _job:
        try:
            _scheduler.remove_job("auto_speedtest")
        except Exception:
            pass
        _job = None

    if enabled and interval_minutes > 0:
        _job = _scheduler.add_job(
            _auto_run,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="auto_speedtest",
            name="Automatischer Speedtest",
            replace_existing=True,
        )


def get_next_run():
    """Gibt den nächsten geplanten Zeitpunkt zurück."""
    job = _scheduler.get_job("auto_speedtest")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None
