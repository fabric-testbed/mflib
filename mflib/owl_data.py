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


import csv
import os
from decimal import Decimal
from pathlib import Path
import scapy.all as scp
import pandas as pd


def list_experiment_ip_addrs(node):
    """
    Get experimenter IPv4 addresses for each node. 

    :param node: Node on which IPv4 address is queried.
    :type node: fablib.Node
    :return: a list of of IPv4 addresses assigned to node interfaces
    :rtype: [ipaddress.IPv4Address,]
    """

    # The following line excludes management net interface
    interfaces = node.get_interfaces()
    exp_network_ips = []
    for interface in interfaces:
        network = interface.toDict()['network']
        if 'l3_meas_net' not in network:
            exp_network_ips.append(interface.get_ip_addr())

    return exp_network_ips 



def list_pcap_files(root_dir):
    """
    Search recursively for pcap files under root_dir
    
    :param root_dir: Directory that will be treated as root for this search
    :type root_dir: str
    :return files_list: absolute paths for all the *.pcap files under the root_dir
    :rtype: [posix.Path]
    """
    
    files_list = []
    
    for path in Path(root_dir).rglob('*.pcap'):
        files_list.append(path.resolve())
    
    return files_list


def convert_pcap_to_csv(pcap_files, outfile="out.csv", append_csv=False, verbose=False):
    """
    Extract data from the list of pcap files and write to one csv file.
    
    :param pcap_files: list of pcap file paths
    :type pcap_files: [posix.Path]
    :param outfile: name of csv file
    :type outfile: str
    :param append_csv: whether to append data to an existing csv file of that name
    :type append_csv: bool
    :param verbose: if True, prints each line as it is appended to csv
    :type verbose: bool

    """

    # TODO: Check if the csv file exists
    
    if append_csv is False:
        if os.path.isfile(outfile):
            print(f"CSV file {outfile} already exists. Either delete the file or pass \
            append_csv=True")
            
            return 
    

    # Remove zero-bye pcap files
    pcapfiles_with_data = [str(f) for f in pcap_files if os.stat(f).st_size > 0]
    print("non-zero pcap files to be processed: ", pcapfiles_with_data)

    # Extract data
    for pcapfile in pcapfiles_with_data:
        print("file name:",  pcapfile)
        pkts = scp.rdpcap(pcapfile)

        for pkt in pkts:
            # Fields are <src-ip, send-t,  
            #             dst-ip, dst-t,  seq-n, latency_nano>
            # latency_nano is in nano-seconds

            fields=[]

            # Field: src-ip
            try:
                fields.append(str(pkt[scp.IP].src))
            except(IndexError) as e:
                print("\nEncountered an issue reading source IP")
                print(e)

            # Field: send-t
            try:
                send_t, seq_n = pkt[scp.Raw].load.decode().split(",")
                send_t = Decimal(send_t)  # To prevent floating point issues
                fields.append(str(send_t))
            except (ValueError, IndexError) as e: 
                print("\nEncountered an issue reading payload data")
                print(e)
               
            # Field: dst-ip
            try:
                fields.append(str(pkt[scp.IP].dst))
            except(IndexError) as e:
                print("\nEncountered an issue reading destination IP")
                print(e)
                
            # Field: dst-t
            try:
                fields.append(str(pkt.time))  # pkt.time is type Decimal
            except(IndexError) as e:
                print("\nEncountered an issue reading received time")
                print(e)
                
            # Field: seq-n
            try:
                fields.append(seq_n)
            except(ValueError) as e:
                print("\nEncountered an issue reading payload data")
                print(e)            

            # Field: latency
            try:
                latency_nano = (pkt.time-send_t)*1000000000
                fields.append(str(int(latency_nano)))
            except(ValueError) as e:
                print(e)

            if verbose:
                print(fields)


            with open(outfile, 'a') as f:
                writer = csv.writer(f)
                writer.writerow(fields)   

                
def convert_to_df(owl_csv):
    '''
    Convert CSV output from the method above to Panda Dataframe
    
    :param owl_csv: path/to/csv/file
    :type owl_csv: str
    '''
    
    owl_df = pd.read_csv(owl_csv, 
                         header=None, 
                         names=["src_ip", "sent_t", "dst_ip", "dst_t", "seq_n", "latency"])

    # Data cleaning
    owl_df['src_ip'] = owl_df['src_ip'].astype('str')
    owl_df['sent_t'] = pd.to_numeric(owl_df['sent_t'], errors='coerce')
    owl_df['sent_t_datetime'] = pd.to_datetime(owl_df['sent_t'], unit='s', errors='coerce')
    owl_df['dst_t'] = pd.to_numeric(owl_df['dst_t'], errors='coerce')
    owl_df['dst_t_datetime'] = pd.to_datetime(owl_df['dst_t'], unit='s', errors='coerce')
    owl_df['seq_n'] = pd.to_numeric(owl_df['seq_n'], errors='coerce')
    owl_df['latency'] = pd.to_numeric(owl_df['latency'], errors='coerce')
    owl_df = owl_df.dropna(how='any')
    owl_df['latency'] = owl_df['latency'].astype(int)

    return owl_df.dropna(how='any')   
                

def filter_data(df, src_ip, dst_ip):
    """
    Filter data by source and destination IPs
    
    :param df: latency data
    :type df: Panda Dataframe 
    :param src[dst]_ip: Source and destination IPv4 addresses
    :type src[dst]_ip: str
    """

    return df.loc[(df['src_ip']==src_ip) & (df['dst_ip']==dst_ip)]        

    
def get_summary(df, src_node, dst_node, src_ip=None, dst_ip=None):
    """
    Print summary of latency data collected between source and destination nodes
    
    :param df: latency data
    :type df: Panda Dataframe 
    :param src[dst]_node: source/destination nodes
    :type src[dst]_node:fablib.Node
    :param src[dst]_ip: needed only if there are multiple experimenter IP interfaces
    :type src[dst]_ip: str
    """

    # If IP addresses not given, assume there is only 1

    if not src_ip:
        src_ip = list_experiment_ip_addrs(src_node)[0]
    if not dst_ip:
        dst_ip = list_experiment_ip_addrs(dst_node)[0]

    f_data = filter_data(df, str(src_ip), str(dst_ip))
    

    print(f"\n*****{src_ip} ({src_node.get_site()}) --> {dst_ip} ({dst_node.get_site()})")
    print(f"Number of samples {len(f_data.index)}")
    print(f"Median Latency (ns): {f_data['latency'].median()}")
    print(f"Median Latency (micros): {(f_data['latency'].median())/1000}")
    print(f"Median Latency (ms): {(f_data['latency'].median())/1000000}")
    print(f"Median Latency (s): {(f_data['latency'].median())/1000000000}")
    print(f"max latency (ns): {f_data['latency'].max()}")
    print(f"min latency (ns): {f_data['latency'].min()}")
    print("\n***Compare the result to ping")
    
    src_node.execute(f"ping -c 2 {dst_ip}")


def graph_latency_data(df, src_node, dst_node, src_ip=None, dst_ip=None):
    """
    Graph latency data collected between source and destination nodes
    
    :param df: latency data
    :type df: Panda Dataframe 
    :param src[dst]_node: source/destination nodes
    :type src[dst]_node:fablib.Node
    :param src[dst]_ip: needed only if there are multiple experimenter IP interfaces
    :type src[dst]_ip: str
    """       
    
    import plotly.graph_objects as go
    
    
    if not src_ip:
        src_ip = list_experiment_ip_addrs(src_node)[0]
    if not dst_ip:
        dst_ip = list_experiment_ip_addrs(dst_node)[0]

    filtered = filter_data(df, str(src_ip), str(dst_ip))
     
    import plotly.io as pio
    pio.renderers.default = 'iframe'


    fig = go.Figure([go.Scatter(x=filtered['sent_t_datetime'],
                                y=filtered['latency'])])
    fig.update_layout(
        title = f'{src_ip} ({src_node.get_site()}) -> {dst_ip} ({dst_node.get_site()})',
        xaxis_title = "Sent time",
        yaxis_title = "latency in nano-sec",
        yaxis = dict(
                tickformat='d'))

    fig.show()
    