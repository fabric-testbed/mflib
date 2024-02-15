# MIT License
#
# Copyright (c) 2022 FABRIC Testbed
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


import string
import random

import logging


class Core:
    """
    MFLib core contains the core methods needed to create and interact with the Measurement Framework installed in a slice.
    It is not intended to be used by itself, but rather, it is the base object for creating Measurement Framework Library objects.
    """

    core_class_version = "1.0.38"

    """
    An updatable version for debugging purposes to make sure the correct version of this file is being used. Anyone can update this value as they see fit.
    Should always be increasing.

    Returns:
        String: Version.sub-version.build
    """

    def set_core_logger(self):
        """
        Sets up the core logging file.
        Note that the self.logging_filename will be set with the slice name when the slice is set.
        Args:
        filename (_type_, optional): _description_. Defaults to None.
        """
        self.core_logger = logging.getLogger(__name__)
        self.core_logger.propagate = False  # needed?
        self.core_logger.setLevel(self.log_level)

        formatter = logging.Formatter(
            "%(asctime)s %(name)-8s %(levelname)-8s %(message)s",
            datefmt="%m/%d/%Y %H:%M:%S %p",
        )

        # Make sure log directory exists
        if not os.path.exists(self.log_directory):
            os.makedirs(self.log_directory)

        file_handler = logging.FileHandler(self.log_filename)
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(formatter)

        self.core_logger.addHandler(file_handler)

    @property
    def slice_name(self):
        """
        Returns the name of the slice associated with this object.

        Returns:
            String: The name of the slice.
        """
        return self._slice_name

    @slice_name.setter
    def slice_name(self, value):
        """
        Sets the name of the slice associated with this object. Also creates the directories used to store local informations for mflib about the slice.
        Generally should not be called directly. It is called when the slice is set.
        Args:
            value (str): Name of the slice
        """
        # Set the slice name
        self._slice_name = value

        # Create the local slice directory
        try:
            os.makedirs(self.local_slice_directory)
            os.makedirs(self.log_directory)

        except FileExistsError:
            pass
            # Don't care if the file already exists.

        self.log_filename = os.path.join(self.log_directory, "mflib.log")

        self.set_core_logger()

        self.core_logger.info(f"Using core_class_version {self.core_class_version}")
        # self.core_logger.basicConfig(filename=self.log_filename, format='%(asctime)s %(name)-8s %(levelname)-8s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level="INFO", force=True)
        self.core_logger.info(f"-----Set slice name {value}.-----")

    @property
    def local_slice_directory(self):
        """
        The directory where local files associated with the slice are stored.

        Returns:
            str: The directory where local files associated files are stored.
        """
        return os.path.join(self.local_storage_directory, self.slice_name)

    @property
    def log_directory(self):
        """
        The full path for the log directory.

        Returns:
            String: The full path to the log directory.
        """
        return os.path.join(self.local_slice_directory, "log")

    @property
    def bootstrap_status_file(self):
        """
        The full path to the local copy of the bootstrap status file.

        Returns:
            String: The full path tp the local copy of the bootsrap status file.
        """
        return os.path.join(self.local_slice_directory, "bootstrap_status.json")

    @property
    def common_hosts_file(self):
        """
        The full path to a local copy of the hosts.ini file.

        Returns:
            String: The full path to a local copy of the hosts.ini file.
        """
        return os.path.join(self.local_slice_directory, "hosts.ini")

    @property
    def local_mfuser_private_key_filename(self):
        """
        The local copy of the private ssh key for the mfuser account.

        Returns:
            String: The local copy of the private ssh key for the mfuser account.
        """
        return os.path.join(self.local_slice_directory, "mfuser_private_key")

    @property
    def local_mfuser_public_key_filename(self):
        """
        The local copy of the public ssh key for the mfuser account.

        Returns:
            String: The local copy of the public ssh key for the mfuser account.
        """
        return os.path.join(self.local_slice_directory, "mfuser_pubic_key")

    @property
    def meas_node(self):
        """
        The fablib node object for the Measurement Node in the slice.

        Returns:
            fablib.node: The fablib node object for the Measurement Node in the slice.

        """
        if self._meas_node:
            return self._meas_node
        else:
            self._find_meas_node()
            return self._meas_node

    @property
    def meas_node_ip(self):
        """
        The management ip address for the Measurement Node

        Returns:
            String: ip address
        """
        if self.meas_node:
            return self._meas_node.get_management_ip()
        else:
            return ""

    @property
    def slice_username(self):
        """
        The default username for the Measurement Node for the slice.

        Returns:
            String: username
        """
        if self.meas_node:
            return self._meas_node.get_username()
        else:
            return ""

    # Tunnels are needed to access the meas node via the bastion host
    # In the future these may be combinded into one port with diff nginx paths mappings.
    # alt copy is a selection added to the fabric_rc file for setting a alertnate location for the files
    #   such as on a laptop. This makes it easy to create a tunnel on a users laptop where they will need access
    #   to the web uis.

    @property
    def tunnel_host(self):
        """
        If a tunnel is used, this value must be set for the localhost, Otherwise it is set to empty string.

        Returns:
            String: tunnel hostname
        """
        return self._tunnel_host

    @tunnel_host.setter
    def tunnel_host(self, value):
        """
        Set to "localhost" if using tunnnel.
        """
        self._tunnel_host = value

    @property
    def grafana_tunnel_local_port(self):
        """
        If a tunnel is used for grafana, this value must be set for the port.
          Returns:
            String: port number
        """
        return self._grafana_tunnel_local_port

    @grafana_tunnel_local_port.setter
    def grafana_tunnel_local_port(self, value):
        """
        Set to port_number if using tunnnel for grafana.
        """
        self._grafana_tunnel_local_port = value

    @property
    def kibana_tunnel_local_port(self):
        """
        If a tunnel is used for Kibana, this value must be set for the port"""
        return self._kibana_tunnel_local_port

    @kibana_tunnel_local_port.setter
    def kibana_tunnel_local_port(self, value):
        """
        Set to port_number if using tunnnel for Kibana.
        """
        self._kibana_tunnel_local_port = value

    @property
    def grafana_tunnel(self):
        """
        Returns the command for createing an SSH tunnel for accesing Grafana.

        Returns:
            String: ssh command
        """
        return self._meas_node_ssh_tunnel(
            local_port=self.grafana_tunnel_local_port, remote_port="443"
        )

    @property
    def kibana_tunnel(self):
        """
        Returns the command for createing an SSH tunnel for accesing Kibana.

        Returns:
            String: ssh command
        """
        return self._meas_node_ssh_tunnel(
            local_port=self.kibana_tunnel_local_port, remote_port="80"
        )

    def _meas_node_ssh_tunnel(self, local_port, remote_port):
        """
        Creates the ssh tunnel command for accessing the Measurement Node using the given local and remote ports.

        Args:
            local_port (String): local port ie port on users machine
            remote_port (String): remote port ie port on Measurement Node

        Returns:
            String : SSH command string or error string.
        """
        # These values from fabric_ssh_tunnel_tools.tgz obtained by user when configuring Fabric environment
        private_key_file = "slice_key"
        ssh_config = "ssh_config"

        slice_username = self.slice_username
        meas_node_ip = self.meas_node_ip

        tunnel_cmd = f"ssh -L {local_port}:localhost:{remote_port} -F {ssh_config} -i {private_key_file} {slice_username}@{meas_node_ip}"
        return tunnel_cmd

    """
    The git branch to be used for cloning the MeasurementFramework branch to the Measusrement Node.
    """

    def __init__(
        self,
        local_storage_directory="/tmp/mflib",
        mf_repo_branch="main",
        logging_level=logging.DEBUG,
    ):
        """
        Core constructor

        Args:
            local_storage_directory (str, optional): Directory where local data will be stored. Defaults to "/tmp/mflib".
            mf_repo_branch (str, optional): git branch name to pull MeasurementFranework code from. Defaults to "main".
        """
        # super().__init__()

        try:
            self.local_storage_directory = local_storage_directory
            os.makedirs(self.local_storage_directory)
        except FileExistsError:
            pass

        # The slice_name
        self._slice_name = ""
        self.mf_repo_branch = mf_repo_branch

        self.core_logger = None
        self.log_level = logging_level
        self.log_filename = os.path.join(self.log_directory, "mflib_core.log")
        self.set_core_logger()
        self.core_logger.info("Creating mflib object.")

        self.tunnel_host = "localhost"
        self.grafana_tunnel_local_port = "10010"
        self.kibana_tunnel_local_port = "10020"

        # The slice object
        self.slice = None
        # The meas_node object
        self._meas_node = None

        # The following are normally constant values
        # Name given to the meas node
        self.measurement_node_name = "meas-node"
        # Services directory on meas node
        self.services_directory = os.path.join("/", "home", "mfuser", "services")
        # Base names for keys
        self.mfuser_private_key_filename = "mfuser_private_key"
        self.mfuser_public_key_filename = "mfuser_public_key"

    # User Methods
    def create(self, service, data=None, files=[]):
        """
        Creates a new service for the slice.

        Args:
            service(String): The name of the service.
            data (JSON serializable object) Data to be passed to a JSON file place in the service's meas node directory.
            files (List of Strings): List of filepaths to be uploaded.
        Returns:
            dict: Dictionary of creation results.
        """
        self.core_logger.info(f"Run create for {service}")
        self.core_logger.debug(f"Data is {data}.")
        return self._run_on_meas_node(service, "create", data, files)

    def update(self, service, data=None, files=[]):
        """
        Updates an existing service for the slice.

        Args:
            service (String): The name of the service.
            data (JSON Serializable Object): Data to be passed to a JSON file place in the service's meas node directory.
            files (List of Strings): List of filepaths to be uploaded.

        Returns:
            dict: Dictionary of update results.
        """

        self.core_logger.info(f"Run update for {service}")
        self.core_logger.debug(f"Data is {data}.")
        return self._run_on_meas_node(service, "update", data, files)

    def info(self, service, data=None):
        """
        Gets inormation from an existing service. Strictly gets information, does not change how the service is running.

        Args:
            service (String): The name of the service.
            data (JSON Serializable Object): Data to be passed to a JSON file place in the service's meas node directory.
        Returns:
            dict: Dictionary of info results.
        """
        # Ensure service inputted is valid
        if service not in self._get_service_list():
            print("You must specify a valid service")
            return {"success": False}

        self.core_logger.info(f"Run info for {service}")
        self.core_logger.debug(f"Data is {data}.")
        return self._run_on_meas_node(service, "info", data)

    def start(self, services=[]):
        """
        Restarts a stopped service using existing configs on meas node.

        Args:
            services (List of Strings): The name of the services to be restarted.
        Returns:
            List: List of start result dictionaries.
        """
        ret_val = []
        for service in services:
            self.core_logger.info(f"Run start for {service}")
            ret_val.append(
                {
                    "service": service,
                    "results": self._run_on_meas_node(service, "start"),
                }
            )
        return ret_val

    def stop(self, services=[]):
        """
        Stops a service, does not remove the service, just stops it from using resources.

        Args:
            services (List of Strings): The names of the services to be stopped.
        Returns:
            List: List of stop result dictionaries.
        """
        ret_val = []
        for service in services:
            self.core_logger.info(f"Run stop for {service}")
            ret_val.append(
                {"service": service, "results": self._run_on_meas_node(service, "stop")}
            )
        return ret_val

    def remove(self, services=[]):
        """
        Stops a service running and removes anything setup on the experiment's nodes. Service will then need to be re-created using the create command before service can be started again.

        Args:
            services (List of Strings): The names of the services to be removed.
        Returns:
            List: List of remove result dictionaries.
        """

        ret_val = []
        for service in services:
            self.core_logger.info(f"Run remove for {service}")
            ret_val.append(
                {
                    "service": service,
                    "results": self._run_on_meas_node(service, "remove"),
                }
            )

    # Utility Methods
    
    def _get_service_list(self):
        """
        Gets a list of all currently existing services
        :return: all currently existing services
        :rtype: List
        """
        service_list = []
        stdout, stderr = self.meas_node.execute(f"ls {self.services_directory}", quiet=True)
        for item in stdout.split('\n'):
            if item != "common" and item != "":
                service_list.append(item)
        return service_list

    def _upload_mfuser_keys(self, private_filename=None, public_filename=None):
        """
        Uploads the mfuser keys to the default user for easy access later.

        """
        if private_filename is None:
            private_filename = self.local_mfuser_private_key_filename
        if public_filename is None:
            public_filename = self.local_mfuser_public_key_filename

        try:
            local_file_path = private_filename
            remote_file_path = self.mfuser_private_key_filename
            fa = self.meas_node.upload_file(
                local_file_path, remote_file_path
            )  # , retry=3, retry_interval=10):

        except TypeError:
            pass
            # TODO set file permissions on remote
            # This error is happening due to the file permmissions not being correctly set on the remote?
        except Exception as e:
            print(f"Failed Private Key Upload: {e}")
            self.core_logger.exception(
                "Failed to upload mfuser private key to default user."
            )

        try:
            local_file_path = public_filename
            remote_file_path = self.mfuser_public_key_filename
            fa = self.meas_node.upload_file(
                local_file_path, remote_file_path
            )  # , retry=3, retry_interval=10):
        except TypeError:
            pass
            self.core_logger.exception(
                "Failed to upload mfuser public key to default user."
            )
            # TODO set file permissions on remote
            # This error is happening due to the file permmissions not being correctly set on the remote?
            # Errors are:
            # Failed Private Key Upload: cannot unpack non-iterable SFTPAttributes object
            # Failed Public Key Upload: cannot unpack non-iterable SFTPAttributes object
        except Exception as e:
            print(f"Failed Public Key Upload: {e}")
            self.core_logger.exception("Failed to upload mfuser keys to default user.")

    def _copy_mfuser_keys_to_mfuser_on_meas_node(self):
        """
        Copies mfuser keys from default location to mfuser .ssh folder and sets ownership & permissions.
        """
        try:
            cmd = (
                f"sudo cp {self.mfuser_public_key_filename} /home/mfuser/.ssh/{self.mfuser_public_key_filename};"
                f"sudo cp {self.mfuser_private_key_filename} /home/mfuser/.ssh/{self.mfuser_private_key_filename};"
                f"sudo chmod 644 /home/mfuser/.ssh/{self.mfuser_public_key_filename};"
                f"sudo chmod 600 /home/mfuser/.ssh/{self.mfuser_private_key_filename};"
                f"sudo chown -R mfuser:mfuser /home/mfuser/.ssh;"
            )
            stdout, stderr = self.meas_node.execute(cmd)
            if stdout:
                self.core_logger.debug(f"STDOUT: {stdout}")
            if stderr:
                self.core_logger.debug(f"STDERR: {stderr}")

        except Exception as e:
            print(f"Failed mfuser key user key copy: {e}")
            self.core_logger.exception("Failed to copy mfuser keys to meas node.")
            if stdout:
                self.core_logger.debug(f"STDOUT: {stdout}")
            if stderr:
                self.core_logger.debug(f"STDERR: {stderr}")
            return False
        return True

    def _download_mfuser_keys(self, private_filename=None, public_filename=None):
        """
        Downloads the mfuser keys.
        """
        if private_filename is None:
            private_filename = self.local_mfuser_private_key_filename
        if public_filename is None:
            public_filename = self.local_mfuser_public_key_filename

        try:
            local_file_path = private_filename
            remote_file_path = self.mfuser_private_key_filename
            stdout, stderr = self.meas_node.download_file(
                local_file_path, remote_file_path
            )  # , retry=3, retry_interval=10):

            local_file_path = public_filename
            remote_file_path = self.mfuser_public_key_filename
            stdout, stderr = self.meas_node.download_file(
                local_file_path, remote_file_path
            )  # , retry=3, retry_interval=10):

        except Exception as e:
            print(f"Download mfuser Keys Failed: {e}")
            self.core_logger.exception("Failed to download mfuser keys.")
            if stdout:
                self.core_logger.debug(f"STDOUT: {stdout}")
            if stderr:
                self.core_logger.debug(f"STDERR: {stderr}")

    def _find_meas_node(self):
        """
        Finds the node named "meas" in the slice and sets the value for class's meas_node

        Returns:
        Boolean: If node found, sets self.meas_node and returns True. If node not found, clears self.meas_node and returns False.
        """
        try:
            for node in self.slice.get_nodes():
                if node.get_name() == self.measurement_node_name:
                    self._meas_node = node
                    return True
        except Exception as e:
            print(f"Find Measure Node Failed: {e}")
            self.core_logger.exception("Failed to find Measure Node")
        self._meas_node = None
        return False

    def _run_on_meas_node(self, service, command, data=None, files=[]):
        """
        Runs one of the commands available for the service on the meas node. Commands are create, update, info, start, stop, remove

        Args:
            service(String): The name of the service.
            command(String): The name of the command to run.
            data(JSON Serializable Object): Data to be passed to a JSON file place in the service's meas node directory.
            files(List of Strings): List of filepaths to be uploaded.

        Returns:
           Dictionary: The stdout & stderr values from running the command formated in dictionary.
        """
        # upload resources
        if data:
            self._upload_service_data(service, data)
        else:
            # Ensure old stale data is remove on meas node
            self._upload_service_data(service, {})
        if files:
            self._upload_service_files(service, files)

        # run command
        return self._run_service_command(service, command)

    def _upload_service_data(self, service, data):
        """
        Uploads the json serializable object data to a json file on the meas node.

        Args:
            service(String): The service to which the data belongs.
        :   data(Object): A JSON Serializable Object
        """

        letters = string.ascii_letters
        try:
            # Create temp file for serialized json data
            randdataname = "mf_service_data_" + "".join(
                random.choice(letters) for i in range(10)
            )
            local_file_path = os.path.join("/tmp", randdataname)
            with open(local_file_path, "w") as datafile:
                # print("dumping data")
                json.dump(data, datafile)

            # Create remote filenames
            final_remote_file_path = os.path.join(
                self.services_directory, service, "data", "data.json"
            )
            remote_tmp_file_path = os.path.join("/tmp", randdataname)

            # upload file
            fa = self.meas_node.upload_file(local_file_path, remote_tmp_file_path)

            # mv file to final location
            cmd = f"sudo mv {remote_tmp_file_path} {final_remote_file_path};  sudo chown mfuser:mfuser {final_remote_file_path}"

            stdout, stderr = self.meas_node.execute(cmd)

            # Remove local temp file.
            os.remove(local_file_path)

        except Exception as e:
            print(f"Service Data Upload Failed: {e}")
            self.core_logger.exception("Upload service data failed")
            if stdout:
                self.core_logger.debug(f"STDOUT: {stdout}")
            if stderr:
                self.core_logger.debug(f"STDERR: {stderr}")
            return False
        return True

    def _upload_service_files(self, service, files):
        """
        Uploads the given local files to the given service's directory on the meas node.
        :param service: Service name for which the files are being upload to the meas node.
        :type service: String
        :param files: List of file paths on local machine.
        :type files: List
        :raises: Exception: for misc failures....
        :return: ?
        :rtype: ?
        """
        letters = string.ascii_letters

        try:
            for file in files:
                # Set src/dst filenames
                # file is local path
                local_file_path = file
                filename = os.path.basename(file)
                final_remote_file_path = os.path.join(
                    self.services_directory, service, "files", filename
                )

                randfilename = "mf_file_" + "".join(
                    random.choice(letters) for i in range(10)
                )
                remote_tmp_file_path = os.path.join("/tmp", randfilename)

                # upload file
                fa = self.meas_node.upload_file(
                    local_file_path, remote_tmp_file_path
                )  # retry=3, retry_interval=10, username="mfuser", private_key="mfuser_private_key")
                cmd = f"sudo mv {remote_tmp_file_path} {final_remote_file_path};  sudo chown mfuser:mfuser {final_remote_file_path};"

                stdout, stderr = self.meas_node.execute(cmd)

        except Exception as e:
            print(f"Service File Upload Failed: {e}")
            self.core_logger.exception("Upload service files failed")
            if stdout:
                self.core_logger.debug(f"STDOUT: {stdout}")
            if stderr:
                self.core_logger.debug(f"STDERR: {stderr}")
            return {"success": False, "message": f"Service file upload failed: {e}"}
        return {"success": True, "message": f"Service file {filename} uploaded successfully."}

    def _upload_service_directory(self, service, local_directory_path, force=False):
        """
        Uploads the given local directory to the given service's directory on the meas node.
        :param service: Service name for which the files are being upload to the meas node.
        :type service: String
        :param local_directory_path: List of file paths on local machine.
        :type local_directory_path: String
        :param force: Whether to overwrite existing directory, if it exists.
        :type force: Bool
        :raises: Exception: for misc failures....
        :return: ?
        :rtype: ?
        """

        local_directory_path = os.path.normpath(local_directory_path)
        if not os.path.dirname(local_directory_path):
            return {"success": False, "message": "The local directory does not exist."}
        local_directory_name = os.path.basename(local_directory_path)

        # Create a tmp spot for directory
        letters = string.ascii_letters
        rand_dir_name = "mf_dir_" + "".join(random.choice(letters) for i in range(10))
        tmp_remote_directory_path = os.path.join("/tmp", rand_dir_name)

        final_remote_directory_path = os.path.join(self.services_directory, service, "files")
        
        stdout, stderr = self.meas_node.execute(f"if test -d {final_remote_directory_path}/{local_directory_name}; then echo 'Directory exists'; else echo 'does not exist'; fi", quiet=True)
        if "Directory exists" in stdout:
            if force:
                stdout, stderr = self.meas_node.execute(f"sudo rm -rf {final_remote_directory_path}/{local_directory_name}")
            else:
                return {"success": False, "message": "The selected directory already exists. Run command with force=True to overwrite it."}
        
        try:
            # upload directory
            self.meas_node.upload_directory(local_directory_path, tmp_remote_directory_path)
            cmd = f"sudo mv -f {tmp_remote_directory_path}/{local_directory_name} {final_remote_directory_path};  sudo chown mfuser:mfuser {final_remote_directory_path}; sudo rm -rf {tmp_remote_directory_path}"
            stdout, stderr = self.meas_node.execute(cmd)

        except Exception as e:
            self.core_logger.exception("Upload service directory failed")
            if stdout: self.core_logger.debug(f"STDOUT: {stdout}")
            if stderr: self.core_logger.debug(f"STDERR: {stderr}")
            return {"success": False, "message": f"Service Directory Upload Failed: {e}"}
        return {"success": True, "message": f"Service Directory {local_directory_name} uploaded successfully."}

    def _run_service_command(self, service, command):
        """
        Runs the given comand for the given service on the meas node.

        Args:
            service(String): Service name for which the command is being run on the meas node.
        :   files(List of ): Command name.

        :raises: Exception: for misc failures....
        Returns:
            Dictionary: Resulting output of comand JSON converted to dictionary.

        """

        try:
            full_command = f"sudo -u mfuser python3 {self.services_directory}/{service}/{command}.py"
            stdout, stderr = self.meas_node.execute(
                full_command, quiet=True
            )  # retry=3, retry_interval=10, username="mfuser", private_key="mfuser_private_key"
            self.core_logger.debug(f"STDOUT: {json.dumps(stdout, indent=2)}")
        except ValueError as e:
            self.core_logger.debug(f"STDOUT: {stdout}")
        except Exception as e:
            print(f"Service Commnad Run Failed: {e}")
        #         print(type(stdout))
        #         print(stdout)
        #         print(stderr)
        try:
            # Convert the json string to a dict
            jsonstr = stdout
            # remove non json string
            jsonstr = jsonstr[jsonstr.find("{") : jsonstr.rfind("}") + 1]
            # Need to "undo" what the exceute command did
            jsonstr = jsonstr.replace("\n", "\\n")
            # print(jsonstr)
            ret_data = json.loads(jsonstr)
            return ret_data
            # TODO add stderr to return value?
        except Exception as e:
            print("Unable to convert returned comand json.")
            # TODO create dictionary with malformed data.
            print("STDOUT: ")
            print(stdout)
            print("STDERR: ")
            print(stderr)
            print(f"Fail: {e}")

            self.core_logger.exception("Unable to convert returned comand json.")
            if stdout:
                self.core_logger.debug(f"STDOUT: {stdout}")
            if stderr:
                self.core_logger.debug(f"STDERR: {stderr}")

        return {}

    def _download_service_file(self, service, filename, local_file_path=""):
        """
        Downloads service files from the meas node and places them in the local storage directory.
        :param service: Service name
        :type service: String
        :param filename: The filename to download from the meas node.
        :param local_file_path: Optional filename for local saved file. If not given, file will be in default slice directory.# Fri Sep 09 2022 14:30
        :type local_file_path: String
        """

        if not local_file_path:
            local_file_path = os.path.join(
                self.local_slice_directory, service, filename
            )
            # ensure local directory exists
            local_dir_path = os.path.dirname(local_file_path)
            if not os.path.exists(local_dir_path):
                os.makedirs(local_dir_path)

        #
        #  Download a file from a service directory
        # Probably most useful for grabbing output from a command run.
        # TODO figure out how to name/where to put file locally
        try:
            # local_file_path = os.path.join(self.local_slice_directory, service, filename)
            remote_file_path = os.path.join(self.services_directory, service, filename)
            file_attributes = self.meas_node.download_file(
                local_file_path, remote_file_path
            )  # , retry=3, retry_interval=10):
            return {"success": True, "filename": local_file_path, "message": "uploaded " + filename + " successfully."}
        except Exception as e:
            self.core_logger.exception()
            return {"success": False, "message": f"Download service file Fail: {e}"}

    def _clone_mf_repo(self):
        """
        Clones the MeasurementFramework  git repository to /home/mfuser/mf_git on the meas node.
        """
        msg = f"Cloning Measurement Framework Repository from github.com..."
        self.core_logger.debug(msg)
        print(msg)

        cmd = f"sudo -u mfuser git clone -q -b {self.mf_repo_branch} https://github.com/fabric-testbed/MeasurementFramework.git /home/mfuser/mf_git"
        stdout, stderr = self.meas_node.execute(cmd, quiet=True)

        msg = f"Cloning Measurement Framework Repository from github.com done."
        self.core_logger.debug(msg)
        print(msg)


        if stdout:
            self.core_logger.debug(f"STDOUT: {stdout}")
        if stderr:
            if "already exists and is not an empty directory" not in stderr:
                msg = (
                    f"Cloning Measurement Framework Repository from github.com Failed."
                )
                self.core_logger.error(msg)
                self.core_logger.error(f"STDERR: {stderr}")
                return False
        return True

    def _run_bootstrap_script(self):
        """
        Run the initial bootstrap script in the meas node mf repo.
        """
        msg = f"Starting Bootstrap Process on Measure Node (bash script)..."
        self.core_logger.debug(msg)
        print(msg)

        cmd = f"sudo -u mfuser /home/mfuser/mf_git/instrumentize/experiment_bootstrap/bootstrap.sh"

        stdout, stderr = self.meas_node.execute(cmd, quiet=True)

        msg = f"Bootstrap Process on Measure Node (bash script) done."
        self.core_logger.debug(msg)
        print(msg)

        if stdout:
            self.core_logger.debug(f"STDOUT: {stdout}")
        if stderr:
            self.core_logger.info(f"STDERR: {stderr}")

    def _run_bootstrap_ansible(self):
        """
        Run the initial bootstrap ansible scripts in the meas node mf repo.
        """
        msg = f"Starting Bootstrap Process on Measure Node (Ansible Playbook)..."
        self.core_logger.debug(msg)
        print(msg)

        cmd = (
            f"sudo cp /home/mfuser/mf_git/instrumentize/experiment_bootstrap/ansible.cfg /home/mfuser/services/common/ansible.cfg;"
            f"sudo chown mfuser:mfuser /home/mfuser/services/common/ansible.cfg;"
            f"sudo -u mfuser python3 /home/mfuser/mf_git/instrumentize/experiment_bootstrap/bootstrap_playbooks.py;"
        )
        stdout, stderr = self.meas_node.execute(cmd, quiet=True)

        msg = f"Bootstrap Process on Measure Node (Ansible Playbook) done."
        self.core_logger.debug(msg)
        print(msg)

        if stdout:
            
            try:
                self.core_logger.debug(f"STDOUT: {json.dumps(stdout, indent=2)}")
            except ValueError as e:
                self.core_logger.debug(f"STDOUT: {stdout}")
            if "Bootstrap playbook install failed" in stdout:
                print("Bootstap ansible scripts Failed. See logs for details")   
                return False 
        if stderr:
            self.core_logger.info(f"STDERR: {stderr}")

        print("Bootstrap ansible scripts done")
        return True

    ############################
    # Calls made as slice user
    ###########################
    def get_bootstrap_status(self, force=True):
        """
        Returns the bootstrap status for the slice. Default setting of force will always download the most recent file from the meas node. The downloaded file will be stored locally for future reference at self.bootstrap_status_file.

        Args:
            force(Boolean): If downloaded file already exists locally, it will not be downloaded unless force is True. .
        Returns:
            Dictionary: Bootstrap dict if any type of bootstraping has occured, Empty dict otherwise.
        """
        if force or not os.path.exists(self.bootstrap_status_file):
            download_success, download_msg = self._download_bootstrap_status()
            if not download_success:
                return {"msg":download_msg }

        if os.path.exists(self.bootstrap_status_file):
            if os.stat(self.bootstrap_status_file).st_size == 0:
                return {}
                # workaround download creating empty file if file not found
            with open(self.bootstrap_status_file) as bsf:
                try:
                    bootstrap_dict = json.load(bsf)
                    # print(bootstrap_dict)
                    if bootstrap_dict:
                        return bootstrap_dict
                    else:
                        return {}
                except Exception as e:
                    print(f"Bootstrap failed to decode")
                    print(f"Fail: {e}")
                    return {}
        else:
            return {}

    def _clear_bootstrap_status(self):
        """
        Deletes the local and remote copy of the bootstrap_status files. This will then allow a rerunning of the init bootstrapping process.
        This is mainly intended for testing/debugging.
        Note that nothing will be removed from the nodes.
        """

        # Delete local copy
        if os.path.exists(self.bootstrap_status_file):
            os.remove(self.bootstrap_status_file)

        # Delete measurement node copy
        try:
            full_command = "rm bootstrap_status.json"
            stdout, stderr = self.meas_node.execute(full_command)
            self.core_logger.info("Removed remote bootstrap_status file.")
        except Exception as e:
            print(f"rm bootstrap_status.json Failed: {e}")
            self.core_logger.exception(f"rm bootstrap_status.json Failed: {e}")
            if stdout: self.core_logger.debug(f"STDOUT: {stdout}")
            if stderr: self.core_logger.debug(f"STDERR: {stderr}")

    def _download_bootstrap_status(self):
        """
        Downloads the bootstrap file from the meas_node. The downloaded file will be stored locally for future reference at self.bootstrap_status_file.

        Returns:
            Boolean: True if bootstrap file downloaded, False otherwise.
        """
        try:
            local_file_path = self.bootstrap_status_file
            remote_file_path = os.path.join("bootstrap_status.json")
            # print(local_file_path)
            # print(remote_file_path)
            file_attributes = self.meas_node.download_file(
                local_file_path, remote_file_path, retry=1
            )  # , retry=3, retry_interval=10): # note retry is really tries
            # print(file_attributes)

            return True, ""
        except FileNotFoundError:
            pass
            # Most likely the file does not exist because it has not yet been created. So we will ignore this exception.
            self.core_logger.warning("Bootstrap file not found on Measure Node")
            return True, "File not found"
        except Exception as e:
            msg = f"Bootstrap download has failed. Fail: {e}"
            #print("Bootstrap download has failed.")
            #print(f"Fail: {e}")
            #return {"msg":msg, "success":False}
            return False, msg
        #return {}

    def get_mfuser_private_key(self, force=True):
        """
        Downloads the mfuser private key. Default setting of force will always download the most recent file from the meas node. The downloaded file will be stored locally for future reference at self.local_mfuser_private_key_filename.


        Args:
            force(Boolean): If downloaded file already exists locally, it will not be downloaded unless force is True.
        Returns:
            Boolean: True if file is found, false otherwise.
        """
        if force or not os.path.exists(self.local_mfuser_private_key_filename):
            self._download_mfuser_private_key()

        if os.path.exists(self.local_mfuser_private_key_filename):
            return True
        else:
            return False

    def _download_mfuser_private_key(self):
        """
        Downloads the mfuser private key from the meas node. The downloaded file will be stored locally for future reference at self.local_mfuser_private_key_filename.

        Returns:
            Boolean: True if key file downloaded, False otherwise.
        """
        try:
            local_file_path = self.local_mfuser_private_key_filename
            remote_file_path = self.mfuser_private_key_filename
            file_attributes = self.meas_node.download_file(
                local_file_path, remote_file_path
            )  # , retry=3, retry_interval=10):
            # print(file_attributes)
            return True
        except Exception as e:
            print(f"Download mfuser private key Failed: {e}")
            self.core_logger.error(f"Download mfuser private key Failed: {e}")
        return False

    def _update_bootstrap(self, key, value):
        """
        Updates the given key to the given value in the bootstrap_status.json file on the meas node.
        """
        bsf_dict = self.get_bootstrap_status()
        # self.download_bootstrap_status()
        # bsf_dict = {}
        bsf_dict[key] = value

        with open(self.bootstrap_status_file, "w") as bsf:
            json.dump(bsf_dict, bsf)

        try:
            local_file_path = self.bootstrap_status_file
            remote_file_path = os.path.join("bootstrap_status.json")
            # print(local_file_path)
            # print(remote_file_path)
            file_attributes = self.meas_node.upload_file(
                local_file_path, remote_file_path
            )  # , retry=3, retry_interval=10):
            # print(file_attributes)

            return True

        except Exception as e:
            print("Bootstrap upload has failed.")
            print(f"Fail: {e}")
        return False

    def download_log_file(self, service, method):
        """
        Download the log file for the given service and method.
        Downloaded file will be stored locally for future reference.
        :param service: The name of the service.
        :type service: String
        :param method: The method name such as create, update, info, start, stop, remove.
        :type method: String
        :return: Writes file to local storage and returns text of the log file.
        :rtype: String
        """
        # Ensure service inputted is valid
        if service not in self._get_service_list():
            print("You must specify a valid service")
            return {"success": False}

        try:
            local_file_path = os.path.join(self.local_slice_directory, f"{method}.log")
            remote_file_path = os.path.join(
                "/", "home", "mfuser", "services", service, "log", f"{method}.log"
            )
            # print(local_file_path)
            # print(remote_file_path)
            file_attributes = self.meas_node.download_file(
                local_file_path, remote_file_path, retry=1
            )  # , retry=3, retry_interval=10): # note retry is really tries
            # print(file_attributes)

            with open(local_file_path) as f:
                log_text = f.read()
                return local_file_path, log_text

        except Exception as e:
            print("Service log download has failed.")
            print(f"Downloading service log file has Failed. It may not exist: {e}")
            return "", ""

    def download_service_file(self, service, filename, local_file_path=""):
        """
        Downloads service files from the meas node and places them in the local storage directory.
        Denies the user from downloading files anywhere outside the service directory
        :param service: Service name
        :type service: String
        :param filename: The filename to download from the meas node.
        :param local_file_path: Optional filename for local saved file.
        :type local_file_path: String
        """
        # Ensure service inputted is valid
        if service not in self._get_service_list():
            print("You must specify a valid service")
            return {"success": False}

        # Ensure remote file path will be within the service directory.
        if ".." in filename:
            print("Error: Remote file must be within the service directory.")
            return {"success": False}

        # Call the internal download service file function
        output = self._download_service_file(service, filename, local_file_path)
        print(output)
        return output

    def upload_service_files(self, service, files):
        """
        Uploads the given local files to the given service's directory on the meas node.
        Denies the user from uploading files anywhere outside the service directory
        :param service: Service name for which the files are being upload to the meas node.
        :type service: String
        :param files: List of file paths on local machine.
        :type files: List
        :raises: Exception: for misc failures....
        :return: ?
        :rtype: ?
        """

        # Ensure service inputted is valid
        if service not in self._get_service_list():
            output = {"success": False, "message": "You must specify a valid service"}
            print(output)
            return output

        # Call the internal upload service file function
        output = self._upload_service_files(service, files)
        print(output)
        return output

    def upload_service_directory(self, service, local_directory_path, force=False):
        """
        Uploads the given local directory to the given service's directory on the meas node.
        :param service: Service name for which the files are being upload to the meas node.
        :type service: String
        :param local_directory_path: Directory path on local machine.
        :type local_directory_path: String
        :param force: Whether to overwrite existing directory, if it exists.
        :type force: Bool
        :raises: Exception: for misc failures....
        :return: ?
        :rtype: ?
        """

        # Ensure service inputted is valid
        if service not in self._get_service_list():
            output = {"success": False, "message": "You must specify a valid service"}
            print(output)
            return output

        # Call the internal upload service directory function
        output = self._upload_service_directory(service, local_directory_path, force)
        print(output)
        return output
