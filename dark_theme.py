"""High-contrast dark instrument-panel theme. Built-in Tk only, no web runtime.

A common visual language with per-product accent. Controls remain native ttk
widgets and retain keyboard traversal and accessibility labels.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#080E18"
SURFACE = "#111C2C"
CARD = "#162438"
TEXT = "#EDF5FF"
MUTED = "#A3B6CC"
BORDER = "#30425A"
SOFT = "#0C1523"
CYAN = "#47DAFF"
PURPLE = "#B79AFF"
AMBER = "#FFC27A"
GREEN = "#77E4AD"
FONT = "Segoe UI"
MONO = "Consolas"


def apply_theme(root: tk.Tk, accent: str = CYAN) -> ttk.Style:
    root.configure(background=BG)
    tkfont.nametofont("TkDefaultFont").configure(family=FONT, size=11)
    tkfont.nametofont("TkTextFont").configure(family=FONT, size=11)
    tkfont.nametofont("TkFixedFont").configure(family=MONO, size=11)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=TEXT, font=(FONT, 11),
                    borderwidth=0)
    style.configure("TFrame", background=BG)
    style.configure("Header.TFrame", background=SOFT)
    style.configure("Toolbar.TFrame", background=BG)
    style.configure("Panel.TFrame", background=SURFACE)
    style.configure("Card.TFrame", background=CARD, relief="flat")
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Header.TLabel", background=SOFT, foreground=TEXT)
    style.configure("Brand.TLabel", background=SOFT, foreground=accent,
                    font=(MONO, 10, "bold"))
    style.configure("Title.TLabel", background=SOFT, foreground=TEXT,
                    font=(FONT, 21, "bold"))
    style.configure("Subtitle.TLabel", background=SOFT, foreground=MUTED,
                    font=(FONT, 10))
    style.configure("Status.TLabel", background=BG, foreground=accent,
                    font=(MONO, 11, "bold"))
    style.configure("Caption.TLabel", background=CARD, foreground=MUTED,
                    font=(FONT, 10, "bold"))
    style.configure("Value.TLabel", background=CARD, foreground=TEXT,
                    font=(MONO, 19, "bold"))
    style.configure("AccentValue.TLabel", background=CARD, foreground=accent,
                    font=(MONO, 19, "bold"))
    style.configure("PanelText.TLabel", background=SURFACE, foreground=MUTED,
                    font=(FONT, 10))
    style.configure("Hint.TLabel", background=BG, foreground=MUTED,
                    font=(FONT, 10))
    style.configure("TButton", background="#23334A", foreground=TEXT,
                    padding=(13, 8), borderwidth=1, bordercolor=BORDER,
                    lightcolor="#23334A", darkcolor="#23334A",
                    font=(FONT, 10, "bold"))
    style.map("TButton",
              background=[("disabled", "#172333"), ("pressed", "#334860"),
                          ("active", "#334860")],
              foreground=[("disabled", "#73859B"), ("active", TEXT)])
    style.configure("Primary.TButton", background=accent, foreground=BG,
                    padding=(16, 8), borderwidth=1, bordercolor=accent)
    style.map("Primary.TButton",
              background=[("disabled", "#24445B"), ("pressed", "#B4F2FF"),
                          ("active", "#B4F2FF")],
              foreground=[("disabled", "#94ADBF"), ("active", BG)])
    style.configure("Quiet.TButton", background=BG, foreground=MUTED,
                    padding=(12, 8), bordercolor=BORDER)
    style.map("Quiet.TButton",
              background=[("disabled", BG), ("active", "#1D3047")],
              foreground=[("disabled", "#667D93"), ("active", TEXT)])
    style.configure("TNotebook", background=BG, borderwidth=0, padding=0)
    style.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED,
                    padding=(18, 10), borderwidth=1, bordercolor=BG,
                    font=(FONT, 10, "bold"))
    style.map("TNotebook.Tab",
              background=[("selected", "#1E3449"), ("active", "#192B3E")],
              foreground=[("selected", accent), ("active", TEXT)],
              bordercolor=[("selected", accent)])
    style.configure("TEntry", foreground=TEXT, fieldbackground=SURFACE,
                    background=SURFACE, insertcolor=TEXT,
                    borderwidth=1, bordercolor=BORDER, padding=(10, 8),
                    lightcolor=BORDER, darkcolor=BORDER)
    style.map("TEntry", fieldbackground=[("disabled", "#101B2A")],
              foreground=[("disabled", MUTED)])
    style.configure("TCombobox", foreground=TEXT, fieldbackground=SURFACE,
                    background=SURFACE, arrowcolor=accent, padding=(10, 7),
                    borderwidth=1, bordercolor=BORDER)
    style.map("TCombobox",
              fieldbackground=[("readonly", SURFACE), ("disabled", BG)],
              foreground=[("readonly", TEXT), ("disabled", MUTED)],
              selectbackground=[("readonly", SURFACE)],
              selectforeground=[("readonly", TEXT)])
    style.configure("TProgressbar", troughcolor=SURFACE, background=accent,
                    borderwidth=0, thickness=8)
    style.configure("TSeparator", background=BORDER)
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", accent)
    root.option_add("*TCombobox*Listbox.selectForeground", BG)
    return style


def header(parent, eyebrow: str, title: str, subtitle: str, *, right: str = ""):
    """Dark title strip; labels are swapped on language change by caller."""
    holder = ttk.Frame(parent, style="Header.TFrame", padding=(21, 16))
    holder.pack(fill="x", pady=(0, 8))
    copy = ttk.Frame(holder, style="Header.TFrame")
    copy.pack(side="left", fill="x", expand=True)
    badge = ttk.Label(copy, text=eyebrow, style="Brand.TLabel")
    badge.pack(anchor="w")
    heading = ttk.Label(copy, text=title, style="Title.TLabel")
    heading.pack(anchor="w", pady=(3, 3))
    summary = ttk.Label(copy, text=subtitle, style="Subtitle.TLabel")
    summary.pack(anchor="w")
    if right:
        ttk.Label(holder, text=right, style="Brand.TLabel").pack(side="right")
    return heading, summary


def metric(parent, key: str, *, accent: bool = False):
    box = ttk.Frame(parent, style="Card.TFrame", padding=(15, 10))
    name = ttk.Label(box, style="Caption.TLabel")
    name.pack(anchor="w", pady=(0, 6))
    value = ttk.Label(box, style=("AccentValue.TLabel" if accent else "Value.TLabel"))
    value.pack(anchor="w")
    return box, name, value


def dark_text(widget: tk.Text):
    widget.configure(background=SOFT, foreground=TEXT, insertbackground=CYAN,
                     selectbackground="#294866", selectforeground=TEXT,
                     relief="flat", borderwidth=0, highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=CYAN,
                     font=(MONO, 11), padx=14, pady=12)
