#!/usr/bin/env python3
"""
Release tool for mflib (PyPI) and MeasurementFramework (git tag), versioned independently.

All settings come from release/release.toml. Run from anywhere:

    python release/release.py status                    # versions, tags, MF Latest release, open PRs
    python release/release.py rc    {mflib|mf} [--dry-run]   # tag vX.Y.ZrcN on the release branch
                                                        #   (mflib: also publish to TestPyPI)
    python release/release.py verify-rc                 # install the mflib rc from TestPyPI and check it
    python release/release.py final {mflib|mf} [--dry-run]   # stamp, push branch, open PR to main;
                                                        #   re-run after the PR is merged to tag
                                                        #   (mflib: also publish to PyPI)
    python release/release.py artifacts                 # (re)build the tests/examples tarballs
    python release/release.py docs                      # rebuild Sphinx HTML + MFLib.pdf locally

Nothing is ever pushed to `main`: the tool pushes only the release branch and
tags. `main` changes only by merging the pull request the tool opens.

mflib does not pin MeasurementFramework: at run time it clones the MF release
GitHub labels "Latest" (mflib/mf_repo.py). So `final mf` publishes a GitHub
Release for the new tag and marks it Latest; that is what makes it live.

Every step checks whether it was already done, so after a failure (or while
waiting for a PR) fix the cause and simply re-run the same command.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.error
import urllib.request
import venv
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MFLIB_ROOT = HERE.parent
CONFIG_PATH = HERE / "release.toml"
ARTIFACT_OUT = MFLIB_ROOT / "dist" / "artifacts"

INDEXES = {
    "testpypi": ("https://test.pypi.org", "https://test.pypi.org/simple/"),
    "pypi": ("https://pypi.org", "https://pypi.org/simple/"),
}

# The line the tool stamps in mflib/__init__.py. The rc gate ignores differences in it.
VERSION_INFO_RE = re.compile(r"^__version_info__\s*=\s*\[.*?\]", re.M)

DRY_RUN = False


class ReleaseError(Exception):
    pass


# --------------------------------------------------------------------------- helpers
def log(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def info(msg: str) -> None:
    print(f"    {msg}", flush=True)


def run(cmd: list, cwd: Path, *, mutate: bool, capture: bool = False, check: bool = True,
        timeout: float | None = None, interactive: bool = False) -> str:
    """Run a command. Mutating commands are only printed under --dry-run.

    stdin is closed so nothing (git, flit, LaTeX) can sit waiting on a hidden prompt.
    """
    shown = " ".join(str(c) for c in cmd)
    if mutate:
        if DRY_RUN:
            print(f"    [dry-run] ({cwd.name}) {shown}")
            return ""
        print(f"    $ ({cwd.name}) {shown}", flush=True)
    try:
        res = subprocess.run([str(c) for c in cmd], cwd=cwd, text=True, capture_output=capture,
                             stdin=None if interactive else subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ReleaseError(f"timed out after {timeout:.0f}s: {shown}")
    if check and res.returncode != 0:
        detail = (res.stderr or "").strip() if capture else ""
        raise ReleaseError(f"command failed (exit {res.returncode}): {shown}\n{detail}")
    return (res.stdout or "").strip() if capture else ""


def write_file(path: Path, text: str) -> None:
    if DRY_RUN:
        print(f"    [dry-run] write {path}")
        return
    path.write_text(text, encoding="utf-8", newline="\n")


def parse_pep(version: str) -> tuple[int, int, int, int | None]:
    """'1.2.3' -> (1, 2, 3, None); '1.2.3rc4' -> (1, 2, 3, 4)."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:rc(\d+))?", version)
    if not m:
        raise ReleaseError(f"version must be X.Y.Z (or X.Y.ZrcN), got {version!r}")
    return int(m[1]), int(m[2]), int(m[3]), (int(m[4]) if m[4] else None)


def index_has_version(index: str, name: str, version: str) -> bool:
    base, _ = INDEXES[index]
    try:
        with urllib.request.urlopen(f"{base}/pypi/{name}/{version}/json", timeout=20):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


# --------------------------------------------------------------------------- repos
class Repo:
    def __init__(self, key: str, cfg: dict, prefix: str):
        self.key = key
        self.cfg = cfg
        self.prefix = prefix
        self.path = (MFLIB_ROOT / cfg["path"]).resolve()
        self.remote = cfg.get("remote", "origin")
        self.release_branch = cfg["release_branch"]
        self.main_branch = cfg.get("main_branch", "main")
        self.remote_main = f"{self.remote}/{self.main_branch}"
        self.version_file = self.path / cfg["version_file"]
        self.version = cfg["version"]
        if parse_pep(self.version)[3] is not None:
            raise ReleaseError(f"[repos.{key}].version must be plain X.Y.Z; rc numbers are automatic")

    # ---- git -----------------------------------------------------------
    def q(self, *args, check: bool = True) -> str:
        return run(["git", *args], self.path, mutate=False, capture=True, check=check)

    def do(self, *args) -> None:
        run(["git", *args], self.path, mutate=True)

    def ok(self, *args) -> bool:
        return subprocess.run(["git", *args], cwd=self.path, capture_output=True).returncode == 0

    def fetch(self, quiet: bool = False) -> None:
        run(["git", "fetch", "--tags", "--prune", *(["--quiet"] if quiet else []), self.remote],
            self.path, mutate=False, check=not quiet)

    def branch(self) -> str:
        return self.q("rev-parse", "--abbrev-ref", "HEAD")

    def dirty(self) -> str:
        return self.q("status", "--porcelain", "--untracked-files=no")

    def has_tag(self, tag: str) -> bool:
        return bool(self.q("tag", "-l", tag))

    def remote_tags(self) -> list[str]:
        out = self.q("ls-remote", "--tags", "--refs", self.remote)
        return [line.split("refs/tags/", 1)[1] for line in out.splitlines() if "refs/tags/" in line]

    def remote_has_tag(self, tag: str) -> bool:
        return bool(self.q("ls-remote", "--tags", self.remote, f"refs/tags/{tag}"))

    def ref_exists(self, ref: str) -> bool:
        return self.ok("rev-parse", "--verify", "--quiet", ref)

    def is_ancestor(self, a: str, b: str) -> bool:
        return self.ok("merge-base", "--is-ancestor", a, b)

    def sha(self, ref: str = "HEAD") -> str:
        return self.q("rev-parse", f"{ref}^{{commit}}")

    def checkout(self, ref: str) -> None:
        if DRY_RUN or self.branch() != ref:
            self.do("checkout", "--quiet", ref)

    def show(self, ref: str, path: Path) -> str | None:
        out = run(["git", "show", f"{ref}:{path.relative_to(self.path).as_posix()}"], self.path,
                  mutate=False, capture=True, check=False)
        return out or None

    def commit_if_changed(self, files: list[Path], message: str) -> None:
        rel = [f.relative_to(self.path).as_posix() for f in files]
        self.do("add", *rel)
        if DRY_RUN:
            self.do("commit", "-m", message)
        elif self.ok("diff", "--cached", "--quiet"):
            info(f"({self.key}) nothing to commit, already stamped")
        else:
            self.do("commit", "-m", message)

    def tag(self, tag: str, message: str, ref: str = "HEAD") -> None:
        if self.has_tag(tag):
            info(f"({self.key}) tag {tag} already exists")
        else:
            self.do("tag", "-a", tag, "-m", message, ref)

    def push(self, *refs: str) -> None:
        """Push branches/tags. Never `main`: that only changes through a pull request."""
        for r in refs:
            dest = r.split(":")[-1].removeprefix("refs/heads/")
            if dest == self.main_branch:
                raise ReleaseError(f"refusing to push to {self.main_branch!r}; it only changes via pull request")
        self.do("push", self.remote, *refs)

    # ---- release tags ----------------------------------------------------
    def tag_name(self, pep: str) -> str:
        return f"{self.prefix}{pep}"

    def rc_numbers(self) -> list[int]:
        base = self.tag_name(self.version)
        pat = re.compile(re.escape(base) + r"rc(\d+)$")
        return sorted(int(m[1]) for t in self.q("tag", "-l", f"{base}rc*").split() if (m := pat.match(t)))

    def last_rc(self) -> str | None:
        rcs = self.rc_numbers()
        return f"{self.version}rc{rcs[-1]}" if rcs else None

    def is_final_tag(self, tag: str) -> bool:
        return re.fullmatch(re.escape(self.prefix) + r"\d+\.\d+\.\d+", tag) is not None

    def latest_final_tag(self) -> str | None:
        finals = [t for t in self.remote_tags() if self.is_final_tag(t)]
        return max(finals, key=lambda t: parse_pep(t[len(self.prefix):])[:3], default=None)

    def github_slug(self) -> str | None:
        url = self.q("remote", "get-url", self.remote, check=False)
        m = re.search(r"github\.com[:/](.+?)(?:\.git)?/?$", url)
        return m[1] if m else None


# --------------------------------------------------------------------------- release context
class Ctx:
    def __init__(self):
        with CONFIG_PATH.open("rb") as f:
            self.cfg = tomllib.load(f)
        prefix = self.cfg.get("tag_prefix", "v")
        lib_cfg = self.cfg["repos"]["mflib"]
        self.mflib = Repo("mflib", lib_cfg, prefix)
        self.mf = Repo("mf", self.cfg["repos"]["mf"], prefix)
        self.mf_github_release = self.cfg["repos"]["mf"].get("github_release", True)
        self.pypi_name = lib_cfg["pypi_name"]
        self.gate_ignore = self.cfg.get("rc_gate", {}).get("ignore", [])
        self.docs = self.cfg.get("docs", {})
        self.pdf_file = (self.mflib.path / self.docs["pdf"]) if self.docs.get("enabled") else None

    def repo(self, key: str) -> Repo:
        return {"mflib": self.mflib, "mf": self.mf}[key]

    def stamp_files(self, repo: Repo) -> list[Path]:
        if repo is self.mf:
            return [self.mf.version_file]
        return [self.mflib.version_file] + ([self.pdf_file] if self.pdf_file else [])

    # ---- reading stamps (working tree, or a git ref) --------------------
    def read_version(self, repo: Repo, ref: str | None = None) -> str | None:
        f = repo.version_file
        text = repo.show(ref, f) if ref else (f.read_text(encoding="utf-8") if f.exists() else None)
        if text is None:
            return None
        if repo is self.mf:
            return text.strip()
        m = VERSION_INFO_RE.search(text)
        if not m:
            raise ReleaseError(f"__version_info__ not found in {f}")
        parts = [p.strip().strip("'\"") for p in m[0].split("[", 1)[1].rstrip("]").split(",")]
        base = ".".join(parts[:3])
        return base if parts[3] == "f" else f"{base}{parts[3]}{parts[4]}"

    # ---- stamping ---------------------------------------------------------
    def stamp(self, repo: Repo, pep: str) -> None:
        if repo is self.mf:
            write_file(self.mf.version_file, pep + "\n")
            return
        x, y, z, rc = parse_pep(pep)
        info_list = f'[{x}, {y}, {z}, "rc", {rc}]' if rc else f'[{x}, {y}, {z}, "f", 0]'
        text = self.mflib.version_file.read_text(encoding="utf-8")
        write_file(self.mflib.version_file,
                   VERSION_INFO_RE.sub(f"__version_info__ = {info_list}", text, count=1))


# --------------------------------------------------------------------------- GitHub releases (MF "Latest")
def github_latest_release(repo: Repo) -> str | None:
    """Tag of the release GitHub labels Latest -- what mflib clones at run time."""
    slug = repo.github_slug()
    if not slug:
        return None
    req = urllib.request.Request(f"https://github.com/{slug}/releases/latest", method="HEAD",
                                 headers={"User-Agent": "mflib-release"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            url = resp.url
    except urllib.error.URLError:
        return None
    return url.split("/releases/tag/", 1)[1].strip("/") if "/releases/tag/" in url else None


def github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def publish_github_release(repo: Repo, tag: str, title: str, notes: str) -> bool:
    """Create the GitHub Release for `tag`, marked Latest. Returns False if it had to be left to the user."""
    slug = repo.github_slug()
    if not slug:
        info(f"{repo.key}: remote is not on GitHub; skipping the GitHub Release")
        return True
    if github_latest_release(repo) == tag:
        info(f"GitHub Release {tag} exists and is labeled Latest")
        return True
    gh = shutil.which("gh")
    try:
        if gh:
            exists = run([gh, "release", "view", tag], repo.path, mutate=False, capture=True, check=False)
            if exists:
                run([gh, "release", "edit", tag, "--latest", "--draft=false", "--prerelease=false"],
                    repo.path, mutate=True)
            else:
                run([gh, "release", "create", tag, "--verify-tag", "--latest", "--title", title,
                     "--notes", notes], repo.path, mutate=True)
            return True
        if token := github_token():
            if DRY_RUN:
                print(f"    [dry-run] POST https://api.github.com/repos/{slug}/releases ({tag}, make_latest)")
                return True
            api = f"https://api.github.com/repos/{slug}/releases"
            hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                   "User-Agent": "mflib-release"}
            try:  # release already exists (e.g. created as a draft): mark it Latest
                with urllib.request.urlopen(urllib.request.Request(f"{api}/tags/{tag}", headers=hdr), timeout=20) as r:
                    rel_id = json.load(r)["id"]
                req = urllib.request.Request(f"{api}/{rel_id}", method="PATCH", headers=hdr, data=json.dumps(
                    {"draft": False, "prerelease": False, "make_latest": "true"}).encode())
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                req = urllib.request.Request(api, method="POST", headers=hdr, data=json.dumps(
                    {"tag_name": tag, "name": title, "body": notes, "make_latest": "true"}).encode())
            with urllib.request.urlopen(req, timeout=30):
                pass
            info(f"GitHub Release {tag} published and marked Latest")
            return True
    except (ReleaseError, urllib.error.URLError) as e:
        info(f"could not publish the GitHub Release automatically: {str(e).splitlines()[0]}")
    info("Publish it by hand and tick 'Set as the latest release':")
    info(f"  https://github.com/{slug}/releases/new?tag={tag}")
    return False


# --------------------------------------------------------------------------- shared steps
def preflight(ctx: Ctx, repo: Repo, *, need_flit: bool) -> None:
    log(f"Preflight checks ({repo.key})")
    if not (repo.path / ".git").exists():
        raise ReleaseError(f"{repo.key}: no git repo at {repo.path}")
    repo.fetch()
    br = repo.branch()
    if br != repo.release_branch:
        raise ReleaseError(f"{repo.key}: on branch {br!r}, expected release_branch {repo.release_branch!r}")
    if d := repo.dirty():
        raise ReleaseError(f"{repo.key}: uncommitted changes to tracked files:\n{d}")
    upstream = f"{repo.remote}/{repo.release_branch}"
    if repo.ref_exists(upstream) and not repo.is_ancestor(upstream, "HEAD"):
        raise ReleaseError(f"{repo.key}: local {br} is behind/diverged from {upstream}; pull first")
    info(f"{repo.key}: {br} @ {repo.sha()[:9]} clean")
    if need_flit:
        if run([sys.executable, "-m", "flit", "--version"], MFLIB_ROOT, mutate=False, capture=True, check=False) == "":
            raise ReleaseError(f"flit not available for {sys.executable}; run `python release/setup_venv.py`")
        check_docs_tools(ctx)


def check_docs_tools(ctx: Ctx) -> None:
    if not ctx.pdf_file:
        return
    res = subprocess.run([sys.executable, "-c", "import sphinx, mflib.mflib, mflib.mfportal"],
                         cwd=MFLIB_ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        raise ReleaseError(
            "docs build environment incomplete (sphinx or mflib's imports, e.g. fablib, missing):\n"
            f"{res.stderr.strip().splitlines()[-1] if res.stderr.strip() else ''}\n"
            f"run: python release/setup_venv.py"
        )
    engine = ctx.docs["pdf_command"][0]
    if not find_tool(engine):
        raise ReleaseError(f"PDF engine {engine!r} not found in the venv or on PATH; "
                           f"run `python release/setup_venv.py` or change [docs].pdf_command")
    info(f"docs: sphinx + {find_tool(engine)}")


def find_tool(name: str) -> str | None:
    """Prefer a tool installed next to the running interpreter (the release venv), then PATH."""
    venv_bin = Path(sys.executable).parent
    return shutil.which(name, path=str(venv_bin)) or shutil.which(name)


def build_docs(ctx: Ctx) -> None:
    """Build HTML (as a check) and the PDF from the freshly stamped source; copy the PDF into the repo."""
    if not ctx.pdf_file:
        return
    log("Building Sphinx docs (version comes from the stamped mflib/__init__.py)")
    src = MFLIB_ROOT / ctx.docs["source"]
    build = MFLIB_ROOT / ctx.docs["build_dir"]
    if ctx.docs.get("check_html", True):
        if not DRY_RUN:
            shutil.rmtree(build / "html", ignore_errors=True)
        run([sys.executable, "-m", "sphinx", "-q", "-b", "html", src, build / "html"], MFLIB_ROOT, mutate=True)
    latex = build / "latex"
    if not DRY_RUN:
        shutil.rmtree(latex, ignore_errors=True)
    run([sys.executable, "-m", "sphinx", "-q", "-b", "latex", src, latex], MFLIB_ROOT, mutate=True)
    cmd = list(ctx.docs["pdf_command"])
    cmd[0] = find_tool(cmd[0]) or cmd[0]
    run(cmd, latex, mutate=True, timeout=ctx.docs.get("pdf_timeout", 900))
    built = latex / (Path(ctx.docs["tex"]).stem + ".pdf")
    if DRY_RUN:
        print(f"    [dry-run] copy {built} -> {ctx.pdf_file}")
        return
    if not built.exists():
        raise ReleaseError(f"PDF build produced no {built}")
    shutil.copyfile(built, ctx.pdf_file)
    info(f"{ctx.pdf_file.name} updated ({built.stat().st_size // 1024} KB)")


def stamp_and_build(ctx: Ctx, repo: Repo, pep: str) -> None:
    """Stamp the version (and rebuild the PDF for mflib); on failure restore the stamp files."""
    try:
        ctx.stamp(repo, pep)
        if repo is ctx.mflib:
            build_docs(ctx)
    except BaseException:
        if not DRY_RUN:
            files = [f.relative_to(repo.path).as_posix() for f in ctx.stamp_files(repo)]
            tracked = [f for f in files if repo.ok("ls-files", "--error-unmatch", f)]
            if tracked:
                repo.do("checkout", "--", *tracked)
            for f in set(files) - set(tracked):
                (repo.path / f).unlink(missing_ok=True)  # e.g. MF VERSION created by this run
            print("    (version stamps reverted)")
        raise


def gate_since_rc(ctx: Ctx, repo: Repo, rc_tag: str) -> None:
    """Refuse to release code that differs from what was tested as the last rc.

    The stamped __version_info__ line, the PDF, the MF VERSION file and
    the [rc_gate].ignore paths may differ; every other byte must match.
    """
    stamp_rel = {f.relative_to(repo.path).as_posix(): f for f in ctx.stamp_files(repo)}
    text_stamps = {ctx.mflib.version_file} if repo is ctx.mflib else set()
    changed = []
    for f in repo.q("diff", "--name-only", rc_tag, "HEAD").splitlines():
        if not f or any(f.startswith(p) for p in ctx.gate_ignore):
            continue
        if f in stamp_rel:
            path = stamp_rel[f]
            if path not in text_stamps:
                continue  # PDF / VERSION: wholly generated
            norm = lambda t: VERSION_INFO_RE.sub("__version_info__ = *", t or "")
            if norm(repo.show(rc_tag, path)) == norm(repo.show("HEAD", path)):
                continue
        changed.append(f)
    if changed:
        raise ReleaseError(
            f"{repo.key}: files changed since {rc_tag} (untested):\n  " + "\n  ".join(changed)
            + f"\nRun `rc {repo.key}` again to test these changes first."
        )
    info(f"{repo.key}: identical to {rc_tag} apart from version stamps")


def publish(ctx: Ctx, pep: str, index: str) -> None:
    if index_has_version(index, ctx.pypi_name, pep):
        info(f"{ctx.pypi_name}=={pep} already on {index}; skipping upload")
        return
    dist = MFLIB_ROOT / "dist"
    if not DRY_RUN:
        for f in dist.glob("*"):
            if f.is_file():
                f.unlink()
    run([sys.executable, "-m", "flit", "build"], MFLIB_ROOT, mutate=True)
    if not DRY_RUN:
        built = [f.name for f in dist.glob("*") if f.is_file()]
        if not any(pep in n for n in built):
            raise ReleaseError(f"built files {built} do not carry version {pep}; refusing to upload")
    # interactive: flit may prompt for an API token if ~/.pypirc / keyring has none
    run([sys.executable, "-m", "flit", "publish", "--repository", index], MFLIB_ROOT, mutate=True, interactive=True)


def build_artifacts(ctx: Ctx, pep: str, mflib_ref: str = "HEAD") -> list[Path]:
    mf_tag = github_latest_release(ctx.mf)
    log(f"Building artifacts for mflib {pep} (MF Latest release now: {mf_tag})")
    if not DRY_RUN:
        ARTIFACT_OUT.mkdir(parents=True, exist_ok=True)
    mf_commit = (ctx.mf.q("rev-parse", f"{mf_tag}^{{commit}}", check=False) or None) if mf_tag else None
    mflib_commit = ctx.mflib.q("rev-parse", f"{mflib_ref}^{{commit}}", check=False) or None
    out = []
    for key, a in ctx.cfg.get("artifacts", {}).items():
        src = MFLIB_ROOT / a["source"]
        if not src.is_dir() or not any(p for p in src.rglob("*") if p.is_file() and p.name != "README.md"):
            info(f"[{key}] {src} is empty or missing; skipping")
            continue
        name = f"mflib-{key}-{pep}"
        tarball = ARTIFACT_OUT / f"{name}.tar.gz"
        if DRY_RUN:
            print(f"    [dry-run] package {src} -> {tarball}")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / name
            shutil.copytree(src, stage, ignore=shutil.ignore_patterns(".ipynb_checkpoints", "__pycache__"))
            reqs = []
            if "rc" in pep:
                reqs.append("--extra-index-url https://test.pypi.org/simple/")
            reqs.append(f"{ctx.pypi_name}=={pep}")
            (stage / "requirements.txt").write_text("\n".join(reqs) + "\n", encoding="utf-8")
            (stage / "RELEASE_INFO.json").write_text(json.dumps({
                "artifact": key,
                "title": a["title"],
                "mflib_version": pep,
                "mf_repo_ref": "latest",
                "mf_latest_release_at_build": mf_tag,
                "mflib_commit": mflib_commit,
                "mf_commit": mf_commit,
                "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }, indent=2) + "\n", encoding="utf-8")
            with tarfile.open(tarball, "w:gz") as tf:
                tf.add(stage, arcname=name)
        info(f"[{key}] {tarball}")
        out.append(tarball)
    return out


# --------------------------------------------------------------------------- pull requests
def open_pr_url(repo: Repo) -> str | None:
    gh = shutil.which("gh")
    if not gh:
        return None
    return run([gh, "pr", "list", "--head", repo.release_branch, "--base", repo.main_branch,
                "--state", "open", "--json", "url", "--jq", ".[0].url"],
               repo.path, mutate=False, capture=True, check=False) or None


def ensure_pr(repo: Repo, title: str, body: str) -> None:
    """Open a PR release_branch -> main (with the GitHub CLI if available), or print the link."""
    slug = repo.github_slug()
    compare = (f"https://github.com/{slug}/compare/{repo.main_branch}...{repo.release_branch}?expand=1"
               if slug else None)
    if existing := open_pr_url(repo):
        info(f"pull request already open: {existing}")
        return
    gh = shutil.which("gh")
    if gh:
        try:
            run([gh, "pr", "create", "--base", repo.main_branch, "--head", repo.release_branch,
                 "--title", title, "--body", body], repo.path, mutate=True)
            return
        except ReleaseError as e:
            info(f"gh could not create the PR ({str(e).splitlines()[0]})")
    info(f"Open this pull request on GitHub (title: {title!r}):")
    info(f"  {compare or f'{repo.release_branch} -> {repo.main_branch}'}")


def find_merged_commit(repo: Repo) -> str | None:
    """The commit on origin/main whose content equals the release branch HEAD.

    Works for every GitHub merge method (merge commit, squash, rebase).
    """
    tree = repo.q("rev-parse", "HEAD^{tree}")
    log_out = repo.q("log", "--first-parent", "-n", "100", "--format=%H %T", repo.remote_main, check=False)
    for line in log_out.splitlines():
        sha, t = line.split()
        if t == tree:
            return sha
    return None


def sync_release_branch(repo: Repo) -> None:
    """Bring the release branch level with main after the PR merge (pushes the branch only)."""
    log(f"{repo.key}: bringing {repo.release_branch} level with {repo.remote_main}")
    repo.checkout(repo.release_branch)
    if not DRY_RUN and repo.is_ancestor(repo.remote_main, "HEAD"):
        info("already contains main")
    elif DRY_RUN or repo.is_ancestor("HEAD", repo.remote_main):
        repo.do("merge", "--ff-only", repo.remote_main)
    else:  # squash/rebase merge: record main as merged so the next cycle's rc check passes
        repo.do("merge", "--no-ff", "-m", f"Merge {repo.main_branch} into {repo.release_branch}", repo.remote_main)
    repo.push(repo.release_branch)


# --------------------------------------------------------------------------- commands
def cmd_status(ctx: Ctx, _args) -> int:
    problems, notes = [], []
    for repo in (ctx.mflib, ctx.mf):
        repo.fetch(quiet=True)
        log(f"{repo.key}  ({repo.path})")
        ahead = repo.q("rev-list", "--count", f"{repo.remote_main}..HEAD", check=False) or "?"
        behind = repo.q("rev-list", "--count", f"HEAD..{repo.remote_main}", check=False) or "?"
        info(f"branch          : {repo.branch()} (release_branch {repo.release_branch}); "
             f"ahead of {repo.remote_main}: {ahead}, behind: {behind}; dirty: {'yes' if repo.dirty() else 'no'}")
        info(f"release.toml    : {repo.version}")
        info(f"stamped         : {ctx.read_version(repo) or '(missing)'}")
        info(f"latest release  : {repo.latest_final_tag() or '(none)'}")
        info(f"rc tags         : {', '.join(f'rc{n}' for n in repo.rc_numbers()) or '(none yet)'}")
        if pr := open_pr_url(repo):
            info(f"open release PR : {pr}")
        if repo.remote_has_tag(repo.tag_name(repo.version)):
            notes.append(f"{repo.key} {repo.version} is already released; bump [repos.{repo.key}].version "
                         f"before the next rc")
        if behind not in ("0", "?"):
            notes.append(f"{repo.key}: {repo.remote_main} has {behind} commit(s) not on {repo.release_branch}; "
                         f"merge main into it before the next rc")

    log("MeasurementFramework release mflib clones at run time")
    latest_label = github_latest_release(ctx.mf)
    latest_tag = ctx.mf.latest_final_tag()
    info(f"GitHub 'Latest' release : {latest_label or '(none / unreachable)'}")
    info(f"newest final MF tag     : {latest_tag or '(none)'}")
    if ctx.mf_github_release and ctx.mf.github_slug() and latest_tag and latest_label != latest_tag:
        problems.append(f"MF tag {latest_tag} is not the GitHub 'Latest' release ({latest_label}); mflib "
                        f"users still get {latest_label}. Run `final mf` to publish it.")

    log("Summary")
    for n in notes:
        info(f"note: {n}")
    for p in problems:
        info(f"PROBLEM: {p}")
    if not problems:
        info("OK")
    return 1 if problems else 0


def cmd_rc(ctx: Ctx, args) -> int:
    repo = ctx.repo(args.repo)
    lib = repo is ctx.mflib
    preflight(ctx, repo, need_flit=lib)
    if repo.remote_has_tag(repo.tag_name(repo.version)):
        raise ReleaseError(f"{repo.key} {repo.version} is already released. "
                           f"Bump [repos.{repo.key}].version in {CONFIG_PATH}.")
    if not repo.is_ancestor(repo.remote_main, "HEAD"):
        raise ReleaseError(
            f"{repo.key}: {repo.remote_main} has commits missing from {repo.release_branch}. "
            f"Merge {repo.main_branch} into {repo.release_branch} first so the rc tests what will ship."
        )
    rcs = repo.rc_numbers()
    # Resume an rc that was tagged locally but never pushed; otherwise start the next one.
    if rcs and not repo.remote_has_tag(repo.tag_name(f"{repo.version}rc{rcs[-1]}")):
        n = rcs[-1]
        log(f"Resuming unfinished rc{n}")
    else:
        n = (rcs[-1] + 1) if rcs else 1
    pep = f"{repo.version}rc{n}"
    tag = repo.tag_name(pep)
    log(f"{repo.key} release candidate {pep}  (tag {tag})")

    if lib:
        info(f"mflib will clone MF {github_latest_release(ctx.mf) or '(unknown)'} (GitHub 'Latest' release) "
             f"when tested; release MF first if this rc needs newer MF code")
    if repo.has_tag(tag):
        if not DRY_RUN and repo.sha() != repo.sha(tag):
            raise ReleaseError(f"local tag {tag} is not at HEAD; delete it (git tag -d {tag}) and re-run")
    else:
        stamp_and_build(ctx, repo, pep)
        repo.commit_if_changed(ctx.stamp_files(repo), f"Release candidate {pep}" + (" (docs)" if lib and ctx.pdf_file else ""))
        repo.tag(tag, f"{'mflib' if lib else 'MeasurementFramework'} {pep}")

    if lib:
        log("Publishing to TestPyPI")
        publish(ctx, pep, "testpypi")

    log(f"Pushing {repo.release_branch} and {tag}")
    repo.push(repo.release_branch, tag)

    if lib:
        build_artifacts(ctx, pep, tag)
        log("Done. Next:")
        info("1. python release/release.py verify-rc")
        info(f"2. Run the tests artifact dist/artifacts/mflib-tests-{pep}.tar.gz on FABRIC")
        info("3. Problems? Fix on the release branch, commit, and run `rc mflib` again (-> next rc).")
        info("4. All good? python release/release.py final mflib")
    else:
        log("Done. Next:")
        info(f"1. Test it: Core/MFLib(mf_repo_branch=\"{tag}\") clones this rc explicitly")
        info("2. All good? python release/release.py final mf  (makes it the GitHub 'Latest' release)")
    return 0


def cmd_verify_rc(ctx: Ctx, _args) -> int:
    ctx.mflib.fetch()
    pep = ctx.mflib.last_rc()
    if not pep:
        raise ReleaseError(f"no rc tags for mflib {ctx.mflib.version}; run `rc mflib` first")
    log(f"Verifying {ctx.pypi_name}=={pep} from TestPyPI")
    if not index_has_version("testpypi", ctx.pypi_name, pep):
        raise ReleaseError(f"{pep} not found on TestPyPI")

    with tempfile.TemporaryDirectory() as tmp:
        venv.create(tmp, with_pip=True)
        py = Path(tmp) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        run([py, "-m", "pip", "install", "-q",
             "--index-url", INDEXES["testpypi"][1], "--extra-index-url", INDEXES["pypi"][1],
             f"{ctx.pypi_name}=={pep}"], Path(tmp), mutate=False)
        probe = ("import mflib; from mflib.mf_repo import latest_mf_release;"
                 "print(mflib.__version__); print(latest_mf_release())")
        got_v, got_mf = run([py, "-c", probe], Path(tmp), mutate=False, capture=True).splitlines()[-2:]
    info(f"installed mflib.__version__  = {got_v}")
    info(f"MF release it will clone     = {got_mf}")
    if got_v != pep:
        raise ReleaseError(f"expected {pep}")
    if got_mf == "None":
        raise ReleaseError("the installed mflib could not look up the latest MeasurementFramework release")
    log(f"OK. Now run the tests artifact on FABRIC against {pep}, then `final mflib`.")
    return 0


def cmd_final(ctx: Ctx, args) -> int:
    repo = ctx.repo(args.repo)
    lib = repo is ctx.mflib
    preflight(ctx, repo, need_flit=lib)
    pep = repo.version
    tag = repo.tag_name(pep)
    rc_pep = repo.last_rc()
    rc_tag = repo.tag_name(rc_pep) if rc_pep else None
    if lib:
        if not rc_pep:
            raise ReleaseError(f"no rc for mflib {pep}. Run `rc mflib` and test it from TestPyPI first.")
        if not index_has_version("testpypi", ctx.pypi_name, rc_pep):
            raise ReleaseError(f"{rc_tag} was never published to TestPyPI")

    if repo.remote_has_tag(tag):
        info(f"{tag} already tagged on GitHub; finishing the remaining steps")
    else:
        log(f"Gate: {repo.release_branch} must match the tested rc")
        if rc_tag:
            gate_since_rc(ctx, repo, rc_tag)
        else:
            info(f"no rc for {repo.key} {pep}; releasing {repo.release_branch} as is")

        if ctx.read_version(repo) != pep:
            if not repo.is_ancestor(repo.remote_main, "HEAD"):
                raise ReleaseError(f"{repo.remote_main} has commits missing from {repo.release_branch}. "
                                   f"Merge {repo.main_branch} into it" + (", then run `rc` again." if rc_tag else "."))
            log(f"Stamping {repo.key} {pep}")
            stamp_and_build(ctx, repo, pep)
            repo.commit_if_changed(ctx.stamp_files(repo), f"Release {pep}" + (" (docs)" if lib and ctx.pdf_file else ""))

        log(f"Pushing {repo.release_branch} (never {repo.main_branch})")
        repo.push(repo.release_branch)

        merged = None if DRY_RUN else find_merged_commit(repo)
        if not merged:
            if not DRY_RUN and repo.is_ancestor("HEAD", repo.remote_main):
                raise ReleaseError(f"{repo.release_branch} was merged, but {repo.remote_main} also contains "
                                   f"other changes, so its content is not what was tested. Tag it by hand "
                                   f"or merge {repo.main_branch} into {repo.release_branch} and start a new rc.")
            if not repo.is_ancestor(repo.remote_main, "HEAD"):
                raise ReleaseError(f"{repo.remote_main} moved on since the release was stamped. Merge "
                                   f"{repo.main_branch} into {repo.release_branch}" +
                                   (", run `rc` again, then `final`." if rc_tag else ", then re-run `final`."))
            name = "mflib" if lib else "MeasurementFramework"
            body = (f"Release {name} {pep}.\n\n"
                    + (f"Tested as {rc_tag}" + (" (TestPyPI)" if lib else "") + ".\n\n" if rc_tag else "")
                    + f"Any merge method works. After merging, run `python release/release.py final {repo.key}` "
                      f"to tag the merge as {tag}" + (" and publish to PyPI." if lib else
                      " and publish it as the GitHub 'Latest' release, which mflib clones at run time."))
            log(f"Pull request {repo.release_branch} -> {repo.main_branch}")
            ensure_pr(repo, f"Release {name} {pep}", body)
            log(f"Waiting for the pull request. After it is merged, run: "
                f"python release/release.py final {repo.key}")
            return 0

        log(f"Tagging merged commit {merged[:9]} on {repo.remote_main} as {tag}")
        repo.tag(tag, f"{'mflib' if lib else 'MeasurementFramework'} {pep}", merged)
        repo.push(tag)

    released_ok = True
    if lib:
        log(f"Publishing to PyPI from tag {tag}")
        repo.checkout(tag)
        try:
            publish(ctx, pep, "pypi")
        finally:
            if not DRY_RUN:
                repo.checkout(repo.release_branch)
        build_artifacts(ctx, pep, tag)
    elif ctx.mf_github_release:
        log(f"GitHub Release {tag} (labeled Latest: mflib clones it from now on)")
        released_ok = publish_github_release(repo, tag, f"MeasurementFramework {pep}",
                                             f"MeasurementFramework {pep}.")

    sync_release_branch(repo)

    if not released_ok:
        log(f"{tag} is tagged, but mflib keeps cloning the previous release until the GitHub Release "
            f"above is published as Latest. Re-run `final mf` afterwards to check.")
        return 1

    log(f"Released {repo.key} {pep}. Next:")
    if lib:
        info("1. Upload the artifacts: python release/upload_artifacts.py (on FABRIC JupyterHub)")
    else:
        info("1. mflib installs clone this release from now on (no mflib release needed)")
    if lib:
        info(f"2. Optional: create a GitHub release for {tag}")
    info(f"3. Bump [repos.{repo.key}].version in release/release.toml for the next cycle")
    return 0


def cmd_artifacts(ctx: Ctx, _args) -> int:
    build_artifacts(ctx, ctx.read_version(ctx.mflib))
    return 0


def cmd_docs(ctx: Ctx, _args) -> int:
    """Rebuild docs/PDF for the currently stamped version (no commit)."""
    check_docs_tools(ctx)
    build_docs(ctx)
    return 0


VENV_DIR = MFLIB_ROOT / ".venv-release"

# fabrictestbed-extensions reads os.environ["HOME"] at import time, which
# Windows PowerShell/cmd do not set. Child processes inherit this.
os.environ.setdefault("HOME", str(Path.home()))


def reexec_in_release_venv() -> int | None:
    """If .venv-release exists and we're not already in it, re-run this command with its python."""
    venv_py = VENV_DIR / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not venv_py.exists() or os.environ.get("RELEASE_NO_VENV"):
        return None
    if Path(sys.prefix).resolve() == VENV_DIR.resolve():
        return None
    return subprocess.run([str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]]).returncode


def main() -> int:
    global DRY_RUN
    if (code := reexec_in_release_venv()) is not None:
        return code
    if Path(sys.prefix).resolve() != VENV_DIR.resolve():
        print("note: not running in .venv-release (create it with: python release/setup_venv.py)")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["status", "rc", "verify-rc", "final", "artifacts", "docs"])
    p.add_argument("repo", nargs="?", choices=["mflib", "mf"], help="repo to release (rc / final)")
    p.add_argument("--dry-run", action="store_true", help="print mutating commands instead of running them")
    args = p.parse_args()
    if args.command in ("rc", "final") and not args.repo:
        p.error(f"`{args.command}` needs a repo: mflib or mf")
    DRY_RUN = args.dry_run
    handlers = {"status": cmd_status, "rc": cmd_rc, "verify-rc": cmd_verify_rc,
                "final": cmd_final, "artifacts": cmd_artifacts, "docs": cmd_docs}
    try:
        return handlers[args.command](Ctx(), args)
    except ReleaseError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
