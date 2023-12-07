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
                initial_msgs.append({ prefix: (route, dest_node),
                                     "segments": segments})


        if len(initial_msgs) != 0:
            message = (("set-initial", {"prefixes" : initial_msgs,
                                        "from": self.name}))
            for parmodule in self.PARModules:
                self.log.debug("PEER %s sending DEFAULT/INITIAL routes for %s PREFIXES to PAR module" %(self.name, len(initial_msgs)))
                parmodule.mailbox.put(message)
                
            ### XXX: Disable adding routes to PAR modules

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
                for route in routes:
                    # exclude duplicates - a route might arrive from many tables
                    if route not in filtered_routes[prefix]:
                        filtered_routes[prefix].append(route)

        # perform normal filtering using all attached filters, which will
        # generate us a copy of the routes, leaving the originals untouched
        filtered_routes = super(Peer,self).filter_export_routes(filtered_routes)

        # fix the nexthop value which will be pointing to a router
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
        # 2023-06-07 pass tuple with local-preference
        for route_tup in self.received.values():
            # work on a copy of the routes so the original unmodified routes
            # can be run through filters again later if required
            route, pref = route_tup
            filtered = self.filter_import_route(route, copy=True)
            if filtered is not None:
                # add the new route to the list to be announced
                filtered_routes.append((filtered, pref))
        return filtered_routes

    def _update_tables_with_routes(self):
        # run the received routes through filters and send to the tables
        message = (("update", {
                    "routes": self._get_filtered_routes(),
                    "from": self.name,
                    "asn": self.asn,
                    "address": self.address,
                    }))
        par_msg = (("add", {
                    "routes": self._get_filtered_routes(),
                    "from": self.name
                    }))

        for table in self.export_tables:
            table.mailbox.put(message)
        
        for parmodule in self.PARModules:
            self.log.debug("Peer %s is adding route to parmodule in _update_tables_with_routes " %(self.name))
            parmodule.mailbox.put(par_msg)
                   
    def _process_table_update(self, message):
        # XXX: check if we can export this prefix, otherwise skip checks
        imp_routes = {}
        for prefix in message["routes"]:

            if self._can_import_prefix(prefix):
                imp_routes[prefix] = message["routes"][prefix]

        # No routes can be imported, stop the update process
        if len(imp_routes) == 0:
            return None
        # clobber the old routes from this table with the new lot
        self.adj_ribs_in[message["from"]] = imp_routes

        if self.enable_PAR is True:
            for module in self.PARModules:
                #if module.name not in self.adj_ribs_in:
                #    self.adj_ribs_in[module.name] = {}
                message = (("get", {
                            "from": self.address,
                            "routes": self.adj_ribs_in,
                          }))
                module.mailbox.put(message)
                
            self.pre_adj_ribs_in = copy.deepcopy(self.adj_ribs_in)
        return self._do_export_routes

    def _process_par_update(self, message):
        # XXX: check if we can export this prefix, otherwise skip checks
        imp_routes = {}
        for prefix in message["routes"]: 
            self.log.info("PEER _process_par_update: prefix : %s is type %s" % (prefix,type(prefix)))
            if len(message["routes"][prefix]) != 1:
                return None
            route, node = message["routes"][prefix][0]
            self.log.info(" _process_par_update IN PEER %s: %s and route %s\n\n\n" %(self.name,node, route))
            
            if self._can_import_prefix(prefix):
                imp_routes[prefix] = [route]
        if len(imp_routes) == 0:
            self.log.info("DEBUG_PEER _process_par_update IN PEER %s, CHECKING EACH STEP OF FUNC" %self.name)
            return None
        
        if node == self.name:
            self.log.info("DEBUG_PEER XDNXKASHDNCSHDHGSKDKSCBSBSG _process_par_update: node is the same\n\n\n")
            return None

       
        self.par_ribs_in[message["type"]] = imp_routes
        #### Segment routing experiments
        segments = self.routing.topology.get_segments_list(self.name, node)


        if segments is None:
            self.log.info("DEBUG_PEER No segments returned from network _process_par_update!!!")
            return None
        else:
            self.log.info("DEBUG_PEER: SEGMENT %s RETURNED to node %s for _process_par_update in PEER %s", segments, node, self.name)


        # XXX: Set routing table for PAR in LINUX to 201
        rtable = self._return_table_no(message["type"])
        for prefix, routes in imp_routes.items():
            for route in routes:
                nexthop = route.nexthop
            if len(routes) > 1:
                self.log.info("DEBUG_PEER: LENGTH ROUTES IS GREATER THAN ONE")
                return None

            seg_iface = self._iface_to_segments(segments)
            datapath = [
                        {
                          "paths": [
                            {
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
            if iface.internal:
                if bool(set(iface.neighbours).intersection(segs)):
                    return iface
                # XXX Check if first address in segment could be in the
                nhop = segs[-1]
                for addr in iface.addresses:
                    check = ipv6_addrs_in_subnet(nhop, addr)
                    if check:
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
        internal_neighbours.append('ff02::5')
        internal_neighbours.append('ff02::6')
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
            if self.active is False:
                self.received.clear()
                self.exported.clear()
                self._update_tables_with_routes()
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

