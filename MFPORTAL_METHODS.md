# MFPortal Method Reference

All methods on `mflib.mfportal.MFPortal` are `@staticmethod`s — call them
as `MFPortal.method_name(...)`, no instance needed. The class is grouped
in the same order as the `samples/create-meas-node.ipynb` notebook it was
split out of (module docstring in `mflib/mfportal.py`); this doc follows
that same grouping. An earlier, buggy version of several methods here
existed at `mflib/first-draft-mfportal.py` — deleted 2026-09, see git
history if it's ever needed again.

Class constants: `MEAS_NODE_NAME = "meas-node"`, `MEAS_NETWORK_NAME = "meas-net6"`,
`RT_V6 = 30`, `DEFAULT_PORTAL_URL = "https://mfportal.fabric-testbed.net"`
(default for `register_slice_with_portal()`/`get_portal_login_link()` below),
`MF_REPO_TAG` (the frozen MeasurementFramework tag `clone_measurement_framework_repo()`/
`meas_node_self_start()` default to -- see their entries), and
`mfportal_class_version` (`__version__`/`__VERSION__` alias -- bump whenever this
file changes in a way worth telling apart from a stale install).

## Slice name / topology helpers

- **`get_unique_slice_name(fablib, name)`** — returns `name` if no slice
  by that name exists yet, otherwise increments a trailing capital letter
  (`A`→`B`→...→`Z`→`A`) until it finds one that doesn't collide.

- **`meas_fabnet_name(meas_network_name, site)`** — reconstructs the
  exact per-site FABNetv6 network name `node.add_fabnet()` creates:
  `f"{meas_network_name}_IPv6_{site}"`. This is how every other method
  below deterministically finds "the same" network for a given node,
  without `add_fabnet()` ever handing the object back directly.

- **`create_meas_node_slice(fablib, slice_name, site="EDC", image="default_ubuntu_24", cores=4, ram_gb=16, disk_gb=100, meas_node_name=None, meas_network_name=None)`**
  — defines (does **not** submit) a brand-new slice containing just a
  meas node. Returns the unsubmitted `slice_obj`; call `submit_slice()`
  next.

- **`add_meas_node(slice_obj, site="EDC", image=..., cores=4, ram_gb=16, disk_gb=100, meas_node_name=None, meas_network_name=None)`**
  — adds a meas node (+ FABNetv6 NIC via `add_fabnet()`) to an
  *existing*, not-yet-submitted `slice_obj` you already have (e.g. one
  with other experiment nodes already on it). Returns the new node.

## Submitting

- **`submit_slice(slice_obj, wait_timeout=600, wait_interval=20, progress=True)`**
  — `slice_obj.submit(wait=True, ...)` plus a follow-up `slice_obj.update()`
  (needed because `submit()`'s Jupyter fast path can return before its
  cached network/interface state refreshes). For *initial* slice
  creation. See `add_meas_network()` below for why a plain `submit()`
  is handled differently when retrofitting an already-submitted slice.

## Node info / FABNetv6 IP assignment

- **`collect_node_info(slice_obj, meas_node_name=None)`** — looks up one
  node by name and returns `{node, node_mgmt_ip, node_ssh_cmd,
  node_username, slice_id}`.

- **`assign_static_fabnet6_ip(slice_obj, node, meas_network_name=None)`**
  — assigns (or confirms) `node`'s static FABNetv6 address. FABRIC's ACL
  only allows cross-slice traffic to/from a *registered static* address,
  not the SLAAC/EUI-64 address auto-assigned by `post_boot_config()`, so
  this explicitly picks a free IP from the network's pool and runs
  `ip -6 addr add` on the node (idempotent — skips the add if already
  present). Returns `{node_ipv6, meas_net_subnet, gw_v6, dev}`.

## Wiring the FABNetv6 meas network onto a slice

- **`add_meas_network(slice_obj, meas_network_name=None, results_file=None)`**
  — ensures every node in an **already-submitted** slice is wired onto
  its own per-site FABNetv6 network (`node.add_fabnet()` per node — a
  single FABNetv6 network can only exist at one site, so nodes at
  different sites each get their own). Submits the slice
  (`submit(wait=False)` + a manually-driven `wait()`/retry loop — see the
  large comment block in the source for why: routing this through
  `submit()`'s default Jupyter path risks a `SliceStateError` from
  `post_boot_config()`'s internal nested resubmit). Does **not** assign
  IPs itself; call `get_meas_net()` afterward for that. Returns the list
  of node names newly wired (nodes already wired are skipped, not
  re-added).

  ⚠️ **Known issue**: retrofitting a FABNetv6 network onto an
  already-submitted slice via `modify` has been unreliable — the new
  network's reservation is created with no error, but the network never
  shows up in the topology afterward and its interfaces later show
  `Closed`. See `mflib/notes/fabnetv6-modify-network-not-in-topology.md`
  for the full investigation. **Prefer `add_meas_network_presubmit()`
  below whenever the slice hasn't been submitted yet.**

- **`add_meas_network_presubmit(slice_obj, meas_network_name=None)`** —
  the confirmed workaround for the issue above: wires the FABNetv6
  NIC(s) onto a slice's local topology **before** its first `submit()`,
  so the network goes through the orchestrator's `create` path instead
  of `modify`. Raises `ValueError` if called on a slice that already has
  a `slice_id`. Does no submitting/waiting itself — call
  `slice_obj.submit()` yourself right after. Tested 3-for-3 successful in
  `samples/prepare-a-slice-mfportal-presubmit-test.ipynb`.

- **`get_meas_net(slice_obj, meas_network_name=None)`** — the read-only,
  whole-slice counterpart to `add_meas_network()`: returns
  `{node_name: assign_static_fabnet6_ip() result}` for **every** node
  in the slice that already has a wired-up FABNetv6 NIC (not just
  newly-wired ones). Nodes without one are silently skipped.

## Collecting registration data

- ~~**`collect_slice_register_info(slice_obj, meas_network_name=None)`**~~
  — **disabled 2026-09, commented out in the source.** Zero call sites
  anywhere in mflib or claude-mflib-portal. Would have returned
  `{slice_name, slice_id, lease_start, lease_end, meas_net}` where
  `meas_net` is `get_meas_net()`'s result.

- **`minimal_register_data(slice_obj, mfuser_private_key, mfuser_public_key)`**
  — the smallest registration payload: `{id_token, slice_uuid,
  mfuser_private_key, mfuser_public_key}`. Touches no node/network.

- **`collect_full_register_data(slice_obj, mfuser_private_key, mfuser_public_key, meas_network_name=None)`**
  — `minimal_register_data()` plus:
  - `meas_net_nodes`: `get_meas_net()` flattened into a list, each entry
    with `node_name`/`site`/`network_name` folded in alongside
    `node_ipv6`/`meas_net_subnet`/`gw_v6`/`dev`.
  - `registered_slice`: `{slice_id, slice_name, nodes, mfuser_private_key}`
    in exactly the shape a meas node's `/home/mfuser/registered_slice.json`
    expects (derived from `meas_net_nodes` above, not a second
    `get_meas_net()` call — that does real SSH work per node). Meant for
    the **portal-managed-meas-node** architecture: the portal receives
    this whole payload and is responsible for writing the
    `registered_slice` sub-dict, verbatim, onto its own meas node once
    it exists (this client has no SSH access to it).

  Note `mfuser_private_key` currently appears twice in the returned
  dict — once top-level, once inside `registered_slice` — since
  `registered_slice` is meant to be self-contained.

- **`minimal_portal_register(data, portal_url)`** — POSTs `data` to
  `portal_url` exactly as given (no path appended, unlike
  `register_meas_node()` below). Returns the portal's parsed JSON, or
  `{"error": str(exc)}` on failure.

## One-call registration / portal login (what notebooks actually call)

- **`register_slice_with_portal(slice_obj, portal_url=None, slice_name=None, meas_network_name=None, register_path="/api/slice/mini/register")`**
  — **the method every current sample notebook actually calls to register a
  slice.** One-call version of the manual add-meas-network → setup-mfuser →
  collect-data → POST sequence: ensures every node has a FABNetv6 meas-net
  NIC (`add_meas_network()`, idempotent), sets up one shared mfuser key pair
  across the whole slice (`setup_mfuser_accounts()`), collects the
  registration payload (`collect_full_register_data()`), and POSTs it via
  `minimal_portal_register()` to `{portal_url}{register_path}`. The meas net
  is added here, in the *caller's own* fablib session with real SSH access —
  the portal itself can't do the IP-assignment half of `add_meas_network()`,
  since it only ever has an ephemeral key never authorized on the user's
  nodes.

  `portal_url` defaults to `MFPortal.DEFAULT_PORTAL_URL`
  (`https://mfportal.fabric-testbed.net`) when not given.

  Returns just the portal's parsed JSON response (or `{"error": ...}` on
  failure) — **not** a tuple with the mfuser keys (that returned-tuple shape
  was removed 2026-09; if a caller needs the keys directly, call
  `setup_mfuser_accounts()`/`setup_mfuser_account()` separately instead of
  this wrapper).

- **`get_portal_login_link(portal_url=None, fablib_manager=None, login_path="/login", display_link=True)`**
  — builds a clickable link that logs the caller into `portal_url` using
  their current FABRIC id_token, so nobody has to copy/paste a token into
  the portal's login page by hand. The token travels in the URL *fragment*
  (`#token=...`), never sent to the server or logged, only read client-side
  by the portal's login page JS — still sensitive once clicked (ends up in
  browser history), and stops working once the underlying token expires.
  `portal_url` defaults to `MFPortal.DEFAULT_PORTAL_URL` here too.
  `display_link=True` renders a clickable HTML link via `IPython.display`
  inside a notebook kernel (falls back to printing the URL otherwise) —
  deliberately not `webbrowser.open()`, which would try to open a browser on
  the notebook *server*, not the user's own machine. Always returns the URL
  string regardless of `display_link`.

## Persistent FABNetv6 routing

- **`install_persistent_fabnetv6_routing(node, node_ipv6, meas_net_subnet, gw_v6, dev, rt_v6=None)`**
  — installs a policy-routing script + systemd oneshot unit so replies
  from `node_ipv6` exit via the FABNetv6 gateway (not the management
  default), surviving reboots. `rt_v6` defaults to `RT_V6` (30).

## mfuser account setup

- **`setup_mfuser_account(node, slice_name, key_path=None, pub_path=None)`**
  — creates (or loads, if `key_path`/`pub_path` given) an mfuser SSH key
  pair, creates the `mfuser` account on `node`, authorizes the public
  key, and saves both keys into mfuser's own `~/.ssh/` (as
  `mfuser_private_key`/`mfuser_public_key`) since `hosts.ini`'s
  `ansible_ssh_private_key_file` points there. Returns
  `(mfuser_private_key, mfuser_public_key)` as strings.

- **`setup_mfuser_accounts(slice_obj, slice_name=None)`** — calls the
  above for every node in the slice; generates the key pair once (on the
  first node) and reuses it for every other node, so the whole slice
  trusts one shared key. Returns that shared `(mfuser_private_key,
  mfuser_public_key)`.

## Info/registration server

- ~~**`deploy_info_server(node, node_ipv6, server_dir=None)`**~~ —
  **disabled 2026-09, commented out in the source.** Zero call sites, and
  confirmed broken even if it were called: per `PORTAL_REGISTRATION_OPTIONS.md`,
  the `./meas-node-server` directory it expects (routers, `main.py`, etc.)
  doesn't exist anywhere in the repo — `server_dir.exists()` would always
  raise `FileNotFoundError`. Fully superseded by `meas_node_server` (now a
  MeasurementFramework `user_service`, installed via `meas_node_self_start()`).

## Writing slice info onto a node

- **`write_json_to_node(node, data, remote_path)`** — writes `data` as
  JSON to `remote_path` on `node` via a base64 pipe (avoids shell-quoting
  issues). Generic helper several methods below build on.

- **`collect_write_slice_info_args(slice_obj, meas_node_name=None, meas_network_name=None)`**
  — gathers `write_slice_info()`'s arguments (via `collect_node_info()` +
  `assign_static_fabnet6_ip()`) so you don't have to wire them by hand:
  `MFPortal.write_slice_info(slice_obj, **MFPortal.collect_write_slice_info_args(slice_obj))`.

- **`write_slice_info(slice_obj, node, node_mgmt_ip, node_ipv6, meas_net_subnet, gw_v6, portal_registration=None, remote_path="/etc/mflib/portal_registration.json")`**
  — writes the info-server's local state file onto `node` (so it always
  has *something* to serve, even before portal registration).

- ~~**`setup_initial_slice_json(slice_obj, meas_node_name=MEAS_NODE_NAME, meas_network_name=MEAS_NETWORK_NAME)`**~~
  — **disabled 2026-09, commented out in the source.** Zero call sites
  anywhere in mflib or claude-mflib-portal. Would have been a one-call
  wrapper: gathers `collect_write_slice_info_args()` and calls
  `write_slice_info()` with `portal_registration=None` (filled in later by
  a second `write_slice_info()` call, after `register_meas_node()`).

## Registering the experiment slice's nodes (+ mfuser key) on a meas node

Distinct from `write_slice_info()`'s `portal_registration.json` (info
*about the meas node itself*, for the portal to poll). This is the file
`meas_node_self_start()`'s generated script reads to populate the full
`[Experiment_Nodes]` group of `hosts.ini`, instead of leaving it empty.

- **`collect_registered_slice_nodes(slice_obj, meas_network_name=None)`**
  — one `{name, ip_addr, network}` entry per node with a wired-up
  FABNetv6 NIC (via `get_meas_net()`). `ip_addr` is the **meas-net** IP,
  not the FABRIC management IP.

- **`collect_registered_slice_info(slice_obj, mfuser_private_key, meas_network_name=None)`**
  — builds `{slice_id, slice_name, nodes, mfuser_private_key}` without
  writing it anywhere. Use this when the caller has **no** direct
  `fablib.Node` handle to the meas node that needs this data — i.e. the
  portal-managed-meas-node architecture.

- **`write_registered_slice_info(meas_node, slice_obj, mfuser_private_key, meas_network_name=None, remote_path="/home/mfuser/registered_slice.json")`**
  — writes the above dict directly onto `meas_node`, then
  `chown mfuser:mfuser` + `chmod 600` it (it embeds a private key). Only
  usable when the caller has a direct `fablib.Node` handle — e.g. a meas
  node embedded in the same experiment slice. If self-start hasn't run
  on that node yet, prefer passing this data into
  `meas_node_self_start()`'s `registered_slice=` argument instead (see
  below) to avoid a race.

  `mfuser_private_key` here must be the **experiment slice's** mfuser
  key (from `setup_mfuser_accounts()`), which is *not necessarily* the
  same key authorized on the meas node's own account — see
  `meas_node_self_start()` for how the two are kept independent.

## Portal connectivity / registration

- **`check_portal_reachable(portal_public_url)`** — `GET
  {portal_url}/api/meas-node/portal-info`. Returns the parsed info dict,
  or raises `RuntimeError` if unreachable. Returns `None` (no-op) if
  `portal_public_url` is falsy.

- **`collect_register_meas_node_args(slice_obj, mfuser_public_key, meas_node_name=None, meas_network_name=None, portal_url=None)`**
  — gathers `register_meas_node()`'s arguments. Tolerant of a missing/
  not-yet-wired meas node: `slice_id`/`slice_name`/`lease_start`/
  `lease_end` are always populated, and `node_ipv6`/`meas_net_subnet`/
  `gw_v6`/`node_mgmt_ip` are left `None` (rather than raising) if the
  meas node can't be found.

- **`register_meas_node(slice_id, slice_name, node_ipv6, meas_net_subnet, gw_v6, mfuser_public_key, node_mgmt_ip, lease_start, lease_end, portal_url)`**
  — `POST {portal_url}/api/meas-node/register`. This is the one
  currently-*working* portal registration option per
  `PORTAL_REGISTRATION_OPTIONS.md` (single meas-node-shaped payload, not
  the newer multi-node `meas_net_nodes`/`registered_slice` shape above —
  check with the portal side about which it actually expects before
  relying on this for a multi-node registration). Returns
  `{registered_at, portal_url, request, response}`; swallows exceptions
  into `response={"error": ...}`. Returns `None` if `portal_url` is
  falsy.

## Ansible `hosts.ini` (meas node only)

For a standalone meas node with no experiment slice, `bootstrap_playbooks.py`
still needs *some* `hosts.ini` inventory to run against.

- **`build_meas_node_hosts_ini(meas_node_name, ansible_host, management_ip_type=None, ansible_connection=None)`**
  — pure text builder (no fablib dependency) for a meas-node-only
  `hosts.ini` (empty `[Experiment_Nodes]` group). Pass
  `ansible_connection="local"` when generating this to run against the
  node itself (as `meas_node_self_start()` does internally).

- ~~**`create_meas_node_hosts_ini(node, meas_node_name=None, remote_path="/home/mfuser/services/common/hosts.ini")`**~~
  — **disabled 2026-09, commented out in the source.** Zero call sites
  anywhere in mflib or claude-mflib-portal. Would have been the
  client-side counterpart, building the above and installing it on `node`
  over SSH — the node builds its own inline instead (`meas_node_self_start()`'s
  generated script duplicates the same logic locally).

## Installing MeasurementFramework (client-driven)

Each of these runs its setup command once, over SSH, when the client
calls it — the client-driven equivalent of what `meas_node_self_start()`
below does as a local systemd service.

- **`clone_measurement_framework_repo(node, mf_repo_branch=None)`** —
  `git clone` the `MeasurementFramework` repo into `/home/mfuser/mf_git`.
  Defaults to `MFPortal.MF_REPO_TAG` (a frozen tag, e.g. `v1.0.0-mfportal`
  cut from `bootstrap-updating` -- not a moving branch) when not given.
- **`run_bootstrap_script(node)`** — runs
  `instrumentize/experiment_bootstrap/bootstrap.sh` (installs ansible,
  stages `user_services`).
- **`run_bootstrap_ansible(node)`** — copies `ansible.cfg` into place and
  runs `bootstrap_playbooks.py` (the actual docker/PTP/node-exporter
  etc. ansible plays).
- ~~**`clone_mflib_and_install_node_server(node, mflib_repo_branch="node")`**~~
  — **disabled 2026-09, commented out in the source.** Was the old way of
  getting a node status server onto the meas node: clone `mflib` itself
  (the `node` branch) and `pip install -e mflib-node`. Zero call sites
  anywhere in mflib or claude-mflib-portal. Fully superseded by
  `meas_node_server` (now a MeasurementFramework `user_service`, installed
  via `meas_node_self_start()`'s own `create.py` call) — no separate mflib
  clone + pip install needed on the node at all anymore.

## Meas node self-start (systemd, runs on the node itself)

- **`meas_node_self_start(node, mf_repo_branch=None, registered_slice=None)`**
  — installs a systemd **oneshot** service on `node` that performs the
  local-node equivalent of the four methods just above (clone
  `MeasurementFramework`, run `bootstrap.sh`, run the ansible bootstrap
  playbook), plus a self-generated `write_hosts_ini()` step (mirrors
  `build_meas_node_hosts_ini()`, since the node has no fablib/mflib
  available to it). The service starts immediately and re-runs on every
  future boot (idempotent).

  The generated script's `write_hosts_ini()` also checks for
  `/home/mfuser/registered_slice.json` (see the section above) and, if
  present, populates the full `[Experiment_Nodes]` group instead of
  leaving it empty — writing the experiment slice's mfuser key to its
  **own** dedicated file, `/home/mfuser/.ssh/experiment_mfuser_private_key`
  (never overwriting the meas node's own
  `/home/mfuser/.ssh/mfuser_private_key`), and pointing
  `[Experiment_Nodes:vars]`'s `ansible_ssh_private_key_file` at it.

  Pass `registered_slice` (from `collect_registered_slice_info()` or
  `write_registered_slice_info()`'s return value) to have this method
  write that file itself, **before** installing/starting the service —
  otherwise the service's very first run (seconds after this call
  returns) can race ahead of a separately-written file and silently fall
  back to an empty `[Experiment_Nodes]` group.

  Not currently called from anywhere else in this repo (no sample
  notebook, no other `MFPortal` method) — it's an available building
  block, not yet wired into an end-to-end flow.

## Summary printing

- ~~**`print_summary(slice_name, slice_id, node_ipv6, meas_net_subnet, gw_v6, node_mgmt_ip, node_ssh_cmd, mfuser_key_filename, portal_registration=None, portal_public_url=None)`**~~
  — **disabled 2026-09, commented out in the source.** Zero call sites
  anywhere in mflib or claude-mflib-portal, superseded by the portal's own
  UI. Would have pretty-printed a final "Meas Node Ready" block; its
  "Proxy URL" line was also stale, still referencing the old
  `{slug}.{PORTAL_DOMAIN}` wildcard-subdomain scheme the portal replaced
  with per-node ports (see `docs/request-flow.md` in claude-mflib-portal).
