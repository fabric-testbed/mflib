#!/usr/bin/env python3
"""
Create (or refresh) the release virtual env: mflib/.venv-release

    python release/setup_venv.py              # create or update
    python release/setup_venv.py --recreate   # delete and rebuild from scratch

Installs release/requirements.txt (flit, Sphinx + docs deps, fablib) and a pinned
tectonic binary (the LaTeX engine for MFLib.pdf) into the venv, then checks that
everything works. release.py switches into this venv automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import venv
import zipfile
from pathlib import Path

# fabrictestbed-extensions reads os.environ["HOME"] at import time, which
# Windows PowerShell/cmd do not set. Child processes inherit this.
os.environ.setdefault("HOME", str(Path.home()))

HERE = Path(__file__).resolve().parent
MFLIB_ROOT = HERE.parent
VENV_DIR = MFLIB_ROOT / ".venv-release"
REQUIREMENTS = HERE / "requirements.txt"

TECTONIC_VERSION = "0.17.0"
TECTONIC_ASSETS = {  # (sys.platform, machine) -> release asset
    ("win32", "amd64"): "x86_64-pc-windows-msvc.zip",
    ("linux", "x86_64"): "x86_64-unknown-linux-musl.tar.gz",
    ("darwin", "x86_64"): "x86_64-apple-darwin.tar.gz",
    ("darwin", "arm64"): "aarch64-apple-darwin.tar.gz",
}

IS_WIN = sys.platform == "win32"
BIN = VENV_DIR / ("Scripts" if IS_WIN else "bin")
PY = BIN / ("python.exe" if IS_WIN else "python")
TECTONIC = BIN / ("tectonic.exe" if IS_WIN else "tectonic")


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def sh(*cmd, cwd: Path | None = None, capture: bool = False) -> str:
    res = subprocess.run([str(c) for c in cmd], cwd=cwd, text=True, capture_output=capture,
                         stdin=subprocess.DEVNULL)
    if res.returncode != 0:
        sys.exit(f"FAILED: {' '.join(map(str, cmd))}\n{(res.stderr or '').strip()}")
    return (res.stdout or "").strip()


def install_tectonic() -> None:
    if TECTONIC.exists() and TECTONIC_VERSION in sh(TECTONIC, "--version", capture=True):
        print(f"    tectonic {TECTONIC_VERSION} already installed")
        return
    key = (sys.platform, platform.machine().lower())
    if key not in TECTONIC_ASSETS:
        sys.exit(f"No tectonic build configured for {key}; install tectonic yourself and put it on PATH.")
    tag = f"tectonic@{TECTONIC_VERSION}"
    name = f"tectonic-{TECTONIC_VERSION}-{TECTONIC_ASSETS[key]}"
    api = f"https://api.github.com/repos/tectonic-typesetting/tectonic/releases/tags/{tag.replace('@', '%40')}"
    with urllib.request.urlopen(api, timeout=30) as r:
        assets = {a["name"]: a for a in json.load(r)["assets"]}
    asset = assets.get(name) or sys.exit(f"asset {name} not found in {tag}")
    print(f"    downloading {name}")
    with urllib.request.urlopen(asset["browser_download_url"], timeout=300) as r:
        data = r.read()
    digest = asset.get("digest", "")
    if digest.startswith("sha256:"):
        if hashlib.sha256(data).hexdigest() != digest.split(":", 1)[1]:
            sys.exit("tectonic download failed its sha256 check; aborting")
        print("    sha256 verified")
    exe = TECTONIC.name
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            member = next(m for m in z.namelist() if Path(m).name == exe)
            TECTONIC.write_bytes(z.read(member))
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            member = next(m for m in t.getmembers() if Path(m.name).name == exe and m.isfile())
            TECTONIC.write_bytes(t.extractfile(member).read())
        TECTONIC.chmod(0o755)
    print(f"    {sh(TECTONIC, '--version', capture=True)} -> {TECTONIC}")


def warm_tectonic() -> None:
    """Compile a tiny document so tectonic downloads its bundle now, not mid-release."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "warm.tex").write_text(
            "\\documentclass{report}\\usepackage{amsmath,graphicx,hyperref,fancyhdr,titlesec}"
            "\\begin{document}warm-up\\end{document}\n", encoding="utf-8")
        sh(TECTONIC, "warm.tex", cwd=Path(tmp), capture=True)
    print("    tectonic works (the first MFLib.pdf build downloads the remaining LaTeX packages, ~1 min)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recreate", action="store_true", help="delete and rebuild the venv")
    args = ap.parse_args()
    if sys.version_info < (3, 11):
        sys.exit("Python >= 3.11 is required (release.py uses tomllib)")

    if args.recreate and VENV_DIR.exists():
        step(f"Removing {VENV_DIR}")
        shutil.rmtree(VENV_DIR)
    if not PY.exists():
        step(f"Creating {VENV_DIR} with {sys.executable} ({platform.python_version()})")
        venv.create(VENV_DIR, with_pip=True)

    step("Installing Python requirements")
    sh(PY, "-m", "pip", "install", "-q", "--upgrade", "pip")
    sh(PY, "-m", "pip", "install", "-q", "--upgrade", "-r", REQUIREMENTS)

    step(f"Installing tectonic {TECTONIC_VERSION}")
    install_tectonic()
    warm_tectonic()

    step("Verifying")
    print("    " + sh(PY, "-m", "flit", "--version", capture=True))
    print("    sphinx " + sh(PY, "-c", "import sphinx; print(sphinx.__version__)", capture=True))
    sh(PY, "-c", "import mflib.mflib, mflib.mfportal", cwd=MFLIB_ROOT)  # what autodoc needs
    print("    mflib (source tree) imports OK, so autodoc will work")
    sh(PY, "-c", "from fabrictestbed_extensions.fablib.fablib import FablibManager as F; F.upload_file_to_artifact")
    print("    fablib Artifact Manager API present")
    pypirc = Path.home() / ".pypirc"
    sections = pypirc.read_text(encoding="utf-8") if pypirc.exists() else ""
    for idx in ("testpypi", "pypi"):
        ok = f"[{idx}]" in sections
        print(f"    ~/.pypirc [{idx}]: {'present' if ok else 'MISSING (flit will prompt for a token)'}")

    step("Ready. release.py uses this venv automatically:")
    print("    python release/release.py status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
