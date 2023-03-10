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

# import string
# import random


import logging

from mflib.core import Core


class MFLib(Core):
    """
    MFLib allows for adding and controlling the MeasurementFramework in a Fabric experiementers slice.

    """

    mflib_class_version = "1.0.30"

    def set_mflib_logger(self):
        """
        Sets up the mflib logging file. Filename is created from the self.logging_filename.
        Note that the self.logging_filename will be set with the slice when the slice name is set.

        This method uses the logging filename inherited from Core.
        """

        self.mflib_logger = logging.getLogger(__name__)
        self.mflib_logger.propagate = False # needed?
        self.mflib_logger.setLevel(self.log_level)
        
        formatter = logging.Formatter('%(asctime)s %(name)-8s %(levelname)-8s %(message)s', datefmt='%m/%d/%Y H:%M:%S %p')

        # Make sure log directory exists
        if not os.path.exists(self.log_directory):
            os.makedirs(self.log_directory)

        # Remove existing log handler if present
        if self.mflib_log_handler:
            self.remove_mflib_log_handler(self.mflib_log_handler)

        file_handler = logging.FileHandler(self.log_filename)
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(formatter)

        #self.mflib_logger.addHandler(file_handler)
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
    def addMeasNode(slice, cores=4, ram=16, disk=500):
        """
        Adds Measurement node and measurement network to unsubmitted slice object.

        Args:
            slice (fablib.slice): Slice object already set with experiment topology.
            cores (int, optional): Cores for measurement node. Defaults to 4 cores.
            ram (int, optional): _description_. Defaults to 16 GB ram.
            disk (int, optional): _description_. Defaults to 500 GB disk.
        """

        interfaces = []
        sites = []
        num = 1
        
        for node in slice.get_nodes():
            interfaces.append(node.add_component(model='NIC_Basic', name=("Meas_Nic"+str(num))).get_interfaces()[0])
            sites.append(node.get_site())
            num += 1
        site = max(set(sites), key = sites.count)
        
        meas = slice.add_node(name="_meas_node", site=site)

        # if not cores: 
        #     cores = meas.default_cores 

        # if not ram: 
        #     ram = meas.default_ram 

        # if not disk: 
        #     disk = 500

        meas.set_capacities(cores=cores, ram=ram, disk=disk)
        meas.set_image("default_ubuntu_20")
        interfaces.append(meas.add_component(model='NIC_Basic', name="Meas_Nic").get_interfaces()[0])
        meas_net = slice.add_l2network(name="_meas_net", interfaces=interfaces)
    
        # This logging will appear in the fablib log.
        logging.info(f'Added Meas node & network to slice "{slice.get_name()}" topography. Cores: {cores}  RAM: {ram}GB Disk {disk}GB')

    def __init__(self, slice_name="",local_storage_directory="/tmp/mflib"):
        """
        Constructor.
        """
        super().__init__(local_storage_directory=local_storage_directory)
        self.mflib_log_handler = None

        if slice_name:
            self.init(slice_name)


    def init(self,slice_name):
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
        
        self.mflib_logger.info(f'Inititializing slice "{slice_name}" for MeasurementFramework.')
        ########################
        # Check for prequisites
        #######################
        
        # Does Measurement Node exist in topology?
        if not self.meas_node:
            print("Failed to find meas node. Need to addMeasureNode first.")
            self.mflib_logger.warning("Failed to find meas node. Need to addMeasureNode first.")
            return False
        
        print(f"Found meas node as {self.meas_node.get_name()} at {self.meas_node.get_management_ip()}")
        self.mflib_logger.info(f"Found meas node as {self.meas_node.get_name()} at {self.meas_node.get_management_ip()}")
        
        bss = self.get_bootstrap_status()
        if bss:
            #print("Bootstrap status is")
            #print(bss)
            self.mflib_logger.info("Bootstrap status is")
            self.mflib_logger.info(bss)
        else:
            print("Bootstrap status not found. Will now start bootstrap process...")
            self.mflib_logger.info("Bootstrap status not found. Will now start bootstrap process...")
        
        if ("status" in bss and bss["status"] == "ready"):
            # Slice already instrumentized and ready to go.
            self.get_mfuser_private_key() 
            print("Bootstrap status indicates Slice Measurement Framework is ready.")
            self.mflib_logger.info("Bootstrap status indicates Slice Measurement Framework is ready.")
            return
        else: 
            
            ###############################
            # Need to do some bootstrapping
            ###############################
 

                
            ######################   
            # Create MFUser keys
            #####################
            if "mfuser_keys" in bss and bss["mfuser_keys"] =="ok":
                print( "mfuser_keys already generated" )
                self.mflib_logger.info( "mfuser_keys already generated" )
            else:
            #if True:
                print ("Generating MFUser Keys...")
                self.mflib_logger.info( "Generating MFUser Keys..." )
                key = rsa.generate_private_key(
                    backend=crypto_default_backend(),
                    public_exponent=65537,
                    key_size=2048
                )

                private_key = key.private_bytes(
                    crypto_serialization.Encoding.PEM,
                    crypto_serialization.PrivateFormat.TraditionalOpenSSL,
                    crypto_serialization.NoEncryption()
                )

                public_key = key.public_key().public_bytes(
                    crypto_serialization.Encoding.OpenSSH,
                    crypto_serialization.PublicFormat.OpenSSH
                )

                # Decode to printable strings
                private_key_str = private_key.decode('utf-8')
                public_key_str = public_key.decode('utf-8')

                # Save public key & change mode
                public_key_file = open(self.local_mfuser_public_key_filename, 'w');
                #public_key_file = open("/tmp/mflib/mfuser.pub", 'w');
                public_key_file.write(public_key_str);
                public_key_file.write('\n');
                public_key_file.close()
                #chmod("/tmp/mflib/mfuser.pub", 0o644);
                chmod(self.local_mfuser_public_key_filename, 0o644);


                # Save private key & change mode
                private_key_file = open(self.local_mfuser_private_key_filename, 'w');
                #private_key_file = open("/tmp/mflib/mfuser", 'w');
                private_key_file.write(private_key_str);
                private_key_file.close()
                #chmod("/tmp/mflib/mfuser", 0o600);
                chmod(self.local_mfuser_private_key_filename, 0o600);

                # Upload mfuser keys to default user dir for future retrieval
                self._upload_mfuser_keys()

                self._update_bootstrap("mfuser_keys", "ok")
                print("MFUser key generation Done.")
                self.mflib_logger.info("MFUser key generation Done.")
            
            
                
            ###############################
            # Add mfusers
            ##############################
            if "mfuser_accounts" in bss and bss["mfuser_accounts"] =="ok":
                print("mfuser accounts are already setup.")
                self.mflib_logger.info("mfuser already setup.")
            else:
            #if True:  
                #Install mflib user/environment
                self.mflib_logger.info("Installing mfuser accounts...")
                print("Installing mfuser accounts...")
                mfusers_install_success = True
   
                #Add user
                threads = []
                for node in self.slice.get_nodes():
                    try:
                        threads.append( node.execute_thread("sudo useradd -G root -m mfuser") )
                    
                    except Exception as e:
                        print(f"Failed to add user: {e}")
                        self.mflib_logger.exception(f"Failed to add mfuser user.")
                        mfusers_install_success = False

                for thread in threads:
                    stdout, stderr = thread.result()
                    if stdout: self.core_logger.debug(f"STDOUT useradd mfuser: {stdout}")
                    if stderr: self.core_logger.error(f"STDERR useradd mfuser: {stderr}")

                #Setup ssh directory
                threads = []
                for node in self.slice.get_nodes():
                    try:
                        threads.append( node.execute_thread("sudo mkdir /home/mfuser/.ssh; sudo chmod 700 /home/mfuser/.ssh; sudo chown -R mfuser:mfuser /home/mfuser/.ssh"))
                        
                    except Exception as e:
                        print(f"Fail to setup ssh directory: {e}")
                        self.mflib_logger.error(f"Fail to setup ssh directory: {e}")
                        mfusers_install_success = False
           
                for thread in threads:
                    stdout, stderr = thread.result()
                    if stdout: self.core_logger.debug(f"STDOUT mkdir ssh: {stdout}")
                    if stderr: self.core_logger.error(f"STDERR mkdir ssh: {stderr}")


                #Add mfuser to sudoers
                threads=[]
                for node in self.slice.get_nodes():
                    try:
                        threads.append( node.execute_thread("echo 'mfuser ALL=(ALL:ALL) NOPASSWD: ALL' | sudo tee -a /etc/sudoers.d/90-cloud-init-users"))
                        
                    except Exception as e:
                        print(f"Fail to add to sudoers: {e}")
                        self.mflib_logger.exception(f"Fail to add to sudoers:")
                        mfusers_install_success = False

                for thread in threads:
                    stdout, stderr = thread.result()
                    if stdout: self.core_logger.debug(f"STDOUT sudoers: {stdout}")
                    if stderr: self.core_logger.error(f"STDERR sudoers: {stderr}")
 

                #Upload keys
                # Ansible.pub is nolonger a good name here
                for node in self.slice.get_nodes():
                    try:
                        threads.append( node.upload_file(self.local_mfuser_public_key_filename ,"mfuser.pub"))
                        
                    except Exception as e:
                        print(f"Failed to upload keys: {e}")
                        self.mflib_logger.exception("Failed to upload keys.")

                        mfusers_install_success = False
                
                #Edit commands
                threads=[]
                for node in self.slice.get_nodes():
                    try:
                        threads.append( node.execute_thread("sudo mv mfuser.pub /home/mfuser/.ssh/mfuser.pub; sudo chown mfuser:mfuser /home/mfuser/.ssh/mfuser.pub;"))
                        
                    except Exception as e:
                        print(f"Fail to set key permissions: {e}")
                        self.mflib_logger.exception("Fail to set key permissions.")
                        mfusers_install_success = False

                self.mflib_logger.info("Moved keys on node.")
                for thread in threads:
                    stdout, stderr = thread.result()
                    if stdout: self.core_logger.debug(f"STDOUT keys moved: {stdout}")
                    if stderr: self.core_logger.error(f"STDERR keys moved: {stderr}")

                #Raise Key
                threads=[]
                for node in self.slice.get_nodes():
                    try:
                        threads.append( node.execute_thread("sudo cat /home/mfuser/.ssh/mfuser.pub | sudo tee -a /home/mfuser/.ssh/authorized_keys;"))
                        
                    except Exception as e:
                        print(f"Failed to create authorized_keys: {e}")
                        self.mflib_logger.exception("Failed to create authorized_keys.")
                        mfusers_install_success = False

                for thread in threads:
                    stdout, stderr = thread.result()
                    if stdout: self.core_logger.debug(f"STDOUT set key permissions: {stdout}")
                    if stderr: self.core_logger.error(f"STDERR set key permissions: {stderr}")


                #Authorize key
                threads=[]
                for node in self.slice.get_nodes():
                    try:
                        threads.append( node.execute_thread("sudo chmod 644 /home/mfuser/.ssh/authorized_keys; sudo chown mfuser:mfuser /home/mfuser/.ssh/authorized_keys"))
                        
                    except Exception as e:
                        print(f"Failed to set authorized_keys permissions: {e}")
                        self.mflib_logger.exception("Failed to set authorized_keys permissions.")
                        mfusers_install_success = False

                for thread in threads:
                    stdout, stderr = thread.result()
                    if stdout: self.core_logger.debug(f"STDOUT authorized keys: {stdout}")
                    if stderr: self.core_logger.error(f"STDERR authorized keys: {stderr}")


                if not self._copy_mfuser_keys_to_mfuser_on_meas_node():
                    mfusers_install_success = False


                if mfusers_install_success:
                    self._update_bootstrap("mfusers", "ok")
                    print("mfuser installations Done.")
                    self.mflib_logger.info("Mfuser installs done.")
                else:
                    print("mfuser installations Failed")
                    self.mflib_logger.error("Mfuser installs Failed.")
                    return False
            


            #######################
            # Set ipv6 to ipv4 DNS 
            #######################
            if "ipv6_4_nat" in bss and (bss["ipv6_4_nat"] == "set" or bss["ipv6_4_nat"] == "not_needed"):
                print("ipv6 to 4 DNS nat already set or is not needed.")
                self.mflib_logger.info("ipv6 to 4 DNS nat already set or is not needed.")
            else:
            #if True:
                nat_set_results = self.set_DNS_all_nodes()
                self.mflib_logger.info(f"ipv6_4_nat: {nat_set_results}")
                self._update_bootstrap("ipv6_4_nat", nat_set_results)

            #######################
            # Set the measurement node
            # in the hosts files 
            #######################
            if "hosts_set" in bss and bss["hosts_set"] == "ok":
                print("Hosts already set.")
                self.mflib_logger.info("Hosts already set.")
            else:
                self._set_all_hosts_file()
                self._update_bootstrap("hosts_set","ok")

            #######################
            # Clone mf repo 
            #######################
            if "repo_cloned" in bss and bss["repo_cloned"] =="ok":
                print("repo already cloned.")
                self.mflib_logger.info("MF repo already cloned")
            else:
            #if True:
                self._clone_mf_repo()
                self._update_bootstrap("repo_cloned", "ok")
                
                
                
            #######################################
            # Create measurement network interfaces  
            # & Get hosts info for hosts.ini
            ######################################
            if "meas_network" in bss and bss["meas_network"] =="ok":
                print("measurement network already setup.")
                self.mflib_logger.info("measurement network already setup.")
            else:
            #if True:
                self._make_hosts_ini_file(set_ip=True)
                self._update_bootstrap("meas_network", "ok")
                
                
            
            #######################
            # Run Bootstrap script
            ######################
            if "bootstrap_script" in bss and bss["bootstrap_script"] =="ok":
                print("Bootstrap script aleady run on measurment node.")
            else:
            #if True:
                print("Bootstrapping measurement node via bash...")
                self.mflib_logger.info("Bootstrapping measurement node via bash...")
                self._run_bootstrap_script()
                self._update_bootstrap("bootstrap_script", "ok")


            if "bootstrap_ansible" in bss and bss["bootstrap_ansible"] =="ok":
                print("Bootstrap ansible script already run on measurement node.")
            else:
            #if True:
                print("Bootstrapping measurement node via ansible...")
                self.mflib_logger.info("Bootstrapping measurement node via ansible...")
                self._run_bootstrap_ansible()
                self._update_bootstrap("bootstrap_ansible", "ok")
            

            self._update_bootstrap("status", "ready")
            print("Inititialization Done.")
            self.mflib_logger.info("Inititialization Done.")
            return True



    def instrumentize(self):
        """
        Instrumentize the slice. This is a convenience method that sets up & starts the monitoring of the slice. Sets up Prometheus, ELK & Grafana.

        Returns:
            dict   : The output from each phase of instrumetizing.
        """
        self.mflib_logger.info(f"Instrumentizing {self.slice_name}")
        self.mflib_logger.info("Setting up Prometheus.")
        print("Setting up Prometheus...")
        prom_data = self.create("prometheus")
        print(prom_data)
        self.mflib_logger.info(prom_data)

        self.mflib_logger.info("Setting up ELK.")
        print("Setting up ELK...")
        elk_data = self.create("elk")
        print(elk_data)
        self.mflib_logger.info(elk_data)

        # Install the default grafana dashboards.
        self.mflib_logger.info("Setting up grafana_manager & dashboards.")
        grafana_manager_data = self.create("grafana_manager")
        self.mflib_logger.info(grafana_manager_data)

        print("Instrumentize Done.")
        self.mflib_logger.info("Instrumetize Done")

        all_data = {}
        all_data["elk"] = elk_data
        all_data["prometheues"] = prom_data 
        all_data["grafana_manager"] = grafana_manager_data
        
        return all_data



    def _make_hosts_ini_file(self, set_ip=False):
        """
        Creates hosts.ini files needed by various services on the measurement node.
        Optionally sets the ip interfaces for the measurement network
        Args:
            set_ip (bool, optional): Optionally sets the the measurement network interfaces. Defaults to False.
        """
        hosts = []                    
        num=1
        base = "10.0.0."
        hosts = []
        if set_ip:
            print("Setting measurement nic IPs")
            self.mflib_logger.info("Setting measurement nic IPs")
        for node in self.slice.get_nodes():
            for interface in node.get_interfaces():
                if ("Meas_Nic" in interface.get_name()):
                    ip = base + str(num)
                   
                    if set_ip:
                        print(f"setting interface ip {ip}")
                        self.mflib_logger.info(f"setting interface ip {ip}")
                        interface.set_ip(ip = ip, cidr = "24")
                    #hosts.append("{0} ansible_host={1} hostname={1} ansible_ssh_user={2} node_exporter_listen_ip={1} node_exporter_username={3} node_exporter_password={3} snmp_community_string={4} grafana_admin_password={3} fabric_prometheus_ht_user={3} fabric_prometheus_ht_password={3}".format(node.get_name(), ip ,"mfuser","fabric","not-in-use"))
                    #hosts.append("{0} ansible_host={1} hostname={1} ansible_ssh_user={2} node_exporter_listen_ip={1}".format(node.get_name(), ip ,"mfuser"))
                    hosts.append("{0} ansible_host={1} hostname={1} ansible_ssh_user={2} node_exporter_listen_ip={1} ansible_ssh_common_args='-o StrictHostKeyChecking=no'".format(node.get_name(), ip ,"mfuser"))
                    num+=1


        # print("Creating Ansible Hosts File\n")
        # Prometheus e_Elk
        hosts_txt = ""
        e_hosts_txt = ""

        experiment_nodes = "[Experiment_Nodes]\n"
        e_experiment_nodes = "[workers]\n"
        for host in hosts:
            if "_meas_node" in host:

                hosts_txt += "[Meas_Node]\n"
                hosts_txt += host + '\n\n'

                e_hosts_txt += "[elk]\n"
                e_hosts_txt += host + '\n\n'

            else: # It is an experimenters node
                experiment_nodes += host + '\n'
                e_experiment_nodes += host + '\n'

        hosts_txt += experiment_nodes
        e_hosts_txt += e_experiment_nodes

        local_prom_hosts_filename = os.path.join(self.local_slice_directory, "promhosts.ini")
        local_elk_hosts_filename = os.path.join(self.local_slice_directory, "elkhosts.ini")

        with open(local_prom_hosts_filename, 'w') as f:
            f.write(hosts_txt)
        with open(local_elk_hosts_filename, 'w') as f:
            f.write(e_hosts_txt)

        # Upload the files to the meas node and move to correct locations

        # Upload Prom hosts
        self.meas_node.upload_file(local_prom_hosts_filename,"promhosts.ini")

        # create a common version of hosts.ini for all to access
        self.mflib_logger.info("Setting up common hosts.ini file to measurement node.")
        stdout, stderr = self.meas_node.execute("sudo mkdir -p /home/mfuser/services/common")
        stdout, stderr = self.meas_node.execute("sudo chown mfuser:mfuser /home/mfuser/services")
        stdout, stderr = self.meas_node.execute("sudo chown mfuser:mfuser /home/mfuser/services/common")
        stdout, stderr = self.meas_node.execute("sudo cp promhosts.ini /home/mfuser/services/common/hosts.ini")
        stdout, stderr = self.meas_node.execute("sudo chown mfuser:mfuser /home/mfuser/services/common/hosts.ini")
        
        # Upload the elkhosts.ini file.
        self.meas_node.upload_file(local_elk_hosts_filename,"elkhosts.ini")

        # create the elk.ini file
        stdout, stderr = self.meas_node.execute("sudo mv elkhosts.ini /home/mfuser/mf_git/elkhosts.ini")
        stdout, stderr = self.meas_node.execute("sudo chown mfuser:mfuser /home/mfuser/mf_git/elkhosts.ini")
        
               
 

    def download_common_hosts(self):
        """
        Downloads hosts.ini file and returns file text.
        Downloaded hosts.ini file will be stored locally for future reference.  
        :param service: The name of the service.
        :type service: String 
        :param method: The method name such as create, update, info, start, stop, remove.
        :type method: String
        :return: Writes file to local storage and returns text of the log file.
        :rtype: String
        """
        try:
            local_file_path = self.common_hosts_file
            remote_file_path =  os.path.join("/home/mfuser/services/common/hosts.ini")
            #print(local_file_path)
            #print(remote_file_path)
            file_attributes = self.meas_node.download_file(local_file_path, remote_file_path, retry=1) #, retry=3, retry_interval=10): # note retry is really tries
            #print(file_attributes)
            
            with open(local_file_path) as f:
                hosts_text = f.read()
                return local_file_path, hosts_text

        except Exception as e:
            print("Common hosts.ini download has failed.")
            print(f"downloading common hosts file Failed: {e}")
            self.mflib_logger.exception("Downloading common hosts.ini file has failed.")
            return "",""


# IPV6 to IPV4 only sites fix
# note: should set bootstrap status file when making these 2 calls, status should be set, restored, not needed.
    def set_DNS_all_nodes(self):
        """
        Sets DNS for nodes to allow them to access ipv4 networks.

        Returns:
            string: "set" if DNS set, "not needed" otherwise.
        """
        # Check if we need to
        if(self.meas_node.validIPAddress(self.meas_node.get_management_ip())=="IPv6"):
            for node in self.slice.get_nodes():
                self.set_DNS(node)
            return "set"
        else:
            return "not needed"

    def restore_DNS_all_nodes(self):
        """
        Restores the DNS to default if previously set. See set_DNS_all_nodes.

        Returns:
            string: "restored" if restored, "not needed" if not needed
        """
        # Check if we need to
        if(self.meas_node.validIPAddress(self.meas_node.get_management_ip())=="IPv6"):
            for node in self.slice.get_nodes():
                self.restore_DNS(node)
            return "restored"
        else:
            return "not needed"

    def set_DNS(self,node):
        """
        Sets the DNS on IPv6 only nodes to enable access to IPv4 sites.
        """
        if(node.validIPAddress(node.get_management_ip())=="IPv6"):
            # needed to fix sudo unable to resolve error
            node.execute('sudo echo -n "127.0.0.1 " | sudo cat - /etc/hostname  | sudo tee -a /etc/hosts')

            node.execute("""
            printf 'nameserver 2a00:1098:2c::1\nnameserver 2a01:4f8:c2c:123f::1\nnameserver 2a01:4f9:c010:3f02::1' > resolv.new;
            sudo mv /etc/resolv.conf /etc/resolv.old;
            sudo mv resolv.new /etc/resolv.conf;
            """)
            #Needed for fedora
            # Check if eth0 exists to prevent errors. TODO check if this is still needed or check if os is fedora instead.
            if os.path.exists(os.path.join("sys", "class", "net", "eth0")):
                node.execute("""
                    sudo resolvectl dns eth0 2a00:1098:2c::1;
                    sudo resolvectl dns eth0 2a01:4f8:c2c:123f::1;
                    sudo resolvectl dns eth0 2a01:4f9:c010:3f02::1;
                """)

    def restore_DNS(self,node):
        if(node.validIPAddress(node.get_management_ip())=="IPv6"):
            node.execute("""
                sudo mv /etc/resolv.old /etc/resolv.conf;
            """)
            #Needed for fedora
            # Check if eth0 exists to prevent errors. TODO check if this is still needed or check if os is fedora instead.
            if os.path.exists(os.path.join("sys", "class", "net", "eth0")):
                node.execute("""
                    resolvectl revert eth0;
                """)

    def _set_all_hosts_file(self):
        for node in self.slice.get_nodes():
            self._set_hosts_file(node)

    def _set_hosts_file(self, node):
        self.meas_node_ip
        # Set the Measurement node ip
        node.execute(f'sudo echo -n "{self.meas_node_ip} {self.measurement_node_name}" | sudo tee -a /etc/hosts')