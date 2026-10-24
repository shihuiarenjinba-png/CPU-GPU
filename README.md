# CPU-GPU Monitor (Windows)

**Development / QA only. Not a commercial release.** Independent repository for a user-controlled read-only PC performance display. It is not Folder Privacy Auditor and does not inspect file contents.

## MVP

- Japanese/English language toggle, Start/Stop, two tabs (overview and top RAM processes).
- Monitoring **OFF by default**. CPU, RAM and disk samples every 2 seconds only after Start.
- NVIDIA GPU 0 usage, VRAM and temperature only when compatible local nvidia-smi is present. All other GPU sensors and CPU temperature explicitly **Unavailable** (never guessed).
- No AI usage detection by load percentage. No server, internet requests, cloud API key, camera, microphone, prompt, or document access.
- Explicit local CSV export; clear history; maximum 900 in-memory snapshots. No auto-save.
- Top process list is sorted by **memory**, not inaccurate freshly primed per-process CPU measurements.

## Running from source

Windows 10/11 and Python 3.12:

    python -m pip install -r requirements.txt
    python app.py
    python -m unittest discover -s tests -v

GPU measurement optionally requires the NVIDIA nvidia-smi executable on PATH. Absence means *unavailable*, not 0%.

## Windows build and release status

On branch pushes matching codex/**, GitHub Actions runs unit tests and builds an **unsigned QA-only EXE**. No signed MSIX, Store listing, WACK, installed runtime screenshot, cross-vendor hardware sensor validation, or 1024x768 GUI screenshot is claimed.

Commercial release is **HOLD** pending real hardware QA, licensing audit, signing, screenshots and Store identity confirmation.

## Privacy

There is no network module or telemetry. Only a user-selected CSV export persists, containing summary metrics, never file contents or process names. On-screen local process names can still be sensitive. No process command lines or usernames are collected.

## Configurable alert rules (QA)

- Open **Alerts & rules / 通知とルール**, select or add a rule and edit its metric, threshold, sustained seconds, repeat cooldown, and optional exact executable name. Click **Update selected rule** and **Apply & save** to activate changes.
- Monitoring and alerts are **OFF until explicitly started/enabled**. Rules/Windows-toast preference are saved locally only on explicit Apply & save. No monitoring in the background after closing the app.
- Preset rules cover CPU/RAM/GPU/disk/VRAM (GPU/VRAM only when sensors truly exist), plus AI candidate and CPU+candidate conditions in AI-PC Monitor. Process-name observations are not proof of active AI inference or hardware failure.
- Alerts include a nonmodal in-app popup, on-screen history bounded to 200 events (not auto-saved), recovery messages, per-rule cooldowns and 10-minute snooze. No repeated alerts during snooze.
- **Windows notification/toast is optional and OFF by default**. This preview uses winotify; uninstalled QA EXEs may be blocked by Windows notification registration or user settings. Toast delivery has **NOT** been physically confirmed and needs the signed package/installer with a valid AUMID. In-app alerts work independently.
- Only local observations; no external network or cloud notification service. Unavailable sensors never count as zero. Process conditions require accessible process listing and match *exact names*, not arbitrary scripts.

No signed Store MSIX or approval is claimed; **Store release remains HOLD**.
