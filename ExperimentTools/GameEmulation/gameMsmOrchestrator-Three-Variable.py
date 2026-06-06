import socket
import perfmon_pb2 as perfmsg
import struct
import os
import sys
from collections import OrderedDict
import time
from datetime import datetime
import asyncio
import statistics as stat
from fractions import Fraction
from decimal import Decimal
from decimal import getcontext
import multiprocessing
import concurrent.futures
import csv
import select
import argparse
import json


def encode_msg_size(size: int) -> bytes:
    return struct.pack("<I", size)


def create_msg(content: bytes) -> bytes:
    size = len(content)
    return encode_msg_size(size) + content


def decode_msg_size(size_bytes: bytes) -> int:
    return struct.unpack("<I", size_bytes)[0]


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(
            description='Measurement orchestrator for game server',
            usage='%(prog)s [ -m msm_period]')
    arg_parser.add_argument('-m', dest='msm_period',
                            help='Measurement period',
                            type=float,
                            default=1)

    args = arg_parser.parse_args()
    latsock = '/home/ubuntu/latency.sock'
    sock4path = '/home/ubuntu/path1.sock'
    sock5path = '/home/ubuntu/path2.sock'
    sock6path = '/home/ubuntu/path3.sock'

    os.mkfifo(sock4path)
    os.mkfifo(sock5path)
    os.mkfifo(sock6path)

    sock4 = os.open(sock4path, os.O_RDONLY | os.O_NONBLOCK)
    sock5 = os.open(sock5path, os.O_RDONLY | os.O_NONBLOCK)
    sock6 = os.open(sock6path, os.O_RDONLY | os.O_NONBLOCK)

    poll = select.poll()
    poll.register(sock4, select.POLLIN)
    poll.register(sock5, select.POLLIN)
    poll.register(sock6, select.POLLIN)

    msm_sockets = [sock4, sock5, sock6]
    parsocks = [latsock]
    # Link measurements to egress nodes
    msmAddrExit = OrderedDict()
    msmAddrExit["55::4"] = ["Tp1ASr2", "100::2", 0.0]
    msmAddrExit["55::5"] = ["Tp1ASr3", "100::3", 0.0]
    msmAddrExit["55::6"] = ["Tp1ASr4", "100::6", 0.0]

    clients = {}
    timer = None

    file_handlers = []
    for sock in parsocks:
        fifo = os.open(sock, os.O_WRONLY)
        file_handlers.append(fifo)

    msm_count = 0
    #with open('/home/ubuntu/Ovw-Eval-Results/AS34410/msmModule/msmtiming', 'w') as msmtimef:
    #    writer = csv.writer(msmtimef, delimiter='|')
    #    writer.writerow(["Measurement start time", "Number of Clients", "Number of measurements", "Duration"])

    with open('/home/ubuntu/Ovw-Eval-Results/AS34410/msmModule/msmvalue', 'w') as msmvalf:
        writer = csv.writer(msmvalf, delimiter='|')
        writer.writerow(["Measurement start time", "Client",
                         "P1 eRTT", "P1 dRTT", "P2 eRTT", "P2 dRTT", "P3 eRTT", "P3 dRTT"])
    saved = []
    for i in range(1, 53):
        addr = f"2001:df{str(i).zfill(2)}::1"
        saved.append(addr)

    try:
        with open('/home/ubuntu/as_topology_config.json', 'r') as f:
            config_data = json.load(f)
            AS_CONFIG = {int(k): v for k, v in config_data['AS_CONFIG'].items()}
    except FileNotFoundError:
        # Fallback: define the three-path networks based on your topology
        AS_CONFIG = {}
        print("Warning: Could not load AS config, using hardcoded values")

    three_path_as_numbers = []
    if AS_CONFIG:
        three_path_as_numbers = [as_num for as_num, (num_routers, _, _) in AS_CONFIG.items() if num_routers >= 3]
    else:
        # Hardcoded fallback based on your topology
        three_path_as_numbers = [1, 3, 6, 38, 49, 50, 51]
    print(f"Three-path AS numbers: {three_path_as_numbers}")

    network_path_count = {}
    three_path_networks = [f'df{str(as_num).zfill(2)}' for as_num in three_path_as_numbers]
    print(f"Three-path network identifiers: {three_path_networks}")

    for i in range(1, len(AS_CONFIG)+1):
        network = f'df{str(i).zfill(2)}'
        network_path_count[network] = 2

    for network in three_path_networks:
        network_path_count[network] = 3
    
    print(f"Network path count configuration: {network_path_count}")
    while True:
        timer = time.perf_counter()
        init_time = str(datetime.now())
        print("Initiating measurements for clients added at %s"
              % (str(datetime.now())))
        t1 = time.perf_counter()
        msg = perfmsg.DstMsmMsgs()

        events = poll.poll(-1)
        #ready_to_read = [sock for sock, event in events if event & select.POLLIN]

        #if len(ready_to_read) != 2:
        #    print("Message available to read on only one socket at %s\n" %(str(datetime.now())))

        #for sock in ready_to_read:
        for sock, event in events:
            if sock == sock4:
                #print("Reading msg from Path 1 Monitor at %s" %(str(datetime.now())))
                msg_size_bytes = os.read(sock, 4)
                msg_size = decode_msg_size(msg_size_bytes)
                msg_recvd = os.read(sock, msg_size)
                # print(f"Length of received message is {len(msg_recvd)}")
                cl_rtts_msg = perfmsg.ClRTTMsgs()
                cl_rtts = cl_rtts_msg.FromString(msg_recvd)
                for cl_rtt in cl_rtts.cl_rtt:
                    cl_addr = cl_rtt.address
                    if cl_addr not in clients:
                        clients[cl_addr] = [(None, None, None), (None, None, None), (None, None, None)]
                    ertt = cl_rtt.ertt
                    rtt = cl_rtt.rtt
                    drtt = cl_rtt.drtt
                    clients[cl_addr][0] = (ertt, rtt, drtt)

            if sock == sock5:
                #print("Reading msg from Path 2 Monitor at %s" %(str(datetime.now())))
                msg_size_bytes = os.read(sock, 4)
                msg_size = decode_msg_size(msg_size_bytes)
                msg_recvd = os.read(sock, msg_size)
                # print(f"Length of received message from sock5 is {len(msg_recvd)}")
                cl_rtts_msg = perfmsg.ClRTTMsgs()
                cl_rtts = cl_rtts_msg.FromString(msg_recvd)
                for cl_rtt in cl_rtts.cl_rtt:
                    cl_addr = cl_rtt.address
                    if cl_addr not in clients:
                        clients[cl_addr] = [(None, None, None), (None, None, None), (None, None, None)]
                    ertt = cl_rtt.ertt
                    rtt = cl_rtt.rtt
                    drtt = cl_rtt.drtt
                    clients[cl_addr][1] = (ertt, rtt, drtt)

            if sock == sock6:
                #print("Reading msg from Path 2 Monitor at %s" %(str(datetime.now())))
                msg_size_bytes = os.read(sock, 4)
                msg_size = decode_msg_size(msg_size_bytes)
                msg_recvd = os.read(sock, msg_size)
                # print(f"Length of received message from sock5 is {len(msg_recvd)}")
                cl_rtts_msg = perfmsg.ClRTTMsgs()
                cl_rtts = cl_rtts_msg.FromString(msg_recvd)
                for cl_rtt in cl_rtts.cl_rtt:
                    cl_addr = cl_rtt.address
                    if cl_addr not in clients:
                        clients[cl_addr] = [(None, None, None), (None, None, None), (None, None, None)]
                    ertt = cl_rtt.ertt
                    rtt = cl_rtt.rtt
                    drtt = cl_rtt.drtt
                    clients[cl_addr][2] = (ertt, rtt, drtt)

        t2 = time.perf_counter()
        t_delta = t2 - t1
        print("Measurement completed in %s seconds  for clients: %s"
              % (t_delta, clients.keys()))

        for client, lat_values in clients.items():

            network = client.split(':')[1]  # Gets df{XX} part
            required_paths = network_path_count.get(network, 2)  # 

            p1_ertt, p1_rtt, p1_drtt = lat_values[0]
            p2_ertt, p2_rtt, p2_drtt = lat_values[1]
            p3_ertt, p3_rtt, p3_drtt = lat_values[2]

            if (required_paths == 2) and (p1_ertt is not None) and (p2_ertt is not None):
                dstMsm = msg.dstMsm.add()
                dstMsm.DstAddr = client
                msm_for_p1 = dstMsm.node.add()
                msm_for_p1.name = msmAddrExit["55::4"][0]
                msm_for_p1.address = msmAddrExit["55::4"][1]
                msm_for_p1.estDelay = round(p1_ertt, 1)
                msm_for_p1.devDelay = round(p1_drtt, 1)
                msm_for_p2 = dstMsm.node.add()
                msm_for_p2.name = msmAddrExit["55::5"][0]
                msm_for_p2.address = msmAddrExit["55::5"][1]
                msm_for_p2.estDelay = round(p2_ertt, 1)
                msm_for_p2.devDelay = round(p2_drtt, 1)
            
                print(f"Client: {client} (2 paths) Path 1 Est/Actual Delay: {p1_ertt}/{p1_rtt}ms Path 2 Est/Actual Delay: {p2_ertt}/{p2_rtt}ms") 


            elif (required_paths == 3) and (p1_ertt is not None) and (p2_ertt is not None) and (p3_ertt is not None):
                dstMsm = msg.dstMsm.add()
                dstMsm.DstAddr = client
                msm_for_p1 = dstMsm.node.add()
                msm_for_p1.name = msmAddrExit["55::4"][0]
                msm_for_p1.address = msmAddrExit["55::4"][1]
                msm_for_p1.estDelay = round(p1_ertt, 1)
                msm_for_p1.devDelay = round(p1_drtt, 1)
                msm_for_p2 = dstMsm.node.add()
                msm_for_p2.name = msmAddrExit["55::5"][0]
                msm_for_p2.address = msmAddrExit["55::5"][1]
                msm_for_p2.estDelay = round(p2_ertt, 1)
                msm_for_p2.devDelay = round(p2_drtt, 1)
                msm_for_p3 = dstMsm.node.add()
                msm_for_p3.name = msmAddrExit["55::6"][0]
                msm_for_p3.address = msmAddrExit["55::6"][1]
                msm_for_p3.estDelay = round(p3_ertt, 1)
                msm_for_p3.devDelay = round(p3_drtt, 1)

                print(f"Client: {client} (3 paths) Path 1 Est/Actual Delay: {p1_ertt}/{p1_rtt}ms  Path 2 Est/Actual Delay: {p2_ertt}/{p2_rtt}ms Path 3 Est/Actual Delay: {p3_ertt}/{p3_rtt}ms")

        msg_encoded = msg.SerializeToString()
        if len(msg_encoded) != 0:
            msg = create_msg(msg_encoded)
            for fifo in file_handlers:
                os.write(fifo, msg)

        with open('/home/ubuntu/Ovw-Eval-Results/AS34410/msmModule/msmvalue', 'a') as val_f:
            rows = []
            for client, lat_values in clients.items():
                p1_ertt, p1_rtt, p1_drtt = lat_values[0]
                p2_ertt, p2_rtt, p2_drtt = lat_values[1]
                p3_ertt, p3_rtt, p3_drtt = lat_values[2]
                #row = [init_time, client, p1_ertt, p2_ertt]
                if client in saved:
                    network = client.split(':')[1]
                    required_paths = network_path_count.get(network, 2)
                    if required_paths == 2:
                        row = [init_time, client, p1_ertt, p1_drtt, p2_ertt, p2_drtt, None, None]
                    else:
                        row = [init_time, client, p1_ertt, p1_drtt,
                           p2_ertt, p2_drtt, p3_ertt, p3_drtt]
                    rows.append(row)
            writer = csv.writer(val_f, delimiter='|')
            writer.writerows(rows)

            print("Msm module sent latency msms to Overwatch for clients at %s"
                  % (str(datetime.now())))
        optime = time.perf_counter() - timer
        if optime < args.msm_period:
            duration = args.msm_period - optime
            time.sleep(duration)
