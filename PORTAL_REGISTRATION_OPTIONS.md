# Meas Node → Portal Registration: Available Options

Inventory of every code path in this repo related to registering a meas
node with mfportal. One is what every current sample notebook actually
calls; one is a real, working, lower-level alternative that's simply never
wired into anything; the rest are dead ends kept for reference (or, as of
2026-09, deleted -- see git history).

## The current, actually-used option

**`MFPortal.register_slice_with_portal(slice_obj, portal_url=None, slice_name=None, meas_network_name=None, register_path="/api/slice/mini/register")`**
— `mflib/mfportal.py` (see `MFPORTAL_METHODS.md` for the full entry). This is
what `sample-code/RegisterSlice.ipynb`, `sample-code/slice-modify.ipynb`, and
`sample-code/slice-modify-repeated.ipynb` all actually call. One-call
wrapper: `add_meas_network()` (idempotent) → `setup_mfuser_accounts()`
(one shared key pair) → `collect_full_register_data()` → POST via
`minimal_portal_register()` to `{portal_url}{register_path}`
(`/api/slice/mini/register` by default). `portal_url` defaults to
`MFPortal.DEFAULT_PORTAL_URL`. Returns just the portal's parsed JSON
response (no mfuser-key tuple -- that was removed 2026-09).

`MFPortal.get_portal_login_link(...)` is the companion for logging into the
portal afterward, without copy-pasting a token by hand.

## A working option that's simply unused

**`MFPortal.register_meas_node(...)`** — `mflib/mfportal.py:1425` (see
`MFPORTAL_METHODS.md`). This one is real and functional -- not buggy, not a
dead end -- it's just never actually called from anywhere in mflib or
claude-mflib-portal. The only place its name appears outside its own
definition is as a docstring *example* inside
`collect_register_meas_node_args()` ("gathers this method's arguments"),
not a real call site.

```python
register_meas_node(slice_id, slice_name, node_ipv6, meas_net_subnet, gw_v6,
                    mfuser_public_key, node_mgmt_ip, lease_start, lease_end, portal_url)
```

`POST {portal_url}/api/meas-node/register` with `{slice_uuid, slice_name,
fabnetv6_ip, fabnetv6_subnet, fabnetv6_gateway, mfuser_public_key,
node_mgmt_ip, slice_created_at, slice_expires_at}` -- a single-meas-node-shaped
payload, distinct from `register_slice_with_portal()`'s multi-node
`meas_net_nodes`/`registered_slice` shape. Returns
`{registered_at, portal_url, request, response}` — swallows exceptions into
`response={"error": ...}` rather than raising. Returns `None` (no-op) if
`portal_url` is falsy.

It's meant to be used together with:

- **`check_portal_reachable(portal_public_url)`** — `GET
  {portal_url}/api/meas-node/portal-info` first, to confirm the portal
  is up before registering; raises `RuntimeError` if not. Also unused
  elsewhere in this repo.
- **`write_slice_info(...)`** — writes the resulting `portal_registration`
  dict (plus slice metadata) to `/etc/mflib/portal_registration.json` on
  the node, via `write_json_to_node()`. This is the file `meas_node_server`'s
  `GET /slice` endpoint reads back. (This one *is* used elsewhere, just not
  as part of this specific chain -- see `MFPORTAL_METHODS.md`.)

This is a straight port of `samples/create-meas-node.ipynb` Cells 11-12
(module docstring confirms `mfportal.py` was split out of that notebook) —
the notebook has an identical inline copy if you'd rather run it
cell-by-cell than call the static method. If you're looking at this option:
prefer `register_slice_with_portal()` above unless you specifically need
the single-meas-node payload shape and are prepared to wire the reachability
check + info-file write yourself.

## Dead / do-not-use options (both deleted 2026-09 — see git history)

- **`first-draft-mfportal.py::register_meas_node_to_portal`** — the
  earlier draft. Explicitly called out in `mfportal.py`'s own module
  docstring as buggy: it referenced undefined names (`subnet_v6`, `gw_v6`,
  `fabetv6_gateway_str`, `mfuser_public_key`, `local_info`,
  `_write_json_to_node`) and would have raised `NameError` if actually
  called. The file also ended mid-function.
- **`xxx-mflib6.py::portal_*`** — an untracked scratch file (`xxx-`
  prefix, never committed) with mfuser/NIC helpers named `portal_*`, but no
  `requests` import anywhere and no actual HTTP call to a portal — it
  stopped short of ever registering anything.

## What's on the receiving/portal side

Two endpoints the portal is expected to expose: `GET
/api/meas-node/portal-info` (reachability probe) and `POST
/api/meas-node/register` (the actual registration). A third, `GET
/api/meas-node/{slice_uuid}/info`, is documented (notebook +
`print_summary`) as what the *portal* uses to poll the meas node's own
`/status`/`/ip`/`/slice` — but that's the portal calling out to the node,
not registration.

On the node side, both `mflib-node/mflib_node/server.py` and
`MeasurementFramework/user_services/meas_node_server/service_commands/server.py`
are purely passive — they only serve `GET /slice` (reads back
`/etc/mflib/portal_registration.json`, 404 with "node may not be
registered yet" if absent) and never push anything to the portal
themselves. `MeasurementFramework` has no registration-initiating code at
all.

**`mflib-node/` itself is flagged for removal (2026-09)** — see its own
README. Fully superseded by the `MeasurementFramework` copy; nothing live
installs it anymore (the only installer, `MFPortal.clone_mflib_and_install_node_server()`,
is disabled).

There was also a dangling reference in `mfportal.py`'s `deploy_info_server()`
to a `./meas-node-server` directory (routers, `main.py`, etc.) documented
in the notebook as exposing its own `POST /register` — that directory never
existed anywhere in the repo. `deploy_info_server()` itself is now disabled
(commented out, 2026-09) for exactly this reason -- see `MFPORTAL_METHODS.md`.
