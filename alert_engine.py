"""Local-only threshold alert engine, independent from any GUI or Windows API.

An event is an OBSERVATION, not proof of hardware damage or active AI inference.
Uses monotonic time for sustained-duration / cooldown / snooze correctness.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

METRICS = ("cpu_percent", "ram_percent", "gpu_percent", "disk_percent",
           "vram_free_mib", "ai_candidate_present", "ai_cpu_high",
           "process_present", "process_memory_mib")
PERCENT_METRICS = {"cpu_percent", "ram_percent", "gpu_percent", "disk_percent", "ai_cpu_high"}
ALLOWED_LEVELS = ("warning", "critical")
MAX_RULES = 16


@dataclass(frozen=True)
class Rule:
    id: str
    metric: str
    threshold: float
    duration_s: int
    cooldown_s: int = 300
    level: str = "warning"
    enabled: bool = True
    target: str = ""

    def validate(self):
        if not self.id.isascii() or not (1 <= len(self.id) <= 48) or not all(
                c.isalnum() or c in "_-" for c in self.id):
            raise ValueError("Invalid rule ID")
        if self.metric not in METRICS or self.level not in ALLOWED_LEVELS:
            raise ValueError("Unsupported rule metric or severity")
        if not isinstance(self.threshold, (int, float)) or not math.isfinite(self.threshold):
            raise ValueError("Threshold must be finite")
        upper = 65536 if self.metric in ("vram_free_mib", "process_memory_mib") else 100
        if not 0 <= self.threshold <= upper:
            raise ValueError("Threshold out of range")
        if self.metric in ("process_present", "process_memory_mib"):
            if not re.fullmatch(r"[A-Za-z0-9._ -]{1,80}", self.target):
                raise ValueError("Process rule needs a simple executable name")
        elif self.target:
            raise ValueError("Target is allowed only for process rules")
        if self.metric in ("process_present", "ai_candidate_present") and self.threshold != 1:
            raise ValueError("AI process detection must have threshold 1")
        if not isinstance(self.duration_s, int) or not 0 <= self.duration_s <= 3600:
            raise ValueError("Duration must be 0-3600 seconds")
        if not isinstance(self.cooldown_s, int) or not 30 <= self.cooldown_s <= 86400:
            raise ValueError("Cooldown must be 30-86400 seconds")
        if type(self.enabled) is not bool:
            raise ValueError("Enabled must be Boolean")
        return self


@dataclass(frozen=True)
class AlertEvent:
    rule_id: str
    metric: str
    kind: str        # ALERT, REPEAT, RECOVERED
    level: str
    value: float
    threshold: float
    timestamp_utc: str


def default_rules(*, ai: bool = False) -> list[Rule]:
    rules = [
        Rule("cpu_high", "cpu_percent", 85, 30, 300, "warning"),
        Rule("ram_high", "ram_percent", 90, 20, 300, "critical"),
        Rule("disk_full", "disk_percent", 95, 30, 600, "critical"),
        Rule("gpu_high", "gpu_percent", 90, 30, 300, "warning", not ai),
        Rule("vram_low", "vram_free_mib", 1024, 20, 300, "warning", not ai),
    ]
    if ai:
        rules += [
            Rule("ai_candidate", "ai_candidate_present", 1, 0, 300, "warning"),
            Rule("ai_cpu_high", "ai_cpu_high", 85, 30, 300, "critical"),
        ]
    return rules


def metric_value(sample: dict, name: str, target: str = "") -> float | None:
    if name == "process_present":
        value = 1.0 if any(str(p.get("name") or "").casefold() == target.casefold()
                           for p in sample.get("observed_processes", ())) else 0.0
    elif name == "process_memory_mib":
        amounts = [float(p["memory_mib"]) for p in sample.get("observed_processes", ())
                   if str(p.get("name") or "").casefold() == target.casefold()
                   and isinstance(p.get("memory_mib"), (float, int))]
        value = max(amounts) if amounts else None
    elif name == "vram_free_mib":
        used, total = sample.get("vram_used_mib"), sample.get("vram_total_mib")
        value = total - used if isinstance(used, (float, int)) and isinstance(total, (float, int)) else None
    elif name == "ai_candidate_present":
        value = 1.0 if sample.get("local_ai_related_process_candidates") else 0.0
    elif name == "ai_cpu_high":
        if not sample.get("local_ai_related_process_candidates"):
            value = None  # a missing AI candidate is NOT an active AI workload
        else:
            value = sample.get("cpu_percent")
    else:
        value = sample.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def meets(rule: Rule, value: float) -> bool:
    if rule.metric == "vram_free_mib":
        return value <= rule.threshold
    return value >= rule.threshold


class AlertEngine:
    """Driven only by new samples while the application monitor is explicitly running."""

    def __init__(self, rules: list[Rule]):
        self.replace_rules(rules)
        self.history: deque[AlertEvent] = deque(maxlen=200)
        self.snooze_until = -1.0
        self._state: dict[str, dict] = {}
        self.recovery_enabled = True

    def replace_rules(self, rules: list[Rule]) -> None:
        if not 1 <= len(rules) <= MAX_RULES or len({r.id for r in rules}) != len(rules):
            raise ValueError("Require unique rule IDs, 1-16 rules")
        for r in rules:
            r.validate()
        self.rules = list(rules)
        # Modifying any thresholds clears pending timers to prevent stale alert triggers.
        self._state = {}

    def clear_runtime(self):
        self._state.clear()

    def snooze(self, minutes: int = 10, *, now: float | None = None):
        if minutes not in (10, 30, 60):
            raise ValueError("Only 10, 30, 60 minute snooze options")
        now = time.monotonic() if now is None else now
        self.snooze_until = now + minutes * 60

    def process(self, sample: dict, *, now: float | None = None) -> list[AlertEvent]:
        now = time.monotonic() if now is None else now
        emitted = []
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for rule in self.rules:
            st = self._state.setdefault(rule.id, {"since": None, "active": False, "last": None})
            if not rule.enabled:
                st.update(since=None, active=False, last=None)
                continue
            val = metric_value(sample, rule.metric, rule.target)
            if val is None:
                # Unavailable is NOT zero / normal, and must not trigger recovery.
                st.update(since=None, active=False, last=None)
                continue
            is_high = meets(rule, val)
            if not is_high:
                if st["active"] and self.recovery_enabled and now >= self.snooze_until:
                    e = AlertEvent(rule.id, rule.metric, "RECOVERED", "info",
                                   val, rule.threshold, stamp)
                    self.history.append(e)
                    emitted.append(e)
                st.update(since=None, active=False, last=None)
                continue
            if st["since"] is None or now < st["since"]:
                st["since"] = now
            if now - st["since"] < rule.duration_s:
                continue
            # Snooze blocks external and in-app events, not subsequent evaluation.
            if now < self.snooze_until:
                continue
            if st["last"] is not None and now - st["last"] < rule.cooldown_s:
                continue
            kind = "REPEAT" if st["active"] else "ALERT"
            event = AlertEvent(rule.id, rule.metric, kind, rule.level,
                               val, rule.threshold, stamp)
            st["active"] = True
            st["last"] = now
            self.history.append(event)
            emitted.append(event)
        return emitted


def config_path(product: str) -> Path:
    if product not in ("CPU_GPU_Monitor", "AI_PC_Monitor"):
        raise ValueError("Unknown product")
    base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / product / "alert_rules.json"


def read_rules(product: str, *, destination: Path | None = None) -> tuple[list[Rule], bool, bool]:
    """Unknown/broken configs fail closed to defaults (notifications OFF)."""
    defaults = default_rules(ai=product == "AI_PC_Monitor")
    path = destination or config_path(product)
    try:
        if path.is_symlink() or not path.exists() or path.stat().st_size > 32768:
            return defaults, False, False
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != 1:
            return defaults, False, False
        rules = [Rule(**r).validate() for r in data["rules"]]
        if not 1 <= len(rules) <= MAX_RULES or len({r.id for r in rules}) != len(rules):
            return defaults, False, False
        if type(data.get("windows_toast")) is not bool or type(data.get("alerts_enabled")) is not bool:
            return defaults, False, False
        return rules, data["alerts_enabled"], data["windows_toast"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return defaults, False, False


def save_rules(product: str, rules: list[Rule], enabled: bool, windows_toast: bool,
               *, destination: Path | None = None) -> Path:
    if type(enabled) is not bool or type(windows_toast) is not bool:
        raise ValueError("Options must be Booleans")
    AlertEngine(rules)
    path = destination or config_path(product)
    if path.is_symlink():
        raise ValueError("Refusing symlink settings destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"schema": 1, "alerts_enabled": enabled, "windows_toast": windows_toast,
            "rules": [asdict(r) for r in rules]}
    fd, tmp = tempfile.mkstemp(prefix=".alert-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path
