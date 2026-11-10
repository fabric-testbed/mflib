"""
Client-side half of the MeasurementFramework ``route_flow`` service.

``route_flow`` (MeasurementFramework user_services/route_flow) puts per-route byte
counters on the experiment nodes and an animated topology dashboard in Grafana.
It runs on the meas node, which has no fablib or slice object -- that's especially
true for portal-managed, self-starting meas nodes. So everything that needs the
slice is collected here, on the client, and shipped to the meas node as plain JSON
before it starts:

* portal / self-started meas nodes: ``collect_experiment_topology()`` is added to the
  ``registered_slice`` dict as ``"experiment_topology"`` (see
  ``MFPortal.collect_full_register_data()`` / ``collect_registered_slice_info()``),
  which ends up in /home/mfuser/registered_slice.json. The self-start script runs
  ``route_flow/create.py`` after Prometheus and grafana_manager.
* meas node in the experiment slice: ``MFLib.instrumentize([..., "route_flow"])``
  passes it as the service data.

The experiment interfaces must already have their IP addresses when this is called;
if they change later, run the service's update.py with the new topology.
"""

DEFAULT_MEAS_NODE_NAME = "meas-node"
# networks that belong to MF itself, not to the experiment
DEFAULT_EXCLUDE_NETWORK_PREFIXES = ("l3_meas_net", "meas-net", "meas_net")


def _ip(iface):
    """The interface's address, or None/ fablib's get_ip_addr() returns the IPv6
    link-local(fe80::) address for an interface that has no address configured yet;
    that's not routeable, so it's treaded as "no address."""
    try:
        ip = iface.get_ip_addr()
    except Exception:
        return None
    if not ip:
        return None
    try:
        if ipaddress.ip_address(str(ip)).is_link_local:
            return None
    except ValueError:
        return None
    return str(ip) if ip else None


def _site(node):
    try:
        return node.get_site()
    except Exception:
        return ""


def collect_experiment_topology(
    slice_obj,
    meas_node_name=DEFAULT_MEAS_NODE_NAME,
    exclude_network_prefixes=DEFAULT_EXCLUDE_NETWORK_PREFIXES,
    routes=None,
    meas_ips=None,
):
    """
    Builds the ``experiment_topology`` dict the route_flow service reads::

        {"slice_name": ...,
         "nodes": [{"name", "site", "meas_ip", "ifaces": [{"dev", "ip", "network"}]}],
         "routes": [{"a", "b", "label"}]}

    slice_obj: a submitted fablib Slice whose experiment interfaces already have IPs.
    routes: optional list of (a, b) or (a, b, label) node-name tuples to draw/count.
        Default: every pair of nodes that has an experiment IP.
    meas_ips: optional {node_name: meas-network IP} to show on the dashboard
        (e.g. from MFPortal.get_meas_net()); otherwise taken from each node's
        meas-network interface if it has an address.
    """
    meas_ips = dict(meas_ips or {})
    nodes = []
    for node in slice_obj.get_nodes():
        name = node.get_name()
        if name == meas_node_name:
            continue
        ifaces = []
        for iface in node.get_interfaces():
            try:
                net = iface.get_network()
                net_name = net.get_name() if net else ""
            except Exception:
                net_name = ""
            if net_name.startswith(tuple(exclude_network_prefixes)):
                if name not in meas_ips:
                    meas_ip = _ip(iface)
                    if meas_ip:
                        meas_ips[name] = meas_ip
                continue
            ip = _ip(iface)
            if not ip:
                continue
            try:
                dev = iface.get_device_name()
            except Exception:
                dev = ""
            ifaces.append({"dev": dev or "", "ip": ip, "network": net_name})
        nodes.append({"name": name, "site": _site(node), "meas_ip": meas_ips.get(name), "ifaces": ifaces})

    topology = {"slice_name": slice_obj.get_name(), "nodes": nodes}
    if routes:
        topology["routes"] = [
            {"a": r[0], "b": r[1], "label": r[2] if len(r) > 2 else ""} for r in routes
        ]
    return topology
