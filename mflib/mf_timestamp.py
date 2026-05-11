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
from mflib import mflib
import os
import sys
import time
import requests
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


class mf_timestamp:
    """
    Creates precision timestamps.
    """

    def __init__(self, slice, container_name):
        """
        Constructor. Builds Manager for mf_timestamp object.
        """
        super().__init__()
        self.slice_name = slice.get_name()
        self.container_name = container_name
        try:
            self.slice = slice
        except Exception as e:
            print(f"Fail: {e}")

    def record_packet_timestamp(
        self,
        node,
        name,
        interface,
        ipversion,
        protocol,
        duration,
        host=None,
        port=None,
        verbose=False,
    ):
        """
        Records packet timestamp by calling timestamptool.py in the timestamp docker container running on the node
        Args:
            node(fablib.node): fabric node on which the timestamp docker container is running
            name(str): name of the packet timestamp experiment
            interface(str): which interface tcpdump captures the packets
            ipversion(str): IPv4 or IPv6
            protocol(str): tcp or udp
            duration(str): seconds to run tcpdump
            host(str, optional): host for tcpdump command
            port(str, optional): port for tcpdump command
        """
        try:
            node = self.slice.get_node(name=node)
        except Exception as e:
            print(f"Fail: {e}")
        base_cmd = f"sudo docker exec -i {self.container_name} python3 /root/services/timestamp/service_files/timestamptool.py record packet"
        name_cmd = f"-n {name}"
        interface_cmd = f"-i {interface}"
        ipversion_cmd = f"-ipv {ipversion}"
        protocol_cmd = f"-proto {protocol}"
        duration_cmd = f"-durn {duration}"
        # storage_cmd= f"-stg {storage}"
        cmd = f"{base_cmd} {name_cmd} {interface_cmd} {ipversion_cmd} {protocol_cmd} {duration_cmd} "
        if host:
            host_cmd = f"-host {host}"
            cmd = f"{cmd} {host_cmd}"
        if port:
            port_cmd = f"-port {port}"
            cmd = f"{cmd} {port_cmd}"
        if verbose is True:
            verbose_cmd = f"-v"
            cmd = f"{cmd} {verbose_cmd}"
        print(f"The docker command is: {cmd}")
        stdout, stderr = node.execute(cmd)

    def record_event_timestamp(
        self, node, name, event, description=None, verbose=False
    ):
        """
        Records event timestamp by calling timestamptool.py in the timestamp docker container running on the node
        Args:
            node(fablib.node): fabric node on which the timestamp docker container is running
            name(str): name of the event timestamp experiment
            event(str): name of the event
            description(str, optional): description of the event
        """
        try:
            node = self.slice.get_node(name=node)
        except Exception as e:
            print(f"Fail: {e}")
        base_cmd = f"sudo docker exec -i {self.container_name} python3 /root/services/timestamp/service_files/timestamptool.py record event"
        name_cmd = f"-n {name}"
        event_cmd = f"-event {event}"
        cmd = f"{base_cmd} {name_cmd} {event_cmd} "
        if description:
            desc_cmd = f"-desc {description}"
            cmd = f"{cmd} {desc_cmd}"
        if verbose is True:
            verbose_cmd = f"-v"
            cmd = f"{cmd} {verbose_cmd}"
        print(f"The docker command is: {cmd}")
        stdout, stderr = node.execute(cmd)

    def get_packet_timestamp(self, node, name, verbose=False):
        """
        Prints the collected packet timestamp by calling timestamptool.py in the timestamp docker container running on the node
        It reads the local packet timestamp file and prints the result
        Args:
            node(fablib.node): fabric node on which the timestamp docker container is running
            name(str): name of the packet timestamp experiment
        """
        try:
            node = self.slice.get_node(name=node)
        except Exception as e:
            print(f"Fail: {e}")
        base_cmd = f"sudo docker exec -i {self.container_name} python3 /root/services/timestamp/service_files/timestamptool.py get packet"
        name_cmd = f"-n {name}"
        # storage_cmd= f"-stg {storage}"
        cmd = f"{base_cmd} {name_cmd} "
        if verbose is True:
            verbose_cmd = f"-v"
            cmd = f"{cmd} {verbose_cmd}"
        # print (f"The docker command is {cmd}")
        stdout, stderr = node.execute(cmd)
        json_obj = json.loads(str(stdout))
        return json_obj

    def get_event_timestamp(self, node, name, verbose=False):
        """
        Prints the collected event timestamp by calling timestamptool.py in the timestamp docker container running on node
        It reads the local event timestamp file and prints the result
        Args:
            node(fablib.node): fabric node on which the timestamp docker container is running
            name(str): name of the event timestamp experiment
        """
        try:
            node = self.slice.get_node(name=node)
        except Exception as e:
            print(f"Fail: {e}")
        base_cmd = f"sudo docker exec -i {self.container_name} python3 /root/services/timestamp/service_files/timestamptool.py get event"
        name_cmd = f"-n {name}"
        # storage_cmd= f"-stg {storage}"
        cmd = f"{base_cmd} {name_cmd}"
        if verbose is True:
            verbose_cmd = f"-v"
            cmd = f"{cmd} {verbose_cmd}"
        # print (f"The docker command is {cmd}")
        stdout, stderr = node.execute(cmd)
        json_obj = json.loads(str(stdout))
        return json_obj

    def download_timestamp_file(self, node, data_type, local_file, bind_mount_volume):
        """
        Downloads the collected timestamp file to Jupyterhub
        Use fablib node.download_file() to download the timestamp data file that can be accessed from the bind mount volume
        Args:
            node(fablib.node): fabric node on which the timestamp docker container is running
            data_type(str): packet_timestamp or event timestamp
            local_file(str): path on Jupyterhub for the download file
            bind_mount_volume(str): bind mount volume of the running timestamp docker container
        """
        try:
            node = self.slice.get_node(name=node)
        except Exception as e:
            print(f"Fail: {e}")
        if data_type == "packet_timestamp":
            remote_file = f"{bind_mount_volume}/packet_output.json"
        elif data_type == "event_timestamp":
            remote_file = f"{bind_mount_volume}/event_output.json"
        else:
            return "wrong data type"
        node.download_file(local_file_path=local_file, remote_file_path=remote_file)
        r = self.read_from_local_file(file=local_file)

    def read_from_local_file(self, file):
        """
        Reads and processes the downloaded timestamp data file
        Args:
            file(str): file path on Jupyterhub for the final timestamp result
        """
        result = {}
        result["hits"] = []
        with open(file, "r") as f:
            for line in f:
                if '"index":{}' in line:
                    continue
                else:
                    try:
                        json_obj = json.loads(line)
                        result["hits"].append(json_obj)
                    except ValueError:
                        self.logger.debug("Json cannot load %s", line)
        with open(file, "w"):
            pass
        pretty_json = json.dumps(result["hits"], indent=2)
        with open(file, "w") as f:
            r = json.dump(result["hits"], f)

    def plot_packet_timestamp(self, json_obj):
        """
        Plots the count of packets captured
        Args:
            json_obj(list): list of json objects with timestamp info
        """
        x_labels = []
        y_labels = []
        count = 0
        for item in json_obj:
            sec = item["timestamp"].split(".")[0].split("T")[1]
            if sec not in x_labels:
                if count != 0:
                    y_labels.append(count)
                x_labels.append(sec)
                count = 0
            count += 1
        y_labels.append(count)
        fig = plt.figure(figsize=(25, 10))
        plt.bar(x_labels, y_labels, width=0.2)
        plt.xlabel("Timestamp")
        plt.ylabel("No. of Packets Captured")
        plt.title("Packets Captured Over Time")

        for i in range(len(y_labels)):
            plt.annotate(
                str(y_labels[i]),
                xy=(x_labels[i], y_labels[i]),
                ha="center",
                va="bottom",
            )
        plt.show()

    def plot_event_timestamp(self, json_obj):
        """
        Plots the count of events
        Args:
            json_obj(list): list of json objects with timestamp info
        """
        x_labels = []
        y_labels = []
        annotation = []
        for item in json_obj:
            sec = item["timestamp"]
            x_labels.append(sec)
            y_labels.append(1)
            annotation.append(item["name"])
        fig = plt.figure(figsize=(15, 6))
        plt.bar(x_labels, y_labels, width=0.4)
        plt.xlabel("Timestamp")
        plt.ylabel("No. of Events Captured")
        plt.title("Events Captured")

        for i in range(len(y_labels)):
            plt.annotate(
                str(annotation[i]),
                xy=(x_labels[i], y_labels[i]),
                ha="center",
                va="bottom",
            )
        plt.show()

    def upload_timestamp_to_influxdb(
        self, node, data_type, bucket, org, token, influxdb_ip=None
    ):
        """
        Uploads the timestamp data to influxdb
        Args:
            node(fablib.node): fabric node on which the timestamp docker container is running
            data_type(str): packet_timestamp or event timestamp
            bucket(str): name of the influxdb bucket to dump data to
            org(str): org of the bucket
            token(str): token of the bucket
            influxdb_ip(str, optional): IP of the node where influxdb container is running
        """
        try:
            node = self.slice.get_node(name=node)
        except Exception as e:
            print(f"Fail: {e}")
        command = f"sudo docker exec -i timestamp python3 /root/services/timestamp/service_files/influxdb_manager.py upload {data_type} -b {bucket} -o {org} -t {token}"
        if influxdb_ip:
            cmd = f"-ip {influxdb_ip}"
            command = f"{command} {cmd}"
        print(f"The docker command is: {command}")
        stdout, stderr = node.execute(command)

    def download_timestamp_from_influxdb(
        self, node, data_type, bucket, org, token, name, influxdb_ip=None
    ):
        """
        Downloads the timestamp data from influxdb
        Args:
            node(fablib.node): fabric node on which the timestamp docker container is running
            data_type(str): packet_timestamp or event timestamp
            bucket(str): name of the influxdb bucket to dump data to
            org(str): org of the bucket
            token(str): token of the bucket
            name(str): name of the timestamp experiment
            influxdb_ip(str, optional): the IP address of the node where the influxdb container is running
        """
        try:
            node = self.slice.get_node(name=node)
        except Exception as e:
            print(f"Fail: {e}")
        command = f"sudo docker exec -i timestamp python3 /root/services/timestamp/service_files/influxdb_manager.py download {data_type} -b {bucket} -o {org} -t {token} -n {name}"
        if influxdb_ip:
            cmd = f"-ip {influxdb_ip}"
            command = f"{command} {cmd}"
        # print (f"The docker command is {command}")
        stdout, stderr = node.execute(command)

    def get_query_for_csv(self, data_node, name, data_type, bucket, org, token):
        """
        Generates a .csv file in the influxdb container for the query data
        Args:
            data_node(str): where the data comes from
            name(str): name of the timestamp experiment
            data_type(str): packet_timestamp or event timestamp
            bucket(str): name of the influxdb bucket to dump data to
            org(str): org of the bucket
            token(str): token of the bucket
            influxdb_node_name(str): which fabric node is influxdb running on
        """
        if data_type == "packet_timestamp":
            remote_file = f"/tmp/{data_node}_packet_timestamp.csv"
            measurement_name = f"{data_node}-packet-timestamp"
        elif data_type == "event_timestamp":
            remote_file = f"/tmp/{data_node}_event_timestamp.csv"
            measurement_name = f"{data_node}-event-timestamp"
        else:
            return "wrong data type"
        query = f"""curl --request POST \
                    http://localhost:8086/api/v2/query?org={org} -o {remote_file} \
                    --header 'Authorization: Token {token}' \
                    --header 'Accept: application/csv' \
                    --header 'Content-type: application/vnd.flux' \
                    --data 'from(bucket:"{bucket}") 
                        |> range(start: 0) 
                        |> filter(fn: (r) => r._measurement == "{measurement_name}" and r.name=="{name}")'
                 """
        return query

    def download_file_from_influxdb(
        self, data_node, data_type, influxdb_node_name, local_file
    ):
        """
        Downlaods the .csv data file from the influxdb container to juputerhub
        Args:
            data_node(str): where the data comes from
            data_type(str): packet_timestamp or event timestamp
            influxdb_node_name(str): which fabric node is influxdb running on
            local_file(str): path on Jupyterhub for the downlaod .csv file
        """

        remote_file = ""
        if data_type == "packet_timestamp":
            remote_file = f"/tmp/{data_node}_packet_timestamp.csv"
        elif data_type == "event_timestamp":
            remote_file = f"/tmp/{data_node}_event_timestamp.csv"
        else:
            return "wrong data type"
        try:
            node_influxdb = self.slice.get_node(name=influxdb_node_name)
        except Exception as e:
            print(f"Fail: {e}")
        node_influxdb.download_file(
            local_file_path=local_file, remote_file_path=remote_file
        )

    def deploy_influxdb_dashboard(
        self, dashboard_file, influxdb_node_name, bind_mount_volume
    ):
        """
        Uploads a dashboard template file from Jupyterhub to influxdb and apply the template
        Args:
            dashboard_file(str): path of the dashboard file on Jupyterhub
            influxdb_node_name(str): which fabric node is influxdb running on
            bind_mount_volume(str): bind mount volume of the influxdb docker container
        """

        # Upload the dashboard file to the directory on meas_node that binds mount on influxdb container
        try:
            influxdb_node = self.slice.get_node(name=influxdb_node_name)
        except Exception as e:
            print(f"Fail: {e}")
        influxdb_node.upload_file(
            local_file_path=dashboard_file,
            remote_file_path=f"{bind_mount_volume}/dashboard.yml",
        )

        # Apply the template in influxdb
        command = f"sudo docker exec -i influxdb influx apply --skip-verify --file /var/lib/influxdb2/dashboard.yml"
        stdout, stderr = influxdb_node.execute(command)
