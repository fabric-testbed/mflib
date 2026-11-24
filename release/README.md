# Releasing mflib and MeasurementFramework

One command-line tool releases **mflib** (PyPI), **MeasurementFramework** (git
tag) and the two FABRIC artifacts, **MFLib Tests** and **MFLib Examples**.

- **The two repos are versioned independently.** Either one can get a release
  (major, minor or patch) without the other.
- **Nothing is ever pushed to `main`.** The tool pushes only the release branch
  and tags. Each release reaches `main` through a pull request that `final`
  opens and you merge.
- **mflib uses the latest MeasurementFramework release at run time.** When
  mflib sets up a measurement node, it looks up the MF release GitHub labels
  **Latest** and clones that tag (`mflib/mf_repo.py`). A new MF release
  reaches existing mflib installs without a new mflib release. If GitHub
  can't be reached, it falls back to `main`. `Core`/`MFLib`/`MFPortal`
  accept `mf_repo_branch="<branch or tag>"` to override.

| What | Release candidate | Final |
|---|---|---|
| mflib package | `X.Y.ZrcN` on **TestPyPI** | `X.Y.Z` on **PyPI** |
| mflib git tag | `vX.Y.ZrcN` on the release branch | `vX.Y.Z` on the PR merge commit in `main` |
| MeasurementFramework git tag | `vA.B.CrcN` on the release branch (optional) | `vA.B.C` on the PR merge commit in `main` |
| MF `VERSION` file | `A.B.CrcN` | `A.B.C` |
| MF GitHub Release | (none; rc tags never become Latest) | published and labeled **Latest**: what mflib clones from then on |
| Artifacts | `mflib-{tests,examples}-X.Y.ZrcN.tar.gz` | `...-X.Y.Z.tar.gz` |
| `MFLib.pdf` (Sphinx) | rebuilt, says "Release X.Y.ZrcN" | rebuilt, says "Release X.Y.Z" |
| ReadTheDocs | (builds `latest` from `main` only) | rebuilds when the PR is merged |

## Where the settings live

All settings are in [`release.toml`](release.toml), in this repo. Per cycle,
edit only these:

- `[repos.mflib].version` and `[repos.mf].version`: the release each repo is
  preparing (plain `X.Y.Z`; rc numbers are automatic).
- `release_branch` for each repo.

The tool stamps the version fields. Don't edit `__version_info__` or
`VERSION` by hand.

`python release/release.py status` shows both repos, their latest releases,
open release PRs, and which MF release GitHub labels Latest (what mflib
clones right now).

## One-time setup

```bash
python release/setup_venv.py          # any Python >= 3.11; creates mflib/.venv-release
```

The release venv (git-ignored) contains everything a release needs:

- **flit**, to build and publish to TestPyPI and PyPI.
- **Sphinx**, the furo theme, myst-parser, and the packages autodoc imports,
  from `docs/requirements.txt`.
- **fabrictestbed-extensions**, used by autodoc and by `upload_artifacts.py`.
- **tectonic**, the LaTeX engine for `MFLib.pdf`. It is pinned and
  sha256-checked, and lives inside the venv.

`release.py` switches into the venv automatically. You can run it with any
`python`. Set `RELEASE_NO_VENV=1` to stop it switching. Re-run `setup_venv.py`
after `docs/requirements.txt` changes, or run `--recreate` to start from
scratch.

You don't need to activate the venv for `release.py`. To run its tools
yourself (`sphinx-build`, `flit`, `tectonic`), activate it from the mflib
folder:

```text
PowerShell   .venv-release\Scripts\Activate.ps1
cmd          .venv-release\Scripts\activate.bat
Git Bash     source .venv-release/Scripts/activate
Linux/macOS  source .venv-release/bin/activate
```

Run `deactivate` to leave it. If PowerShell refuses to run `Activate.ps1`,
allow local scripts once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Or skip activating and
call the venv's Python directly: `.venv-release\Scripts\python.exe -m sphinx ...`.

You also need:

- A `~/.pypirc` with `[testpypi]` and `[pypi]` sections (API tokens). The
  setup script checks for them.
- MeasurementFramework checked out next to mflib, as set by `repos.mf.path`.
- Optional: the [GitHub CLI](https://cli.github.com/) (`gh auth login`). With
  it, `final` opens the pull request and `final mf` publishes the GitHub
  Release for you. Without it, `final mf` can use a `GITHUB_TOKEN` (or
  `GH_TOKEN`) environment variable for the release; otherwise `final` prints
  the links to do both by hand.

## Docs (Sphinx, PDF, ReadTheDocs, PyPI page)

- `docs/source/conf.py` reads `release = mflib.__version__`. The HTML and PDF
  therefore always show the version that was just stamped.
- **`MFLib.pdf` is rebuilt by `rc mflib` and `final mflib`.** It is committed
  in the same commit as the version stamp, so each tag carries a PDF with its
  own version. The PDF is linked from the README, which is the PyPI page, and
  it ships in the sdist. A failed docs build reverts the stamps and stops the
  release.
- `rc mflib` also builds the HTML, so anything that would break ReadTheDocs
  shows up before `final`.
- ReadTheDocs builds `latest` from `main`, so it rebuilds when the release PR
  is merged. `python release/release.py docs` rebuilds the docs locally for
  the current version, without committing.
- `create_pdf_doc.sh` and `create_html_doc.sh` are replaced by this step.

## Releasing MeasurementFramework

```bash
python release/release.py rc mf        # optional: tags vA.B.CrcN on the release branch, pushes it
python release/release.py final mf     # stamps VERSION, pushes the release branch, opens PR -> main
#   ... review and merge the PR on GitHub (any merge method) ...
python release/release.py final mf     # tags the merge commit vA.B.C, publishes the GitHub
                                       #   Release labeled Latest, syncs the release branch
```

**Publishing the GitHub Release as Latest is the step that makes an MF release
live.** Every mflib install clones it from then on. If the tool can't publish
it (no `gh`, no token), it prints the link, exits non-zero, and `status`
reports the mismatch until it's done.

An MF rc is optional. If one exists for this version, `final mf` refuses to
release anything that changed since it. To try an MF rc before releasing it,
pass it explicitly: `MFLib(..., mf_repo_branch="vA.B.CrcN")`.

Because every mflib version clones the latest MF release, a new MF release
must keep working with the mflib versions people have installed.

## Releasing mflib

```bash
# 1. release candidate -> TestPyPI. Tested against the current Latest MF release.
python release/release.py rc mflib --dry-run     # see exactly what will happen
python release/release.py rc mflib
python release/release.py verify-rc              # clean venv install from TestPyPI, checks version + MF lookup

# 2. test on FABRIC with dist/artifacts/mflib-tests-X.Y.ZrcN.tar.gz
#    found a bug? fix on the release branch, commit, `rc mflib` again (-> rc2, rc3, ...)

# 3. final: stamps X.Y.Z, pushes the release branch, opens PR -> main
python release/release.py final mflib
#    ... review and merge the PR on GitHub (any merge method) ...
python release/release.py final mflib            # tags the merge commit vX.Y.Z, publishes to PyPI

# 4. on FABRIC JupyterHub (where FABlib is configured):
python release/upload_artifacts.py
```

If this mflib needs MF changes that aren't in the Latest MF release yet,
release MF first. Otherwise mflib users get an MF without them.

### Safety rails

- **`main` is never pushed to.** The tool refuses any push whose destination
  is `main`. Only the release branch and tags are pushed.
- **`final` ships exactly what was tested.** It refuses to run if the repo
  changed since its last rc, apart from the stamped lines and `release/` and
  `artifacts/`. It also refuses if `main` has commits the rc didn't include.
  This includes commits that land on `main` while the PR is open.
- **The merged commit is found by content.** After the PR merge, `final` tags
  the commit on `main` whose tree equals the stamped release branch. This
  works for merge-commit, squash and rebase merges.
- **Every step can be re-run.** Steps that already happened (commit, tag,
  push, PR, upload) are skipped. Re-running `final` while the PR is still open
  just reports that it is waiting.

### Artifacts

Put notebooks in `artifacts/tests/` and `artifacts/examples/`. Each tarball
gets a generated `requirements.txt` pinning `fabrictestbed-mflib==<version>`
and a `RELEASE_INFO.json` with the commit SHAs and the MF release that was
Latest when it was built.
Notebooks therefore always install the matching library.
`upload_artifacts.py` adds each tarball as a new version of the artifact titled
in `release.toml`. It tags the artifact `mflib-<version>`.

`create_release.sh` (repo root) is replaced by this tool.
