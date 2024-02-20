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


import json
import traceback
import os

from fabrictestbed_extensions.fablib.fablib import fablib

# For getting vars to make tunnel
from fabrictestbed_extensions.fablib.fablib import FablibManager

from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend as crypto_default_backend
from os import chmod

import logging

from mflib.core import Core


class MFLib(Core):
    """
    MFLib allows for adding and controlling the MeasurementFramework in a Fabric experiementers slice.
    """

    mflib_class_version = "1.0.40"
    __version__ = mflib_class_version
    __VERSION__ = mflib_class_version

    def set_mflib_logger(self):
        """
        Sets up the mflib logging file. The filename is created from the self.logging_filename.
        Note that the self.logging_filename will be set with the slice when the slice name is set.

        This method uses the logging filename inherited from Core.
        """

        self.mflib_logger = logging.getLogger(__name__)
        self.mflib_logger.propagate = False  # needed?
        self.mflib_logger.setLevel(self.log_level)

        formatter = logging.Formatter(
            "%(asctime)s %(name)-8s %(levelname)-8s %(message)s",
            datefmt="%m/%d/%Y %H:%M:%S %p",
        )

        # Make sure log directory exists
        if not os.path.exists(self.log_directory):
            os.makedirs(self.log_directory)

        # Remove existing log handler if present
        if self.mflib_log_handler:
            self.remove_mflib_log_handler(self.mflib_log_handler)

        file_handler = logging.FileHandler(self.log_filename)
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(formatter)

        # self.mflib_logger.addHandler(file_handler)
        self.add_mflib_log_handler(file_handler)

    def remove_mflib_log_handler(self, log_handler):
        """
        Removes the given log handler from the mflib_logger.

        Args:
            log_handler (logging handler): Log handler to remove from mflib_logger
        """
        if self.mflib_logger:
            self.mflib_logger.removeHandler(log_handler)

    def add_mflib_log_handler(self, log_handler):
        """
        Adds the given log handler to the mflib_logger. Note log handler needs to be created with set_mflib_logger first.

        Args:
            log_handler (logging handler): Log handler to add to the mflib_logger.
        """
        if self.mflib_logger:
            self.mflib_logger.addHandler(log_handler)

    # This is a temporary method needed untill modify slice ability is avaialble.
    @staticmethod
    def addMeasNode(
        slice,
        cores=4,
        ram=16,
        disk=500,
        site="EDC",
        image="docker_ubuntu_20",
    ):
        """
        Adds Measurement node and measurement network to an unsubmitted slice object.

        Args:
            slice (fablib.slice): Slice object already set with experiment topology.
            cores (int, optional): Cores for measurement node. Defaults to 4 cores.
            ram (int, optional): _description_. Defaults to 16 GB ram.
            disk (int, optional): _description_. Defaults to 500 GB disk.
            network_type (string, optional): _description_. Defaults to FABNetv4.
            site (string, optional): _description_. Defaults to NCSA.
        """
        interfaces = {}
        meas_nodename = "meas-node"
        meas_node = None
        meas_interface = None
        meas_net = None
        meas_site = site

        # Create L3 meas net at each site of the slice
        for node in slice.get_nodes():
            this_site = node.get_site()
            if slice.get_l3network(name=f"l3_meas_net_{this_site}") is None:
                slice.add_l3network(name=f"l3_meas_net_{this_site}", type="IPv4")

        # Create L3 meas net at meas node site of the slice
        meas_net = slice.get_l3network(name=f"l3_meas_net_{meas_site}")
        if meas_net is None:
            meas_net = slice.add_l3network(name=f"l3_meas_net_{meas_site}", type="IPv4")

        for node in slice.get_nodes():
            this_site = node.get_site()
            this_nodename = node.get_name()
            this_meas_net_interface = None
            this_meas_net = slice.get_l3network(name=f"l3_meas_net_{this_site}")
            # this_meas_net_interfaces = this_meas_net.get_interfaces()
            # if len(this_meas_net_interfaces) > 0:
            #     for interface in this_meas_net_interfaces:
            #         if node == interface.get_node():
            #             this_meas_net_interface = interface
            #             break

            this_meas_net_interface = this_meas_net.get_interface(
                name=(f"meas_nic_{this_nodename}_{this_site}")
            )
            if this_meas_net_interface is None:
                this_meas_net_interface = node.add_component(
                    model="NIC_Basic",
                    name=(f"meas_nic_{this_nodename}_{this_site}"),
                ).get_interfaces()[0]
                this_meas_net_interface.set_mode("auto")
                this_meas_net.add_interface(this_meas_net_interface)
            node.add_route(
                subnet=meas_net.get_subnet(), next_hop=this_meas_net.get_gateway()
            )

        try:
            meas_node = slice.get_node(name=meas_nodename)
        except Exception as e:
            if "Node not found" in str(e):
                meas_node = slice.add_node(name=meas_nodename, site=meas_site)
                meas_node.set_capacities(cores=cores, ram=ram, disk=disk)
                meas_node.set_image(image)
                meas_interface = meas_node.add_component(
                    model="NIC_Basic",
                    name=(f"meas_nic_{meas_nodename}_{meas_site}"),
                ).get_interfaces()[0]
                meas_interface.set_mode("auto")
                meas_net.add_interface(meas_interface)
            else:
                print(f"Exception: {e}")
                # traceback.print_exc()
        meas_node.add_route(
            subnet=FablibManager.FABNETV4_SUBNET, next_hop=meas_net.get_gateway()
        )

        if len(meas_net.get_interfaces()) == 0:
            meas_interface = meas_node.add_component(
                model="NIC_Basic",
                name=(f"meas_nic_{meas_nodename}_{meas_site}"),
            ).get_interfaces()[0]
            meas_interface.set_mode("auto")
            meas_net.add_interface(meas_interface)

        logging.info(
            f'Added Meas node & network to slice "{slice.get_name()}" topology. Cores: {cores}  RAM: {ram}GB Disk {disk}GB'
        )

    def __init__(
        self,
        slice_name="",
        local_storage_directory="/tmp/mflib",
        mf_repo_branch="main",
        optimize_repos=False,
    ):
        """
        Constructor
        Args:
            slice (fablib.slice): Slice object already set with experiment topology.
            local_storage_directory (str, optional): Directory where local data will be stored. Defaults to "/tmp/mflib".
            mf_repo_branch (str, optional): git branch name to pull MeasurementFranework code from. Defaults to "main".
        """
        super().__init__(
            local_storage_directory=local_storage_directory,
            mf_repo_branch=mf_repo_branch,
        )
        self.mflib_log_handler = None

        if slice_name:
            self.init(slice_name, optimize_repos)

    def init(self, slice_name, optimize_repos):
        """
        Sets up the slice to ensure it can be monitored. Sets up basic software on Measurement Node and experiment nodes.
        Slice must already have a Measurement Node.
        See log file for details of init output.

        Args:
            slice_name (str): The name of the slice to be monitored.
        Returns:
            Bool: False if no Measure Node found or a init process fails. True otherwise.

        """

        print(f'Inititializing slice "{slice_name}" for MeasurementFramework.')

        ########################
        # Get slice
        ########################
        self.slice_name = slice_name

        self.slice = fablib.get_slice(name=slice_name)

        self.set_mflib_logger()

        if optimize_repos:
            msg = f'Optimizing Software Repositories fetch strategies for "{slice_name}"...'
            print(msg)
            self.mflib_logger.info(msg)
            self._optimize_repos()

        self.mflib_logger.info(
            f'Inititializing slice "{slice_name}" for MeasurementFramework.'
        )
        ########################
        # Check for prequisites
        #######################

        # Does Measurement Node exist in topology?
        if not self.meas_node:
            print("Failed to find meas node. Need to addMeasureNode first.")
            self.mflib_logger.warning(
                "Failed to find meas node. Need to addMeasureNode first."
            )
            return False

        print(
            f"Found meas node as {self.meas_node.get_name()} at {self.meas_node.get_management_ip()}"
        )
        self.mflib_logger.info(
            f"Found meas node as {self.meas_node.get_name()} at {self.meas_node.get_management_ip()}"
        )

        bss = self.get_bootstrap_status()
        if "msg" in bss:
            print(f"Bootstrap Download failed {bss['msg']}")
            return False
        if bss:
            # print("Bootstrap status is")
            # print(bss)
            self.mflib_logger.info("Bootstrap status is")
            self.mflib_logger.info(bss)
        else:
            print("Bootstrap status not found. Will now start bootstrap process...")
            self.mflib_logger.info(
                "Bootstrap status not found. Will now start bootstrap process..."
            )

        if "status" in bss and bss["status"] == "ready":
            # Slice already instrumentized and ready to go.
            self.get_mfuser_private_key()
            print("Bootstrap status indicates Slice Measurement Framework is ready.")
            self.mflib_logger.info(
                "Bootstrap status indicates Slice Measurement Framework is ready."
            )
            return
        else:
            ###############################
            # Need to do some bootstrapping
            ###############################

            ######################
            # Create MFUser keys
            #####################
            if "mfuser_keys" in bss and bss["mfuser_keys"] == "ok":
                print("mfuser_keys already generated")
                self.mflib_logger.info("mfuser_keys already generated")
            else:
                # if True:
                print("Generating MFUser Keys...")
                self.mflib_logger.info("Generating MFUser Keys...")
                key = rsa.generate_private_key(
                    backend=crypto_default_backend(),
                    public_exponent=65537,
                    key_size=2048,
                )

                private_key = key.private_bytes(
                    crypto_serialization.Encoding.PEM,
                    crypto_serialization.PrivateFormat.TraditionalOpenSSL,
                    crypto_serialization.NoEncryption(),
                )

                public_key = key.public_key().public_bytes(
                    crypto_serialization.Encoding.OpenSSH,
                    crypto_serialization.PublicFormat.OpenSSH,
                )

                # Decode to printable strings
                private_key_str = private_key.decode("utf-8")
                public_key_str = public_key.decode("utf-8")

                # Save public key & change mode
                public_key_file = open(self.local_mfuser_public_key_filename, "w")
                public_key_file.write(public_key_str)
                public_key_file.write("\n")
                public_key_file.close()
                chmod(self.local_mfuser_public_key_filename, 0o644)

                # Save private key & change mode
                private_key_file = open(self.local_mfuser_private_key_filename, "w")
                private_key_file.write(private_key_str)
                private_key_file.close()
                chmod(self.local_mfuser_private_key_filename, 0o600)

                # Upload mfuser keys to default user dir for future retrieval
                self._upload_mfuser_keys()

                self._update_bootstrap("mfuser_keys", "ok")
                print("MFUser key generation Done.")
                self.mflib_logger.info("MFUser key generation Done.")

            ###############################
            # Add mfusers
            ##############################
            if "mfuser_accounts" in bss and bss["mfuser_accounts"] == "ok":
                print("mfuser accounts are already setup.")
                self.mflib_logger.info("mfuser already setup.")
            else:
                # if True:
                # Install mflib user/environment
                msg = f"Installing mfuser account..."
                self.mflib_logger.info(msg)
                print(msg)
                mfusers_install_success = True

                # Upload keys
                # Ansible.pub is nolonger a good name here
                threads = []
                for node in self.slice.get_nodes():
                    try:
                        threads.append(
                            node.upload_file(
                                self.local_mfuser_public_key_filename, "mfuser.pub"
                            )
                        )

                    except Exception as e:
                        print(f"Failed to upload keys: {e}")
                        self.mflib_logger.exception("Failed to upload keys.")

                        mfusers_install_success = False

                # Add user
                threads = []
                cmd = (
                    f"sudo useradd -s /bin/bash -G root -m mfuser;"
                    f"sudo mkdir /home/mfuser/.ssh;"
                    f"sudo chmod 700 /home/mfuser/.ssh;"
                    f"echo 'mfuser ALL=(ALL:ALL) NOPASSWD: ALL' | sudo tee -a /etc/sudoers.d/90-cloud-init-users;"
                    f"sudo mv mfuser.pub /home/mfuser/.ssh/mfuser.pub;"
                    f"sudo cat /home/mfuser/.ssh/mfuser.pub | sudo tee -a /home/mfuser/.ssh/authorized_keys;"
                    f"sudo chmod 644 /home/mfuser/.ssh/authorized_keys;"
                    f"sudo chown -R mfuser:mfuser /home/mfuser/.ssh;"
                )

                for node in self.slice.get_nodes():
                    try:
                        threads.append(node.execute_thread(cmd))

                    except Exception as e:
                        print(f"Failed to setup mfuser: {e}")
                        self.mflib_logger.exception(f"Failed to setup mfuser user.")
                        mfusers_install_success = False

                for thread in threads:
                    stdout, stderr = thread.result()
                    if stdout:
                        self.core_logger.debug(f"STDOUT useradd mfuser: {stdout}")
                    if stderr:
                        self.core_logger.error(f"STDERR useradd mfuser: {stderr}")

                if not self._copy_mfuser_keys_to_mfuser_on_meas_node():
                    mfusers_install_success = False

                if mfusers_install_success:
                    self._update_bootstrap("mfusers", "ok")
                    msg = f"Installing mfuser account done."
                    print(msg)
                    self.mflib_logger.info(msg)
                else:
                    msg = f"Installing mfuser account failed."
                    print(msg)
                    self.mflib_logger.info(msg)
                    return False

            #######################
            # Clone mf repo
            #######################
            if "repo_cloned" in bss and bss["repo_cloned"] == "ok":
                msg = f"Measurement Framework github repository already cloned."
                print(msg)
                self.mflib_logger.info(msg)
            else:
                # if True:
                if self._clone_mf_repo():
                    self._update_bootstrap("repo_cloned", "ok")
                else:
                    msg = f"Measurement Framework github repository clone Failed."
                    return False

            #######################################
            # Create measurement network interfaces
            # & Get hosts info for hosts.ini
            ######################################
            if "meas_network" in bss and bss["meas_network"] == "ok":
                msg = f"Measurement Network already setup."
                print(msg)
                self.mflib_logger.info(msg)
            else:
                # if True:
                self._make_hosts_ini_file(set_ip=True)
                self._update_bootstrap("meas_network", "ok")

            #######################
            # Set the measurement node
            # in the hosts files
            #######################
            if "hosts_set" in bss and bss["hosts_set"] == "ok":
                msg = f"/etc/host entries already set."
                print(msg)
                self.mflib_logger.info(msg)
            else:
                self._set_all_hosts_file()
                self._update_bootstrap("hosts_set", "ok")

            #######################
            # Run Bootstrap script
            ######################
            if "bootstrap_script" in bss and bss["bootstrap_script"] == "ok":
                print("Bootstrap script already run on measurment node.")
            else:
                # if True:
                print("Bootstrapping measurement node via bash...")
                self.mflib_logger.info("Bootstrapping measurement node via bash...")
                self._run_bootstrap_script()
                self._update_bootstrap("bootstrap_script", "ok")

            if "bootstrap_ansible" in bss and bss["bootstrap_ansible"] == "ok":
                print("Bootstrap ansible script already run on measurement node.")
            else:
                # if True:
                print("Bootstrapping measurement node via ansible...")
                self.mflib_logger.info("Bootstrapping measurement node via ansible...")
                if self._run_bootstrap_ansible():
                    self._update_bootstrap("bootstrap_ansible", "ok")
                else:
                    return False

            self._update_bootstrap("status", "ready")
            print("Inititialization Done.")
            self.mflib_logger.info("Inititialization Done.")
            return True

    def instrumentize(self, services=["prometheus", "elk"]):
        """
        Instrumentize the slice. This is a convenience method that sets up & starts the monitoring of the slice. Sets up Prometheus, ELK & Grafana.

        Args:
            services(List of Strings): Just add the listed components. Options are elk or prometheus.

        Returns:
            dict   : The output from each phase of instrumetizing.
        """
        all_data = {}

        if not services:
            msg = f"Nothing to Instrumentize on FABRIC Slice {self.slice_name}"
            print(msg)
            self.mflib_logger.debug(msg)
            return all_data

        msg = f'Instrumentizing slice "{self.slice_name}"'
        print(msg)

        self.mflib_logger.debug(msg)

        for service in services:
            service = service.strip()
            if "prometheus" == service:
                msg = f"   Setting up Prometheus..."
                print(msg)
                self.mflib_logger.debug(msg)

                prom_data = self.create("prometheus")
                if not prom_data["success"]:
                    print(prom_data)
                self.mflib_logger.debug(prom_data)

                msg = f"   Setting up Prometheus done."
                print(msg)
                self.mflib_logger.debug(msg)

                all_data["prometheues"] = prom_data

                # Install the default grafana dashboards.
                msg = f"   Setting up grafana_manager & dashboards..."
                print(msg)
                self.mflib_logger.info(msg)

                grafana_manager_data = self.create("grafana_manager")
                if not grafana_manager_data["success"]:
                    print(grafana_manager_data)
                self.mflib_logger.debug(grafana_manager_data)

                msg = f"   Setting up grafana_manager & dashboards done."
                print(msg)
                self.mflib_logger.info(msg)
                all_data["grafana_manager"] = grafana_manager_data

            elif service:
                msg = f"   Setting up {service}..."
                print(msg)
                self.mflib_logger.debug(msg)

                service_data = self.create(service)
                if not service_data["success"]:
                    print(service_data)
                self.mflib_logger.debug(service_data)

                msg = f"   Setting up {service} done."
                print(msg)
                self.mflib_logger.debug(msg)
                all_data[service] = service_data

        msg = f"Instrumentize Process Complete."
        print(msg)
        self.mflib_logger.info(msg)

        return all_data

    def _make_hosts_ini_file(self, set_ip=False):
        hosts = []
        mfuser = "mfuser"
        if set_ip:
            msg = f"Configuring Measurement Network..."
            print(msg)
            self.mflib_logger.info(msg)

        meas_node = self.slice.get_node(name=self.measurement_node_name)
        meas_site = meas_node.get_site()
        meas_network = self.slice.get_network(name=f"l3_meas_net_{meas_site}")
        meas_net_subnet = meas_network.get_subnet()
        networks = self.slice.get_networks()

        for network in networks:
            network_name = network.get_name()
            if network_name.startswith("l3_meas_net_"):
                network_site = network.get_site()
                interfaces = network.get_interfaces()
                for interface in interfaces:
                    this_node = interface.get_node()
                    ip_addr = interface.get_ip_addr()
                    if ip_addr in ("", None):
                        # Fablib has failed to configure this node
                        # Force configure
                        this_node.config()
                        ip_addr = interface.get_ip_addr()
                    hosts.append(
                        f"{this_node.get_name()} "
                        f"ansible_host={ip_addr} "
                        f"hostname={ip_addr} "
                        f"ansible_ssh_user={mfuser} "
                        f"node_exporter_listen_ip={ip_addr} "
                        f"ansible_ssh_common_args='-o StrictHostKeyChecking=no' "
                        f'management_ip_type="{this_node.validIPAddress(this_node.get_management_ip())}"'
                    )

        # Prometheus e_Elk
        hosts_txt = f"""
[all:vars]
ansible_ssh_private_key_file=/home/mfuser/.ssh/mfuser_private_key

"""
        # e_hosts_txt = ""
        hosts_tail = f"""

[elk:children]
Meas_Node

[workers:children]
Experiment_Nodes
"""

        experiment_nodes = "[Experiment_Nodes]\n"
        e_experiment_nodes = "[workers]\n"
        for host in hosts:
            if self.measurement_node_name in host:
                hosts_txt += "[Meas_Node]\n"
                hosts_txt += host + "\n\n"
            else:  # It is an experimenters node
                experiment_nodes += host + "\n"

        hosts_txt += experiment_nodes
        hosts_txt += hosts_tail
        hosts_ini = "hosts.ini"

        local_prom_hosts_filename = os.path.join(self.local_slice_directory, hosts_ini)

        with open(local_prom_hosts_filename, "w") as f:
            f.write(hosts_txt)

        remote_dir = "/tmp"
        # Upload the files to the meas node and move to correct locations
        self.meas_node.upload_file(
            local_prom_hosts_filename, f"{remote_dir}/{hosts_ini}"
        )
        msg = f"Measurement Network setup complete."
        print(msg)
        self.mflib_logger.info(msg)

        # create a common version of hosts.ini for all to access
        msg = f"Generating Ansible Inventory for Measurement Framework Deployment..."
        print(msg)
        self.mflib_logger.info(msg)

        stdout, stderr = self.meas_node.execute(
            f"sudo mkdir -p /home/mfuser/services/common;"
            f"sudo mv {remote_dir}/{hosts_ini} /home/mfuser/services/common/hosts.ini;"
            f"sudo chown -R mfuser:mfuser /home/mfuser/services /home/mfuser/mf_git;",
            quiet=True,
        )
        if stderr:
            print(f"STDERR: {stderr}")
            self.mflib_logger.error(f"STDERR: {stderr}")
        self.mflib_logger.debug(f"STDOUT: {stdout}")
        msg = f"Ansible Inventory for Measurement Framework Deployment generated and saved."
        print(msg)
        self.mflib_logger.info(msg)

    def download_common_hosts(self):
        """
        Downloads hosts.ini file and returns file text.
        Downloaded hosts.ini file will be stored locally for future reference.
        """
        try:
            local_file_path = self.common_hosts_file
            remote_file_path = os.path.join("/home/mfuser/services/common/hosts.ini")
            file_attributes = self.meas_node.download_file(
                local_file_path, remote_file_path, retry=1
            )  # , retry=3, retry_interval=10): # note retry is really tries

            with open(local_file_path) as f:
                hosts_text = f.read()
                return local_file_path, hosts_text

        except Exception as e:
            msg = f"downloading common hosts file Failed: {e}"
            print(msg)
            self.mflib_logger.error(msg)
            return "", ""

    def _set_all_hosts_file(self):
        meas_node_meas_net_ip = None
        for interface in self.meas_node.get_interfaces():
            if "meas-node-meas_nic" in interface.get_name():
                meas_node_meas_net_ip = interface.get_ip_addr()
        if meas_node_meas_net_ip:
            execute_threads = {}
            cmd = f'sudo echo -n "{meas_node_meas_net_ip} {self.measurement_node_name}\n" | sudo tee -a /etc/hosts; sudo echo -n "{meas_node_meas_net_ip} _meas_node\n" | sudo tee -a /etc/hosts;'
            for node in self.slice.get_nodes():
                execute_threads[node] = node.execute_thread(cmd)
            for node, thread in execute_threads.items():
                self.mflib_logger.info(
                    f"Waiting for result from node {node.get_name()}"
                )
                stdout, stderr = thread.result()
                if stdout:
                    self.mflib_logger.info(f"STDOUT: {stdout}")
                if stderr:
                    self.mflib_logger.error(f"STDERR: {stderr}")

    def _optimize_repos(self):
        nodes = self.slice.get_nodes()
        for node in nodes:
            IPv6Management = False
            ip_proto_index = "4"
            commands = "sudo ip -6 route del default via `ip -6 route show default|grep fe80|awk '{print $3}'` > /dev/null 2>&1"
            if node.validIPAddress(node.get_management_ip()) == "IPv6":
                IPv6Management = True
                ip_proto_index = "6"
            if [ele for ele in ["rocky", "centos"] if (ele in node.get_image())]:
                commands = (
                    f'sudo echo "max_parallel_downloads=10" |sudo tee -a /etc/dnf/dnf.conf;'
                    f'sudo echo "fastestmirror=True" |sudo tee -a /etc/dnf/dnf.conf;'
                    f'sudo echo "ip_resolve='
                    + ip_proto_index
                    + '" |sudo tee -a /etc/dnf/dnf.conf;'
                )
            elif [ele for ele in ["ubuntu", "debian"] if (ele in node.get_image())]:
                commands = (
                    'sudo echo "Acquire::ForceIPv'
                    + ip_proto_index
                    + ' "true";" | sudo tee -a /etc/apt/apt.conf.d/1000-force-ipv'
                    + ip_proto_index
                    + "-transport"
                )
            if commands:
                stdout, stderr = node.execute(commands, quiet=True)
                self.mflib_logger.info(f"STDOUT: {stdout}")
                if stderr:
                    self.mflib_logger.error(f"STDERR: {stderr}")
