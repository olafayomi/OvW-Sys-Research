import socket
import time
import argparse
import netifaces
import select

def get_address(hostname):
    intfName = hostname+'-eth0'
    addrs = netifaces.ifaddresses(intfName)
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
    arg_parser.add_argument('-p', dest='server_port',
                            help='server port address',
                            type=int,
                            default=None)
    arg_parser.add_argument('-s', dest='server_addr',
                            help='server address',
                            type=str,
                            default=None)

    args = arg_parser.parse_args()

    if args.hostname is None:
        raise SystemExit("Host name not provided for client")

    if args.server_port is None:
        raise SystemExit("Server port not provided for client")

    if args.server_addr is None:
        raise SystemExit("Server address not provided for client")

    # Set up client socket
    server_address = (args.server_addr, args.server_port)
    client_socket = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    client_socket.setblocking(False)
    #client_ipv6_address = client_socket.getsockname()[0]
    client_ipv6_address = get_address(args.hostname)
    message_counter = 0
    init_msm = False
    # Loop through messages
    start_time = time.monotonic()
    end_time = start_time + args.duration
    while time.monotonic() < end_time:
        if init_msm is False:
            s_time = time.monotonic()
            send_time = time.time()
            message = f"{client_ipv6_address},{send_time},{message_counter}"
            client_socket.sendto(message.encode(), server_address)
            init_msm = True

        # Wait for response
        ready = select.select([client_socket], [], [], 1.0)
        if ready[0]:
            try:
                data, server = client_socket.recvfrom(4096)
            except socket.timeout:
                print("Socket timed out on response from server")
            else:
                client_socket.sendto(data, server)
                print(f"Received {data.decode()} at {time.time()}")

        message_counter += 1
        time.sleep(0.04)
    client_socket.close()
