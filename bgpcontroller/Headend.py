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

from collections import defaultdict
from abc import abstractmethod, ABCMeta
from multiprocessing import Process, Queue
from queue import Empty
from ctypes import cdll, byref, create_string_buffer
from Prefix import Prefix
import csv
from PolicyObject import PolicyObject, ACCEPT
import copy
import grpc
import json
import time
import random
import logging
import struct
import select
import os
from Flow import Flow
from Interface import Interface
from Routing import BGPDefaultRouting
from Network import Network
from DPRouteTable import DPRouteTable, DPFlowMarking
from utils import ipv4_addrs_in_subnet, ipv6_addrs_in_subnet

class Headend(PolicyObject):

    def __init__(self, name, address, control_queue, internal_command_queue,
             datadir):

        super(Headend, self).__init__(name, control_queue,
                                      default_import=ACCEPT,
                                      default_export=ACCEPT)
        self.name = name
        self.address = address
        self.internal_command_queue = internal_command_queue
        self.active = False
        self.degraded = 0
        self.PARModules = []
        self.PAR_prefixes = []
        self.interfaces = []
        self.flowobj = []
        self.DPRouteTable = []
        self.localSIDMap = []
        self.network = None
        self.log = logging.getLogger("Headend")
        self.steering_inst_file = datadir+'/'+str(self.name)+'HeadendSteerInstFile.csv'
        with open(self.steering_inst_file, 'w') as steering:
            writer = csv.writer(steering, delimiter='|')
            writer.writerow(["Time","Prefix","Exit-Hop","Segments","Routing-Table","Action"])
        self.internal_command_queue.put(("headend-notify", {
            "address": self.address,
            "action": "init"
        }))
        
        self.actions.update({
            "topology": self._process_topology_message,
            "topolinks": self._process_topology_links_message,
            "debug": self._process_debug_message,
            "status": self._process_status_message,
            "par": self._process_par_update,
            "interfaces": self._process_dp_interface,
            "dp-tables": self._process_create_dp_table,
            "dp-flowmarks": self._process_create_flow_objects,
            "interface-init": self._get_interfaces,
            #"rtable-init": self._dp_create_routetables,
            #"req-flowmark": self._dp_create_flowmarks,
        })
        self.par_ribs_in  = {}
        self.afi_safi = []

    # XXX topology messages are a pickled data structure wrapped in a protobuf
    # to make the transition easier. They should probably be made into proper
    # protobuf messages sometime.
    def _process_topology_message(self, message):
        self.log.debug("Topology update received by %s" % self.name)

        # update topology with the new one
        self.network = Network(message)

        # re-evaluate what we are exporting based on the new topology
        # XXX Todo: re-evaluate PAR routes too based on new topology.
        return None

    def _process_topology_links_message(self, message):
        self.log.debug("Topology links update received by %s" % self.name)

        # update topology with new links
        self.network.createGraph(message)


    def _process_debug_message(self, message):
        self.log.debug(self)
        return None

    def _process_status_message(self, message):
        # some of our other peers have changed status, so our routing table
        # may not be as good as it was, but should still be announced. Update
        # the routes we send to our peer to reflect that we might be degraded.
        self.log.debug("%s told to change status: %s" % (self.name, message))
        self.degraded = message
        # XXX peers disappearing should cause routes to be withdrawn, updating
        # our tables and causing this peer to export... if we can be certain
        # this message arrives before the route update then we don't need to
        # do an export here
        return None

    def _process_par_update(self, message):
        # XXX: check if we can export this prefix, otherwise skip checks
        imp_routes = {}
        for prefix in message["routes"]: 
            #stuff = message["routes"][prefix]
            if len(message["routes"][prefix]) != 1:
                #self.log.info("INSERTING RANDOM PRINT HERE TO DEBUG _PROCESS_PAR_UPDATE")
                #self.log.info("DEBUG_PEER _PROCESS_PAR_UPDATE LENGTH OF PREFIX %s"  %len(message["routes"][prefix]))
                #self.log.info("DEBUG_PEER _PROCESS_PAR_UPDATE MESSAGE PREFIX %s" %(message["routes"][prefix]))
                return None
            route, node = message["routes"][prefix][0]
            
            #if self._can_import_prefix(prefix):
            imp_routes[prefix] = [route]
                #message["routes"][prefix]
        if len(imp_routes) == 0:
            return None
        
        if node == self.name:
            return None

       
        self.par_ribs_in[message["type"]] = imp_routes
        #### Segment routing experiments
        segments = self.network.get_segments_list(self.name, node)

        #no_of_nodes, list_nodes = self.routing.topology.returnGraph()

        if segments is None:
            return None
        else:


        # XXX: Set routing table for PAR in LINUX to 201
        rtable = self._return_table_no(message["type"])
        for prefix, routes in imp_routes.items():
            for route in routes:
                nexthop = route.nexthop
            if len(routes) > 1:
                return None

            seg_iface = self._iface_to_segments(segments)
            self.log.info("DEBUGGING HEADEND LOCAL SID: %s"  %self.localSIDMap)
            if self.localSIDMap:
                for localSID in self.localSIDMap:
                    if localSID[0] == node:
                        self.log.info("HEADEND SID DEBUG, localSID is %s and node is %s" %(localSID[0], node))
                        for community in route.communities():
                            if int(localSID[3]) in community:
                                segments.insert(0, localSID[2])
                            #for c in community:
                            #    self.log.info("HEADEND SID DEBUG, com val is %s and type %s, localSID is type %s" %(c, type(c), type(localSID[3])))
                            #    if int(localSID[3]) in community:
                            #        segments.insert(0, localSID[2])

            datapath = [
                        {
                          "paths": [
                            {
                               #"device": "as3r2-eth1",
                               "device": seg_iface.ifindex,
                               "destination": str(prefix),
                               "encapmode": "encap",
                               "segments": segments,
                               "table": rtable
                            }
                          ]
                        }
                       ]
            self.internal_command_queue.put(("steer", {
                "path": datapath[0]["paths"][0],
                "peer": {
                          "address": self.address,
                          #"asn": self.asn,
                        },
                "action": "Replace"
            }))
            with open(self.steering_inst_file, 'a') as steering:
                row =[time.time(), str(prefix), node, str(segments), rtable, 'Replace']
                writer = csv.writer(steering, delimiter='|')
                writer.writerow(row)

        return

    def _process_dp_interface(self, message):
        self.log.debug("TRYING SOMETHING XXXX %s" % message)
        self.active = True
        ifaces = message['iface']
        internal_neighbours = self.network.getNeighbourAddr(self.name)
        # XXX: Add OSPF IPv6 multicast addresses. All internal interfaces 
        #      should have these addresses in their neighbour list
        internal_neighbours.append('ff02::1:ff00:4')
        internal_neighbours.append('ff02::1:ff00:2') 
        internal_neighbours.append('ff02::16')
        ## Add this to for Eval debug
        #internal_neighbours.append('100::4')
        self.log.debug("PRINTING INTERNAL NEIGHBOURS for %s %s" %(self.name, internal_neighbours))
        for iface in ifaces:
            name = iface['IfName']
            ind  = iface['IfIndex']
            state = iface['IfState']
            try:
                neighs = iface['Neighbours']
            except KeyError:
                if name == 'lo':
                    neighs = []
                else:
                    self.log.warn("Interface %s has no neighbours!!!")
                    neighs = []
            addrs  = iface['Addresses']
            intf = Interface(name, ind, state, neighs, addrs)
            if name == 'lo':
                val = True
            else:
                self.log.debug("Neighbours of %s on interface %s: %s" %(self.name, name, neighs))
                #val = bool(set(neighs).intersection(internal_neighbours))
                if bool(set(neighs).intersection(internal_neighbours)):
                    val = False
            intf.set_internal(val)
            fetch_if = self._fetch_iface_by_name(name)
            # XXX: Only add interface if it doesn't already exist!!!!
            if fetch_if is not None:
                fetch_if.set_internal(val)
            else:
                self.interfaces.append(intf)
        self._dp_create_routetables()

    def _return_table_no(self, table_name): 
        for table in self.DPRouteTable:
            self.log.debug("Getting table number for %s checking %s" %(table_name, table.name))
            if table.name == table_name:
                return table.num
        return None

    def _process_create_flow_objects(self, message):
        dpflows = message
        for dpflow in dpflows:
            fwmark, proto, port, ifname, tab_no = dpflow
            flowmarks = DPFlowMarking(fwmark, proto, port, ifname, tab_no)
            self.flowobj.append(flowmarks) 

    def _get_interfaces(self, message):
        self.internal_command_queue.put(("manage-dataplane", {
            "headend": {
                      "address": self.address,
                    },
            "action": "get-interfaces",
        }))
        return

    def _dp_create_routetables(self):
        par_traffic = []
        
        for mod in self.PARModules:
            self.log.debug("_DP_CREATE_ROUTETABLES Appending: %s" %mod.name)
            par_traffic.append(mod.name)
        self.internal_command_queue.put(("configure-dataplane", {
            "par-modules": par_traffic,
            "headend": {
                      "address": self.address,
                    },
            "action": "create-tables"
        }))
        return

    def _dp_create_flowmarks(self):
        flows = {}
        i = 1
        ext_ifaces = [] 
        for intf in self.interfaces: 
            self.log.debug("Check for external interface: %s  %s" %(intf.ifname,intf.internal))
            if not intf.internal:
                ext_ifaces.append(intf.ifname)

        for module in self.PARModules:
            self.log.debug("_DP_CREATE_FLOWMARKS Appending: %s" %module.name)
            table_no = self._return_table_no(module.name)
            self.log.debug("_DP_CREATE_FLOWMARKS TABLENO: %s" %table_no)
            for flow in module.flows:
                details =[]
                details.append(i)
                details.append(table_no)
                details.append(flow.protocol)
                details.append(flow.port)
                details.append(ext_ifaces)
                flow.update_routetable(table_no)
                name = flow.name
                flows[name] = details
                i += 1
        self.log.debug("DEBUG DP_CREATE_FLOWMARKS FUNCXXXX Flow sent: %s" %flows) 

        self.internal_command_queue.put(("configure-dataplane", {
            "flows": flows,
            "peer": {
                      "address": self.address,
                      #"asn": self.asn,
                    },
            "action": "create-flowmark-rules"
        }))
        return

    def _process_create_dp_table(self, message):
        tables = message
        for tab in tables:
            tableName, tableNo = tab
            self.log.debug("Creating table object with %s and %s" %(tableName, tableNo))
            # XXX: Only add table if it hasn't been added!!!!
            fetch_tab = self._return_table_no(tableName)
            if fetch_tab is None:
                DPTab = DPRouteTable(tableName, tableNo) 
                self.DPRouteTable.append(DPTab)
        self._dp_create_flowmarks()

    def _fetch_iface_by_name(self, name):
        for iface in self.interfaces:
            if iface.ifname == name:
                return iface
        return None

    def _can_import_prefix(self, prefix):
        """
            Check if a prefixes AFI/SAFI is in our AFI/SAFI list. If not
            return False (can't import prefix from table) otherwise return
            true (import prefix from table)
        """

        # XXX: If the peer has just started up (no negotiated message) we will
        # not import any prefixes. When the negotiated message is received we
        # will re-ask the tables for routes sending a reload command.
        fam = self._afi_safi_to_str(prefix.afi(), prefix.safi())
        family = fam.split(" ")
        for afi, safi in self.afi_safi:

            #if afi == prefix.afi() and safi == prefix.safi():
            if afi == family[0] and safi == family[1]:
                return True
        return False

    def _afi_safi_to_str(self, afi, safi):
        """
            Convert a pair of AFI SAFI numeric values to their exaBGP
            name representation
        """
        name = ""
        if afi == 1:
            name = "ipv4"
        elif afi == 2:
            name = "ipv6"

        if safi == 1:
            name += " unicast"
        elif safi == 2:
            name += " multicast"
        elif safi == 4:
            name += " nlri-mpls"
        elif safi == 128:
            name += " mpls-vpn"
        return name

    def _str_to_afi_safi(self, name):
        """
            Convert an exabgp afi safi string to numeric values
        """
        parts = name.split(" ")
        afi = 0
        safi = 0

        if parts[0] == "ipv4":
            afi = 1
        elif parts[0] == "ipv6":
            afi = 2

        if parts[1] == "unicast":
            safi = 1
        elif parts[1] == "multicast":
            safi = 2
        return (afi, safi)

    def _iface_to_segments(self, segs):
        for iface in self.interfaces:
            self.log.debug("LISTING IFACES in _iface_to_segments function for peer:%s Interface:%s" %(self.name, iface))
            if iface.internal is False:
                if bool(set(iface.neighbours).intersection(segs)):
                    return iface
                # XXX Check if first address in segment could be in the
                # same subnet as any of the IP addresses of an each interface
                # get last address in segment list
                nhop = segs[-1]
                for addr in iface.addresses:
                    check = ipv6_addrs_in_subnet(nhop, addr)
                    if check:
                        self.log.debug("COMPARING SUBNET FOR IFACE ADDRESS and FIRST SEGMENT RETURNED A MATCH for NH %s on IFACE %s on Peer %s" %(nhop, iface.ifname, self.name))
                        return iface

