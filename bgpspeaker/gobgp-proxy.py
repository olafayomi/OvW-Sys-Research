#!/usr/bin/env python

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
#

import json
import grpc
import sys
import attribute_pb2 as attrs
import capability_pb2 as caps
import gobgp_pb2 as gobgp
import gobgp_pb2_grpc as gobgpapi
import exabgp_pb2 as exabgp
import exabgpapi_pb2_grpc as exaBGPChannel
from google.protobuf.any_pb2 import Any
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.empty_pb2 import Empty
from google.protobuf.json_format import MessageToJson
from google.protobuf.json_format import MessageToDict
from beeprint import pp
import time


gobgp_metadata = [('ip', '192.168.122.172')]
local_metadata = [('ip', '127.0.0.1')]


def ControllerStub():
    channel = grpc.insecure_channel('localhost:50051')
    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        sys.stderr.write('Error connecting to overwatch controller')
        sys.stderr.flush()
    else:
        stub = exaBGPChannel.ControllerInterfaceStub(channel)
        return stub


def GoBGPStub():
    channel = grpc.insecure_channel('192.168.122.172:50052')
    try:
        grpc.channel_ready_future(channel).result(timeout=10)
    except grpc.FutureTimeoutError:
        sys.stderr.write('Error connecting to GoBGP instance')
        sys.stderr.flush()
    else:
        stub = gobgpapi.GobgpApiStub(channel)
        return stub


def run():
    ctlrStub = ControllerStub()
    goStub = GoBGPStub()
    peers = ctlrStub.GetPeerAddr(Empty(), metadata=local_metadata)
    peer_addresses = []
    for peer in peers:
        peer_addresses.append(peer.peer_addr)
        Peer = gobgp.Peer()
        pconf = gobgp.PeerConf(local_as=peer.local_as,
                               neighbor_address=peer.peer_addr,
                               peer_as=peer.peer_as)
        tcp = gobgp.Transport(local_address=peer.speaker_id,
                              local_port=179,
                              mtu_discovery=True,
                              passive_mode=True,
                              remote_address=peer.peer_addr,
                              remote_port=179)
        timer = gobgp.Timers(
              config=gobgp.TimersConfig(hold_time=90,
                                        keepalive_interval=60,
                                        minimum_advertisement_interval=30),
              state=gobgp.TimersState(hold_time=90,
                                      keepalive_interval=60,
                                      minimum_advertisement_interval=30))
        Peer.conf.MergeFrom(pconf)
        Peer.timers.MergeFrom(timer)
        Peer.transport.MergeFrom(tcp)
        addPeerReq = gobgp.AddPeerRequest(peer=Peer)
        goStub.AddPeer(addPeerReq, metadata=gobgp_metadata)
        enablePeerReq = gobgp.EnablePeerRequest(address=peer.peer_addr)
        goStub.EnablePeer(enablePeerReq, metadata=gobgp_metadata)
    time.sleep(60)
    while True:
        # Check Peer state
        for addr in peer_addresses:
            peers = goStub.ListPeer(gobgp.ListPeerRequest(
                      address=addr,
                      enableAdvertised=True), metadata=gobgp_metadata)
            for peer in peers:
                peer_dict = MessageToDict(peer)
                print("Peer: %s\n" %peer_dict)
                                                         
        listpathreq = gobgp.ListPathRequest()
        listpathreq.table_type = 0
        listpathreq.family.MergeFrom(gobgp.Family(
                                       afi=gobgp.Family.AFI_IP,
                                       safi=gobgp.Family.SAFI_UNICAST))
        paths = goStub.ListPath(listpathreq, metadata=gobgp_metadata)
        for path in paths:
            path_var = MessageToDict(path)
            for key, value in path_var.items():
                print("Key: %s  Value: %s\n" %(key,value))

            



        

if __name__ == '__main__':
    run()
