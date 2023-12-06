import socket
import time
import argparse
import csv
import math
import netifaces
import numpy as np
import select
from collections import deque


def get_address(hostname):
    intfName = hostname+'-eth0'
    addrs = netifaces.ifaddresses(intfName)
    if netifaces.AF_INET6 in addrs:
        ipv6_addrs = addrs[netifaces.AF_INET6]
        ipv6_addr = [addr['addr'] for addr in ipv6_addrs if not addr['addr'].startswith('fe80')]
        return ipv6_addr[0]
    return None


def most_recent_rtts_above_threshold(last_thirty_rtts):
    for rtt in last_thirty_rtts:
        if rtt <= 60.0:
            return False
    return True


def calc_percentage(rtts):
    total_values = len(rtts)
    above_threshold = 0 
    for rtt in rtts:
        if rtt > 60.0:
            above_threshold += 1
    percent = (above_threshold/total_values) * 100
    return percent


if __name__ == "__main__":

    # Set up command line arguments
    arg_parser = argparse.ArgumentParser(
            description='Game client emulator',
            usage='%(prog)s [ -d duration  -c csv-output-file]')
    arg_parser.add_argument('-d', dest='duration',
                            help='Connection duration of the game client',
                            type=int,
                            default=300)
    arg_parser.add_argument('-n', dest='hostname',
                            help='Hostname of the game client',
                            type=str,
                            default=None)
    arg_parser.add_argument('-c', dest='output',
                            help='File to write CSV output of RTT',
                            type=argparse.FileType('w'),
                            default=None)
    args = arg_parser.parse_args()

    if args.output is None:
        raise SystemExit("No filename supplied for the output")

    if args.hostname is None:
        raise SystemExit("Host name not provided for client")

    # Set up client socket
    server_address = ('55::1', 12345)
    client_socket = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    client_socket.setblocking(False)
    client_ipv6_address = get_address(args.hostname)
    message_counter = 0
    # Set up variables for tracking consecutive counts and times
    consecutive_count = 0  # count of packets with RTT above 60ms
    last_consecutive_time = None  # time duration RTT is above 60ms threshold
    rtt_window = deque(maxlen=180)
    timer = None

    # Set up CSV writer and write headers
    with args.output as f, client_socket:
        writer = csv.writer(f, delimiter='|')
        writer.writerow(["Message", "Receive Time", "RTT", "Received"])

        # Loop through messages
        start_time = time.monotonic()
        end_time = start_time + args.duration
        while time.monotonic() < end_time:
            if timer is None:
                timer = time.monotonic()

            s_time = time.monotonic()
            send_time = time.time()
            message = f"{client_ipv6_address},{send_time},{message_counter}"
            try:
                client_socket.sendto(message.encode(), server_address)
            except socket.error as e:
                print(f"Sending to server from socket failed with {e}")

            # Wait for response
            ready = select.select([client_socket], [], [], 0.9)
            if ready[0]:
                try:
                    data, server = client_socket.recvfrom(4096)
                    received = True
                except socket.error as e:
                    print(f"Receive from socket failed with {e}")
                    received = False
                    rtt = math.nan
                    receive_time = send_time
            else:
                print("Socket timed out on response from server")
                received = False
                rtt = math.nan
                receive_time = send_time

            if received:
                r_time = time.monotonic()
                receive_time = time.time()
                rtt = (r_time - s_time) * 1000
                print(f"Received {data.decode()} in {rtt:.3f} ms")

            if math.isnan(rtt):
                rtt_window.append(1000)
            else:
                rtt_window.append(rtt)

            # Write row to CSV
            writer.writerow([message, receive_time, rtt, received])
            message_counter += 1

            if len(rtt_window) == 180:
                #p75val = np.percentile(rtt_window, 75)
                rtt_l = list(rtt_window)
                p75val = calc_percentage(rtt_l)
                last_thirty = list(rtt_window)[-30:]
                bad_recent = most_recent_rtts_above_threshold(last_thirty)


                if (p75val >= 25.0):
                    writer.writerow(['percent-disconnect','percent-disconnect','percent-disconnect','percent-disconnect'])
                    print(f"Disconnection caused by 25% of traffic in the last 180 seconds")
                    break

                if bad_recent:
                    writer.writerow(['Thirty-High', 'Thirty-High', 'Thirty-High', 'Thirty-High'])
                    print(f"High RTT experienced for all traffic in the last 30 seconds")
                    break

            t_delta = time.monotonic() - s_time
            if t_delta < 1.0:
                duration = 1.0 - t_delta
                time.sleep(duration)
        f.flush()
