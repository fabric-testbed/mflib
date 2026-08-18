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
Split out of samples/create-meas-node.ipynb. Each method below corresponds
to one cell (or a small group of cells) from that notebook, turned into a
reusable MFPortal staticmethod instead of notebook-global procedural code.

The earlier version of this class (methods moved wholesale out of mflib.py,
before this notebook-derived rewrite) is kept at mflib/first-draft-mfportal.py
for reference — several of its methods (register_meas_node_to_portal in
particular) had undefined-name bugs that this version fixes.
"""

import base64
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import paramiko
import requests as _req

from mflib.mflib import MFLib


class MFPortal(MFLib):
    """
    Draft MFPortal — see module docstring. Methods are grouped in the same
    order as the notebook's cells.
    """

    MEAS_NODE_NAME = "meas-node"
    MEAS_NETWORK_NAME = "meas-net6"
    RT_V6 = 30

    # ------------------------------------------------------------------
    # Cell "get_unique_slice_name" helper
    # ------------------------------------------------------------------
    @staticmethod
    def get_unique_slice_name(fablib, name):
        """
        Returns the given slice name if it doesn't exist, otherwise increments
        the last character to the next capital letter (A->B, B->C, ... Z->A).

        :param fablib: FablibManager instance
        :param name: desired slice name
        :return: unique slice name
        """
        existing = {s.get_name() for s in fablib.get_slices()}

        if name not in existing:
            return name

        base = name[:-1] if name and name[-1].isupper() else name
        suffix_ord = ord(name[-1]) if name and name[-1].isupper() else ord('A') - 1

        while True:
            next_char = chr((suffix_ord - ord('A') + 1) % 26 + ord('A'))
            candidate = base + next_char
            if candidate not in existing:
                return candidate
            suffix_ord = ord(next_char)

    # ------------------------------------------------------------------
    # Cell 3 — Define Slice Topology
    # ------------------------------------------------------------------
    @staticmethod
    def meas_fabnet_name(meas_network_name, site):
        """
        The exact per-site network name node.add_fabnet(name=meas_network_name,
        net_type="IPv6") creates/reuses for a node at `site` — fablib names
        it "<name>_<net_type>_<site>" internally. Reconstructing it here
        (rather than guessing/substring-matching) is what lets
        add_meas_network() and assign_static_fabnet6_ip() look up the same
        network deterministically, without needing add_fabnet() to return
        it directly.
        """
        return f"{meas_network_name}_IPv6_{site}"

    @staticmethod
    def create_meas_node_slice(
        fablib,
        slice_name,
        site="EDC",
        image="docker_ubuntu_20",
        cores=4,
        ram_gb=16,
        disk_gb=100,
        meas_node_name=None,
        meas_network_name=None,
    ):
        """
        Defines (but does not submit) a slice with a single meas node
        connected to a FABNetv6 (IPv6) network.

        Returns the unsubmitted slice_obj — call submit_slice() next.
        """
        slice_obj = fablib.new_slice(name=slice_name)

        MFPortal.add_meas_node(
            slice_obj,
            site=site,
            image=image,
            cores=cores,
            ram_gb=ram_gb,
            disk_gb=disk_gb,
            meas_node_name=meas_node_name,
            meas_network_name=meas_network_name,
        )

        return slice_obj

    @staticmethod
    def add_meas_node(
        slice_obj,
        site="EDC",
        image="docker_ubuntu_20",
        cores=4,
        ram_gb=16,
        disk_gb=100,
        meas_node_name=None,
        meas_network_name=None,
    ):
        """
        Adds a meas node (with a FABNetv6 NIC/network) to an existing,
        not-yet-submitted slice object. Unlike create_meas_node_slice(),
        this doesn't create the slice itself — use it when the caller
        already has a slice_obj (e.g. one with other experiment nodes on
        it) and just wants the meas node added to it.

        Uses node.add_fabnet() rather than manually creating an
        add_l3network()/add_component() — this is the same mechanism
        add_meas_network() uses for the slice's other nodes, so the meas
        node ends up on a "<meas_network_name>_IPv6_<site>" network
        (see meas_fabnet_name()) just like everyone else, and
        assign_static_fabnet6_ip() works identically for either. Also
        means a single FABNetv6 network is never asked to span more than
        one site — FABRIC's orchestrator rejects that with "cannot span
        N sites. Limit: 1."

        Returns the newly added meas_node.
        """
        meas_node_name = meas_node_name or MFPortal.MEAS_NODE_NAME
        meas_network_name = meas_network_name or MFPortal.MEAS_NETWORK_NAME

        meas_node = slice_obj.add_node(name=meas_node_name, site=site)
        meas_node.set_capacities(cores=cores, ram=ram_gb, disk=disk_gb)
        meas_node.set_image(image)

        meas_node.add_fabnet(name=meas_network_name, net_type="IPv6")

        print("Meas node added to slice:")
        print(f"  {meas_node_name} <-- FABNetv6 --> {MFPortal.meas_fabnet_name(meas_network_name, site)}")

        return meas_node

    # ------------------------------------------------------------------
    # Cell 4 — Submit Slice
    # ------------------------------------------------------------------
    @staticmethod
    def submit_slice(slice_obj, wait_timeout=600, wait_interval=20, progress=True):
        print(f"Submitting '{slice_obj.get_name()}' ({wait_timeout // 60}-{wait_timeout // 60 + 5} min)...")
        slice_obj.submit(
            wait=True,
            wait_timeout=wait_timeout,
            wait_interval=wait_interval,
            progress=progress,
        )
        # submit()'s default Jupyter fast path returns before refreshing the
        # slice's cached network_services/interfaces — without this, an
        # immediately-following get_network()/get_interface() call (e.g. in
        # collect_node_info()/assign_static_fabnet6_ip()) can still see
        # pre-submit state.
        slice_obj.update()
        print(f"\nSlice up — ID: {slice_obj.get_slice_id()}")
        return slice_obj

    # ------------------------------------------------------------------
    # Cell 5 — Collect Node Info
    # ------------------------------------------------------------------
    @staticmethod
    def collect_node_info(slice_obj, meas_node_name=None):
        meas_node_name = meas_node_name or MFPortal.MEAS_NODE_NAME
        node = slice_obj.get_node(meas_node_name)

        info = {
            "node": node,
            "node_mgmt_ip": str(node.get_management_ip()) if node.get_management_ip() else None,
            "node_ssh_cmd": node.get_ssh_command(),
            "node_username": node.get_username(),
            "slice_id": slice_obj.get_slice_id(),
        }

        print(f"Slice ID : {info['slice_id']}")
        print(f"Mgmt IP  : {info['node_mgmt_ip']}")
        print(f"SSH      : {info['node_ssh_cmd']}")
        print(f"Username : {info['node_username']}")

        return info

    # ------------------------------------------------------------------
    # Cell 6 — Assign Static FABNetv6 IP
    #
    # The version of this method in first-draft-mfportal.py doesn't return
    # the values it computes, so nothing downstream (routing, registration)
    # can use them. This version returns them instead of leaving them as
    # notebook globals.
    # ------------------------------------------------------------------
    @staticmethod
    def assign_static_fabnet6_ip(slice_obj, node, meas_network_name=None):
        """
        Assigns (or confirms) the node's static FABNetv6 address.

        FABRIC's ACL only allows cross-slice traffic to/from the registered
        static address, not the SLAAC/EUI-64 address assigned by
        post_boot_config().

        `meas_network_name` is the base name passed to add_meas_node()/
        add_meas_network() (which use node.add_fabnet() under the hood) —
        this resolves it to that node's actual per-site network via
        meas_fabnet_name(), since a FABNetv6 network can only exist at one
        site, so nodes at different sites are never on the same actual
        network even though they share a base name.

        Returns a dict: node_ipv6, meas_net_subnet, gw_v6, dev.
        """
        meas_network_name = meas_network_name or MFPortal.MEAS_NETWORK_NAME
        site_network_name = MFPortal.meas_fabnet_name(meas_network_name, node.get_site())

        net_obj = slice_obj.get_network(site_network_name)
        iface_obj = node.get_interface(network_name=site_network_name)
        net_obj.config()

        subnet_v6 = net_obj.get_subnet()
        gw_v6 = net_obj.get_gateway()
        node_ipv6 = net_obj.get_available_ips(count=1)[0]
        dev = iface_obj.get_device_name()

        print(f"Subnet  : {subnet_v6}")
        print(f"Gateway : {gw_v6}")
        print(f"IP      : {node_ipv6}")
        print(f"Device  : {dev}")

        # Only call ip_addr_add() if the address is not already present
        _check, _ = node.execute(f"ip -6 addr show dev {dev}")
        if str(node_ipv6) not in _check:
            node.ip_addr_add(addr=node_ipv6, subnet=subnet_v6, interface=iface_obj)
            print("Static IPv6 assigned.")
        else:
            print("Address already present — skipping ip_addr_add().")

        stdout, _ = node.execute(f"ip -6 addr show {dev}")
        print(stdout)

        return {
            "node_ipv6": str(node_ipv6),
            "meas_net_subnet": str(subnet_v6),
            "gw_v6": str(gw_v6),
            "dev": dev,
        }

    @staticmethod
    def add_meas_network(slice_obj, meas_network_name=None, assign_static_fabnet6_ip=False, results_file=None):
        """
        Ensures every node in the slice is wired onto a FABNetv6 meas
        network with a static IP assigned.

        FABRIC enforces that a single FABNetv6 (or FABNetv4) network can
        only span one site — trying to attach nodes from multiple sites to
        one shared network fails at submit time with an orchestrator error
        ("Service ... of type FABNetv6 cannot span N sites. Limit: 1.").
        So rather than one shared network for the whole slice, this uses
        node.add_fabnet() per node, which creates (or reuses) a FABNetv6
        network local to *that node's own site* and adds a route to
        FablibManager.FABNETV6_SUBNET — the FABRIC-wide address space every
        site's local network is carved out of. Because every node ends up
        with a route to that same top-level subnet, nodes at different
        sites can still reach each other, the same way
        MFLib.addMeasNode() does it manually for FABNetv4 with per-site
        l3_meas_net_<site> networks + add_route(). add_meas_node() uses
        this same mechanism for the meas node itself, so both land on
        "<meas_network_name>_IPv6_<site>" networks (meas_fabnet_name()).

        For each node: if it already has an interface on its own
        meas_fabnet_name() network, it's left alone — a note is printed
        and the node is skipped (add_fabnet() itself always adds a new NIC
        unconditionally, so this check is what makes repeat calls safe).
        Otherwise node.add_fabnet() wires it up and assign_static_fabnet6_ip()
        is called to give it a static address.

        Note: adding a component to a node implies the slice supports
        adding hardware after submission (fablib's modify/resubmit flow).
        A newly added NIC/network only exists in fablib's local model until
        the slice is (re)submitted — before that, the network has no real
        subnet/gateway from FABRIC yet, so assign_static_fabnet6_ip() would
        fail with net_obj.get_available_ips() returning None. This method
        calls slice_obj.submit() after wiring up any new NICs, before
        assigning IPs, to cover both the pre-submit case (initial slice
        build) and the already-submitted case (retrofitting an existing
        slice) — assuming your fablib version supports resubmitting an
        already-submitted slice to add hardware; older versions may need
        slice_obj.modify()/modify_accept() instead.

        If results_file is given, the results dict is also written there as
        JSON. Left as None (the default), nothing is saved to disk.

        Returns {node_name: assign_static_fabnet6_ip() result} for every
        node that was newly wired up. Nodes that already had a FABNetv6 NIC
        are not included.
        """
        meas_network_name = meas_network_name or MFPortal.MEAS_NETWORK_NAME

        newly_wired = []
        for node in slice_obj.get_nodes():
            site_network_name = MFPortal.meas_fabnet_name(meas_network_name, node.get_site())

            if node.get_interface(network_name=site_network_name) is not None:
                print(f"{node.get_name()}: FABNetv6 NIC on {site_network_name} already exists — skipping.")
                continue

            print(f"{node.get_name()}: adding FABNetv6 NIC via add_fabnet() ({site_network_name}).")
            node.add_fabnet(name=meas_network_name, net_type="IPv6")
            newly_wired.append(node)

        if newly_wired:
            print("Submitting slice to provision new NIC(s)/network before assigning IPs...")
            slice_obj.submit(wait=False)
            slice_obj.update()
            # submit()'s default Jupyter fast path returns before refreshing
            # the slice's cached network_services/interfaces, so
            # get_network()/get_interface() below can still see the
            # pre-submit state without this.
            slice_obj.update()

        results = {}
        if (assign_static_fabnet6_ip):
            for node in newly_wired:
                results[node.get_name()] = MFPortal.assign_static_fabnet6_ip(
                    slice_obj, node, meas_network_name=meas_network_name
                )

        if results_file is not None:
            with open(results_file, "w") as f:
                json.dump(results, f, indent=2)
            print(f"add_meas_network results written to {results_file}")

        return results

    @staticmethod
    def get_meas_net(slice_obj, meas_network_name=None):
        """
        Returns {node_name: assign_static_fabnet6_ip() result} for every
        node in the slice that already has a FABNetv6 meas NIC wired up
        (via add_meas_node()/add_meas_network()) -- a read-only query,
        unlike add_meas_network() which only reports on nodes it just
        wired up. Nodes without one (e.g. the meas node doesn't exist in
        this slice, or a node just hasn't been wired yet) are silently
        skipped rather than raising.
        """
        meas_network_name = meas_network_name or MFPortal.MEAS_NETWORK_NAME

        results = {}
        for node in slice_obj.get_nodes():
            site_network_name = MFPortal.meas_fabnet_name(meas_network_name, node.get_site())
            if node.get_interface(network_name=site_network_name) is None:
                print(f"{node.get_name()}: no FABNetv6 NIC on {site_network_name} — skipping.")
                continue

            results[node.get_name()] = MFPortal.assign_static_fabnet6_ip(
                slice_obj, node, meas_network_name=meas_network_name
            )

        return results

    @staticmethod
    def collect_slice_register_info(slice_obj, meas_network_name=None):
        """
        Gathers slice-level registration info without assuming a dedicated
        meas node exists -- unlike collect_register_meas_node_args(), this
        never looks up any specific node by name, so there's no meas-node
        lookup to fail. Per-node FABNetv6 info comes from get_meas_net(),
        which already skips any node without a wired-up NIC instead of
        raising.

        Returns a dict: slice_name, slice_id, lease_start, lease_end,
        meas_net (get_meas_net()'s {node_name: assign_static_fabnet6_ip()
        result} dict).
        """
        meas_network_name = meas_network_name or MFPortal.MEAS_NETWORK_NAME

        return {
            "slice_name": slice_obj.get_name(),
            "slice_id": slice_obj.get_slice_id(),
            "lease_start": slice_obj.get_lease_start(),
            "lease_end": slice_obj.get_lease_end(),
            "meas_net": MFPortal.get_meas_net(slice_obj, meas_network_name=meas_network_name),
        }

    @staticmethod
    def minimal_register_data(slice_obj, mfuser_private_key, mfuser_public_key):
        """
        Returns a minimal JSON-serializable dict for registration: the
        current user's FABRIC id_token, this slice's UUID, and the mfuser
        key pair. Unlike collect_register_meas_node_args()/
        collect_slice_register_info(), this doesn't touch any node or
        network at all -- just slice_obj itself and the keys the caller
        already has from setup_mfuser_account()/setup_mfuser_accounts().
        """
        id_token = slice_obj.get_fablib_manager().get_manager().get_id_token()

        return {
            "id_token": id_token,
            "slice_uuid": slice_obj.get_slice_id(),
            "mfuser_private_key": mfuser_private_key,
            "mfuser_public_key": mfuser_public_key,
        }

    @staticmethod
    def minimal_portal_register(data, portal_url):
        """
        POSTs `data` (e.g. from minimal_register_data()) to `portal_url` as
        the JSON body. `portal_url` is used exactly as given -- no path is
        appended, unlike register_meas_node()'s fixed /api/meas-node/
        register suffix -- so callers point this at whatever the portal's
        actual minimal-registration endpoint turns out to be.

        Returns the portal's parsed JSON response, or {'error': str(exc)}
        if the request failed.
        """
        print(f"Registering with portal at {portal_url} ...")
        try:
            resp = _req.post(portal_url, json=data, timeout=30)
            resp.raise_for_status()
            response = resp.json()
            print(f"Status   : {response.get('status')}")
            print(json.dumps(response, indent=2))
            return response
        except Exception as exc:
            print(f"Registration failed: {exc}")
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Cell 7 — Persistent FABNetv6 Routing
    # ------------------------------------------------------------------
    @staticmethod
    def install_persistent_fabnetv6_routing(node, node_ipv6, meas_net_subnet, gw_v6, dev, rt_v6=None):
        """
        Installs policy routing table `rt_v6` so replies from node_ipv6 exit
        via the FABNetv6 gateway rather than the management default. Writes
        a generated script + systemd one-shot unit so it survives reboots.
        """
        rt_v6 = rt_v6 or MFPortal.RT_V6

        routing_script = "\n".join([
            "#!/usr/bin/env bash",
            "# /etc/mflib/fabnetv6_routing.sh — MFLib meas-node FABNetv6 policy routing",
            "# Generated by MFPortal.install_persistent_fabnetv6_routing — idempotent, safe to re-run.",
            "set -euo pipefail",
            "",
            f'NODE_IPV6="{node_ipv6}"',
            f'SUBNET_V6="{meas_net_subnet}"',
            f'GW_V6="{gw_v6}"',
            f'DEV="{dev}"',
            f"RT_V6={rt_v6}",
            "",
            "ip -6 route flush table $RT_V6 2>/dev/null || true",
            "ip -6 route add $SUBNET_V6 dev $DEV scope link table $RT_V6",
            "ip -6 route add default via $GW_V6 dev $DEV table $RT_V6",
            'ip -6 rule show | grep -qF "from $NODE_IPV6 lookup $RT_V6" || \\',
            "    ip -6 rule add from $NODE_IPV6 table $RT_V6 priority 300",
            'echo "[mflib] FABNetv6 routing table $RT_V6 applied"',
        ]) + "\n"

        routing_unit = "\n".join([
            "[Unit]",
            f"Description=MFLib meas-node FABNetv6 policy routing (table {rt_v6})",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            "ExecStart=/etc/mflib/fabnetv6_routing.sh",
            "RemainAfterExit=yes",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
        ]) + "\n"

        with open("/tmp/fabnetv6_routing.sh", "w") as f:
            f.write(routing_script)
        with open("/tmp/mflib-fabnetv6.service", "w") as f:
            f.write(routing_unit)

        node.upload_file("/tmp/fabnetv6_routing.sh", "/tmp/fabnetv6_routing.sh")
        node.upload_file("/tmp/mflib-fabnetv6.service", "/tmp/mflib-fabnetv6.service")

        stdout, _ = node.execute(
            "sudo mkdir -p /etc/mflib && "
            "sudo cp /tmp/fabnetv6_routing.sh /etc/mflib/fabnetv6_routing.sh && "
            "sudo chmod +x /etc/mflib/fabnetv6_routing.sh && "
            "sudo cp /tmp/mflib-fabnetv6.service /etc/systemd/system/mflib-fabnetv6.service && "
            "sudo systemctl daemon-reload && "
            "sudo systemctl enable mflib-fabnetv6.service && "
            "sudo /etc/mflib/fabnetv6_routing.sh"
        )
        print(stdout)
        return stdout

    # ------------------------------------------------------------------
    # Cell 8 — mfuser Account Setup (single node, paramiko key generation)
    #
    # Distinct from MFLib.init()'s multi-node mfuser bootstrap (which uses
    # the `cryptography` package) and from MFPortal.bootstrap_mfusers() —
    # this is the notebook's simpler single-node variant for a standalone
    # meas node that isn't part of an experimenter's slice.
    # ------------------------------------------------------------------
    @staticmethod
    def setup_mfuser_account(node, slice_name, key_path=None, pub_path=None):
        """
        Creates (or loads) an mfuser SSH key pair and creates the mfuser
        account on `node` with that key authorized.

        In addition to authorizing the public key, both the private and
        public key are saved into mfuser's own ~/.ssh as mfuser_private_key
        / mfuser_public_key — the hosts.ini this class generates
        (see build_meas_node_hosts_ini()) points
        ansible_ssh_private_key_file at exactly that path, so ansible needs
        the private key sitting there, not just the public key authorized.

        Returns (mfuser_private_key, mfuser_public_key) as strings.
        """
        if key_path and pub_path:
            print(f"Loading mfuser keys from {key_path}")
            with open(key_path) as f:
                mfuser_private_key = f.read()
            with open(pub_path) as f:
                mfuser_public_key = f.read().strip()
            local_priv_path, local_pub_path = key_path, pub_path
        else:
            save_prefix = f"{slice_name}_mfuser"
            key = paramiko.RSAKey.generate(2048)
            buf = io.StringIO()
            key.write_private_key(buf)
            mfuser_private_key = buf.getvalue()
            mfuser_public_key = f"ssh-rsa {key.get_base64()} mfuser"
            local_priv_path = f"{save_prefix}.key"
            local_pub_path = f"{save_prefix}.pub"
            with open(local_priv_path, "w") as f:
                f.write(mfuser_private_key)
            with open(local_pub_path, "w") as f:
                f.write(mfuser_public_key + "\n")
            print(f"Keys saved: {local_priv_path}  /  {local_pub_path}")

        cmd = " && ".join([
            "sudo useradd -s /bin/bash -G root -m mfuser || true",
            "sudo mkdir -p /home/mfuser/.ssh",
            "sudo chmod 700 /home/mfuser/.ssh",
            "echo 'mfuser ALL=(ALL:ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/mfuser",
            f"echo '{mfuser_public_key}' | sudo tee /home/mfuser/.ssh/authorized_keys",
            "sudo chmod 644 /home/mfuser/.ssh/authorized_keys",
            "sudo chown -R mfuser:mfuser /home/mfuser/.ssh",
        ])
        stdout, stderr = node.execute(cmd)
        print("mfuser account ready.")
        if stderr:
            print("stderr:", stderr[:200])

        # Save both keys into mfuser's own ~/.ssh too (not just the
        # authorized_keys entry above) -- uploaded rather than echo'd since
        # the private key is multi-line PEM text.
        node.upload_file(local_priv_path, "/tmp/mfuser_private_key")
        node.upload_file(local_pub_path, "/tmp/mfuser_public_key")
        key_cmd = " && ".join([
            "sudo mv /tmp/mfuser_private_key /home/mfuser/.ssh/mfuser_private_key",
            "sudo mv /tmp/mfuser_public_key /home/mfuser/.ssh/mfuser_public_key",
            "sudo chmod 600 /home/mfuser/.ssh/mfuser_private_key",
            "sudo chmod 644 /home/mfuser/.ssh/mfuser_public_key",
            "sudo chown mfuser:mfuser /home/mfuser/.ssh/mfuser_private_key /home/mfuser/.ssh/mfuser_public_key",
        ])
        _, stderr = node.execute(key_cmd)
        if stderr:
            print("stderr:", stderr[:200])

        return mfuser_private_key, mfuser_public_key

    @staticmethod
    def setup_mfuser_accounts(slice_obj, slice_name=None):
        """
        Calls setup_mfuser_account() for every node in the slice. The key
        pair is generated once, on the first node; every other node reuses
        that same key pair (via the key files setup_mfuser_account() saves
        for the first node) instead of generating its own, so all nodes end
        up trusting the same mfuser key.

        Returns (mfuser_private_key, mfuser_public_key) as strings — the
        keys returned by the first call, shared by every node.
        """
        slice_name = slice_name or slice_obj.get_name()
        nodes = slice_obj.get_nodes()
        if not nodes:
            print("No nodes found in slice.")
            return None, None

        first_node, *remaining_nodes = nodes

        print(f"Setting up mfuser account on {first_node.get_name()} (generating key pair)...")
        mfuser_private_key, mfuser_public_key = MFPortal.setup_mfuser_account(
            first_node, slice_name
        )

        key_path = f"{slice_name}_mfuser.key"
        pub_path = f"{slice_name}_mfuser.pub"

        for node in remaining_nodes:
            print(f"Setting up mfuser account on {node.get_name()} (reusing key pair)...")
            MFPortal.setup_mfuser_account(
                node, slice_name, key_path=key_path, pub_path=pub_path
            )

        return mfuser_private_key, mfuser_public_key

    # ------------------------------------------------------------------
    # Cell 9 — Deploy FastAPI Info/Registration Server
    # ------------------------------------------------------------------
    @staticmethod
    def deploy_info_server(node, node_ipv6, server_dir=None):
        """
        Uploads the FastAPI server from `server_dir` (defaults to
        <repo_root>/meas-node-server) to /etc/mflib/server/ on the node,
        installs pip dependencies, and starts the systemd service.
        """
        server_dir = Path(server_dir) if server_dir else Path("meas-node-server")

        if not server_dir.exists():
            raise FileNotFoundError(
                f"Server source not found at {server_dir.resolve()}. "
                "Pass server_dir explicitly."
            )
        print(f"Server source: {server_dir.resolve()}")

        node.execute("sudo mkdir -p /etc/mflib/server/routers")
        node.execute("sudo chown -R mfuser:mfuser /etc/mflib/server")

        top_level_files = ["main.py", "schemas.py", "storage.py", "requirements.txt"]
        for fname in top_level_files:
            src = server_dir / fname
            node.upload_file(str(src), f"/tmp/mfserver_{fname}")
            node.execute(f"sudo cp /tmp/mfserver_{fname} /etc/mflib/server/{fname}")
            print(f"  uploaded {fname}")

        router_files = ["__init__.py", "info.py", "register.py", "mflib_ops.py"]
        for fname in router_files:
            src = server_dir / "routers" / fname
            if not src.exists():
                print(f"  skipping routers/{fname} (not found)")
                continue
            node.upload_file(str(src), f"/tmp/mfrouter_{fname}")
            node.execute(f"sudo cp /tmp/mfrouter_{fname} /etc/mflib/server/routers/{fname}")
            print(f"  uploaded routers/{fname}")

        print("\nInstalling pip dependencies...")
        stdout, stderr = node.execute(
            "sudo pip3 install -q -r /etc/mflib/server/requirements.txt"
        )
        if stdout:
            print(stdout)
        if stderr and "WARNING" not in stderr:
            print("pip stderr:", stderr[:400])

        node.upload_file(
            str(server_dir / "mflib-info-server.service"),
            "/tmp/mflib-info-server.service",
        )
        stdout, _ = node.execute(
            "sudo cp /tmp/mflib-info-server.service /etc/systemd/system/mflib-info-server.service && "
            "sudo systemctl daemon-reload && "
            "sudo systemctl enable mflib-info-server.service && "
            "sudo systemctl restart mflib-info-server.service"
        )
        print(stdout)

        time.sleep(3)
        stdout, _ = node.execute(
            "sudo systemctl is-active mflib-info-server.service && "
            'curl -sf http://[::1]:5000/status || echo "WARNING: /status not yet responding"'
        )
        print(stdout)
        print(f"\nFastAPI server started — http://[{node_ipv6}]:5000/status")
        return stdout

    # ------------------------------------------------------------------
    # Cell 10 — Write Slice Info File
    # ------------------------------------------------------------------
    @staticmethod
    def write_json_to_node(node, data, remote_path):
        """Write data as JSON to remote_path using a base64 pipe (avoids quoting issues)."""
        encoded = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
        stdout, stderr = node.execute(
            f"echo {encoded} | base64 -d | sudo tee {remote_path} > /dev/null"
        )
        return stdout, stderr

    @staticmethod
    def collect_write_slice_info_args(slice_obj, meas_node_name=None, meas_network_name=None):
        """
        Gathers the node/node_mgmt_ip/node_ipv6/meas_net_subnet/gw_v6
        arguments write_slice_info() needs, via collect_node_info() and
        assign_static_fabnet6_ip(), so callers don't have to wire those two
        cells together by hand.

        Returns a dict with keys node, node_mgmt_ip, node_ipv6,
        meas_net_subnet, gw_v6 -- pass it straight through:
            args = MFPortal.collect_write_slice_info_args(slice_obj)
            MFPortal.write_slice_info(slice_obj, **args)
        """
        node_info = MFPortal.collect_node_info(slice_obj, meas_node_name=meas_node_name)
        node = node_info["node"]

        ip_info = MFPortal.assign_static_fabnet6_ip(
            slice_obj, node, meas_network_name=meas_network_name
        )

        return {
            "node": node,
            "node_mgmt_ip": node_info["node_mgmt_ip"],
            "node_ipv6": ip_info["node_ipv6"],
            "meas_net_subnet": ip_info["meas_net_subnet"],
            "gw_v6": ip_info["gw_v6"],
        }

    @staticmethod
    def write_slice_info(
        slice_obj,
        node,
        node_mgmt_ip,
        node_ipv6,
        meas_net_subnet,
        gw_v6,
        portal_registration=None,
        remote_path="/etc/mflib/portal_registration.json",
    ):
        """
        Builds the local_info dict the notebook writes unconditionally after
        slice setup (so the info server always has something to serve, even
        before/without portal registration) and writes it to `node`.

        Returns the local_info dict that was written.
        """
        local_info = {
            "written_at": datetime.now(timezone.utc).isoformat(),
            "slice_id": slice_obj.get_slice_id(),
            "slice_name": slice_obj.get_name(),
            "node_mgmt_ip": node_mgmt_ip,
            "node_ipv6": node_ipv6,
            "meas_net_subnet": meas_net_subnet,
            "meas_net_gateway": gw_v6,
            "lease_start": str(slice_obj.get_lease_start()),
            "lease_end": str(slice_obj.get_lease_end()),
            "portal_registration": portal_registration,
        }
        print(local_info)
        MFPortal.write_json_to_node(node, local_info, remote_path)
        print(f"Slice info written to {remote_path}")
        return local_info


    @staticmethod
    def setup_initial_slice_json(slice_obj, meas_node_name=MEAS_NODE_NAME, meas_network_name=MEAS_NETWORK_NAME):
        """
        One-call convenience wrapper for writing the initial
        /etc/mflib/portal_registration.json right after slice setup, before
        portal registration has happened (portal_registration is left None
        -- register_meas_node() plus a second write_slice_info() call fill
        that in later).

        Gathers write_slice_info()'s arguments via
        collect_write_slice_info_args() so the only required argument here
        is slice_obj. Returns the local_info dict that was written.
        """
        args = MFPortal.collect_write_slice_info_args(
            slice_obj, meas_node_name=meas_node_name, meas_network_name=meas_network_name
        )
        return MFPortal.write_slice_info(slice_obj, **args)

    # ------------------------------------------------------------------
    # Cell 11 — Test Portal Connectivity
    #
    # Identical to first-draft-mfportal.py's check_portal_reachable — no
    # behavior change, just carried over so this file stands alone.
    # ------------------------------------------------------------------
    @staticmethod
    def check_portal_reachable(portal_public_url):
        if not portal_public_url:
            print("PORTAL_PUBLIC_URL is not set.")
            return None

        portal_url = portal_public_url.rstrip("/")
        health_url = f"{portal_url}/api/meas-node/portal-info"
        print(f"Checking portal at {health_url} ...")
        try:
            r = _req.get(health_url, timeout=10)
            r.raise_for_status()
            info = r.json()
            print("Portal reachable.")
            print(f"  FABNetv6 IP      : {info.get('fabnetv6_ip')}")
            print(f"  FABNetv6 subnet  : {info.get('fabnetv6_subnet')}")
            print(f"  FABNetv6 gateway : {info.get('fabnetv6_gateway')}")
            return info
        except Exception as exc:
            raise RuntimeError(f"Portal unreachable at {health_url}: {exc}") from None

    # ------------------------------------------------------------------
    # Cell 12 — Register with Portal
    #
    # This is a working replacement for first-draft-mfportal.py's
    # register_meas_node_to_portal(), which references undefined names
    # (subnet_v6, gw_v6, fabetv6_gateway_str, mfuser_public_key, local_info,
    # _write_json_to_node) and would raise NameError if called. This version
    # takes everything it needs as explicit arguments instead of relying on
    # notebook-global state.
    # ------------------------------------------------------------------
    @staticmethod
    def collect_register_meas_node_args(
        slice_obj,
        mfuser_public_key,
        meas_node_name=None,
        meas_network_name=None,
        portal_url=None,
    ):
        """
        Gathers the slice_id/slice_name/node_ipv6/meas_net_subnet/gw_v6/
        node_mgmt_ip/lease_start/lease_end arguments register_meas_node()
        needs, via collect_node_info() and assign_static_fabnet6_ip() --
        the same pattern collect_write_slice_info_args() uses for
        write_slice_info(). mfuser_public_key and portal_url aren't part of
        the slice itself, so the caller still has to supply those (the key
        comes from setup_mfuser_account()/setup_mfuser_accounts()).

        Works even if there's no meas node in this slice (or it hasn't been
        wired onto the FABNetv6 network yet) -- slice_id/slice_name/
        lease_start/lease_end are always populated; node_ipv6/
        meas_net_subnet/gw_v6/node_mgmt_ip are left None instead of raising
        if the meas node can't be found or has no FABNetv6 NIC, so callers
        can still get a (partial) dict back rather than an exception.

        Returns a dict ready to pass straight through:
            args = MFPortal.collect_register_meas_node_args(
                slice_obj, mfuser_public_key, portal_url=portal_url
            )
            MFPortal.register_meas_node(**args)
        """
        node_ipv6 = meas_net_subnet = gw_v6 = node_mgmt_ip = None

        try:
            node_info = MFPortal.collect_node_info(slice_obj, meas_node_name=meas_node_name)
            node = node_info["node"]
            node_mgmt_ip = node_info["node_mgmt_ip"]

            ip_info = MFPortal.assign_static_fabnet6_ip(
                slice_obj, node, meas_network_name=meas_network_name
            )
            node_ipv6 = ip_info["node_ipv6"]
            meas_net_subnet = ip_info["meas_net_subnet"]
            gw_v6 = ip_info["gw_v6"]
        except Exception as e:
            print(f"No meas node FABNetv6 info available ({e}); registering without it.")

        return {
            "slice_id": slice_obj.get_slice_id(),
            "slice_name": slice_obj.get_name(),
            "node_ipv6": node_ipv6,
            "meas_net_subnet": meas_net_subnet,
            "gw_v6": gw_v6,
            "mfuser_public_key": mfuser_public_key,
            "node_mgmt_ip": node_mgmt_ip,
            "lease_start": slice_obj.get_lease_start(),
            "lease_end": slice_obj.get_lease_end(),
            "portal_url": portal_url,
        }

    @staticmethod
    def register_meas_node(
        slice_id,
        slice_name,
        node_ipv6,
        meas_net_subnet,
        gw_v6,
        mfuser_public_key,
        node_mgmt_ip,
        lease_start,
        lease_end,
        portal_url,
    ):
        """
        Calls POST /api/meas-node/register on the portal. Returns a
        portal_registration dict (with 'response' holding either the
        portal's JSON reply or an {'error': ...} on failure), or None if
        portal_url is falsy.
        """
        if not portal_url:
            print("PORTAL_PUBLIC_URL is not set — skipping registration.")
            return None

        portal_url = portal_url.rstrip("/")
        reg_url = f"{portal_url}/api/meas-node/register"

        reg_payload = {
            "slice_uuid": slice_id,
            "slice_name": slice_name,
            "fabnetv6_ip": node_ipv6,
            "fabnetv6_subnet": meas_net_subnet,
            "fabnetv6_gateway": gw_v6,
            "mfuser_public_key": mfuser_public_key,
            "node_mgmt_ip": node_mgmt_ip,
            "slice_created_at": str(lease_start),
            "slice_expires_at": str(lease_end),
        }

        print(f"Registering with portal at {reg_url} ...")
        try:
            resp = _req.post(reg_url, json=reg_payload, timeout=30)
            resp.raise_for_status()
            reg_response = resp.json()
            print(f"Status   : {reg_response.get('status')}")
            print(json.dumps(reg_response, indent=2))
        except Exception as exc:
            print(f"Registration failed: {exc}")
            reg_response = {"error": str(exc)}

        return {
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "portal_url": portal_url,
            "request": reg_payload,
            "response": reg_response,
        }

    # ------------------------------------------------------------------
    # Ansible hosts.ini — meas node only
    #
    # MFLib._make_hosts_ini_file() builds a hosts.ini covering the meas
    # node plus every experiment node in the slice. When there's no
    # experiment slice at all — just a standalone meas node bootstrapping
    # itself — the ansible playbooks (bootstrap_playbooks.py, etc.) still
    # need *some* hosts.ini at /home/mfuser/services/common/hosts.ini to
    # use as their inventory. These two methods build that meas-node-only
    # version: build_meas_node_hosts_ini() is the pure text builder (no
    # fablib dependency), and its logic is also inlined directly into the
    # meas_node_self_start() script below so the node can generate its own
    # hosts.ini locally, before running bootstrap_playbooks.py.
    # ------------------------------------------------------------------
    @staticmethod
    def build_meas_node_hosts_ini(meas_node_name, ansible_host, management_ip_type=None, ansible_connection=None):
        """
        Returns ansible hosts.ini text containing only the meas node —
        an empty Experiment_Nodes group, so playbooks/roles that expect
        both groups to exist still work.

        ansible_connection: pass "local" when this will run on the meas
        node against itself (e.g. from meas_node_self_start(), before
        mfuser's SSH keys necessarily exist yet). Leave None for the
        normal SSH-based entry a client would use.
        """
        host_fields = [
            meas_node_name,
            f"ansible_host={ansible_host}",
            f"hostname={ansible_host}",
            "ansible_ssh_user=mfuser",
            f"node_exporter_listen_ip={ansible_host}",
        ]
        if ansible_connection:
            host_fields.append(f"ansible_connection={ansible_connection}")
        host_fields.append("ansible_ssh_common_args='-o StrictHostKeyChecking=no'")
        if management_ip_type:
            host_fields.append(f'management_ip_type="{management_ip_type}"')

        return "\n".join([
            "[all:vars]",
            "ansible_ssh_private_key_file=/home/mfuser/.ssh/mfuser_private_key",
            "",
            "[Meas_Node]",
            " ".join(host_fields),
            "",
            "[Experiment_Nodes]",
            "",
            "[elk:children]",
            "Meas_Node",
            "",
            "[workers:children]",
            "Experiment_Nodes",
        ]) + "\n"

    @staticmethod
    def create_meas_node_hosts_ini(node, meas_node_name=None, remote_path="/home/mfuser/services/common/hosts.ini"):
        """
        Builds a meas-node-only hosts.ini (see build_meas_node_hosts_ini)
        and installs it on `node` at remote_path. Client-side counterpart
        to the inline version meas_node_self_start() generates for itself.
        """
        meas_node_name = meas_node_name or MFPortal.MEAS_NODE_NAME
        ip_addr = node.get_management_ip()
        management_ip_type = node.validIPAddress(ip_addr) if ip_addr else None

        hosts_ini = MFPortal.build_meas_node_hosts_ini(
            meas_node_name, ip_addr, management_ip_type=management_ip_type
        )

        with open("/tmp/hosts.ini", "w") as f:
            f.write(hosts_ini)
        node.upload_file("/tmp/hosts.ini", "/tmp/hosts.ini")

        stdout, stderr = node.execute(
            "sudo mkdir -p /home/mfuser/services/common && "
            f"sudo mv /tmp/hosts.ini {remote_path} && "
            "sudo chown -R mfuser:mfuser /home/mfuser/services"
        )
        if stdout:
            print(f"STDOUT: {stdout}")
        if stderr:
            print(f"STDERR: {stderr}")
        return hosts_ini

    # ------------------------------------------------------------------
    # Cell 13 — Install MeasurementFramework
    # ------------------------------------------------------------------
    @staticmethod
    def clone_measurement_framework_repo(node, mf_repo_branch="main"):
        # TODO change to downloading a release tarball instead of cloning the repo
        cmd = (
            f"sudo -u mfuser git clone -q -b {mf_repo_branch} "
            f"https://github.com/fabric-testbed/MeasurementFramework.git /home/mfuser/mf_git"
        )
        stdout, stderr = node.execute(cmd, quiet=True)

        if stdout:
            print(f"STDOUT: {stdout}")
        if stderr:
            if "already exists and is not an empty directory" not in stderr:
                print("Clone Directory already exist. Cloning Measurement Framework Repository from github.com Failed.")
            else:
                print(f"STDERR: {stderr}")
        return stdout, stderr

    @staticmethod
    def run_bootstrap_script(node):
        print("Starting Bootstrap Process on Measure Node (bash script)...")
        cmd = "sudo -u mfuser /home/mfuser/mf_git/instrumentize/experiment_bootstrap/bootstrap.sh"
        stdout, stderr = node.execute(cmd, quiet=True)
        print("Bootstrap Process on Measure Node (bash script) done.")

        if stdout:
            print(f"STDOUT: {stdout}")
        if stderr:
            print(f"STDERR: {stderr}")
        return stdout, stderr

    @staticmethod
    def run_bootstrap_ansible(node):
        print("Starting Bootstrap Process on Measure Node (Ansible Playbook)...")
        cmd = (
            "sudo cp /home/mfuser/mf_git/instrumentize/experiment_bootstrap/ansible.cfg /home/mfuser/services/common/ansible.cfg;"
            "sudo chown mfuser:mfuser /home/mfuser/services/common/ansible.cfg;"
            "sudo -u mfuser python3 /home/mfuser/mf_git/instrumentize/experiment_bootstrap/bootstrap_playbooks.py;"
        )
        stdout, stderr = node.execute(cmd, quiet=True)
        print("Bootstrap Process on Measure Node (Ansible Playbook) done.")

        if stdout:
            try:
                print(f"STDOUT: {json.dumps(stdout, indent=2)}")
            except ValueError:
                print(f"STDOUT: {stdout}")
            if "Bootstrap playbook install failed" in stdout:
                print("Bootstrap ansible scripts Failed. See logs for details")
        if stderr:
            print(f"STDERR: {stderr}")

        print("Bootstrap ansible scripts done")
        return stdout, stderr

    @staticmethod
    def clone_mflib_and_install_node_server(node, mflib_repo_branch="node"):
        cmd = (
            f"sudo -u mfuser git clone -q -b {mflib_repo_branch} "
            f"https://github.com/fabric-testbed/mflib.git /home/mfuser/mflib;"
            f"cd /home/mfuser/mflib;"
            f"sudo -u mfuser pip install -e mflib-node;"
        )
        stdout, stderr = node.execute(cmd, quiet=True)

        if stdout:
            print(f"STDOUT: {stdout}")
        if stderr:
            if "already exists and is not an empty directory" not in stderr:
                print("Clone Directory already exist. Cloning MFLIB Repository from github.com Failed.")
            else:
                print(f"STDERR: {stderr}")
        return stdout, stderr

    # ------------------------------------------------------------------
    # Meas node self-start
    #
    # The methods above (clone_measurement_framework_repo,
    # run_bootstrap_script, run_bootstrap_ansible, etc.) run their setup
    # commands over SSH from the client, once, when the client calls them.
    # This installs the equivalent clone + bootstrap.sh + ansible
    # bootstrap.yml sequence as a systemd oneshot service that runs locally
    # on the node itself — so the node can self-start its own setup, e.g.
    # on first boot, without a client driving it interactively.
    # ------------------------------------------------------------------
    @staticmethod
    def meas_node_self_start(node, mf_repo_branch="main"):
        """
        Installs a systemd oneshot service on `node` that runs a small
        Python script to clone the MeasurementFramework repo, create the
        mfuser services directory, then run bootstrap.sh (installs ansible
        and stages all user_services) and the ansible bootstrap.yml
        playbook (docker/PTP/node-exporter etc.) — the local-node
        equivalent of calling clone_measurement_framework_repo(),
        run_bootstrap_script(), and run_bootstrap_ansible() from the mflib
        client side.

        The service starts immediately and also runs on every future boot
        (safe to re-run: git clone / mkdir / bootstrap.sh / the ansible
        playbook are all idempotent here).
        """
        meas_node_name = MFPortal.MEAS_NODE_NAME

        self_start_script = "\n".join([
            "#!/usr/bin/env python3",
            '"""MFLib meas-node self-start — generated by MFPortal.meas_node_self_start."""',
            "import json",
            "import os",
            "import subprocess",
            "from datetime import datetime, timezone",
            "",
            f'MF_REPO_BRANCH = "{mf_repo_branch}"',
            'MF_REPO_URL = "https://github.com/fabric-testbed/MeasurementFramework.git"',
            'MF_REPO_DIR = "/home/mfuser/mf_git"',
            'SERVICES_DIR = "/home/mfuser/services/common"',
            'SERVICES_BASE_DIR = "/home/mfuser/services"',
            'HOSTS_INI_PATH = SERVICES_DIR + "/hosts.ini"',
            'SLICE_INFO_PATH = "/etc/mflib/portal_registration.json"',
            'ACTIONS_LOG_PATH = "/home/mfuser/mflib_self_start_actions.json"',
            f'MEAS_NODE_NAME = "{meas_node_name}"',
            "",
            "ACTIONS = []",
            "",
            "",
            "def record_action(title, success, detail=None):",
            "    # Appends one entry per action to ACTIONS and rewrites",
            "    # ACTIONS_LOG_PATH (owned by mfuser) so the log is current even if",
            "    # a later step in main() fails or the script is interrupted.",
            "    entry = {",
            '        "action": title,',
            '        "result": "success" if success else "failed",',
            '        "completed_at": datetime.now(timezone.utc).isoformat(),',
            "    }",
            "    if detail:",
            '        entry["detail"] = detail',
            "    ACTIONS.append(entry)",
            '    with open(ACTIONS_LOG_PATH, "w") as f:',
            "        json.dump(ACTIONS, f, indent=2)",
            '    subprocess.run(f"chown mfuser:mfuser {ACTIONS_LOG_PATH}", shell=True, check=False)',
            "",
            "",
            "def run(title, cmd):",
            '    print(f"+ {cmd}")',
            "    result = subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)",
            "    if result.stdout:",
            "        print(result.stdout)",
            "    if result.stderr:",
            "        print(result.stderr)",
            "    detail = result.stderr.strip() if result.returncode != 0 else None",
            "    record_action(title, result.returncode == 0, detail)",
            "    return result",
            "",
            "",
            "def discover_ip():",
            "    # Cell 10 / write_slice_info() writes this file with the node's",
            "    # own FABNetv6/mgmt IP. Fall back to loopback if it's not there",
            "    # yet — ansible_connection=local below means the IP is only used",
            "    # for display/templating, not for actually connecting.",
            "    try:",
            "        with open(SLICE_INFO_PATH) as f:",
            "            info = json.load(f)",
            '        return info.get("node_ipv6") or info.get("node_mgmt_ip") or "127.0.0.1"',
            "    except Exception:",
            '        return "127.0.0.1"',
            "",
            "",
            "def write_hosts_ini():",
            "    # A meas-node-only ansible inventory — mirrors",
            "    # MFPortal.build_meas_node_hosts_ini(), inlined here since this",
            "    # script runs standalone on the node, with no mflib/fablib",
            "    # available. bootstrap_playbooks.py needs this file to exist",
            "    # before it runs.",
            "    ip_addr = discover_ip()",
            "    host_line = (",
            '        f"{MEAS_NODE_NAME} ansible_host={ip_addr} hostname={ip_addr} "',
            '        f"ansible_ssh_user=mfuser node_exporter_listen_ip={ip_addr} "',
            '        f"ansible_connection=local"',
            "    )",
            "    hosts_ini = \"\\n\".join([",
            '        "[all:vars]",',
            '        "ansible_ssh_private_key_file=/home/mfuser/.ssh/mfuser_private_key",',
            '        "",',
            '        "[Meas_Node]",',
            "        host_line,",
            '        "",',
            '        "[Experiment_Nodes]",',
            '        "",',
            '        "[elk:children]",',
            '        "Meas_Node",',
            '        "",',
            '        "[workers:children]",',
            '        "Experiment_Nodes",',
            '    ]) + "\\n"',
            "    os.makedirs(SERVICES_DIR, exist_ok=True)",
            "    with open(HOSTS_INI_PATH, \"w\") as f:",
            "        f.write(hosts_ini)",
            "    print(f\"[mflib] wrote {HOSTS_INI_PATH}\")",
            "",
            "",
            "def main():",
            '    run("Clone MeasurementFramework repo", f"sudo -u mfuser git clone -q -b {MF_REPO_BRANCH} {MF_REPO_URL} {MF_REPO_DIR}")',
            '    run("Create services directory", f"sudo mkdir -p {SERVICES_DIR}")',
            '    run("Set ownership of services dir and mf_git", f"sudo chown -R mfuser:mfuser /home/mfuser/services {MF_REPO_DIR}")',
            "    try:",
            "        write_hosts_ini()",
            '        record_action("Write meas-node hosts.ini", True)',
            "    except Exception as e:",
            '        record_action("Write meas-node hosts.ini", False, str(e))',
            '    run("Set ownership of services dir (post hosts.ini)", f"sudo chown -R mfuser:mfuser /home/mfuser/services")',
            '    run("Run bootstrap.sh", f"sudo -u mfuser {MF_REPO_DIR}/instrumentize/experiment_bootstrap/bootstrap.sh")',
            '    run(',
            '        "Run ansible bootstrap.yml playbook",',
            '        f"sudo cp {MF_REPO_DIR}/instrumentize/experiment_bootstrap/ansible.cfg {SERVICES_DIR}/ansible.cfg && "',
            '        f"sudo chown mfuser:mfuser {SERVICES_DIR}/ansible.cfg && "',
            '        f"sudo -u mfuser python3 {MF_REPO_DIR}/instrumentize/experiment_bootstrap/bootstrap_playbooks.py"',
            "    )",
            '    run("Create prometheus service", f"sudo -u mfuser python3 {SERVICES_BASE_DIR}/prometheus/create.py")',
            '    run("Create meas_node_server service", f"sudo -u mfuser python3 {SERVICES_BASE_DIR}/meas_node_server/create.py")',
            '    print("[mflib] self-start complete")',
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
        ]) + "\n"

        self_start_unit = "\n".join([
            "[Unit]",
            "Description=MFLib meas-node self-start (clone MeasurementFramework repo, run bootstrap.sh and ansible bootstrap.yml)",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            "ExecStart=/usr/bin/python3 /etc/mflib/meas_node_self_start.py",
            "RemainAfterExit=yes",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
        ]) + "\n"

        with open("/tmp/meas_node_self_start.py", "w", encoding="utf-8") as f:
            f.write(self_start_script)
        with open("/tmp/mflib-meas-node-self-start.service", "w", encoding="utf-8") as f:
            f.write(self_start_unit)

        node.upload_file("/tmp/meas_node_self_start.py", "/tmp/meas_node_self_start.py")
        node.upload_file("/tmp/mflib-meas-node-self-start.service", "/tmp/mflib-meas-node-self-start.service")

        stdout, _ = node.execute(
            "sudo mkdir -p /etc/mflib && "
            "sudo cp /tmp/meas_node_self_start.py /etc/mflib/meas_node_self_start.py && "
            "sudo chmod +x /etc/mflib/meas_node_self_start.py && "
            "sudo cp /tmp/mflib-meas-node-self-start.service /etc/systemd/system/mflib-meas-node-self-start.service && "
            "sudo systemctl daemon-reload && "
            "sudo systemctl enable mflib-meas-node-self-start.service && "
            "sudo systemctl start --no-block mflib-meas-node-self-start.service"
        )
        print(stdout)
        print(
            "Self-start triggered — it runs in the background on the node. "
            "Poll /home/mfuser/mflib_self_start_actions.json (or "
            "`systemctl status mflib-meas-node-self-start.service`) for progress."
        )
        return stdout

    # ------------------------------------------------------------------
    # Cell 14 — Summary
    # ------------------------------------------------------------------
    @staticmethod
    def print_summary(
        slice_name,
        slice_id,
        node_ipv6,
        meas_net_subnet,
        gw_v6,
        node_mgmt_ip,
        node_ssh_cmd,
        mfuser_key_filename,
        portal_registration=None,
        portal_public_url=None,
    ):
        sep = "=" * 62
        print(sep)
        print(f"  Meas Node Ready — {slice_name}")
        print(sep)
        print(f"  Slice ID      : {slice_id}")
        print(f"  FABNetv6 IP   : {node_ipv6}")
        print(f"  Subnet        : {meas_net_subnet}")
        print(f"  Gateway       : {gw_v6}")
        print(f"  Mgmt IP       : {node_mgmt_ip}")
        print(f"  SSH           : {node_ssh_cmd}")
        print(f"  mfuser key    : {mfuser_key_filename}")
        print("-" * 62)
        print(f"  Info server   : http://[{node_ipv6}]:5000/status")
        if portal_registration:
            print("  Portal        : registered")
            print(f"  Portal info   : {portal_public_url}/api/meas-node/{slice_id}/info")
            slug = re.sub(r"[^a-z0-9]+", "-", slice_name.lower()).strip("-") + "-" + slice_id[:5]
            print(f"  Proxy URL     : http://{slug}.<PORTAL_DOMAIN>/status  (set PORTAL_DOMAIN in docker-compose)")
        else:
            print("  Portal        : not registered")
        print(sep)
