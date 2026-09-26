> **⚠️ FLAGGED FOR REMOVAL (2026-09).** Fully superseded by
> `meas_node_server` (now a `MeasurementFramework` `user_service`, installed
> automatically via `MFPortal.meas_node_self_start()` — see that project's
> `user_services/meas_node_server/`). Confirmed zero live callers anywhere in
> this repo: the only code that installed this package
> (`MFPortal.clone_mflib_and_install_node_server()`) is itself disabled
> (commented out, `mflib/mfportal.py`), and its one other reference
> (`samples/create-meas-node.ipynb`'s final cell) is an inline copy of that
> same dead path in a notebook that's already broken elsewhere (Cell 9
> references a `meas-node-server/` directory that doesn't exist in this
> repo). See `PORTAL_REGISTRATION_OPTIONS.md` and `MFPORTAL_METHODS.md` in
> the repo root for the full history. Kept for now pending an explicit
> decision to delete the directory outright.

# MFLib Node Server

REST API server for the FABRIC Measurement Framework measurement node.

## Install from source (pip)

On Debian/Ubuntu, the system Python is "externally managed" (PEP 668) and
refuses plain `pip install`. Use a virtual environment instead:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

Or for an editable install while developing:

```bash
pip install -e .
```

This installs the `mflib-node` console script, which can then be run directly
(with the venv activated):

```bash
mflib-node --port 5000 --token <your-token>
```

## Docker

Build and run via Docker Compose:

```bash
docker compose build
docker compose up -d
```

Set `MFLIB_API_TOKEN` in your environment (or a `.env` file next to
`docker-compose.yml`) to require bearer-token auth on the API.

To stop it:

```bash
docker compose down
```
