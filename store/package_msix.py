"""Build an unsigned *QA_ONLY* MSIX staging directory with visually consistent tiles.

This is not a Store submission tool. Identity is deliberately isolated from
Partner Center and is supplied only to create an unpackable QA artifact.
When Partner Center values are confirmed, code owner should substitute exact
Identity Name, Publisher and Version in a reviewed release branch, sign using
a trusted certificate and retest Windows notifications after installed launch.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

PKG = "http://schemas.microsoft.com/appx/manifest/foundation/windows10"
UAP = "http://schemas.microsoft.com/appx/manifest/uap/windows10"
UAP10 = "http://schemas.microsoft.com/appx/manifest/uap/windows10/10"
RESCAP = "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
ET.register_namespace("", PKG)
ET.register_namespace("uap", UAP)
ET.register_namespace("uap10", UAP10)
ET.register_namespace("rescap", RESCAP)

PRODUCTS = {
    "cpu": {"source": "CPU_GPU_Monitor_QA_UNSIGNED.exe", "exe": "CPU_GPU_Monitor.exe",
            "name": "CPU / GPU Monitor — QA ONLY", "accent": (71, 218, 255), "glyph": "C"},
    "ai": {"source": "AI_PC_Monitor_QA_UNSIGNED.exe", "exe": "AI_PC_Monitor.exe",
           "name": "AI PC Monitor — QA ONLY", "accent": (183, 154, 255), "glyph": "AI"},
}
QA_IDENTITY = {
    "cpu": "QATEST.CPUGPUMonitor.DoNotSubmit",
    "ai": "QATEST.AIPCMonitor.DoNotSubmit",
}
QA_PUBLISHER = "CN=QA-LOCAL-UNSIGNED-NOT-FOR-STORE"
QA_VERSION = "0.0.1.0"
LOGO_SIZES = {
    "StoreLogo.png": (50, 50),
    "Square44x44Logo.png": (44, 44),
    "Square71x71Logo.png": (71, 71),
    "Square150x150Logo.png": (150, 150),
    "Square310x310Logo.png": (310, 310),
    "Wide310x150Logo.png": (310, 150),
}


def hash_file(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def logo(path, size, accent, glyph):
    w, h = size
    scale = 3
    W, H = w * scale, h * scale
    im = Image.new("RGB", (W, H), "#08121F")
    d = ImageDraw.Draw(im)
    inset = int(min(W, H) * 0.075)
    d.rounded_rectangle((inset, inset, W - inset, H - inset),
                        radius=max(4, int(min(W, H) * 0.19)),
                        fill="#12243A", outline=accent, width=max(2, scale * 2))
    box = int(min(W, H) * 0.47)
    cx, cy = W // 2, H // 2
    d.ellipse((cx - box // 2, cy - box // 2, cx + box // 2, cy + box // 2),
              outline=accent, width=max(3, scale * 4))
    for ratio in (0.72, 0.81, 0.90):
        rr = int(box * ratio) // 2
        d.arc((cx - rr, cy - rr, cx + rr, cy + rr), 205, 335, fill=accent,
              width=max(1, scale * 2))
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf",
                                  max(9, int(min(W, H) * (0.20 if len(glyph) == 2 else 0.31))))
    except OSError:
        font = ImageFont.load_default()
    d.text((cx, cy), glyph, fill="#ECF7FF", font=font, anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.resize((w, h), Image.Resampling.LANCZOS).save(path)


def build_layout(product: str, exe: Path, layout: Path):
    if product not in PRODUCTS:
        raise ValueError("Unknown product")
    info = PRODUCTS[product]
    if not exe.is_file() or exe.stat().st_size < 1_000_000:
        raise ValueError("Expected non-empty compiled Windows EXE")
    if layout.exists() and list(layout.iterdir()):
        raise ValueError("Layout must be empty; refusing stale-package contamination")
    layout.mkdir(parents=True, exist_ok=True)
    out_exe = layout / info["exe"]
    shutil.copyfile(exe, out_exe)
    assets = layout / "Assets"
    for name, size in LOGO_SIZES.items():
        logo(assets / name, size, info["accent"], info["glyph"])

    root = ET.Element(f"{{{PKG}}}Package", {"IgnorableNamespaces": "uap10 rescap"})
    # IgnorableNamespaces must only list prefixes actually declared by ElementTree.
    identity = ET.SubElement(root, f"{{{PKG}}}Identity", {
        "Name": QA_IDENTITY[product], "Publisher": QA_PUBLISHER,
        "Version": QA_VERSION, "ProcessorArchitecture": "x64"})
    properties = ET.SubElement(root, f"{{{PKG}}}Properties")
    ET.SubElement(properties, f"{{{PKG}}}DisplayName").text = info["name"]
    ET.SubElement(properties, f"{{{PKG}}}PublisherDisplayName").text = "QA TEST ONLY"
    ET.SubElement(properties, f"{{{PKG}}}Description").text = "Unsigned testing package. Not for Store submission."
    ET.SubElement(properties, f"{{{PKG}}}Logo").text = "Assets/StoreLogo.png"
    resources = ET.SubElement(root, f"{{{PKG}}}Resources")
    ET.SubElement(resources, f"{{{PKG}}}Resource", {"Language": "en-us"})
    ET.SubElement(resources, f"{{{PKG}}}Resource", {"Language": "ja-jp"})
    dependencies = ET.SubElement(root, f"{{{PKG}}}Dependencies")
    ET.SubElement(dependencies, f"{{{PKG}}}TargetDeviceFamily", {
        "Name": "Windows.Desktop", "MinVersion": "10.0.19041.0",
        "MaxVersionTested": "10.0.26100.0"})
    apps = ET.SubElement(root, f"{{{PKG}}}Applications")
    app = ET.SubElement(apps, f"{{{PKG}}}Application", {
        "Id": "App", "Executable": info["exe"],
        f"{{{UAP10}}}RuntimeBehavior": "packagedClassicApp",
        f"{{{UAP10}}}TrustLevel": "mediumIL",
    })
    ET.SubElement(app, f"{{{UAP}}}VisualElements", {
        "DisplayName": info["name"], "Description": "Local PC telemetry with configurable alerts",
        "Square150x150Logo": "Assets/Square150x150Logo.png",
        "Square44x44Logo": "Assets/Square44x44Logo.png",
        "BackgroundColor": "#08121F",
    })
    capabilities = ET.SubElement(root, f"{{{PKG}}}Capabilities")
    ET.SubElement(capabilities, f"{{{RESCAP}}}Capability", {"Name": "runFullTrust"})
    ET.ElementTree(root).write(layout / "AppxManifest.xml", encoding="utf-8", xml_declaration=True)
    # Explicit XML schema auditing: parse back before handing it to MakeAppx.
    parsed = ET.parse(layout / "AppxManifest.xml")
    assert parsed.find(f".//{{{PKG}}}Identity").attrib["Name"] == QA_IDENTITY[product]
    # Plain statement included in the package, not a certificate or Store identity.
    (layout / "QA_ONLY_NOT_FOR_STORE.txt").write_text(
        "QA_UNSIGNED / QA_ONLY.\nIdentity is a deliberate non-Store testing marker.\n"
        "Do not upload to Partner Center. Not signed or install-ready.\n"
        "Windows toast delivery and MSIX installation on a physical PC are unverified.\n",
        encoding="utf-8")
    manifest = {
        "purpose": "QA_UNSIGNED_ONLY_NOT_FOR_STORE",
        "identity": QA_IDENTITY[product],
        "publisher": QA_PUBLISHER,
        "version": QA_VERSION,
        "embedded_exe_name": info["exe"],
        "source_exe_sha256": hash_file(exe),
        "embedded_exe_sha256": hash_file(out_exe),
        "store_identity_verified": False,
        "windows_toast_installed_qa": "HOLD",
        "signed": False,
    }
    if manifest["source_exe_sha256"] != manifest["embedded_exe_sha256"]:
        raise RuntimeError("EXE mismatch while staging")
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--product", choices=PRODUCTS, required=True)
    p.add_argument("--exe", type=Path, required=True)
    p.add_argument("--layout", type=Path, required=True)
    p.add_argument("--provenance", type=Path, required=True)
    args = p.parse_args()
    metadata = build_layout(args.product, args.exe, args.layout)
    args.provenance.parent.mkdir(parents=True, exist_ok=True)
    args.provenance.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
