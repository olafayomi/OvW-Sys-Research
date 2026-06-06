#!/usr/bin/env python

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

import time
import sys
import grpc
import attribute_pb2 as attrs
import gobgp_pb2 as gobgp
import exabgp_pb2 as exabgp
import exabgpapi_pb2_grpc as exaBGPChannel
from google.protobuf.empty_pb2 import Empty
from google.protobuf.json_format import MessageToDict
from concurrent import futures

metadata = [('ip', '127.0.0.1')]
_ONE_DAY_IN_SECONDS = 60 * 60 * 24

def wait_for_grpc_server(server_address, max_retries=30, initial_delay=1, max_delay=60):
    """Wait for gRPC server to become available with exponential backoff"""
    for attempt in range(max_retries):
        try:
            sys.stderr.write(f"Attempt {attempt + 1}: Trying to connect to ExaBGP gRPC server at {server_address}...\n")
            sys.stderr.flush()
            
            channel = grpc.insecure_channel(server_address)
            
            # Try to connect with a shorter timeout for faster failure detection
            grpc.channel_ready_future(channel).result(timeout=5)
            
            sys.stderr.write(f"Successfully connected to ExaBGP gRPC server at {server_address}\n")
            sys.stderr.flush()
            return channel
            
        except grpc.FutureTimeoutError:
            sys.stderr.write(f"Connection timeout on attempt {attempt + 1}\n")
            sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"Connection failed on attempt {attempt + 1}: {e}\n")
            sys.stderr.flush()
        
        if attempt < max_retries - 1:  # Don't sleep on the last attempt
            # Exponential backoff with jitter and max delay cap
            delay = min(initial_delay * (2 ** attempt), max_delay)
            # Add some jitter to prevent thundering herd
            jitter = delay * 0.1 * (0.5 - abs(hash(str(attempt)) % 1000) / 1000.0)
            total_delay = delay + jitter
            
            sys.stderr.write(f"Waiting {total_delay:.2f} seconds before retry...\n")
            sys.stderr.flush()
            time.sleep(total_delay)
    
    raise Exception(f"Failed to connect to ExaBGP gRPC server at {server_address} after {max_retries} attempts")

def CreateExaBGPStub():
    """Create ExaBGP gRPC stub with retry logic and exponential backoff"""
    sys.stderr.write("Creating gRPC connection to ExaBGP server...\n")
    sys.stderr.flush()
    try:
        channel = wait_for_grpc_server('127.0.0.1:50051', max_retries=30, initial_delay=2, max_delay=60)
        stub = exaBGPChannel.ExabgpInterfaceStub(channel)
        sys.stderr.write("Successfully created ExaBGP gRPC stub\n")
        sys.stderr.flush()
        return stub
    except Exception as e:
        print(f"Failed to create ExaBGP gRPC stub: {e}\n")
        sys.exit(1)


def FetchMsg(stub):
    message = stub.GetCtlrMsg(Empty(), metadata=metadata)
    output = MessageToDict(message)
    if len(output) != 0:
        neigh = output['neighborAddress']
        nexthop = output['nexthop']['address']
        peer_as = output['peerAs']
        #prefix = output['nlri']['prefix'][0]
        prefix = output['nlri']['prefix']
        #sys.stderr.write("DEBUG:::::::Announcing/Withdraw to neighbor %s\n" %neigh)
        #sys.stderr.flush()
        if message.msgtype == 0:
            pattrs = output['pattrs']
            sys.stderr.write("DEBUG:::: Attributes for annouce %s\n" %pattrs)
            sys.stderr.flush()
            origin = 'incomplete'
            aspath = " "
            community = " "
            pref = " "
            for attr in pattrs:
                if 'origin' in attr:
                    ori = attr['origin']
                    if ori == 0:
                        origin = 'igp'
                    elif ori == 1:
                        origin = 'egp'
                    elif ori == 2:
                        origin = 'incomplete'
                    elif ori == 3:
                        origin = 'igp'
                    else:
                        origin = 'incomplete'
                
                if 'segments' in attr:
                    as_set = []
                    paths = attr['segments']
                    for as_seg in attr['segments']:
                        if 'numbers' in as_seg:
                            as_set = as_set + as_seg['numbers']
                            for asn in as_set:
                                aspath = aspath +" "+str(asn)

                if 'communities' in attr:
                    for comm in attr['communities']:
                        community = community +" "+str(comm)

                # 2023-05-26 Add local-preference
                #if 'local-preference' in attr:
                if 'localPref' in attr:
                    pref = attr['localPref']


            if isinstance(pref, str):
                announce = 'neighbor ' + neigh + ' announce route '\
                    + prefix + ' next-hop ' + nexthop + ' origin '\
                    + origin + ' as-path ['+ aspath +' ] community ['\
                    + community +' ]'
            else:
                announce = 'neighbor ' + neigh + ' announce route '\
                    + prefix + ' next-hop ' + nexthop + ' origin '\
                    + origin + ' as-path ['+ aspath +' ] community ['\
                    + community + ' ]' + ' local-preference '+ str(pref)

            sys.stdout.write(announce + '\n')
            #sys.stdout.write('neighbor ' + neigh + ' announce route '
            #                 + prefix + ' next-hop '
            #                 + nexthop + ' origin ' + origin + '\n')
            #sys.stdout.write('announce route ' + prefix + ' next-hop '
            #                 + nexthop + ' origin ' + origin + '\n')
            sys.stdout.flush()
        else:
            sys.stdout.write('neighbor ' + neigh + ' withdraw route '
                             + prefix + '\n')
            #sys.stdout.write('withdraw route ' + prefix + '\n')
            sys.stdout.flush()


def run():
    sendStub = CreateExaBGPStub()
    while True:
        FetchMsg(sendStub)
        time.sleep(0.1)


if __name__ == '__main__':
    time.sleep(45)
    run()
