#!/usr/bin/env python3
"""
Upload the tests/examples artifact tarballs built by `release.py` to the FABRIC
Artifact Manager, each as a new version of the artifact named in release.toml.

Run where FABlib is configured (FABRIC JupyterHub, or a laptop with a fabric_rc):

    python release/upload_artifacts.py                 # upload tarballs for the current stamped version
    python release/upload_artifacts.py --version 1.1.0rc1
    python release/upload_artifacts.py --dry-run

Uses FablibManager.create_artifact(update_existing=True) + upload_file_to_artifact()
(fabrictestbed-extensions >= 1.8).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
MFLIB_ROOT = HERE.parent
ARTIFACT_OUT = MFLIB_ROOT / "dist" / "artifacts"


def stamped_version() -> str:
    text = (MFLIB_ROOT / "mflib" / "__init__.py").read_text(encoding="utf-8")
    parts = [p.strip().strip("'\"") for p in re.search(r"__version_info__\s*=\s*\[(.*?)\]", text)[1].split(",")]
    base = ".".join(parts[:3])
    return base if parts[3] == "f" else f"{base}{parts[3]}{parts[4]}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", help="mflib version whose tarballs to upload (default: stamped version)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    cfg = tomllib.loads((HERE / "release.toml").read_text(encoding="utf-8"))
    version = args.version or stamped_version()
    authors = cfg.get("artifact_authors", [])

    fablib = None
    if not args.dry_run:
        from fabrictestbed.external_api.artifact_manager import Visibility
        from fabrictestbed_extensions.fablib.fablib import FablibManager
        fablib = FablibManager()

    rc = 0
    for key, a in cfg.get("artifacts", {}).items():
        tarball = ARTIFACT_OUT / f"mflib-{key}-{version}.tar.gz"
        if not tarball.exists():
            print(f"[{key}] {tarball} not found; run `python release/release.py artifacts` first")
            rc = 1
            continue
        with tarfile.open(tarball) as tf:
            member = next(m for m in tf.getmembers() if m.name.endswith("RELEASE_INFO.json"))
            rel = json.load(tf.extractfile(member))
        if rel["mflib_version"] != version:
            print(f"[{key}] RELEASE_INFO says {rel['mflib_version']}, expected {version}; refusing")
            rc = 1
            continue
        long_desc = (
            f"{a['description_short']}\n\n"
            f"Built for fabrictestbed-mflib=={version} and MeasurementFramework {rel['mf_repo_tag']}.\n"
            f"Install the matching library with: pip install -r requirements.txt"
        )
        tags = list(a.get("tags", [])) + [f"mflib-{version}"]
        print(f"[{key}] {a['title']!r} <- {tarball.name}  (MF {rel['mf_repo_tag']})")
        if args.dry_run:
            continue
        fablib.create_artifact(
            artifact_title=a["title"],
            description_short=a["description_short"],
            description_long=long_desc,
            authors=authors,
            tags=tags,
            visibility=getattr(Visibility, a.get("visibility", "Author")),
            update_existing=True,
        )
        result = fablib.upload_file_to_artifact(file_to_upload=str(tarball), artifact_title=a["title"])
        print(f"[{key}] uploaded: {result}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
