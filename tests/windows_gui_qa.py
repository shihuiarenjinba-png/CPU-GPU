"""Windows VM GUI QA. Real Tk source screenshots + packaged EXE window test.

Screenshots at requested *window sizes* are not physical display-mode tests.
Windows Actions VM is not the user's hardware. Fail closed on missing image/window.
"""
from __future__ import annotations

import argparse
import ctypes
import importlib
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Running a script inside tests/ excludes the repository root from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil
from PIL import ImageGrab, ImageStat

user32 = ctypes.windll.user32
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p), ctypes.c_void_p]
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.GetParent.argtypes = [ctypes.c_void_p]
user32.GetParent.restype = ctypes.c_void_p


def windows():
    found = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, ignored):
        if user32.IsWindowVisible(hwnd):
            name = ctypes.create_unicode_buffer(400)
            user32.GetWindowTextW(hwnd, name, 399)
            if name.value:
                pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                found.append((int(hwnd), int(pid.value), name.value))
        return True
    callback = callback_type(cb)
    if not user32.EnumWindows(callback, None):
        raise OSError("EnumWindows failed")
    return found


def capture(hwnd: int, output: Path) -> dict:
    image = ImageGrab.grab(window=hwnd).convert("RGB")
    stddev = ImageStat.Stat(image).stddev
    if image.width < 600 or image.height < 400 or max(stddev) < 2:
        raise RuntimeError(f"Invalid/blank GUI capture: {image.size} deviation={stddev}")
    image.save(output)
    return {"png": output.name, "image_width": image.width, "image_height": image.height,
            "color_stddev": [round(x, 2) for x in stddev]}


def source_ui(kind: str, folder: Path) -> dict:
    import tkinter as tk
    app_module = importlib.import_module("app")
    cls = {"cpu": "Application", "ai": "App", "whisper": "TranscriberApp"}[kind]
    root = tk.Tk()
    controller = getattr(app_module, cls)(root)
    result = {"kind": kind, "source_screenshots": [], "language_toggle": False,
              "start_stop": "not_applicable", "physical_display_change": "NOT_TESTED"}
    try:
        root.update()
        if kind in {"cpu", "ai"}:
            assert not (controller.monitor.thread if kind == "cpu" else controller.monitor.worker), "Monitoring started without user action"
            controller.start()
            root.update()
            time.sleep(0.4)
            root.update()
            assert controller.monitor.thread.is_alive() if kind == "cpu" else controller.monitor.worker.is_alive()
            controller.stop()
            root.update()
            assert not (controller.monitor.thread.is_alive() if kind == "cpu" else controller.monitor.worker.is_alive())
            result["start_stop"] = "PASS"
        else:
            assert not controller.running, "Whisper should open idle"
            result["start_stop"] = "idle / no model supplied"
        # This is layout **window geometry**, not screen resolution.
        for lang, size in (("ja", (1024, 768)), ("en", (1280, 720))):
            if kind == "cpu" and controller.lang != lang:
                controller.switch_language()
            elif kind == "ai" and controller.lang != lang:
                controller.change_language()
            elif kind == "whisper":
                controller.locale.set(lang)
            root.geometry(f"{size[0]}x{size[1]}+8+8")
            root.deiconify()
            root.lift()
            root.update()
            time.sleep(0.35)
            root.update()
            actual = (root.winfo_width(), root.winfo_height())
            # Windows hosted VM can clamp full window to its work area (e.g. 768 -> 749).
            # Record the real client size; never claim exact physical display-mode coverage.
            if actual[0] < 700 or actual[1] < 460:
                raise RuntimeError(f"Tk window unusably small in CI: requested={size}, actual={actual}")
            hwnd = int(user32.GetParent(root.winfo_id())) or root.winfo_id()
            file = folder / f"source_{kind}_{lang}_{size[0]}x{size[1]}.png"
            evidence = capture(hwnd, file)
            result["source_screenshots"].append(
                {**evidence, "locale": lang, "requested_tk_client_size": list(size),
                 "actual_tk_client_size": list(actual),
                 "exact_window_geometry": actual == size,
                 "runner_desktop_size": [root.winfo_screenwidth(), root.winfo_screenheight()]})
        result["language_toggle"] = True
    finally:
        if kind in {"cpu", "ai"}:
            controller.stop()
        root.destroy()
    return result


def packaged_exe(exe: Path, kind: str, folder: Path) -> dict:
    prefixes = {"cpu": ("CPU・GPU モニター", "CPU / GPU Monitor"),
                "ai": ("AI PC 負荷モニター", "AI PC Load Monitor"),
                "whisper": ("Local Speech Studio",)}[kind]
    path = exe.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    # Compile/launch user-facing Windows EXE; never send a file to any service.
    process = subprocess.Popen([str(path)], cwd=str(path.parent))
    result = {"exe_path": str(path), "exe_pid": process.pid, "launch_succeeded": False}
    try:
        deadline = time.monotonic() + 28
        match = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"EXE exited before window was visible: code {process.returncode}")
            try:
                family = psutil.Process(process.pid)
                pids = {family.pid, *(p.pid for p in family.children(recursive=True))}
            except psutil.Error:
                pids = {process.pid}
            for hwnd, pid, title in windows():
                if pid in pids and any(title.startswith(p) for p in prefixes):
                    match = (hwnd, pid, title)
                    break
            if match:
                break
            time.sleep(0.7)
        if not match:
            raise RuntimeError("Packaged EXE did not expose a visible matching Tk window on CI desktop")
        hwnd, pid, title = match
        time.sleep(0.8)
        screenshot = capture(hwnd, folder / f"packaged_{kind}_startup.png")
        result.update({"launch_succeeded": True, "window_title": title,
                       "window_pid": pid, "screenshot": screenshot})
        proc = psutil.Process(pid)
        try:
            result["window_process_private_rss_mib"] = round(proc.memory_info().rss / 1048576, 2)
        except psutil.Error:
            result["window_process_private_rss_mib"] = None
        return result
    finally:
        try:
            family = psutil.Process(process.pid)
            descendants = family.children(recursive=True)
            for child in descendants:
                child.terminate()
            family.terminate()
            psutil.wait_procs([*descendants, family], timeout=5)
            for child in descendants:
                if child.is_running():
                    child.kill()
            if family.is_running():
                family.kill()
        except psutil.Error:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=("cpu", "ai", "whisper"))
    parser.add_argument("--exe", required=True)
    parser.add_argument("--out", default="qa_evidence")
    args = parser.parse_args()
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runner": "GitHub-hosted Windows VM, not user's physical hardware",
        "scope": "real Tk UI source window screenshots and unsigned packaged EXE startup",
        "screen_resolution_test": "NOT_PERFORMED; window client geometries only",
        "msix_install_test": "NOT_PERFORMED",
        "status": "FAIL",
    }
    try:
        report["source_ui"] = source_ui(args.kind, folder)
        report["packaged_exe"] = packaged_exe(Path(args.exe), args.kind, folder)
        report["status"] = "PASS"
        print("WINDOWS_GUI_QA=PASS", flush=True)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        print("WINDOWS_GUI_QA=FAIL\n" + report["traceback"], flush=True)
    finally:
        (folder / "qa_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
