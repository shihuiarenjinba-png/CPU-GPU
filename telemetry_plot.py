"""Real, session-only CPU/RAM trend visualization for Tk Canvas.

Never invents sample points and never reports missing metrics as zero.
"""
from __future__ import annotations

import tkinter as tk

from dark_theme import BORDER, CYAN, MUTED, PURPLE, SOFT, TEXT, MONO


def draw_telemetry(canvas: tk.Canvas, samples, *, empty_label: str) -> None:
    canvas.delete("all")
    width, height = max(300, canvas.winfo_width()), max(90, canvas.winfo_height())
    left, right, top, bottom = 48, width - 22, 29, height - 26
    canvas.create_text(left, 12, text="CPU / RAM  •  SESSION TELEMETRY",
                       anchor="w", fill=TEXT, font=(MONO, 10, "bold"))
    for pct in (0, 25, 50, 75, 100):
        y = bottom - (bottom - top) * pct / 100
        canvas.create_line(left, y, right, y, fill=BORDER,
                           dash=(3, 7) if pct not in (0, 100) else ())
        if pct in (0, 50, 100):
            canvas.create_text(left - 7, y, text=str(pct), anchor="e",
                               fill=MUTED, font=(MONO, 9))
    values = list(samples)[-120:]
    if not values:
        canvas.create_text((left + right) / 2, (top + bottom) / 2,
                           text=empty_label, fill=MUTED, font=("Segoe UI", 11))
    else:
        for key, color in (("cpu_percent", CYAN), ("ram_percent", PURPLE)):
            points = []
            for index, sample in enumerate(values):
                number = sample.get(key)
                if not isinstance(number, (int, float)):
                    # Missing sensor reading breaks the path instead of creating false zero.
                    if len(points) >= 4:
                        canvas.create_line(*points, fill=color, width=2, smooth=False)
                    points = []
                    continue
                x = left + (right - left) * index / max(1, len(values) - 1)
                y = bottom - (bottom - top) * max(0, min(100, number)) / 100
                points.extend((x, y))
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2, smooth=False)
            elif len(points) == 2:
                canvas.create_oval(points[0] - 2, points[1] - 2,
                                   points[0] + 2, points[1] + 2,
                                   fill=color, outline=color)
    canvas.create_line(right - 158, 12, right - 142, 12, fill=CYAN, width=3)
    canvas.create_text(right - 135, 12, text="CPU", anchor="w",
                       fill=CYAN, font=(MONO, 10))
    canvas.create_line(right - 78, 12, right - 62, 12, fill=PURPLE, width=3)
    canvas.create_text(right - 55, 12, text="RAM", anchor="w",
                       fill=PURPLE, font=(MONO, 10))
