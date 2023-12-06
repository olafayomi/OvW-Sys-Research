import socket
import time
import argparse
import csv
import math
import netifaces
import numpy as np


def get_address(hostname):
    intfName = hostname+'-eth0'
    addrs = netifaces.ifaddreses(intfName)
    if netifaces.AF_INET6 in addrs:
        ipv6_addrs = addrs[netifaces.AF_INET6]
        ipv6_addr = [addr['addr'] for addr in ipv6_addrs if not addr['addr'].startswith('fe80')]
        return ipv6_addr[0]
    return None


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
    #client_socket.connect(server_address)
    # Set timeout for socket
    #client_socket.settimeout(1.0)
    # Set socket to blocking until timeout exceeded
    client_socket.setblocking(False)
    #client_ipv6_address = client_socket.getsockname()[0]
    client_ipv6_address = get_address(args.hostname)
    message_counter = 0
    # Set up variables for tracking consecutive counts and times
    consecutive_count = 0  # count of packets with RTT above 60ms
    last_consecutive_time = None  # time duration RTT is above 60ms threshold
    last_sent = None
    last_thirty_rtts = []
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
            client_socket.sendto(message.encode(), server_address)
            # last_sent = time.monotonic()

            # Wait for response
            try:
                data, server = client_socket.recvfrom(4096)
            except socket.timeout:
                print("Socket timed out on response from server")
                received = False
                rtt = math.nan
                receive_time = None
            else:
                received = True
                r_time = time.monotonic()
                receive_time = time.time()
                rtt = (r_time - s_time) * 1000
                # print(f"Received {data.decode()} in {rtt:.3f} ms")

            if math.isnan(rtt):
                last_thirty_rtts.append(1000)
            else:
                last_thirty_rtts.append(rtt)

            # Write row to CSV
            writer.writerow([message, receive_time, rtt, received])
            message_counter += 1
            time.sleep(0.04)

            # Update consecutive count and time variables
            # if math.isnan(rtt) or rtt > 60.0:
            #    if consecutive_count == 0:
            #        last_consecutive_time = time.monotonic()
            #    consecutive_count += 1
            #    #if time.monotonic() - last_consecutive_time >= 30:
            #    #    print(f"Consistent high RTT and timeouts for {consecutive_count} packets")
            #    #    break
            # else:
            #    consecutive_count = 0
            #    last_consecutive_time = None
            if time.monotonic() - timer >= 30:
                p70val = np.percentile(last_thirty_rtts, 70)
                if (p70val > 60.0):
                    print(f"High RTT experienced for 30% of {len(last_thirty_rtts)} packets in the last 30 seconds")
                    break
                last_thirty_rtts.clear()
                timer = None

            # t_delta = time.monotonic() - s_time
            # if t_delta < 1.0:
            #    duration = 1.0 - t_delta
            #    time.sleep(duration)
