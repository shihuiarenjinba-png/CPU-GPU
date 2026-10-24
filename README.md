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
