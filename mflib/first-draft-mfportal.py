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

import base64
import json
import os
from datetime import datetime, timezone

import requests as _req

from mflib.mflib import MFLib


class MFPortal(MFLib):
    """
    MFPortal groups the FABRIC Portal integration helpers: setting up/checking
    mfuser accounts, locating measurement NICs/networks, and registering a
    slice's meas node with the portal. These operate directly on a fablib
    slice/node rather than an MFLib instance.
    """

    mfportal_class_version = "1.0.0"
    __version__ = mfportal_class_version
    __VERSION__ = mfportal_class_version

    MEAS_NODE_NAME = "meas-node"
    MEAS_NETWORK_NAME = "meas-net6"
    MEAS_NIC_NAME = "meas-nic"

    @staticmethod
    def check_mfuser_status(slice):
        # Check if the slice nodes have been setup for the mfuser
        # Return a list of bools that describe what parts have been setup on which nodes
        account_status = []
        msg = f"checkin mfuser accounts..."
        node_checks = []

        cmd = (
            f'sudo [ -d /home/mfuser/.ssh ] && echo "Directory OK" || echo "Directory FAIL";'
            f'sudo [ -f /home/mfuser/.ssh/mfuser.pub ] && echo "Public Key OK" || echo "Public Key FAIL";'
            f"sudo grep -q '^ssh-.* mfuser$' /home/mfuser/.ssh/authorized_keys && echo \"Auth Key OK\" || echo \"Auth Key FAIL\";"
        )

        for node in slice.get_nodes():
            try:
                node_checks.append( {"node":node.get_name(), "thread":node.execute_thread(cmd)})

            except Exception as e:
                print(f"Failed to check mfuser: {e}")
                #self.mflib_logger.exception(f"Failed to setup mfuser user.")
                mfusers_install_success = False

        status = []
        for node_check in node_checks:
            stdout, stderr = node_check['thread'].result()
            if stdout:
                #print(f"{stdout}") #self.core_logger.debug(f"STDOUT useradd mfuser: {stdout}")
                status.append( { 'node':node_check['node'],
                                  'home_dir':"Directory OK" in stdout,
                                  'public_key':"Public Key OK" in stdout,
                                  'auth_key':"Auth Key OK" in stdout
                              } )

            if stderr:
                print(f"STDERR: {stderr}")#self.core_logger.error(f"STDERR useradd mfuser: {stderr}")


        overview = {}
        overview["home_dirs_complete"] = all(node['home_dir'] for node in status)
        overview["home_dirs_partial"] = any(node['home_dir'] for node in status)

        overview["public_key_complete"] = all(node['public_key'] for node in status)
        overview["public_key_partial"] = any(node['public_key'] for node in status)

        overview["auth_key_complete"] = all(node['auth_key'] for node in status)
        overview["auth_key_partial"] = any(node['auth_key'] for node in status)

        all_mfuser_accounts_setup = overview["home_dirs_complete"] and overview['public_key_complete'] and overview['auth_key_complete']
        return {'nodes':status, 'overview':overview, 'complete':all_mfuser_accounts_setup }

    @staticmethod
    def get_mfuser_keys(slice, return_keys=False, save_public_key_filename=None, save_private_key_filename=None): #, return_strings=True,):
        # if key filenames are given, then the keys will be saved to those directories
        #   otherwise the downloaded files will be tmp files and be deleted once the contents have been read
        # if return_keys is true keys will be returned as string tuple private_key, public_key

        # Looks for the keys in the mfuser dir
        # Copies keys to default user so they can be downloaded
        # Downloads the keys
        # Deletes the copies

        local_private_key_filename = f'/tmp/{slice.get_name()}_mfuser_private_key'
        local_public_key_filename = f'/tmp/{slice.get_name()}_mfuser_public_key'

        # The unique name for copy of the keys moved to the remotes default account
        #   so we can use the download method. The files will then be deleted.
        delme_private_key_filename = 'mfuser.key.mflib.framework.tmp.delme'
        delme_public_key_filename = 'mfuser.pub.mflib.framework.tmp.delme'

        if save_public_key_filename:
            local_public_key_filename = save_public_key_filename
        if save_private_key_filename:
            local_private_key_filename  = save_private_key_filename
        #keys_missing = True
        for node in slice.get_nodes():
            #node.show()
            try:
                if True: #keys_missing:
                    # Copy
                    copy_cmd = (
                        f"sudo cp /home/mfuser/.ssh/mfuser.pub ~/{delme_public_key_filename};"
                        f"sudo cp /home/mfuser/.ssh/mfuser.key ~/{delme_private_key_filename};"
                    )
                    stdout, stderr = node.execute(copy_cmd)
                    if stderr:
                        pass
                        #print(f'On {node.get_name()} Copy keys command failed {stderr}')

                        # copy command failed, so files likely not there
                    else:
                        # Download
                        public_result = node.download_file(f'{local_public_key_filename}', delme_public_key_filename)
                        private_result = node.download_file(f'{local_private_key_filename}', delme_private_key_filename)
                        #print(public_result)
                        #print(private_result)

                        # Remove Copy
                        remove_cmd = (
                            f"sudo rm ~/{delme_public_key_filename};"
                            f"sudo rm ~/{delme_private_key_filename};"
                        )
                        stdout, stderr = node.execute(remove_cmd)
                        # print(remove_cmd)
                        # print(f'Remove OUT on {node.get_name()} stdout')
                        # print(f'Remove ERR on {node.get_name()} stderr')
                        # print('keys found')
                        #keys_missing = False

                        if return_keys:
                            # Read the keys to return the text
                            with open( local_public_key_filename , 'r') as f:
                                public_key_str = f.read()
                            with open( local_private_key_filename , 'r') as f:
                                private_key_str = f.read()
                        else:
                            private_key_str = ""
                            public_key_str = ""

                        # If the caller did not specify to save the files
                        #   we need to delete them
                        if not save_public_key_filename:
                            os.remove(local_public_key_filename)
                        if not save_private_key_filename:
                            os.remove(local_private_key_filename)

                        return node.get_name(), private_key_str, public_key_str


            except Exception as e:
                print(f'Failed to download key file {e}')
        #if keys_missing:
        #print("No keys were found")
        return "", "", ""

    @staticmethod
    def bootstrap_mfusers(slice):

        ######################
        # Check Status       #
        ######################
        status = MFPortal.portal_check_mfuser_status(slice)
        if status['complete']:
            # Nothing to do
            print("MFUsers are already setup. Nothing to do")
            return True

        ######################
        # Create MFUser keys
        #####################
        mfuser_private_key_filename = "mfuser_private_key"
        mfuser_public_key_filename = "mfuser_public_key"
        local_mfuser_private_key_filename = "mfuser_private_key"
        local_mfuser_public_key_filename = "mfuser_public_key"

        #############################
        # Account Creation
        ############################
        mfuser_account_threads = []
        try:
            for node in status['nodes']:
                if not node["home_dir"]:
                    # Only create user if they don't already exist
                    n = slice.get_node(node['node'])
                    cmd = (
                        f"sudo useradd -s /bin/bash -G root -m mfuser;"
                        f"sudo mkdir /home/mfuser/.ssh;"
                        f"sudo chmod 700 /home/mfuser/.ssh;"
                        f"echo 'mfuser ALL=(ALL:ALL) NOPASSWD: ALL' | sudo tee -a /etc/sudoers.d/90-cloud-init-users;"
                        f"sudo touch /home/mfuser/os_image_{n.get_image()};"
                        f"sudo chown mfuser:mfuser /home/mfuser/os_image_{n.get_image()};"
                    )
                    mfuser_account_threads.append(n.execute_thread(cmd))
        except Exception as e:
            print(f'Failed setting up mfuser accounts: {e}')


        for thread in mfuser_account_threads:
            stdout, stderr = thread.result()
            if stdout:
                print(f"{stdout}") #self.core_logger.debug(f"STDOUT useradd mfuser: {stdout}")
            if stderr:
                print(f"{stderr}")#self.core_logger.error(f"STDERR useradd mfuser: {stderr}")
        #===========================
        # END Account Creation
        #===========================


        #############################
        # Key Creation and possible key retriveal
        ############################
        private_key_file_to_upload = None
        public_key_file_to_upload = None
        # Only create keys if NO keys have been setup and placed in mfuser .ssh dir at all
        if not status['overview']['public_key_complete'] and not status['overview']['public_key_partial']:
            # No mfuser keys have been placed

            print("Generating MFUser Keys...")
            #self.mflib_logger.info("Generating MFUser Keys...")
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
            public_key_file = open(local_mfuser_public_key_filename, "w")
            public_key_file.write(public_key_str)
            public_key_file.write("\n")
            public_key_file.close()
            chmod(local_mfuser_public_key_filename, 0o644)

            public_key_file_to_upload = local_mfuser_public_key_filename

            # Save private key & change mode
            private_key_file = open(local_mfuser_private_key_filename, "w")
            private_key_file.write(private_key_str)
            private_key_file.close()
            chmod(local_mfuser_private_key_filename, 0o600)

            private_key_file_to_upload = local_mfuser_private_key_filename

            print("MFUser key generation Done.")

        elif status['overview']['public_key_partial']:
            # Some keys got setup, but not all of them
            # We should grab one of the existing keys to ensure they are all the same
            print("WARNING! some keys have not been uploaded. Keys will be found and uploaded.")
            # Could add the nodes without keys for output
            #public_key_missing = True

            keys_found, pub_key_str, priv_key_str = MFPortal.portal_get_mfuser_keys(slice, local_mfuser_public_key_filename, local_mfuser_private_key_filename)
            if keys_found:
                public_key_file_to_upload = local_mfuser_public_key_filename
                private_key_file_to_upload = local_mfuser_private_key_filename
            else:
                print("Keys are needed but were not found on any nodes")

        #===================================
        #  END Key Creation or Retrival
        #===================================


        ####################################
        # Public Key Upload
        ###################################
        if public_key_file_to_upload:
            # Upload key to those who need it

            public_key_uploads = []
            for node in status['nodes']:
                try:
                    if not node['public_key']:
                        n = slice.get_node(node["node"])
                        public_key_uploads.append( {"node":n.get_name(), "thread":n.upload_file_thread(public_key_file_to_upload, "mfuser.pub") } )
                except Exception as e:
                    print(f"Failed to public upload key: {e}")


            for upload in public_key_uploads:

                file_attributes = upload["thread"].result()
                #print(f'Upload to {upload["node"]} file attributes: {file_attributes}')
                if not file_attributes:
                    # Actually don't know what error would look like
                    print("Failed to upload public key file")
                else:
                    print(file_attributes)

        else:
            # There is nothing to upload
            pass

        #======================================
        # END Public Key Upload
        #======================================


        ####################################
        # Private Key Upload
        ###################################
        if private_key_file_to_upload:
            # Assume that we are uploading the private key at the same time as the public
            #   so if public key is present, then the private key should be as well
            #   Private key is only for keeping a copy somewhere if we need it later
            # Upload key to those who need it

            private_key_uploads = []
            for node in status['nodes']:
                try:
                    if not node['public_key']:
                        n = slice.get_node(node["node"])
                        private_key_uploads.append( {"node":n.get_name(), "thread":n.upload_file_thread(private_key_file_to_upload, "mfuser.key") } )
                except Exception as e:
                    print(f"Failed to upload private keys: {e}")


            for upload in private_key_uploads:

                file_attributes = upload["thread"].result()
               # print(f'Uploaded private key to {upload["node"]} file attributes: {file_attributes}')
                if not file_attributes:
                    # Actually don't know what error would look like
                    print("Failed to upload private key file")
                else:
                    pass
                    #print(file_attributes)

        else:
            # There is nothing to upload
            pass

        #======================================
        # END Private Key Upload
        #======================================




        ##########################################
        # Authorized Keys
        #########################################

        if not status['overview']['auth_key_complete']:
            # There are keys that need to be added to authorized keys file
            auth_key_threads = []
            # note that private key is also being copied here as opposed to having a separate section
            cmd = (
                f"sudo mv mfuser.key /home/mfuser/.ssh/mfuser.key;"
                f"sudo mv mfuser.pub /home/mfuser/.ssh/mfuser.pub;"
                f"sudo grep -qf /home/mfuser/.ssh/mfuser.pub /home/mfuser/.ssh/authorized_keys || sudo sh -c \"sed 's/$/ mfuser/' /home/mfuser/.ssh/mfuser.pub >> /home/mfuser/.ssh/authorized_keys\";"
                f"sudo chmod 644 /home/mfuser/.ssh/authorized_keys;"
                f"sudo chown -R mfuser:mfuser /home/mfuser/.ssh;"
            )


            try:
                for node in status['nodes']:
                    if not node["auth_key"]:
                        # Only move the key to auth if it is not already there
                        n = slice.get_node(node['node'])
                        auth_key_threads.append(n.execute_thread(cmd))
            except Exception as e:
                print(f'Failed moving key to authorized users: {e}')


            for thread in auth_key_threads:
                stdout, stderr = thread.result()
                if stdout:
                    print(f"auth key STDOUT {stdout}") #self.core_logger.debug(f"STDOUT useradd mfuser: {stdout}")
                if stderr:
                    print(f"auth key STDERR {stderr}")#self.core_logger.error(f"STDERR useradd mfuser: {stderr}")

        else:
            print("All auth keys are aleady in place")

        # TODO flesh out return values
        return True

    # Checks each node in the slice to see if there is a meas nic
    # Returns a list of nic information, meas newtwork info, if node has meas nic & a list of nodes without meas nic
    @staticmethod
    def check_meas_nics(slice, filename= None):
        slice_info = slice.toDict()
        meas_nics = []
        nicless_nodes = []
        for node in slice.get_nodes():
            meas_nic_found = False
            node_name = node.get_name()
            interfaces = node.get_interfaces()
            for interface in interfaces:
                #print(interface)
                #print(dir(interface))
                nic_name = interface.get_name()
                if "mflib_meas" in nic_name:
                    nic_address = interface.get_ip_addr()
                    meas_nics.append( interface.toDict() ) #{'name':nic_name, 'node_name':node_name, 'ip_addr':str(nic_address)} )
                    meas_nic_found = True
            if not meas_nic_found:
                nicless_nodes.append( { 'node_name':node_name } )

        networks = slice.get_l3networks()
        meas_networks = []
        for network in networks:
            if "mflib_meas" in network.get_name():
                #print(f'Meas network {network.get_name()}')
                meas_networks.append(network.toDict())
        #print(meas_networks)

        #print(meas_nics)
        file_dict = {'meas_nics':meas_nics, 'nicless_nodes':nicless_nodes, 'meas_networks': meas_networks, 'slice_info':slice_info }

        if filename:
            with open(filename, "w") as f:
                json.dump(file_dict, f, indent=4)

        return meas_nics, nicless_nodes, meas_networks, slice_info

    # This method added top level subnet and tested Jan12
    # This method is all that is needed to add the meas network
    # This has not been tested to see if ips are consitent after reboots
    @staticmethod
    def add_fabnet_meas_network(slice):
        #fabnet_v6_top_level_subnet = "2600:2701:5000::/40"
        fabnet_v6_top_level_subnet = "2602:fcfb::/36"
        for node in slice.get_nodes():
            fabnet_name = f"mflib_meas" # method auto adds site & net type
            node.add_fabnet(fabnet_name, net_type="IPv6", routes=[fabnet_v6_top_level_subnet])

    @staticmethod
    def assign_static_fabnet6_ip(slice_obj, node):
        # This is to be run on the meas-node so that it can assign the static fabnet 6 IP to the meas nic on the node.
        # This is needed because FABRIC's ACL only allows cros-slice traffic from the registered static address not the SLAAC/EUI-64 address assigned by post_boot_config().
        # It is assumed that the meas nic has been added to the node and slice and that the slice has been submitted.
        # This can be called at anytime, but submit needs to be called aferwards.
        # Normally this would be done when the meas node is added before the slice is submitted
        net_obj   = slice_obj.get_network(MFPortal.MEAS_NETWORK_NAME)
        iface_obj = node.get_interface(network_name=MFPortal.MEAS_NETWORK_NAME)
        net_obj.config()

        subnet_v6 = net_obj.get_subnet()
        gw_v6     = net_obj.get_gateway()
        node_ipv6 = net_obj.get_available_ips(count=1)[0]
        dev       = iface_obj.get_device_name()

        print(f'Subnet  : {subnet_v6}')
        print(f'Gateway : {gw_v6}')
        print(f'IP      : {node_ipv6}')
        print(f'Device  : {dev}')

        # Only call ip_addr_add() if the address is not already present
        _check, _ = node.execute(f'ip -6 addr show dev {dev}')
        if str(node_ipv6) not in _check:
            node.ip_addr_add(addr=node_ipv6, subnet=subnet_v6, interface=iface_obj)
            print('Static IPv6 assigned.')
        else:
            print('Address already present — skipping ip_addr_add().')

        node_ipv6       = str(node_ipv6)
        meas_net_subnet = str(subnet_v6)
        gw_v6_str       = str(gw_v6)

        stdout, _ = node.execute(f'ip -6 addr show {dev}')
        print(stdout)

# TODO Add Persisten fabnetv6 routing

    @staticmethod
    def write_json_to_meas_node(slice_obj, data=None, remote_path="/etc/mflib/portal_registration.json"):

        net_obj   = slice_obj.get_network(MFPortal.MEAS_NETWORK_NAME)
        net_obj.config()

        if data is None:
            data = {
                'written_at':       datetime.now(timezone.utc).isoformat(),
                'slice_id':         slice_obj.get_slice_id(),
                'slice_name':       slice_obj.get_name(),
                'node_ipv6':        net_obj.get_available_ips(count=1)[0],
                'meas_net_subnet':  net_obj.get_subnet(),
                'meas_net_gateway': net_obj.get_gateway(),
                'lease_start':      str(slice_obj.get_lease_start()),
                'lease_end':        str(slice_obj.get_lease_end()),
                'portal_registration': None,
            }

        print(data)

        """Write data as JSON to remote_path using a base64 pipe (avoids quoting issues)."""
        encoded = base64.b64encode(json.dumps(data, indent=2).encode()).decode()
        stdout, stderr = slice_obj.get_node("meas-node").execute(
            f'echo {encoded} | base64 -d | sudo tee {remote_path} > /dev/null'
        )
    @staticmethod
    def check_portal_reachable(PORTAL_PUBLIC_URL):
        if not PORTAL_PUBLIC_URL:
            print('PORTAL_PUBLIC_URL is not set.')
        else:
            _portal_url   = PORTAL_PUBLIC_URL.rstrip('/')
            _health_url   = f'{_portal_url}/api/meas-node/portal-info'
            print(f'Checking portal at {_health_url} …')
            try:
                _r = _req.get(_health_url, timeout=10)
                _r.raise_for_status()
                _info = _r.json()
                print('Portal reachable.')
                print(f"  FABNetv6 IP      : {_info.get('fabnetv6_ip')}")
                print(f"  FABNetv6 subnet  : {_info.get('fabnetv6_subnet')}")
                print(f"  FABNetv6 gateway : {_info.get('fabnetv6_gateway')}")
                print('\nReady to register — proceed to Cell 12.')
            except Exception as _exc:
                raise RuntimeError(
                    f'Portal unreachable at {_health_url}: {_exc}\n'
                    'Fix PORTAL_PUBLIC_URL in Cell 3, re-run Cell 3, then re-run this cell.'
                ) from None


    @staticmethod
    def register_meas_node_to_portal(slice_obj, portal_url="http://23.134.232.147"):
        #
        # We need to register the meas node. It may be independent or in the same slice as the experiment
        # In either case the meas node name should be the same so we can just use that to get the meas node info

        # Get the needed info for registrations

        slice_id   = slice_obj.get_slice_id()
        slice_name = slice_obj.get_name()
        meas_node = slice_obj.get_node(MFPortal.MEAS_NODE_NAME)


        net_obj   = slice_obj.get_network(MFPortal.MEAS_NETWORK_NAME)
        iface_obj = meas_node.get_interface(network_name=MFPortal.MEAS_NETWORK_NAME)
        net_obj.config()

        fabnetv6_subnet_str     = str(net_obj.get_subnet())
        fabnetv6_gateway_str    = str(net_obj.get_gateway())
        dev                     = str(iface_obj.get_device_name())

        node_ipv6               = str(iface_obj.get_ip_addr())

        print(f'Subnet  : {subnet_v6}')
        print(f'Gateway : {gw_v6}')
        print(f'IP      : {node_ipv6}')
        print(f'Device  : {dev}')

        import requests as _req

        portal_registration = None

        if not portal_url:
            print('PORTAL_PUBLIC_URL is not set — skipping registration.')
        else:
            portal_url = portal_url.rstrip('/')
            reg_url    = f'{portal_url}/api/meas-node/register'

            reg_payload = {
                'slice_uuid':        slice_id,
                'slice_name':        slice_name,
                'fabnetv6_ip':       node_ipv6,
                'fabnetv6_subnet':   fabnetv6_subnet_str,
                'fabnetv6_gateway':  fabetv6_gateway_str,
                'mfuser_public_key': mfuser_public_key,
                'node_mgmt_ip':      "",
                'slice_created_at':  str(slice_obj.get_lease_start()),
                'slice_expires_at':  str(slice_obj.get_lease_end()),
            }

            print(f'Registering with portal at {reg_url} …')
            try:
                resp = _req.post(reg_url, json=reg_payload, timeout=30)
                resp.raise_for_status()
                reg_response = resp.json()
                print(f"Status   : {reg_response.get('status')}")
                print(json.dumps(reg_response, indent=2))
            except Exception as exc:
                print(f'Registration failed: {exc}')
                reg_response = {'error': str(exc)}

            portal_registration = {
                'registered_at': datetime.now(timezone.utc).isoformat(),
                'portal_url':    portal_url,
                'request':       reg_payload,
                'response':      reg_response,
            }

            # Overwrite the slice info file with full registration data
            local_info['portal_registration'] = portal_registration
            local_info['written_at'] = datetime.now(timezone.utc).isoformat()
            _write_json_to_node(meas_node, local_info, '/etc/mflib/portal_registration.json')
            print('\nRegistration record saved to /etc/mflib/portal_registration.json')



    @staticmethod
    def portal_add_meas_node_to_slice(slice_obj, meas_node_name=None, meas_network_name=None):
        # Need to add the meas node for a portal accesible slice
        # Add the meas node

        SITE              = "EDC"    # Place all meas nodes on EDC
        IMAGE             = "docker_ubuntu_24"
        CORES             = 4
        RAM_GB            = 16
        DISK_GB           = 100

        MEAS_NODE_NAME    = meas_node_name or MFPortal.MEAS_NODE_NAME
        MEAS_NETWORK_NAME = meas_network_name or MFPortal.MEAS_NETWORK_NAME
        MEAS_NIC_NAME     = MFPortal.MEAS_NIC_NAME
