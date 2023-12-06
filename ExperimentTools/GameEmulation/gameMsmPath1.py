#!/usr/bin/env python
# Copyright (c) 2023, WAND Network Research Group
#                     Department of Computer Science
#                     University of Waikato
#                     Hamilton
#                     New Zealand
#
# Author Dimeji Fayomi (oof1@students.waikato.ac.nz)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330,
# Boston,  MA 02111-1307  USA


import asyncio
import time
from datetime import datetime
import perfmon_pb2 as perfmsg
import struct
import os
from collections import OrderedDict
import argparse


def encode_msg_size(size: int) -> bytes:
    return struct.pack("<I", size)


def create_msg(content: bytes) -> bytes:
    size = len(content)
    return encode_msg_size(size) + content


def decode_msg_size(size_bytes: bytes) -> int:
    return struct.unpack("<I", size_bytes)[0]


class Path1Protocol:
    def __init__(self, pathsock, msm_int):
        self.alpha = 0.125
        self.beta = 0.25
        self.clients = {}
        self.srcAddr = "55::4"
        self.send_ping_tasks = []
        self.send_update_task = None
        self.calculate_task = None
        self.pathsock = pathsock
        self.msmperiod = msm_int
        self.msmperiod_d = self.msmperiod - 0.07
        self.duration = 901
        self.calculate_finished_event = asyncio.Event()
        self.receive_event = asyncio.Event()

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        message = data.decode()
        msg_list = message.split(",")
        client_addr = addr[0]
        if len(msg_list) == 3:
            pkts = OrderedDict()
            self.clients[client_addr] = [(None, None, None), pkts, None, False]
            self.send_ping_tasks.append(asyncio.create_task(
                self.send_ping(addr)))

            if self.calculate_task is None:
                self.calculate_task = asyncio.create_task(self.calculate())

            if self.send_update_task is None:
                self.send_update_task = asyncio.create_task(self.send_update())
        else:
            r_time = asyncio.get_running_loop().time()
            pkt_s_time = float(msg_list[4])
            pkt_no = int(msg_list[3])
            #print(f"on {self.srcAddr} for {client_addr} for packet no: {pkt_no}, received: {r_time}, sent: {pkt_s_time}")
            cur_pkt_no = self.clients[client_addr][2]
            rtt = (r_time - pkt_s_time) * 1000

            if cur_pkt_no == pkt_no:
                #print(f"on {self.srcAddr} for {client_addr} for packet no: {pkt_no}, received: {r_time}, sent: {pkt_s_time} rtt: {rtt}ms")
                #rtt = (r_time - pkt_s_time) * 1000
                self.clients[client_addr][1][pkt_no] = (pkt_s_time, r_time, rtt)
            else:
                #print(f"On {self.srcAddr} for {client_addr}, received reply for packet {pkt_no}, but current packet is {cur_pkt_no}")
                if rtt >= 1000.0:
                    self.clients[client_addr][1][pkt_no] = (pkt_s_time, r_time, None)
                else:
                    #print(f"On {self.srcAddr} recieved late reply for packet {pkt_no} from {client_addr} but RTT is {rtt}ms which is less than 1000ms")
                    self.clients[client_addr][1][pkt_no] = (pkt_s_time, r_time, rtt)
            self.clients[client_addr][3] = True
            self.receive_event.set()

    async def send_ping(self, addr):
        #event = asyncio.Event()
        end_task_time = asyncio.get_running_loop().time() + self.duration
        while asyncio.get_running_loop().time() < end_task_time:
            s_time = asyncio.get_running_loop().time()
            if self.clients[addr[0]][2] is None:
                self.clients[addr[0]][2] = 0
                self.clients[addr[0]][1][0] = (s_time, None, None)
                ping = f"Ping,{addr[0]},{self.srcAddr},{0},{s_time}"
            else:
                self.clients[addr[0]][2] += 1
                n_pkt = self.clients[addr[0]][2]
                self.clients[addr[0]][1][n_pkt] = (s_time, None, None)
                ping = f"Ping,{addr[0]},{self.srcAddr},{n_pkt},{s_time}"
            self.transport.sendto(ping.encode(), addr)
            t_delta = asyncio.get_running_loop().time() - s_time
            if t_delta < self.msmperiod:
                s_duration = self.msmperiod - t_delta
                await asyncio.sleep(s_duration)
            #await asyncio.sleep(1)
        #event.clear()

    async def calculate(self):
        while True:
            calc_time = asyncio.get_running_loop().time()
            await self.receive_event.wait()
            for client_addr, vals in self.clients.items():
                ertt, rtt, drtt = vals[0]
                packets = vals[1]
                pkt_num = vals[2]
                new_receive = vals[3]

                if pkt_num is None:
                    continue

                if new_receive is False:
                    continue

                p_s_time, p_r_time, p_rtt = packets[pkt_num]

                if pkt_num == 0:
                    if p_rtt is not None:
                        d_rtt = p_rtt/2
                        self.clients[client_addr][0] = (p_rtt, p_rtt, d_rtt)
                    else:
                        c_time = asyncio.get_running_loop().time()
                        t_diff = c_time - p_s_time
                        if t_diff >= 0.350:
                            self.clients[client_addr][0] = (0.0, 0.0, 0.0)
                else:
                    if p_rtt is not None:
                        if ertt != 0.0:
                            drtt = ((1 - self.beta) * drtt) + (self.beta * abs(ertt - p_rtt))
                            ertt = ((1 - self.alpha) * ertt) + (self.alpha * p_rtt)
                        else:
                            drtt = ((1 - self.beta) * drtt) + (self.beta * abs(ertt - rtt))
                            ertt = p_rtt
                        self.clients[client_addr][0] = (ertt, p_rtt, drtt)
                    else:
                        c_time = asyncio.get_running_loop().time()
                        t_diff = c_time - p_s_time
                        if t_diff >= 0.350:
                            self.clients[client_addr][0] = (0.0, 0.0, 0.0)

                pr_ertt, pr_rtt, pd_rtt = self.clients[client_addr][0]
                #if pr_ertt == 0.0:
                #    print(f'{str(datetime.now())}:Path via {self.srcAddr} is down for client {client_addr} and RTT is {p_rtt} for packet {pkt_num} ')
                #else:
                #    print(f'{str(datetime.now())}: For client {client_addr}  ERTT is {pr_ertt}ms and RTT is {pr_rtt}ms for packet {pkt_num}')
                self.clients[client_addr][3] = False
            self.calculate_finished_event.set()
            calc_time_delta = asyncio.get_running_loop().time() - calc_time
            if calc_time_delta < self.msmperiod:
                await asyncio.sleep(calc_time_delta*2)
                #print(f'{str(datetime.now())}: Completed calculation, going to sleep now')

            #await asyncio.sleep(self.msmperiod_d)
            #await asyncio.sleep(0.93)

    async def send_update(self):
        #event = asyncio.Event()
        while True:
            sl_time = asyncio.get_running_loop().time()
            await self.calculate_finished_event.wait()
            rtt_msgs = perfmsg.ClRTTMsgs()
            for client_addr, vals in self.clients.items():
                ertt, rtt, drtt = vals[0]
                if ertt is not None:
                    cl = rtt_msgs.cl_rtt.add()
                    cl.address = client_addr
                    cl.ertt = ertt
                    cl.rtt = rtt
                    cl.drtt = drtt
            msg_encoded = rtt_msgs.SerializeToString()
            msg = create_msg(msg_encoded)
            os.write(self.pathsock, msg)
            sl_delta = asyncio.get_running_loop().time() - sl_time
            if sl_delta < self.msmperiod:
                sl_duration = self.msmperiod - sl_delta
                #print(f'{str(datetime.now())}: Sending update to MSM orchestrator and going to sleep')
                await asyncio.sleep(sl_duration)
            # await asyncio.sleep(1)
        #event.clear()


if __name__ == '__main__':

    loop = asyncio.get_event_loop()
    print("Starting the path 1 server")
    sockfile = '/home/ubuntu/path1.sock'
    path1sock = os.open(sockfile, os.O_WRONLY)
    # listen = loop.create_datagram_endpoint(
    #    lambda: Path1Protocol(path1sock),
    #    local_addr=('55::4', 12346))
    # transport, protocol = loop.run_until_complete(listen)
    arg_parser = argparse.ArgumentParser(
            description='Measurement script for game server',
            usage='%(prog)s [-m msm_period]')
    arg_parser.add_argument('-m', dest='msm_period',
                            help='Measurement period',
                            type=float,
                            default=1)
    args = arg_parser.parse_args()

    try:
        transport, protocol = loop.run_until_complete(loop.create_datagram_endpoint(
            lambda: Path1Protocol(path1sock, args.msm_period),
            local_addr=('55::4', 12346),
            reuse_address=True))
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        print("Game server is shutting down.")
    finally:
        for task in protocol.send_ping_tasks:
            task.cancel()

        if protocol.send_update_task is not None:
            protocol.send_update_task.cancel()

        if protocol.calculate_task is not None:
            protocol.calculate_task.cancel()
        transport.close()
        loop.run_until_complete(transport.wait_closed())
        loop.close()
