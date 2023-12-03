#!/usr/bin/env python

# Copyright (c) 2020, WAND Network Research Group
#                     Department of Computer Science
#                     University of Waikato
#                     Hamilton
#                     New Zealand
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
# @Author : Brendon Jones (Original Disaggregated Router)
# @Author : Dimeji Fayomi

from collections import defaultdict
from abc import abstractmethod
import csv
from RouteEntry import RouteEntry, DEFAULT_LOCAL_PREF
from PolicyObject import PolicyObject, ACCEPT
from Routing import BGPDefaultRouting
import copy
import grpc
import json
import time
from Interface import Interface
from DPRouteTable import DPRouteTable, DPFlowMarking
from utils import ipv4_addrs_in_subnet, ipv6_addrs_in_subnet

class Peer(PolicyObject):
    def __init__(self, name, asn, address, control_queue,
            internal_command_queue,
            datadir,
            #preference,
            preference=DEFAULT_LOCAL_PREF,
            default_import=ACCEPT,
            default_export=ACCEPT,
            par=False):

        super(Peer, self).__init__(name, control_queue, default_import,
                default_export)

        # XXX: The self.log attribute is defined by the inheriting classes.
        # This will allow us to specify the correct name for each peer type
        # used, currently BGPPeers and SDNPeers.

        self.asn = asn
        self.address = address
        self.preference = preference
        self.internal_command_queue = internal_command_queue
        self.routing = BGPDefaultRouting(self.address)
        self.export_tables = []
        self.active = False
        self.degraded = 0
        self.enable_PAR = par
        self.PAR_prefixes = []
        self.PARModules = []
        self.interfaces = []
        self.flowobj = []
        self.DPRouteTable = []
        self.steering_inst_file = datadir+'/'+str(self.name)+'PeerSteerInstFile.csv'
        with open(self.steering_inst_file, 'w') as steering:
            writer = csv.writer(steering, delimiter='|')
            writer.writerow(["Time","Prefix","Exit-Hop","Segments","Routing-Table","Action"])

        # Get internal interfaces from dataplane 
        #self._get_interfaces()

        # Create the custom routing tables on the dataplane
        #self._dp_create_routetables()

        # Mark flows with rules and iptables on dataplane
        #self._dp_create_flowmarks()

        # XXX: List of tables we are receive routes from (needed to
        # send reload message to correct tables)
        self.import_tables = []

        self.actions.update({
            "topology": self._process_topology_message,
            "topolinks": self._process_topology_links_message,
            "update": self._process_table_update,
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

        # routes that we are in the process of receiving from a table
        self.pending = {}
        # routes that we are currently exporting
        self.exported = set()
        # routes that were received and accepted from the peer
        # that this process represents.
        self.received = {}
        # routes received from all the tables that we are involved with
        self.adj_ribs_in = {}
        # routes received from all the tables that we are involved with 
        # before processing for PAR routes 
        self.pre_adj_ribs_in = {}

        # PAR routes
        self.par_ribs_in = {}


    def add_import_tables(self, tables):
        if not isinstance(tables, list):
            tables = [tables]
        self.import_tables.extend(tables)

    @abstractmethod
    def _do_announce(self, prefix, route):
        pass

    @abstractmethod
    def _do_withdraw(self, prefix, route):
        pass

    def _do_export_routes(self, refresh=False):

        # if the peer isn't connected then don't bother trying to export routes
        if self.active is False:
            self.log.debug("Peer %s is not connected, not exporting routes" %
                    self.name)
            return

        # if there is no topology then don't bother trying to export routes
        if self.routing.topology is None:
            self.log.debug("Peer %s is missing topology, not exporting routes" %
                    self.name)
            return

        if refresh:
            # This is a route refresh, announce all the routes that we are
            # currently exporting
            for (prefix, route, locPref) in self.exported:
                self._do_announce(prefix, route, locPref)
            return
        #self.log.info("DIMEJI_DEBUG_PEER _do_export_routes printing self.adj_ribs_in for %s" %self.name)
        #for table, routes in self.adj_ribs_in.items():
        #    self.log.info("DIMEJI_DEBUG_PEER_YYYYYYYYYY _do_export_routes TABLE: %s, ROUTES: %s" %(table, routes))

        # XXX: Enabling PAR for specific prefixes 20201120
        #if self.enable_PAR is True:
        #    par_table_name = []
        #    for module in self.PARModules:
        #        par_table_name.append(module.name)
        #    self.pre_adj_ribs_in = copy.deepcopy(self.adj_ribs_in)
        #    for table, routes in self.adj_ribs_in.items():
        #        if table not in par_table_name:
        #            for prefix in self.PAR_prefixes:
        #                if prefix in routes:
        #                    #self.log.info("DIMEJI_DEBUG_PEER_JDHGDDH _do_export_routes  %s   Popping %s routes from other tables" %(self.name, str(prefix)))
        #                    routes.pop(prefix)
            
        # XXX massage this to list of tuples because that's what old code wants
        # XXX removing this would save a ton of memory!
        # XXX what is this actually doing and why? going from dict of
        # prefix:routes to tuple prefix,route?

        
        # XXX: Remove this because now we hide paths. 20201120

        #if self.enable_PAR is True:
        #    adj_export_routes = self.filter_export_routes(self.adj_ribs_in)
        #    par_export_routes = self.filter_export_routes(self.par_ribs_in)
        #    export_routes = {**par_export_routes, **adj_export_routes}
        #else:
        export_routes = self.filter_export_routes(self.adj_ribs_in)

        # at this point we have all the routes that might be relevant to us
        # and we need to figure out which ones we actually want to advertise
        export_routes = self.routing.apply(export_routes)

        if len(export_routes) == 0:
            # XXX: IF ROUTES ARE NO LONGER EXPORTABLE TO THE PEER
            # WITHDRAW ALL ROUTES, IF ANY, BEFORE CLEARING THE EXPOTED
            # ROUTES.
            self.exported.clear()
            return

        full_routes = []
        full_routes_pfxs = set()
        for prefix, routes in export_routes.items():
            for route_t in routes:
                route, pref = route_t
                if self.degraded:
                    # add communities if we are degraded in some way
                    route.add_communities([(self.asn, self.degraded)])
                
                full_routes.append((prefix, route, pref))
            full_routes_pfxs.add(prefix)
        full_routes = set(full_routes)
        del export_routes

        # withdraw all the routes that were previously advertised in self.exported  but are 
        # not in `full_routes` to prevent advertising invalid routes and blackholing traffic.
        self.log.debug("For Peer Process %s Number of routes in full_routes and self.exported are %s and %s", self.name, len(full_routes), len(self.exported))
        self.log.debug("For Peer Process %s The following routes in are self.exported", self.name)
        for  (prefix, route, pref) in self.exported:
            self.log.debug("                   Peer Process %s self.exported Prefix: %s, Route: %s, Pref: %s", self.name, prefix, route, pref)
        self.log.debug("For Peer Process %s The following routes in are full_routes", self.name)
        for  (prefix, route, pref) in full_routes:
            self.log.debug("                   Peer Process %s full_routes Prefix: %s, Route: %s, Pref: %s", self.name, prefix, route, pref)
        
        for (prefix, route, pref) in self.exported.difference(full_routes):
            if prefix in full_routes_pfxs:
                continue
            self._do_withdraw(prefix, route, pref)
            edges = list(self.routing.topology.graph.edges)
            dest_node = ""
            for edge in edges:
                edge_data = self.routing.topology.graph.get_edge_data(edge[0], edge[1])
                if route.nexthop == edge_data['dest_addr']:
                    dest_node = edge[1]
                    break

            if dest_node:
                segments = self.routing.topology.get_segments_list(self.name, dest_node)
                self.log.info("TESTING FOR FULL SRV6 FOR ALL ROUTES XXXXXXX: SEGMENT %s RETURNED to node %s for _process_par_update in PEER %s", segments, dest_node, self.name)
                seg_iface = self._iface_to_segments(segments) 
                datapath = [
                            {
                              "paths": [
                                {
                                  "device": seg_iface.ifindex,
                                  "destination": str(prefix),
                                  "encapmode": "encap",
                                  "segments": segments,
                                }
                              ]
                            }
                           ]
                self.internal_command_queue.put(("steer", {
                    "path": datapath[0]["paths"][0],
                    "peer": {
                              "address": self.address,
                              "asn": self.asn,
                            },
                    "action": "Remove"
                }))
                with open(self.steering_inst_file, 'a') as steering:
                    row =[time.time(), str(prefix), dest_node, str(segments), 254, 'Remove']
                    writer = csv.writer(steering, delimiter='|')
                    writer.writerow(row)
                    

            # XXX: I need to fix this... Routes that are still valid should not be removed
            #      from the PAR module list
            # XXX:     Could be removed 20201120
            #if prefix in self.PAR_prefixes:
            #    self.log.info("DIMEJI_DEBUG_PEER _do_export_routes length of pre_adj_ribs_in is %s\n\n\n" %len(self.pre_adj_ribs_in))
            #    rib_len = len(self.pre_adj_ribs_in)
            #    del_route = []
            #    count = 0
            #    for table, routes in self.pre_adj_ribs_in.items():
            #        if prefix not in routes:
            #            rib_len -= 1
            #            continue

            #        if route not in routes[prefix]:
            #            count += 1
            #            del_route.append(count)
            #    if rib_len != len(del_route):
            #        message = (("remove", {
            #                    "route": route,
            #                    "prefix": prefix,
            #                    "from": self.name
            #                  }))
            #        for parmodule in self.PARModules:
            #            self.log.debug("PEER WEIRDNESS DEBUG PAR route delete XXXX Peer %s removing route: %s in _do_export_routes\n\n" %(self.name, route))
            #            parmodule.mailbox.put(message)
        
        # 2023-08-15 Send default/initial routes to PAR module at once as a batch
        initial_msgs = []
        # announce all the routes that haven't been advertised before
        for (prefix, route, pref) in full_routes.difference(self.exported):
            self._do_announce(prefix, route, pref)
            self.log.info("I WANT TO TEST SOMETHING SEE PREFIX: %s, SEE ROUTE: %s", prefix, route)
            self.log.info("AFTER WHICH NEXTHOP is %s", route.nexthop)
            edges = list(self.routing.topology.graph.edges)
            dest_node = ""
            for edge in edges:
                edge_data = self.routing.topology.graph.get_edge_data(edge[0], edge[1])
                if route.nexthop == edge_data['dest_addr']:
                    dest_node = edge[1]
                    break

            ## XXX TODO: How to map interfaces to next-hops ???
            if dest_node:
                segments = self.routing.topology.get_segments_list(self.name, dest_node)
                #self.log.info("TESTING FOR FULL SRV6 FOR ALL ROUTES XXXXXXX: SEGMENT %s RETURNED to node %s for _process_par_update in PEER %s", segments, dest_node, self.name)
                seg_iface = self._iface_to_segments(segments) 
                #self.log.info("PRINTING IFACE INDEX PEERXXXX in %s: %s" % (self.name,seg_iface))
                datapath = [
                            {
                              "paths": [
                                {
                                  "device": seg_iface.ifindex,
                                  "destination": str(prefix),
                                  "encapmode": "encap",
                                  "segments": segments,
                                }
                              ]
                            }
                           ]
                self.internal_command_queue.put(("steer", {
                    "path": datapath[0]["paths"][0],
                    "peer": {
                              "address": self.address,
                              "asn": self.asn,
                            },
                    "action": "Replace"
                }))
                with open(self.steering_inst_file, 'a') as steering:
                    row =[time.time(), str(prefix), dest_node, str(segments), 254, 'Replace']
                    writer = csv.writer(steering, delimiter='|')
                    writer.writerow(row)

                ###: Add initial routes
                ### XXX: 20230306
                ### XXX: 20230815 Send all routes and prefixes to PAR modules at once instead of bit by by
                initial_msgs.append({ prefix: (route, dest_node),
                                     "segments": segments})

                #message = (("set-initial", { prefix: (route, dest_node),
                #                            "segments": segments,
                #                            "from": self.name }))
                #for parmodule in self.PARModules:
                #    self.log.debug("PEER %s sending DEFAULT/INITIAL route for PREFIX:%s to PAR module" %(self.name, prefix))
                #    parmodule.mailbox.put(message)

        ### XXX: 20230815 Update PAR modules with all default/initial routes for prefixes at once instead of bit by bit.
        if len(initial_msgs) != 0:
            message = (("set-initial", {"prefixes" : initial_msgs,
                                        "from": self.name}))
            for parmodule in self.PARModules:
                self.log.debug("PEER %s sending DEFAULT/INITIAL routes for %s PREFIXES to PAR module" %(self.name, len(initial_msgs)))
                parmodule.mailbox.put(message)
                
            ### XXX: Disable adding routes to PAR modules
            ### XXX: Done 20201119
            #if prefix in self.PAR_prefixes:
            #    addroute = { prefix: [route] }
            #    message = (("add", { "routes": addroute,
            #                         "from": self.name}))
            #    for parmodule in self.PARModules:
            #        self.log.debug("PEER DIMEJI DEBUG WEIRDNESS XXXXX _do_export peer %s adding routes to PAR" %(self.name))
            #        parmodule.mailbox.put(message)

        # record the routes we last exported so we can check for changes
        self.exported = full_routes
        #self.log.info("PEER: Checking self.preference for %s is %s" %(self.name, self.preference))
        self.log.info("Finished exporting routes to peer %s", self.name)

    @abstractmethod
    def _can_import_prefix(self, route):
        """
            Check if we can import a specific prefix, by default all prefixes
            are importable. This method should be overwritten in inheriting
            classes to implement this differently. i.e. BGP peers will do a
            negotiated AFI/SAFI check.
        """
        return True

    def _do_export_pa_routes(self, refresh=False):
        pass

    def filter_export_routes(self, export_routes):
        filtered_routes = defaultdict(list)
        # unpack the routes from different tables
        for table in export_routes.values():
            for prefix, routes in table.items():
                #self.log.info("DIMEJI_DEBUG_PEER filter_export_routes printing routes in export_routes: %s and length is %s " % (routes, len(routes)))
                for route in routes:
                    # exclude duplicates - a route might arrive from many tables
                    if route not in filtered_routes[prefix]:
                        filtered_routes[prefix].append(route)

        # perform normal filtering using all attached filters, which will
        # generate us a copy of the routes, leaving the originals untouched
        filtered_routes = super(Peer,self).filter_export_routes(filtered_routes)

        # fix the nexthop value which will be pointing to a router
        # id rather than an address, and may not even be directly
        # adjacent to this peer
        if self.routing.topology:
            for prefix, routes in filtered_routes.items():
                for route_t in routes:
                    route, pref = route_t 
                    nexthop = self.routing.topology.get_next_hop(
                            self.address, route.nexthop)
                    if nexthop:
                        route.set_nexthop(nexthop)
        return filtered_routes

    def _get_filtered_routes(self):
        filtered_routes = []
        #self.log.info("DIMEJI_PEER_DEBUG: self.received.values() is %s" % self.received.values())
        # 2023-06-07 pass tuple with local-preference
        for route_tup in self.received.values():
            # work on a copy of the routes so the original unmodified routes
            # can be run through filters again later if required
            route, pref = route_tup
            filtered = self.filter_import_route(route, copy=True)
            if filtered is not None:
                # add the new route to the list to be announced
                filtered_routes.append((filtered, pref))
        #self.log.info("DIMEJI_PEER_DEBUG: filtered_routes is %s" % filtered_routes)
        return filtered_routes

    def _update_tables_with_routes(self):
        # run the received routes through filters and send to the tables
        # 2023-05-26 Add local-preference of Peer to message sent to table
        message = (("update", {
                    "routes": self._get_filtered_routes(),
                    "from": self.name,
                    "asn": self.asn,
                    "address": self.address,
                    #"local-preference": self.preference,
                    }))
        ### XXX: Added on 20201119
        ### XXX: Testing pushing routes directly to PARModule
        par_msg = (("add", {
                    "routes": self._get_filtered_routes(),
                    "from": self.name
                    }))

        #self.log.info("DIMEJI_PEER_DEBUG _update_tables_with_routes message: %s" % str(message))
        for table in self.export_tables:
            #self.log.info("DIMEJI_PEER_DEBUG _update_tables_with_routes message: %s" % str(message))
            table.mailbox.put(message)
        
        ### XXX: Added on 20201119
        ### XXX: Testing pushing routes directly to PARModule
        for parmodule in self.PARModules:
            self.log.debug("PEER DIMEJI WEIRDNESS DEBUG: Peer %s is adding route to parmodule in _update_tables_with_routes " %(self.name))
            parmodule.mailbox.put(par_msg)
                   
    def _process_table_update(self, message):
        # XXX: check if we can export this prefix, otherwise skip checks
        imp_routes = {}
        for prefix in message["routes"]:
            #self.log.info("DIMEJI_DEBUG_PEER _process_table_update: prefix : %s is type %s" % (prefix,type(prefix)))

            if self._can_import_prefix(prefix):
                imp_routes[prefix] = message["routes"][prefix]

        #self.log.info("DIMEJI_PEER_DEBUG _process_table_update message: %s" % message)
        # No routes can be imported, stop the update process
        if len(imp_routes) == 0:
            return None
        #self.log.info("DIMEJI_PEER_DEBUG _process_table_update message: %s" % message)
        # clobber the old routes from this table with the new lot
        self.adj_ribs_in[message["from"]] = imp_routes
        ### XXX: Disabling adding of routes to PAR module here
        ### XXX: Done 20201119
        #message = (("add", {
        #             "routes": imp_routes,
        #             "from": self.name
        #             }))
        #for parmodule in self.PARModules:
        #    self.log.debug("PEER DIMEJI WEIRDNESS DEBUG: Peer %s is adding route to parmodule in _process_table_update " %(self.name))
        #    parmodule.mailbox.put(message)

        if self.enable_PAR is True:
            #self.log.info("DIMEJI_DEBUG_PEER_YYSYDYDSYSYS _process_table_update requesting par-update peer: %s" %self.name)
            for module in self.PARModules:
                #self.log.info("DIMEJI_DEBUG_PEER_DYDGDSKJHDKHJDDD _do_export_routes      %s          Sending message to PAR Module: %s" %(self.name, module.name))
                #if module.name not in self.adj_ribs_in:
                #    self.adj_ribs_in[module.name] = {}
                message = (("get", {
                            "from": self.address,
                            "routes": self.adj_ribs_in,
                          }))
                module.mailbox.put(message)
                #self.log.info("DIMEJI_DEBUG_PEER_DYDGDSKJHDKHJDDD _process_table_update      %s          Sent message to PAR Module: %s" %(self.name, module.name))
                
            self.pre_adj_ribs_in = copy.deepcopy(self.adj_ribs_in)
        return self._do_export_routes

    def _process_par_update(self, message):
        # XXX: check if we can export this prefix, otherwise skip checks
        imp_routes = {}
        for prefix in message["routes"]: 
            self.log.info("DIMEJI_DEBUG_PEER _process_par_update: prefix : %s is type %s" % (prefix,type(prefix)))
            #stuff = message["routes"][prefix]
            #self.log.info("DIMEJI_DEBUG_PEER XXXXXXXXXXXXXXXYYYYYYYYYYYYYYYYYYYYYYYY _process_par_update: routeprefix is %s and type is: %s\n\n\n" %(stuff, type(stuff)))
            if len(message["routes"][prefix]) != 1:
                #self.log.info("INSERTING RANDOM PRINT HERE TO DEBUG _PROCESS_PAR_UPDATE")
                #self.log.info("DEBUG_PEER _PROCESS_PAR_UPDATE LENGTH OF PREFIX %s"  %len(message["routes"][prefix]))
                #self.log.info("DEBUG_PEER _PROCESS_PAR_UPDATE MESSAGE PREFIX %s" %(message["routes"][prefix]))
                return None
            route, node = message["routes"][prefix][0]
            self.log.info("DIMEJI_DEBUG_PEER XXXXXXXXXXXXXXXXXYYYYYY _process_par_update IN PEER %s: %s and route %s\n\n\n" %(self.name,node, route))
            
            if self._can_import_prefix(prefix):
                imp_routes[prefix] = [route]
                #message["routes"][prefix]
        if len(imp_routes) == 0:
            self.log.info("DIMEJI_DEBUG_PEER _process_par_update IN PEER %s, CHECKING EACH STEP OF FUNC" %self.name)
            return None
        
        if node == self.name:
            self.log.info("DIMEJI_DEBUG_PEER XDNXKASHDNCSHDHGSKDKSCBSBSG _process_par_update: node is the same\n\n\n")
            return None

       
        #self.log.info("DIMEJI_PEER_DEBUG _process_par_update message: %s" % message)
        self.par_ribs_in[message["type"]] = imp_routes
        #### Segment routing experiments
        segments = self.routing.topology.get_segments_list(self.name, node)
        #self.log.info("DIMEJI_PEER_DEBUG _PROCESS_PAR_UPDATE PRINT SEGMENTS: %s" % segments)

        #no_of_nodes, list_nodes = self.routing.topology.returnGraph()
        #self.log.info("DIMEJI_DEBUG_PEER XVSGDGSDSSYXNXNXFDF _process_par_update: number of nodes from graph is %s and list of nodes in graph is %s", no_of_nodes, list_nodes)

        if segments is None:
            self.log.info("DIMEJI_DEBUG_PEER No segments returned from network _process_par_update!!!")
            return None
        else:
            self.log.info("DIMEJI_DEBUG_PEER: SEGMENT %s RETURNED to node %s for _process_par_update in PEER %s", segments, node, self.name)


        # XXX: Set routing table for PAR in LINUX to 201
        rtable = self._return_table_no(message["type"])
        for prefix, routes in imp_routes.items():
            for route in routes:
                nexthop = route.nexthop
                #self.log.info("DIMEJI_PEER_DEBUG _process_par_update NEXTHOP value in route: %s" % nexthop)
            if len(routes) > 1:
                self.log.info("DIMEJI_DEBUG_PEER: LENGTH ROUTES IS GREATER THAN ONE")
                return None

            seg_iface = self._iface_to_segments(segments)
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
                          "asn": self.asn,
                        },
                "action": "Replace"
            }))
            with open(self.steering_inst_file, 'a') as steering:
                row =[time.time(), str(prefix), node, str(segments), rtable, 'Replace']
                writer = csv.writer(steering, delimiter='|')
                writer.writerow(row)

        return
        #return self._do_export_routes


    def _iface_to_segments(self, segs):
        for iface in self.interfaces:
            #self.log.debug("LISTING IFACES in _iface_to_segments function for peer:%s Interface:%s" %(self.name, iface))
            if iface.internal:
                if bool(set(iface.neighbours).intersection(segs)):
                    return iface
                # XXX Check if first address in segment could be in the
                # same subnet as any of the IP addresses of an each interface
                # get last address in segment list
                nhop = segs[-1]
                for addr in iface.addresses:
                    check = ipv6_addrs_in_subnet(nhop, addr)
                    if check:
                        #self.log.debug("COMPARING SUBNET FOR IFACE ADDRESS and FIRST SEGMENT RETURNED A MATCH for NH %s on IFACE %s on Peer %s" %(nhop, iface.ifname, self.name))
                        return iface

    def _fetch_iface_by_name(self, name):
        for iface in self.interfaces:
            if iface.ifname == name:
                return iface
        return None

    def _process_dp_interface(self, message):
        self.log.debug("TRYING SOMETHING XXXX %s" % message)
        ifaces = message['iface']
        internal_neighbours = self.routing.topology.getNeighbourAddr(self.name)
        # XXX: Add OSPF IPv6 multicast addresses. All internal interfaces 
        #      should have these addresses in their neighbour list
        internal_neighbours.append('ff02::5')
        internal_neighbours.append('ff02::6')
        ## Add this to for Eval debug
        internal_neighbours.append('100::4')
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
                val = bool(set(neighs).intersection(internal_neighbours))
            intf.set_internal(val)
            fetch_if = self._fetch_iface_by_name(name)
            # XXX: Only add interface if it doesn't already exist!!!!
            if fetch_if is not None:
                fetch_if.set_internal(val)
            else:
                self.interfaces.append(intf)
        self._dp_create_routetables()


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
            "peer": {
                      "address": self.address,
                      "asn": self.asn,
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
            "peer": {
                      "address": self.address,
                      "asn": self.asn,
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
                      "asn": self.asn,
                    },
            "action": "create-flowmark-rules"
        }))
        return

    # XXX topology messages are a pickled data structure wrapped in a protobuf
    # to make the transition easier. They should probably be made into proper
    # protobuf messages sometime.
    def _process_topology_message(self, message):
        self.log.debug("Topology update received by %s" % self.name)

        # update topology with the new one
        self.routing.set_topology(message)

        # re-evaluate what we are exporting based on the new topology
        # XXX Todo: re-evaluate PAR routes too based on new topology.
        if len(self.adj_ribs_in) > 0:
            return self._do_export_routes
        return None

    def _process_topology_links_message(self, message):
        self.log.debug("Topology links update received by %s" % self.name)

        # update topology with new links
        self.routing.topology.createGraph(message)


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
        return self._do_export_routes


    def _reload_import_filters(self):
        if len(self.received) == 0:
            return
        self._update_tables_with_routes()


    # BGP Connection changed state, tell the controller about it
    def _state_change(self, status):
        if self.active != status:
            self.active = status
            # Make sure we remove routes that have been received from this peer
            # so they don't linger around
            if self.active is False:
                self.received.clear()
                #for prefix, route in self.exported:
                #    self._do_withdraw(prefix, route)
                # Check if this makes the withdrawal of routes any faster!!!
                self.exported.clear()
                self._update_tables_with_routes()
            # tell the controller the new status of this peer
            self.log.debug("%s signalling controller new status: %s" %
                    (self.name, status))
            self.internal_command_queue.put(("status", {
                "peer": {
                    "address": self.address,
                    "asn": self.asn,
                },
                "status": status,
            }))

    def _reload_from_tables(self):
        message = (("reload", {
                    "from": self.name,
                    "asn": self.asn,
                    "address": self.address,
                    }))
        for table in self.import_tables:
            table.mailbox.put(message)
