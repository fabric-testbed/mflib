# MIT License
#
# Copyright (c) 2023 FABRIC Testbed
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

"""
Maps the slice's dataplane interfaces to the FABRIC data-switch port and VLAN they use,
and builds links to the matching sub-interface on the public-metrics
"Per Port Bandwidth" Grafana dashboard.

Everything except the switch address comes from the slice's FIM model. The
public-metrics dashboard selects a site's switch by an address prefix (its "Rack"
variable), which is not in the FIM model, so it comes from SITE_RACK_PREFIX.
"""

import urllib.parse

PUBLIC_METRICS_PORT_BANDWIDTH_URL = (
    "https://public-metrics.fabric-testbed.net/grafana/d/bdvlpnm4jd8n4c/per-port-bandwidth"
)

# Value of the dashboard's "switch" variable for the data switch (mgt-sw is 2).
# The switch address is <rack prefix><this value>, e.g. 192.168.20.3 for NCSA.
DATA_SWITCH = "3"

# Site -> value of the dashboard's "Rack" (hankip) variable, copied from its options.
SITE_RACK_PREFIX = {
    "RENC": "192.168.11.", "UKY": "192.168.12.", "LBNL": "192.168.13.", "STAR": "192.168.14.",
    "MAX": "192.168.15.", "TACC": "192.168.16.", "MICH": "192.168.17.", "MASS": "192.168.18.",
    "UTAH": "192.168.19.", "NCSA": "192.168.20.", "WASH": "192.168.21.", "DALL": "192.168.22.",
    "SALT": "192.168.23.", "UCSD": "192.168.24.", "GPN": "192.168.25.", "FIU": "192.168.26.",
    "CLEM": "192.168.27.", "GATECH": "192.168.28.", "LEARN": "192.168.29.", "LOSA": "192.168.30.",
    "NEWY": "192.168.31.", "KANS": "192.168.32.", "ATLA": "192.168.33.", "SEAT": "192.168.34.",
    "PRIN": "192.168.35.", "INDI": "192.168.36.", "PSC": "192.168.37.", "RUTG": "192.168.38.",
    "SRI": "192.168.39.", "CERN": "192.168.40.", "BRIST": "192.168.41.", "AMST": "192.168.42.",
    "TOKY": "192.168.43.", "HAWI": "192.168.44.", "EDUKY": "192.168.45.", "CIEN": "192.168.46.",
    "SCM": "192.168.50.2",
}

DASHBOARD_UID = "mflib-switch-ports"


def _fim_network_interface(network, iface):
    """
    Finds the network service interface (the switch side) in the network's FIM model that
    belongs to the given node interface. Same name match fablib's Interface.get_switch_port uses.
    """
    fim_network = network.get_fim()
    if not fim_network:
        return None
    for name, fim_iface in fim_network.interfaces.items():
        if iface.get_name() in name:
            return fim_iface
    return None


def public_metrics_url(entry, base_url=PUBLIC_METRICS_PORT_BANDWIDTH_URL, time_from="now-1h"):
    """
    Builds the public-metrics Per Port Bandwidth link for one port map entry.

    Args:
        entry (dict): An entry from get_switch_port_map().
        base_url (String): The Per Port Bandwidth dashboard URL.
        time_from (String): Grafana start time for the link.

    Returns:
        String: The URL, or None if the entry lacks a rack prefix or sub-interface.
    """
    if not entry.get("rack_prefix") or not entry.get("switch_interface"):
        return None
    query = {
        "orgId": "1",
        "var-switch": DATA_SWITCH,
        "var-hankip": entry["rack_prefix"],
        "var-Interface": entry["switch_interface"],
        "from": time_from,
        "to": "now",
    }
    return base_url + "?" + urllib.parse.urlencode(query)


def get_switch_port_map(slice, rack_prefixes=None, base_url=PUBLIC_METRICS_PORT_BANDWIDTH_URL):
    """
    Maps each dataplane interface in the slice to its data-switch port and VLAN.

    Args:
        slice (fablib.Slice): An instantiated slice.
        rack_prefixes (dict): Site -> rack prefix overrides, merged over SITE_RACK_PREFIX.
        base_url (String): The Per Port Bandwidth dashboard URL.

    Returns:
        List of dict: One entry per interface, with network, network_type, node, site,
        os_interface, mac, ip, switch, switch_port, vlan, rack_prefix, switch_ip,
        switch_interface and url.
    """
    prefixes = dict(SITE_RACK_PREFIX, **(rack_prefixes or {}))
    port_map = []
    for network in slice.get_networks():
        for iface in network.get_interfaces():
            fim_iface = _fim_network_interface(network, iface)
            labels = fim_iface.labels if fim_iface else None
            port = getattr(labels, "local_name", None)
            vlan = getattr(labels, "vlan", None) or iface.get_vlan() or None
            node = iface.get_node()
            site = iface.get_site() or (node.get_site() if node else None)
            entry = {
                "network": network.get_name(),
                "network_type": str(network.get_type()),
                "node": node.get_name() if node else None,
                "site": site,
                "os_interface": iface.get_device_name(),
                "mac": iface.get_mac(),
                # Address fablib saved in the FIM model; get_ip_addr() would ssh to the node.
                "ip": str(iface.get_fablib_data().get(iface.ADDR) or ""),
                "switch": getattr(labels, "device_name", None),
                "switch_port": port,
                "vlan": str(vlan) if vlan else None,
                "rack_prefix": prefixes.get(site),
                "switch_ip": prefixes[site] + DATA_SWITCH if site in prefixes else None,
                "switch_interface": f"{port}.{vlan}" if port and vlan else port,
            }
            entry["url"] = public_metrics_url(entry, base_url)
            port_map.append(entry)
    return port_map


def make_switch_port_dashboard(slice_name, port_map):
    """
    Builds a Grafana dashboard (as the body for POST /api/dashboards/db) listing every
    interface with a link to its sub-interface on public-metrics.

    Args:
        slice_name (String): Slice name, used in the dashboard title.
        port_map (List of dict): Output of get_switch_port_map().

    Returns:
        dict: The dashboard request body.
    """
    rows = []
    for e in sorted(port_map, key=lambda e: (e["network"], e["node"] or "")):
        link = f"[Per Port Bandwidth]({e['url']})" if e["url"] else "n/a"
        rows.append(
            f"| {e['network']} | {e['node']} | {e['site']} | `{e['os_interface']}` | {e['ip']} | "
            f"{e['switch_ip'] or ''} | `{e['switch_interface'] or ''}` | {link} |"
        )
    table = (
        "Each link opens the data-switch sub-interface (port.VLAN) this slice uses on "
        "FABRIC public-metrics.\n\n"
        "| network | node | site | interface | IP | data switch | sub-interface | public-metrics |\n"
        "|---|---|---|---|---|---|---|---|\n" + "\n".join(rows)
    )
    dashboard = {
        "uid": DASHBOARD_UID,
        "title": f"{slice_name} - switch ports",
        "tags": ["mflib", "public-metrics"],
        "schemaVersion": 36,
        "time": {"from": "now-1h", "to": "now"},
        "links": [{"title": "public-metrics Per Port Bandwidth", "type": "link",
                   "url": PUBLIC_METRICS_PORT_BANDWIDTH_URL, "targetBlank": True}],
        "panels": [{"type": "text", "title": "Slice interfaces on the FABRIC data switches",
                    "gridPos": {"x": 0, "y": 0, "w": 24, "h": 4 + len(rows)},
                    "options": {"mode": "markdown", "content": table}}],
    }
    return {"dashboard": dashboard, "overwrite": True}
