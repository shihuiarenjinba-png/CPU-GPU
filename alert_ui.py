"""Bilingual alert configuration + in-app history; no monitoring without Start.

Windows toasts are best effort, require OS notification registration/permissions,
and may not display for unsigned/uninstalled QA executables. In-app alerts work
independently. No network calls.
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from dataclasses import replace
from datetime import datetime
from tkinter import messagebox, ttk

from alert_engine import AlertEngine, Rule, default_rules, read_rules, save_rules, METRICS
from dark_theme import BG, BORDER, CARD, MUTED, TEXT

MESSAGES = {
    "ja": {
        "tab": "⚠ 通知とルール", "enable": "アラート有効", "windows": "Windows通知（任意）",
        "save": "設定を適用・保存", "snooze": "10分停止", "resume": "停止を解除",
        "add": "ルール追加", "apply": "選択ルール更新", "delete": "ルール削除",
        "rules": "監視ルール：項目を選び条件を編集できます",
        "history": "通知履歴（この起動中のみ）", "enabled": "有効", "metric": "検知条件",
        "threshold": "しきい値", "duration": "継続（秒）", "cooldown": "再通知（秒）",
        "target": "プロセス名", "severity": "重要度", "warn": "注意", "critical": "警告",
        "state": "状態", "ready": "監視停止中 / アラートは自動で動きません",
        "saved": "設定を保存しました（監視開始後に判定します）",
        "invalid": "設定値を確認してください", "alert": "警告", "repeat": "再通知",
        "recovered": "正常に戻りました", "ai_notice": "AI関連プロセスの候補を検出（推論中とは断定できません）",
        "process_missing": "対象プロセスの確認ができません", "blocked": "OS通知を送信できませんでした。アプリ内履歴は記録しています。",
        "paused": "通知を一時停止しています", "snoozed": "10分間通知を停止しました",
        "unsnoozed": "通知停止を解除しました", "active": "アラート: ",
        "off": "アラートOFF（設定タブで有効化）",
        "explain": "CPU/GPUが高いだけでは故障やAI推論中とは判定しません。"
                   "GPU値が取得不可ならGPU警告は発生しません。",
    },
    "en": {
        "tab": "⚠ Alerts & rules", "enable": "Enable alerts", "windows": "Windows toasts (optional)",
        "save": "Apply & save settings", "snooze": "Snooze 10 min", "resume": "Resume",
        "add": "Add rule", "apply": "Update selected rule", "delete": "Delete rule",
        "rules": "Alert rules: select and edit a condition",
        "history": "Alert history (this session only)", "enabled": "Enabled", "metric": "Condition",
        "threshold": "Threshold", "duration": "Duration (s)", "cooldown": "Cooldown (s)",
        "target": "Process name", "severity": "Severity", "warn": "Warning", "critical": "Critical",
        "state": "Status", "ready": "Monitoring stopped: alert evaluation is not running",
        "saved": "Settings saved. Alerts evaluate only after Start.",
        "invalid": "Check the rule inputs", "alert": "Alert", "repeat": "Reminder",
        "recovered": "Back to normal", "ai_notice": "Local AI-related process candidate (NOT proof of inference)",
        "process_missing": "Process is not observed", "blocked": "Windows toast unavailable; in-app history still works.",
        "paused": "Notifications temporarily snoozed", "snoozed": "Alerts snoozed for 10 min",
        "unsnoozed": "Alerts resumed", "active": "Alert: ",
        "off": "Alerts OFF (enable from Alerts tab)",
        "explain": "High CPU/GPU alone never proves failure or AI inference. "
                   "Missing GPU sensor values never trigger GPU alerts.",
    },
}
METRIC_TEXT = {
    "ja": {
        "cpu_percent": "CPU使用率（%）", "ram_percent": "メモリ使用率（%）",
        "gpu_percent": "GPU使用率（%）", "disk_percent": "ディスク使用率（%）",
        "vram_free_mib": "VRAM残量（MiB以下）",
        "ai_candidate_present": "ローカルAI候補の起動",
        "ai_cpu_high": "AI候補あり＋CPU高負荷",
        "process_present": "指定プロセスの起動",
        "process_memory_mib": "指定プロセスのメモリ（MiB）",
    },
    "en": {
        "cpu_percent": "CPU usage (%)", "ram_percent": "RAM usage (%)",
        "gpu_percent": "GPU usage (%)", "disk_percent": "Disk used (%)",
        "vram_free_mib": "VRAM free below (MiB)",
        "ai_candidate_present": "AI process candidate present",
        "ai_cpu_high": "AI candidate + CPU high",
        "process_present": "Named process started",
        "process_memory_mib": "Named process RAM (MiB)",
    },
}


class AlertPanel:
    def __init__(self, root, tabs, product: str, get_lang, *, accent: str, on_status=None):
        self.root = root
        self.tabs = tabs
        self.product = product
        self.get_lang = get_lang
        self.accent = accent
        self.on_status = on_status
        self.rules, self.enabled, self.toasts = read_rules(product)
        self.engine = AlertEngine(self.rules)
        self.tab = ttk.Frame(tabs, style="Panel.TFrame", padding=9)
        tabs.add(self.tab)
        self.top_row = ttk.Frame(self.tab, style="Panel.TFrame")
        self.top_row.pack(fill="x", pady=2)
        self.enabled_var = tk.BooleanVar(value=self.enabled)
        self.toasts_var = tk.BooleanVar(value=self.toasts)
        self.enable_box = ttk.Checkbutton(self.top_row, variable=self.enabled_var)
        self.enable_box.pack(side="left", padx=5)
        self.toasts_box = ttk.Checkbutton(self.top_row, variable=self.toasts_var)
        self.toasts_box.pack(side="left", padx=5)
        self.save_button = ttk.Button(self.top_row, command=self.save, style="Primary.TButton")
        self.save_button.pack(side="left", padx=5)
        self.snooze_button = ttk.Button(self.top_row, command=self.snooze)
        self.snooze_button.pack(side="left", padx=5)
        self.resume_button = ttk.Button(self.top_row, command=self.resume, style="Quiet.TButton")
        self.resume_button.pack(side="left", padx=3)

        self.rules_title = ttk.Label(self.tab, style="PanelText.TLabel")
        self.rules_title.pack(anchor="w", pady=(5, 3))
        style = ttk.Style(root)
        style.configure("Alert.Treeview", background=CARD, fieldbackground=CARD,
                        foreground=TEXT, rowheight=25, borderwidth=0)
        style.map("Alert.Treeview", background=[("selected", "#284360")],
                  foreground=[("selected", TEXT)])
        style.configure("Alert.Treeview.Heading", background="#25364A", foreground=TEXT)
        self.tree = ttk.Treeview(self.tab, style="Alert.Treeview",
                                 columns=("metric", "threshold", "duration", "repeat", "state"),
                                 show="headings", height=5, selectmode="browse")
        for key, width in (("metric", 240), ("threshold", 90), ("duration", 110),
                           ("repeat", 120), ("state", 90)):
            self.tree.column(key, width=width, minwidth=65,
                             stretch=key == "metric", anchor="w")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self.selected)

        editor = ttk.Frame(self.tab, style="Panel.TFrame")
        editor.pack(fill="x", pady=(7, 4))
        self.metric_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.threshold_var = tk.StringVar()
        self.duration_var = tk.StringVar()
        self.cooldown_var = tk.StringVar()
        self.severity_var = tk.StringVar()
        self.rule_on_var = tk.BooleanVar(value=True)
        self.field_labels = {}
        self.metric_combo = ttk.Combobox(editor, textvariable=self.metric_var,
                                         state="readonly", width=26)
        self.target_entry = ttk.Entry(editor, textvariable=self.target_var, width=15)
        self.threshold_entry = ttk.Entry(editor, textvariable=self.threshold_var, width=9)
        self.duration_entry = ttk.Entry(editor, textvariable=self.duration_var, width=9)
        self.cooldown_entry = ttk.Entry(editor, textvariable=self.cooldown_var, width=9)
        self.severity_combo = ttk.Combobox(editor, textvariable=self.severity_var,
                                           values=("warning", "critical"),
                                           state="readonly", width=10)
        fields = (("metric", self.metric_combo), ("target", self.target_entry),
                  ("threshold", self.threshold_entry), ("duration", self.duration_entry),
                  ("cooldown", self.cooldown_entry), ("severity", self.severity_combo))
        for col, (name, control) in enumerate(fields):
            cell = ttk.Frame(editor, style="Panel.TFrame")
            cell.grid(row=0, column=col, padx=(0, 7), sticky="w")
            label = ttk.Label(cell, style="PanelText.TLabel")
            label.pack(anchor="w")
            control.pack(anchor="w")
            self.field_labels[name] = label
        ops = ttk.Frame(self.tab, style="Panel.TFrame")
        ops.pack(fill="x", pady=(2, 5))
        self.rule_box = ttk.Checkbutton(ops, variable=self.rule_on_var)
        self.rule_box.pack(side="left", padx=5)
        self.edit_button = ttk.Button(ops, command=self.edit_rule)
        self.edit_button.pack(side="left", padx=5)
        self.add_button = ttk.Button(ops, command=self.add_rule)
        self.add_button.pack(side="left", padx=5)
        self.remove_button = ttk.Button(ops, command=self.remove_rule, style="Quiet.TButton")
        self.remove_button.pack(side="left", padx=5)

        self.log_title = ttk.Label(self.tab, style="PanelText.TLabel")
        self.log_title.pack(anchor="w")
        self.log = tk.Listbox(self.tab, height=4, background="#0C1523",
                              foreground=TEXT, selectbackground="#294866",
                              font=("Consolas", 10), borderwidth=0)
        self.log.pack(fill="both", expand=True, pady=(3, 0))
        self.info_var = tk.StringVar()
        ttk.Label(self.tab, textvariable=self.info_var,
                  style="PanelText.TLabel", wraplength=900).pack(anchor="w", pady=3)
        self.refresh_locale()
        if self.rules:
            self.tree.selection_set(self.rules[0].id)
            self.selected()

    def w(self, key):
        return MESSAGES[self.get_lang()][key]

    def metrics(self):
        names = METRIC_TEXT[self.get_lang()]
        return {v: k for k, v in names.items()
                if self.product == "AI_PC_Monitor"
                or k not in ("ai_candidate_present", "ai_cpu_high")}

    def refresh_locale(self):
        lang = self.get_lang()
        self.tabs.tab(self.tab, text=self.w("tab"))
        for control, key in ((self.enable_box, "enable"), (self.toasts_box, "windows"),
                             (self.save_button, "save"), (self.snooze_button, "snooze"),
                             (self.resume_button, "resume"), (self.edit_button, "apply"),
                             (self.add_button, "add"), (self.remove_button, "delete"),
                             (self.rule_box, "enabled"), (self.rules_title, "rules"),
                             (self.log_title, "history")):
            control.configure(text=self.w(key))
        for key, label in self.field_labels.items():
            label.configure(text=self.w(key))
        for col, key in (("metric", "metric"), ("threshold", "threshold"),
                         ("duration", "duration"), ("repeat", "cooldown"),
                         ("state", "state")):
            self.tree.heading(col, text=self.w(key))
        self.metric_combo.configure(values=tuple(self.metrics()))
        self.refresh_rules()
        self.info_var.set(self.w("explain"))
        self.selected()

    def refresh_rules(self):
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for rule in self.rules:
            self.tree.insert("", "end", iid=rule.id,
                             values=(METRIC_TEXT[self.get_lang()][rule.metric],
                                     int(rule.threshold) if rule.threshold.is_integer() else rule.threshold,
                                     rule.duration_s, rule.cooldown_s,
                                     "ON" if rule.enabled else "OFF"))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])

    def selected(self, _event=None):
        chosen = self.tree.selection()
        rule = next((r for r in self.rules if chosen and r.id == chosen[0]), None)
        if rule is None:
            return
        names = METRIC_TEXT[self.get_lang()]
        self.metric_var.set(names[rule.metric])
        self.target_var.set(rule.target)
        self.threshold_var.set(str(rule.threshold))
        self.duration_var.set(str(rule.duration_s))
        self.cooldown_var.set(str(rule.cooldown_s))
        self.severity_var.set(rule.level)
        self.rule_on_var.set(rule.enabled)

    def parse_rule(self, id_value: str) -> Rule:
        metric = self.metrics().get(self.metric_var.get())
        if metric is None:
            raise ValueError("Invalid metric selection")
        target = self.target_var.get().strip() if metric.startswith("process_") else ""
        return Rule(id=id_value, metric=metric,
                    threshold=float(self.threshold_var.get()),
                    duration_s=int(self.duration_var.get()),
                    cooldown_s=int(self.cooldown_var.get()),
                    level=self.severity_var.get(), enabled=bool(self.rule_on_var.get()),
                    target=target).validate()

    def edit_rule(self):
        selected = self.tree.selection()
        if not selected:
            return
        try:
            changed = self.parse_rule(selected[0])
            self.rules = [changed if rule.id == selected[0] else rule for rule in self.rules]
            self.refresh_rules()
        except (ValueError, TypeError) as exc:
            messagebox.showerror(self.w("invalid"), str(exc), parent=self.root)

    def add_rule(self):
        for n in range(1, 100):
            ident = f"custom_{n}"
            if ident not in {r.id for r in self.rules}:
                break
        try:
            if len(self.rules) >= 16:
                raise ValueError("Maximum 16 rules")
            self.rules.append(self.parse_rule(ident))
            self.refresh_rules()
            self.tree.selection_set(ident)
        except (ValueError, TypeError) as exc:
            messagebox.showerror(self.w("invalid"), str(exc), parent=self.root)

    def remove_rule(self):
        selected = self.tree.selection()
        if selected and len(self.rules) > 1:
            self.rules = [r for r in self.rules if r.id != selected[0]]
            self.refresh_rules()

    def save(self):
        try:
            # Explicit Apply/Save means disabled/unapplied edits aren't silently activated.
            tested = AlertEngine(self.rules)
            save_rules(self.product, self.rules, bool(self.enabled_var.get()),
                       bool(self.toasts_var.get()))
            self.engine = tested
            self.enabled = bool(self.enabled_var.get())
            self.toasts = bool(self.toasts_var.get())
            self.info_var.set(self.w("saved"))
            if self.on_status:
                self.on_status(self.w("off") if not self.enabled else self.w("saved"))
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror(self.w("invalid"), str(exc), parent=self.root)

    def snooze(self):
        self.engine.snooze(10)
        self.info_var.set(self.w("snoozed"))

    def resume(self):
        self.engine.snooze_until = -1
        self.info_var.set(self.w("unsnoozed"))

    def on_sample(self, sample):
        if not self.enabled:
            return
        for event in self.engine.process(sample):
            metric = METRIC_TEXT[self.get_lang()].get(event.metric, event.metric)
            kind = {"ALERT": "alert", "REPEAT": "repeat",
                    "RECOVERED": "recovered"}[event.kind]
            stamp = datetime.now().strftime("%H:%M:%S")
            text = f"{self.w(kind)} · {metric}: {event.value:g}"
            if event.metric == "ai_candidate_present":
                text += " · " + self.w("ai_notice")
            self.log.insert(0, f"[{stamp}] {text}")
            if self.log.size() > 200:
                self.log.delete(200, "end")
            if self.on_status:
                self.on_status(text)
            self.popup(text, event.kind == "RECOVERED")
            if self.toasts:
                self.send_toast(text)

    def popup(self, text, recovered=False):
        # Nonmodal in-app alert; cannot block the sampling loop. It is dismissible.
        toast = tk.Toplevel(self.root)
        toast.title(self.w("recovered") if recovered else self.w("alert"))
        toast.configure(background="#14263B")
        toast.geometry("460x110")
        toast.transient(self.root)
        body = tk.Label(toast, text=text, wraplength=425, justify="left",
                        background="#14263B", foreground=("#77E4AD" if recovered else "#FFC27A"),
                        font=("Segoe UI", 11, "bold"), padx=15, pady=12)
        body.pack(fill="both", expand=True)
        toast.after(8500, lambda: toast.destroy() if toast.winfo_exists() else None)

    def send_toast(self, text):
        if sys.platform != "win32":
            self.info_var.set(self.w("blocked"))
            return
        def work():
            try:
                from winotify import Notification
                # Best-effort dispatch; OS notification settings or AppID registration
                # may block the visual toast. Never claim delivery from .show().
                Notification(app_id=("CPU GPU Monitor" if self.product == "CPU_GPU_Monitor"
                                     else "AI PC Monitor"),
                             title="PC Alert", msg=text).show()
            except Exception:
                try:
                    self.root.after(0, lambda: self.info_var.set(self.w("blocked")))
                except (tk.TclError, RuntimeError):
                    pass
        threading.Thread(target=work, name="local-alert-toast", daemon=True).start()
