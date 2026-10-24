"""CPU-GPU Monitor bilingual Windows GUI. Monitoring is off until Start."""
from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from monitor_core import Monitor, export_csv
from telemetry_plot import draw_telemetry
from alert_ui import AlertPanel
from dark_theme import CYAN, SOFT, apply_theme, dark_text, header, metric

WORDS = {
    "ja": {
        "title": "CPU・GPU モニター — ローカル計測", "overview": "概要",
        "processes": "メモリ使用量上位", "start": "計測開始", "stop": "停止",
        "export": "履歴をCSV保存", "clear": "履歴消去", "language": "English",
        "off": "停止中（自動計測しません）", "on": "計測中（2秒ごと）",
        "cpu": "CPU使用率", "ram": "メモリ使用率", "disk": "ディスク使用率",
        "gpu": "GPU使用率（NVIDIA GPU 0のみ）", "vram": "VRAM使用量",
        "temp": "GPU温度", "unsupported": "取得不可", "history": "履歴件数",
        "process_head": "PID    メモリ(MiB)    プロセス名", "notice":
        "GPU値は対応するnvidia-smiがある場合のみ表示。CPU温度は未対応。\n"
        "AI使用状況の判定・通信・ファイル内容の検査は行いません。",
        "no_data": "保存する履歴がありません", "saved": "CSVを保存しました",
        "confirm": "既存のファイルを上書きしますか？", "error": "エラー",
    },
    "en": {
        "title": "CPU / GPU Monitor — local only", "overview": "Overview",
        "processes": "Top memory processes", "start": "Start monitoring", "stop": "Stop",
        "export": "Export CSV", "clear": "Clear history", "language": "日本語",
        "off": "Stopped (no automatic sampling)", "on": "Running (every 2 seconds)",
        "cpu": "CPU usage", "ram": "RAM usage", "disk": "Disk usage",
        "gpu": "GPU usage (NVIDIA GPU 0 only)", "vram": "VRAM used",
        "temp": "GPU temperature", "unsupported": "Unavailable", "history": "History samples",
        "process_head": "PID    RAM(MiB)    Process name", "notice":
        "GPU readings require compatible nvidia-smi. CPU temperature is unsupported.\n"
        "This tool does not infer AI usage, access file contents, or connect to a server.",
        "no_data": "No history to export", "saved": "CSV exported",
        "confirm": "Overwrite existing file?", "error": "Error",
    },
}


class Application:
    def __init__(self, root: tk.Tk):
        self.root = root
        apply_theme(root, accent=CYAN)
        self.lang = "ja"
        self.monitor = Monitor(interval=2)
        self.messages: queue.Queue[dict] = queue.Queue()
        self.monitor.on_sample = self.messages.put
        self.last: dict | None = None
        self.root.geometry("980x700")
        self.root.minsize(740, 540)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.hero_title, self.hero_subtitle = header(
            root, "●  SYSTEM / PERFORMANCE", "CPU / GPU MONITOR",
            "リアルタイム・ローカル診断  /  HARDWARE TELEMETRY",
            right="LOCAL  •  READ ONLY")
        bar = ttk.Frame(root, style="Toolbar.TFrame", padding=(14, 10))
        bar.pack(fill="x")
        self.start_button = ttk.Button(bar, command=self.start, style="Primary.TButton")
        self.start_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(bar, command=self.stop)
        self.stop_button.pack(side="left", padx=4)
        self.export_button = ttk.Button(bar, command=self.export)
        self.export_button.pack(side="left", padx=4)
        self.clear_button = ttk.Button(bar, command=self.clear, style="Quiet.TButton")
        self.clear_button.pack(side="left", padx=4)
        self.language_button = ttk.Button(bar, command=self.switch_language, style="Quiet.TButton")
        self.language_button.pack(side="right", padx=4)

        self.status_var = tk.StringVar()
        ttk.Label(root, textvariable=self.status_var, style="Status.TLabel", padding=(19, 4)).pack(anchor="w")

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=10)
        self.overview_tab = ttk.Frame(self.tabs, style="Panel.TFrame", padding=15)
        self.process_tab = ttk.Frame(self.tabs, style="Panel.TFrame", padding=15)
        self.tabs.add(self.overview_tab)
        self.tabs.add(self.process_tab)
        self.alert_text = tk.StringVar(value="")
        ttk.Label(root, textvariable=self.alert_text, style="Status.TLabel",
                  padding=(19, 1)).pack(anchor="w", before=self.tabs)
        self.alert_panel = AlertPanel(root, self.tabs, "CPU_GPU_Monitor",
                                      lambda: self.lang, accent=CYAN,
                                      on_status=self.alert_text.set)

        self.values = {}
        self.row_labels = {}
        cards = ttk.Frame(self.overview_tab, style="Panel.TFrame")
        cards.pack(fill="both", expand=True)
        for col in range(3):
            cards.columnconfigure(col, weight=1, uniform="metrics")
        for idx, name in enumerate(("cpu", "ram", "gpu", "disk", "vram", "temp", "history")):
            frame, label, value = metric(cards, name, accent=name in {"cpu", "gpu", "history"})
            frame.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=5, pady=5)
            self.row_labels[name] = label
            self.values[name] = value
        self.live_chart = tk.Canvas(self.overview_tab, height=135, background=SOFT,
                                    highlightthickness=1, highlightbackground="#30425A")
        self.live_chart.pack(fill="x", pady=(9, 0))
        self.live_chart.bind("<Configure>", lambda event: self.draw_live_chart())
        self.notice = ttk.Label(self.overview_tab, wraplength=780, justify="left", style="PanelText.TLabel")
        self.notice.pack(anchor="w", pady=(12, 0))
        self.process_head = ttk.Label(self.process_tab, style="PanelText.TLabel")
        self.process_head.pack(anchor="w", pady=(2, 12))
        self.process_text = tk.Text(self.process_tab, wrap="none", height=12, state="disabled")
        dark_text(self.process_text)
        self.process_text.pack(fill="both", expand=True, pady=8)
        self.translate()
        self.root.after(250, self.poll)

    def w(self, key):
        return WORDS[self.lang][key]

    def translate(self):
        self.root.title(self.w("title"))
        self.hero_subtitle.configure(text=("リアルタイム・ローカル診断  /  HARDWARE TELEMETRY" if self.lang == "ja" else "Local real-time diagnostics  /  HARDWARE TELEMETRY"))
        self.start_button.configure(text=self.w("start"))
        self.stop_button.configure(text=self.w("stop"))
        self.export_button.configure(text=self.w("export"))
        self.clear_button.configure(text=self.w("clear"))
        self.language_button.configure(text=self.w("language"))
        self.tabs.tab(self.overview_tab, text=self.w("overview"))
        self.tabs.tab(self.process_tab, text=self.w("processes"))
        self.alert_panel.refresh_locale()
        self.notice.configure(text=self.w("notice"))
        self.process_head.configure(text=self.w("process_head"))
        for key, label in self.row_labels.items():
            label.configure(text=self.w(key))
        self.refresh()

    def switch_language(self):
        self.lang = "en" if self.lang == "ja" else "ja"
        self.translate()

    def start(self):
        self.alert_panel.engine.clear_runtime()
        self.monitor.start()
        self.refresh()

    def stop(self):
        self.monitor.stop()
        self.alert_panel.engine.clear_runtime()
        self.refresh()

    def refresh(self):
        running = bool(self.monitor.thread and self.monitor.thread.is_alive())
        self.status_var.set(self.w("on") if running else self.w("off"))
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        d = self.last or {}
        missing = self.w("unsupported")
        def pct(key):
            x = d.get(key)
            return f"{x:.1f} %" if isinstance(x, (int, float)) else missing
        self.values["cpu"].configure(text=pct("cpu_percent"))
        self.values["ram"].configure(text=pct("ram_percent"))
        self.values["disk"].configure(text=pct("disk_percent"))
        self.values["gpu"].configure(text=pct("gpu_percent"))
        used, total = d.get("vram_used_mib"), d.get("vram_total_mib")
        self.values["vram"].configure(text=f"{used:.0f} / {total:.0f} MiB"
                                      if isinstance(used, (int, float)) and isinstance(total, (int, float))
                                      else missing)
        temperature = d.get("gpu_temp_c")
        self.values["temp"].configure(text=f"{temperature:.1f} °C"
                                       if isinstance(temperature, (int, float)) else missing)
        self.values["history"].configure(text=str(len(self.monitor.history)))
        lines = [f"{p['pid']:<9} {p['memory_mib']:>10.1f}    {p['name']}"
                 for p in d.get("top_processes", [])]
        self.process_text.configure(state="normal")
        self.process_text.delete("1.0", "end")
        self.process_text.insert("1.0", "\n".join(lines))
        self.process_text.configure(state="disabled")
        self.draw_live_chart()

    def draw_live_chart(self):
        draw_telemetry(self.live_chart, self.monitor.history,
                       empty_label=("計測開始後に推移を表示します" if self.lang == "ja"
                                    else "Start monitoring to see the trend"))

    def poll(self):
        changed = False
        try:
            while True:
                self.last = self.messages.get_nowait()
                if self.monitor.thread and self.monitor.thread.is_alive():
                    self.alert_panel.on_sample(self.last)
                changed = True
        except queue.Empty:
            pass
        if changed:
            self.refresh()
        if self.monitor.errors:
            err = self.monitor.errors.popleft()
            self.stop()
            messagebox.showerror(self.w("error"), err)
        self.root.after(250, self.poll)

    def export(self):
        if not self.monitor.history:
            messagebox.showinfo(self.w("export"), self.w("no_data"))
            return
        target = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not target:
            return
        if Path(target).exists() and not messagebox.askyesno(self.w("export"), self.w("confirm")):
            return
        try:
            export_csv(list(self.monitor.history), Path(target))
            messagebox.showinfo(self.w("export"), self.w("saved"))
        except (OSError, ValueError) as exc:
            messagebox.showerror(self.w("error"), str(exc))

    def clear(self):
        self.monitor.clear()
        self.refresh()

    def close(self):
        self.monitor.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Application(root)
    root.mainloop()
