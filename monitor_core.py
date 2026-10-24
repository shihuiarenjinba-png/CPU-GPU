"""Local-only opt-in CPU/RAM/GPU monitor; GPU 0 readings need NVIDIA nvidia-smi."""
from __future__ import annotations

import csv
import os
import shutil
import subprocess
import tempfile
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except ImportError:  # the app will show a clear missing-dependency error
    psutil = None

MAX_SAMPLES = 900
COLUMNS = ("timestamp_utc", "cpu_percent", "ram_percent", "ram_used_bytes",
           "ram_total_bytes", "disk_percent", "gpu_percent", "vram_used_mib",
           "vram_total_mib", "gpu_temp_c")


def gpu_snapshot(*, which=shutil.which, runner=subprocess.run) -> dict:
    """NVIDIA GPU 0 only. Never replace unavailable measurements with 0."""
    empty = {"gpu_status": "UNAVAILABLE", "gpu_percent": None,
             "vram_used_mib": None, "vram_total_mib": None,
             "gpu_temp_c": None}
    executable = which("nvidia-smi")
    if not executable:
        return empty
    cmd = [executable, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
           "--format=csv,noheader,nounits"]
    try:
        result = runner(cmd, capture_output=True, text=True, timeout=3, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return empty
        fields = next(csv.reader(result.stdout.splitlines()))
        if len(fields) != 4:
            return empty
        def number(s):
            try:
                return float(s.strip())
            except (ValueError, TypeError):
                return None
        usage, vused, vtotal, temp = (number(field) for field in fields)
        return {"gpu_status": "MEASURED_NVIDIA_GPU_0" if usage is not None else "UNAVAILABLE",
                "gpu_percent": usage, "vram_used_mib": vused,
                "vram_total_mib": vtotal, "gpu_temp_c": temp}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return empty


def sample(*, disk: str | Path | None = None, gpu_reader=gpu_snapshot) -> dict:
    if psutil is None:
        raise RuntimeError("psutil is required: pip install -r requirements.txt")
    cpu = float(psutil.cpu_percent(interval=0.1))
    mem = psutil.virtual_memory()
    disk_usage = psutil.disk_usage(str(disk or Path.home()))
    processes = []
    for process in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = process.info
            mi = info.get("memory_info")
            if not mi:
                continue
            processes.append({"pid": int(info["pid"]), "name": str(info.get("name") or ""),
                              "memory_mib": round(mi.rss / 1048576, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess,
                PermissionError, OSError, KeyError, ValueError):
            continue
    processes.sort(key=lambda p: p["memory_mib"], reverse=True)
    result = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "cpu_percent": cpu, "ram_percent": float(mem.percent),
              "ram_used_bytes": int(mem.used), "ram_total_bytes": int(mem.total),
              "disk_percent": float(disk_usage.percent), "top_processes": processes[:10],
              "observed_processes": processes,
              "cpu_temp_c": None, "cpu_temp_status": "UNAVAILABLE"}
    result.update(gpu_reader())
    return result


def export_csv(samples: list[dict], destination: Path) -> Path:
    """Explicit export only; atomically replace the chosen CSV (confirm in UI)."""
    dest = Path(destination)
    if dest.is_symlink():
        raise ValueError("Refusing to follow symlink export destination")
    if not dest.parent.is_dir():
        raise FileNotFoundError("Export destination directory does not exist")
    fd, tmp = tempfile.mkstemp(prefix=".cpu-gpu-", suffix=".csv", dir=dest.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            for item in samples[-MAX_SAMPLES:]:
                writer.writerow({key: item.get(key) for key in COLUMNS})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return dest


class Monitor:
    """Starts OFF. No files, process command-lines, network or chats collected."""
    def __init__(self, interval: float = 2, sampler=sample):
        if not 1 <= interval <= 30:
            raise ValueError("interval must be 1..30 seconds")
        self.interval = interval
        self.sampler = sampler
        self.history: deque[dict] = deque(maxlen=MAX_SAMPLES)
        self.errors: deque[str] = deque(maxlen=8)
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.on_sample = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        def work():
            while not self.stop_event.is_set():
                try:
                    record = self.sampler()
                    self.history.append(record)
                    if self.on_sample:
                        self.on_sample(record)
                except Exception as exc:
                    self.errors.append(f"{type(exc).__name__}: {exc}")
                if self.stop_event.wait(self.interval):
                    break
        self.thread = threading.Thread(target=work, name="cpu-gpu-local-monitor", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=4)

    def clear(self):
        self.history.clear()
