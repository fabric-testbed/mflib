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

from fabrictestbed_extensions.fablib.fablib import fablib
import json
from mflib.mflib import MFLib
import time


class ImportTool:
    """
    Parent class for import classes (Elk and Prometheus)
    """

    def __init__(self, node, service, git_repo_path='/home/ubuntu/mf-data-import-containers'):
        """
        Constructor
        Args:
            node (fablib.node): Fabric node from slice.get_node()
            service (str): Name of the service used (Elk or Prometheus)
            git_repo_path (str): Path to where the git repo directory is on the node
        """
        self.repo_path = git_repo_path
        self.node = node
        self.service = service
    
    def setup_docker_app(self, node_name):
        """
        Runs the 3 commands needed to set up the docker-compose app
        """
        self.install_docker()
        #self.setup_nat64(node_name)
        self.clone_repository()

    def install_docker(self):
        """
        Installs Docker and Docker-Compose then prints their versions.
        """
        commands = [
            'sudo apt-get update',
            'sudo apt-get install docker -y',
            'sudo apt-get install docker-compose -y',
            'sudo docker -v',
            'sudo docker-compose -v'
        ]
        try:
            for command in commands:
                self.node.execute(command)
        except Exception as e:
            print(f"Fail: {e}")

    def setup_nat64(self, node_name):
        """
        NAT64 script to allow accessing IPV4 and IPV6 sites.
        This function should be removed when NAT64 is fixed.
        """
        commands = [
            f"sudo sed -i '1s/^/0.0.0.0 {node_name}\\n/' /etc/hosts",
            "sudo sed -i '/nameserver/d' /etc/resolv.conf",
            "sudo sh -c 'echo nameserver 2a00:1098:2c::1 >> /etc/resolv.conf'",
            "sudo sh -c 'echo nameserver 2a01:4f8:c2c:123f::1 >> /etc/resolv.conf'",
            "sudo sh -c 'echo nameserver 2a00:1098:2b::1 >> /etc/resolv.conf'"
        ]
        for command in commands:
            try:
                self.node.execute(command)
            except Exception as e:
                print(f"Fail: {e}")

    def clone_repository(self):
        """
        Clones the data-import docker-container repository from GitHub.
        """
        try:

            self.node.execute(
                f'sudo git clone https://github.com/fabric-testbed/mf-data-import-containers.git {self.repo_path}')
        except Exception as e:
            print(f"Fail: {e}")

    def start_docker(self):
        """
        Starts the docker-compose app for the current service (Elk or Prometheus).
        """
        try:
            self.node.execute(f'sudo docker-compose -f {self.repo_path}/{self.service}/docker-compose.yml up -d')
        except Exception as e:
            print(f"Fail: {e}")

    def stop_docker(self):
        """
        Stops the docker-compose app for the current service (Elk or Prometheus).
        """
        try:
            self.node.execute(f'sudo docker-compose -f {self.repo_path}/{self.service}/docker-compose.yml down')
        except Exception as e:
            print(f"Fail: {e}")
            
    def generate_scp_upload_command(self, snapshot_name, directory_path, ssh_config="ssh_config", private_key="slice_key"):
        """
        Creates the command to upload your snapshot file to the node VIA SCP.
        Args:
            snapshot_name (str): Name of snapshot file (including extension)
            directory_path (str): Path to directory containing snapshot file
            ssh_config (str, optional): Path to Fabric SSH config file
            private_key (str, optional): Path to Fabric slice private key file
        Returns:
            String : SCP command string or error string.
        """
        username = self.node.get_username()
        ip = self.node.get_management_ip()
        scp_command = f"scp -F {ssh_config} -i {private_key} {directory_path}/{snapshot_name} {username}@\[{ip}]:/tmp/{snapshot_name}"
        return scp_command


class ElkExporter(MFLib):
    """
    Tool for Exporting ELK snapshots.
    """
    def __init__(self, slice_name="", local_storage_directory="/tmp/mflib", node_name="meas-node"):
        """
        Constructor
        Args:
            slice_name (fablib.slice): Slice object name already set with experiment topology.
            local_storage_directory (str, optional): Directory where local data will be stored.
                Defaults to "/tmp/mflib".
            node_name (str): Name of the measurement node.
                Defaults to meas-node
        """
        super().__init__(slice_name, local_storage_directory)
        try:
            self.node = self.slice.get_node(name=node_name)
        except Exception as e:
            print("Yeah")
            print(f"Fail: {e}")

    def create_repository(self, repository_name):
        self._ensure_dir_permissions()
        """
        Registers a snapshot repo using ELK rest api
        Args:
            repository_name(str): name of the repo to be created.
        """
        snapshot_directory = "/usr/share/elasticsearch/backup"
        cmd = f'curl -X PUT "http://localhost:9200/_snapshot/{repository_name}?pretty" -H "Content-Type: application/json" -d \'{{ "type": "fs", "settings": {{ "location": "{snapshot_directory}" }} }}\''
        try:
            self.node.execute(cmd)
        except Exception as e:
            print(f"Fail: {e}")

    def create_snapshot(self, repository_name, snapshot_name):
        """
        Creates a snapshot repository using elk rest api
        Args:
            repository_name(str): name of the repository
            snapshot_name(str): name of the snapshot to be created
        """
        cmd = f'curl -X PUT "http://localhost:9200/_snapshot/{repository_name}/{snapshot_name}?wait_for_completion=true&pretty" -H "Content-Type: application/json" -d \'"ignore_unavailable": true, "include_global_state": false\''
        try:
            self.node.execute(cmd)
        except Exception as e:
            print(f"Fail: {e}")

    def export_snapshot_tar(self, snapshot_name):
        """
        Compresses and exports an ELK snapshot as a tar file.
        Args:
            snapshot_name(str): name of the snapshot to be exported
        """
        self._ensure_dir_permissions()
        commands = [
            'sudo mkdir -p /home/mfuser/services/elk/files/snapshots',
            f'sudo tar -cvf /home/mfuser/services/elk/files/snapshots/{snapshot_name}.tar -C /var/lib/docker/volumes/elk_snapshotbackup .',
        ]
        for command in commands:
            try:
                self.node.execute(command)
            except Exception as e:
                print(f"Fail: {e}")
        self.view_snapshot_directory()

    def _ensure_dir_permissions(self):
        """
        Gives the ELK docker volume permission to be exported.
        """
        commands = [
            'sudo chown -R 1000:1000 /var/lib/docker/volumes/elk_snapshotbackup',
            'sudo chown -R 1000:1000 /var/lib/docker/volumes/elk_snapshotbackup/_data',
        ]
        for command in commands:
            try:
                self.node.execute(command)
            except Exception as e:
                print(f"Fail: {e}")

    def view_indices(self):
        """
        Show existing elk indices using elk rest api
        """
        cmd = f'curl "http://localhost:9200/_cat/indices?v"'
        try:
            self.node.execute(cmd)
        except Exception as e:
            print(f"Fail: {e}")


    def view_repository(self, repository_name):
        """
        Show existing elk repository using elk rest api
        """
        cmd = f'curl -X GET "http://localhost:9200/_cat/snapshots/{repository_name}?pretty"'
        try:
            self.node.execute(cmd)
        except Exception as e:
            print(f"Fail: {e}")

    def view_snapshot(self, repository_name, snapshot_name):
        """
        Show elk snapshot inside repository using elk rest api
        """
        cmd = f'curl -X GET "http://localhost:9200/_snapshot/{repository_name}/{snapshot_name}?pretty"'
        try:
            self.node.execute(cmd)
        except Exception as e:
            print(f"Fail: {e}")

    def view_snapshot_directory(self):
        """
        Show ELK tar files available inside snapshot directory on meas_node
        """
        commands = [
            'echo snapshots in directory on measurement node:',
            'ls /home/mfuser/services/elk/files/snapshots/'
        ]
        for command in commands:
            try:
                self.node.execute(command)
            except Exception as e:
                print(f"Fail: {e}")

    def generate_scp_download_command(self, snapshot_name, local_destination, ssh_config="ssh_config", private_key="slice_key"):
        """
        Creates the command to download your snapshot file from the meas_node to local pc.
        Args:
            snapshot_name (str): Name of snapshot file (including extension)
            local_destination (str): Path to where you want to place snapshot file
            ssh_config (str, optional): Path to Fabric SSH config file
            private_key (str, optional): Path to Fabric slice private key file
        Returns:
            String : SCP command string or error string.
        """
        username = self.node.get_username()
        ip = self.node.get_management_ip()
        scp_command = f"scp -F {ssh_config} -i {private_key} {username}@\[{ip}]:/home/mfuser/services/elk/files/snapshots/{snapshot_name}.tar {local_destination}"
        return scp_command


class PrometheusExporter(MFLib):
    """
    Tool for Exporting Prometheus snapshots.
    """
    def __init__(self, slice_name, local_storage_directory="/tmp/mflib", node_name="meas-node"):
        """
        Constructor
        Args:
            slice_name (fablib.slice): Slice object name already set with experiment topology.
            local_storage_directory (str, optional): Directory where local data will be stored.
                Defaults to "/tmp/mflib".
            node_name (str): Name of the measurement node.
                Defaults to meas-node
        """
        super().__init__(slice_name, local_storage_directory)
        try:
            self.node = self.slice.get_node(name=node_name)
        except Exception as e:
            print(f"Fail: {e}")

    def create_snapshot(self, user, password):
        """
        Creates a prometheus snapshot using the rest api.
        Requires Prometheus credentials to use.
        Args:
            user (str): Prometheus username
            password (str): Prometheus password
        """
        try:
            stdout = self.node.execute(
                f'sudo curl -k -u {user}:{password} -XPOST https://localhost:9090/api/v1/admin/tsdb/snapshot?skip_head=false')
            return json.loads(stdout[0])["data"]["name"]
        except Exception as e:
            print(f"Fail: {e}")

    def export_snapshot_tar(self, snapshot_name):
        """
        Exports Prometheus snapshot file out of docker into meas_node
        Args:
            snapshot_name (str): Name of snapshot to export
        """
        commands = [
            'sudo mkdir -p /home/mfuser/services/prometheus/files/snapshots',
            f'sudo tar -cvf /home/mfuser/services/prometheus/files/snapshots/{snapshot_name}.tar -C /opt/data/fabric_prometheus/prometheus/snapshots .',
        ]
        for command in commands:
            try:
                self.node.execute(command=command, quiet=True)
            except Exception as e:
                return f"Fail: {e}"
        return f"Successfully exported {snapshot_name} to /home/mfuser/services/prometheus/files/snapshots/"

    def view_snapshot_directory(self):
        """
        Show Prometheus tar files available inside snapshot directory on meas_node
        """
        commands = [
            'echo snapshots in directory on measurement node:',
            'ls /home/mfuser/services/prometheus/files/snapshots/'
        ]
        for command in commands:
            try:
                self.node.execute(command)
            except Exception as e:
                print(f"Fail: {e}")

    def generate_scp_download_command(self, snapshot_name, local_destination, ssh_config="ssh_config", private_key="slice_key"):
        """
        Creates the command to download your snapshot file from the meas_node to local pc.
        Args:
            snapshot_name (str): Name of snapshot file (including extension)
            local_destination (str): Path to where you want to place snapshot file
            ssh_config (str, optional): Path to Fabric SSH config file
            private_key (str, optional): Path to Fabric slice private key file
        Returns:
            String : SCP command string or error string.
        """
        username = self.node.get_username()
        ip = self.node.get_management_ip()
        scp_command = f"scp -F {ssh_config} -i {private_key} {username}@\[{ip}]:/home/mfuser/services/prometheus/files/snapshots/{snapshot_name}.tar {local_destination}"
        return scp_command


class ElkImporter(ImportTool):
    """
    Tool for Importing ELK snapshots.
    """
    def __init__(self, slice_name, node_name, git_repo_path='/home/ubuntu/mf-data-import-containers'):
        """
        Constructor
        Args:
            slice_name (fablib.slice): Slice object name already set with experiment topology.
            node_name (str): Name of the measurement node.
                Defaults to meas-node
            git_repo_path (str, optional): Directory where local data will be stored.
                Defaults to "/home/ubuntu/mf-data-import-containers".
        """
        self.slice_name = slice_name
        try:
            self.slice = fablib.get_slice(name=self.slice_name)
        except Exception as e:
            print(f"Fail: {e}")
        try:
            self.node = self.slice.get_node(name=node_name)
        except Exception as e:
            print(f"Fail: {e}")
        super().__init__(self.node, "elk", git_repo_path)
        
    def upload_snapshot(self, snapshot_file_name):
        """
        Uploads snapshot tar file into meas_node tmp directory.
        Tar file must be in snapshots directory on Jupyter Hub.
        Args:
        snapshot_file_name(str): ELK snapshot tar file name
        """
        try:
            self.node.execute(f"echo uploading {snapshot_file_name} to measurement node..")
            self.node.upload_file(f"./snapshots/{snapshot_file_name}", f'/tmp/{snapshot_file_name}')
        except Exception as e:
            print(f"Fail: {e}")


    def import_snapshot(self, snapshot_file_name):
        """
        Extracts snapshot from tar file and places snapshot in new data directory.
        Args:
        snapshot_file_name(str): ELK snapshot file name
        """

        commands = [
            "echo 'Creating imported_data directory..'",
            f"sudo mkdir {self.repo_path}/{self.service}/imported_data",
            "echo 'Moving snapshot file..'",
            f"sudo mv /tmp/{snapshot_file_name} {self.repo_path}/{self.service}/snapshots/",
            "echo 'Untarring snapshot data into shared docker volume..'",
            f"sudo tar -xvf {self.repo_path}/{self.service}/snapshots/{snapshot_file_name} -C {self.repo_path}/{self.service}/imported_data"
        ]
        for command in commands:
            try:
                self.node.execute(command)
            except Exception as e:
                print(f"Fail: {e}")

    def register_repository(self, repository_name):
        """
            You must register a repository before you can take or restore snapshots.
            Args:
                repository_name(str): Name of repository to register
        """
        cmd = f'curl -X PUT -H "Content-Type: application/json" -d \'{{"type": "fs", "settings": {{"location": "/usr/share/elasticsearch/imported_data/_data", "compress": true }} }}\' http://localhost:9200/_snapshot/{repository_name}'
        try:
            self.node.execute(cmd)
        except Exception as e:
            print(f"Fail: {e}")

    def restore_snapshot(self, repository_name, snapshot_name):
        """
        Deletes indices currently on ELK and replaces with desired snapshot data
        Args:
            repository_name(str): ELK Repository name
            snapshot_name(str): ELK Snapshot name
        """
        cmds = ['curl -X DELETE "http://localhost:9200/_all"',
                f'curl -X POST "http://localhost:9200/_snapshot/{repository_name}/{snapshot_name}/_restore?pretty" -H "Content-Type: application/json" -d \'{{"indices": "*","rename_pattern": "(.+)","rename_replacement": "restored-$1"}}\'']
        for cmd in cmds:
            try:
                self.node.execute(cmd)
            except Exception as e:
                print(f"Fail: {e}")

    def remove_data(self):
        """
        Deletes the docker volume and snapshot directory so that you can add new data.
        """
        commands = [
            'sudo docker volume rm elk_es-data',
            f'sudo rm -rf {self.repo_path}/{self.service}/imported_data/*'
        ]
        try:
            for command in commands:
                self.node.execute(command)
        except Exception as e:
            print(f"Fail: {e}")

    def view_indices(self):
        """
        show existing elk indices using elk rest api
        """
        cmd = f'curl "http://localhost:9200/_cat/indices?v"'
        try:
            self.node.execute(cmd)
        except Exception as e:
            print(f"Fail: {e}")

    def view_repository(self, repository_name):
        """
        show existing elk repository using elk rest api
        """
        cmd = f'curl -X GET "http://localhost:9200/_cat/snapshots/{repository_name}?pretty"'
        try:
            self.node.execute(cmd)
        except Exception as e:
            print(f"Fail: {e}")

    def view_snapshot(self, repository_name, snapshot_name):
        """
        show elk snapshot inside repository using elk rest api
        """
        cmd = f'curl -X GET "http://localhost:9200/_snapshot/{repository_name}/{snapshot_name}?pretty"'
        try:
            self.node.execute(cmd)
        except Exception as e:
            print(f"Fail: {e}")


class PrometheusImporter(ImportTool):
    """
    Tool for Importing Prometheus snapshots.
    """
    def __init__(self, slice_name, node_name, git_repo_path='/home/ubuntu/mf-data-import-containers'):
        """
        Constructor
        Args:
            slice_name (fablib.slice): Slice object name already set with experiment topology.
            node_name (str): Name of the measurement node.
                Defaults to meas-node
            git_repo_path (str, optional): Directory where local data will be stored.
                Defaults to "/home/ubuntu/mf-data-import-containers".
        """
        self.slice_name = slice_name
        try:
            self.slice = fablib.get_slice(name=self.slice_name)
        except Exception as e:
            print(f"Fail: {e}")
        try:
            self.node = self.slice.get_node(name=node_name)
        except Exception as e:
            print(f"Fail: {e}")
        super().__init__(self.node, "prometheus", git_repo_path)

    def import_snapshot(self, snapshot_file_name):
        """
        Uploads snapshot file into correct place on meas_node then runs import_snapshot.sh to import snapshot.
        Args:
        snapshot_file_name(str): Prometheus snapshot file name
        """
        commands = [
            "echo 'Importing snapshot into Prometheus..'",
            f"sudo {self.repo_path}/{self.service}/import_snapshot.sh /tmp/{snapshot_file_name} {self.repo_path}/{self.service}/snapshots"
        ]
        for command in commands:
            try:
                self.node.execute(command)
            except Exception as e:
                print(f"Fail: {e}")

    def remove_data(self):
        """
        Deletes the docker volume and snapshot directory so that you can add new data.
        """
        commands = [
            'sudo docker volume rm prometheus_prom_data',
            f'sudo rm -rf {self.repo_path}/{self.service}/snapshots'
        ]
        try:
            for command in commands:
                self.node.execute(command)
        except Exception as e:
            print(f"Fail: {e}")
