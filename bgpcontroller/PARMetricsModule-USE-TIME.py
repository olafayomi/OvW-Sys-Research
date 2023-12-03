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

import json
import time
import csv
from copy import deepcopy
from abc import abstractmethod, ABCMeta
from multiprocessing import Process, Queue
from queue import Empty
from ctypes import cdll, byref, create_string_buffer
from collections import defaultdict
from Prefix import Prefix
from RouteEntry import RouteEntry, DEFAULT_LOCAL_PREF
import random
import logging
from PolicyObject import PolicyObject, ACCEPT
import perfmon_pb2 as perfmsg
import struct
import select
import os
from google.protobuf.json_format import MessageToDict
from utils import get_address_family, ipv6_addr_is_subset,\
     ipv4_addr_is_subset
from Flow import Flow
from socket import AF_INET, AF_INET6
from decimal import Decimal
from decimal import getcontext


def decode_msg_size(size_bytes: bytes) -> int:
    return struct.unpack("<I", size_bytes)[0]


class BasePARModule(Process):
    __metaclass__ = ABCMeta

    def __init__(self, name, command_queue, flows,
                 peer_addrs, period, m_period, datadir):
        Process.__init__(self, name=name)
        getcontext().prec = 5
        self.command_queue = command_queue
        self.flows = []

        self.prefixes = set()
        self.thresholds = {}
        for flowtype, desc in flows.items():
            print("Desc: %s" % desc)
            print("desc['prefixes']: %s" % desc['prefixes'])
            flow = Flow(flowtype, desc['protocol'], desc['port'], desc['prefixes'])
            if 'threshold' in desc:
                self.thresholds[flowtype] = float(desc['threshold'])
            else:
                self.thresholds[flowtype] = 30.0
            self.flows.append(flow)
            for prefix in desc['prefixes']:
                self.prefixes.add(Prefix(prefix))
            print("Threshold: %s" % self.thresholds)
        self.routes = {prefix: set() for prefix in self.prefixes}
        self.daemon = True
        self.enabled_peers = peer_addrs
        self.period = period
        self.mperiod = m_period
        self.mailbox = Queue()
        self.last_performed = 0
        self.best_routes = {}
        self.counter = 0
        self.current_routes = {}
        self.preferred_routes = {}
        self.clients = set()
        self.client_dst_msm = {}
        self.flag = False
        self.actions = {
            "add": self._process_add_route,
            "remove": self._process_remove_route,
            "get": self._process_send_best_route,
            "set-initial": self._process_initial_route,
        }
        self.unixsock = '/home/ubuntu/'+str(self.name)+'.sock'
        self.decision_report_file = datadir+'/PARDecisionFile.csv'
        with open(self.decision_report_file, 'w') as report:
            writer = csv.writer(report, delimiter='|')
            writer.writerow(["Time", "Prefix", "Exit-Node Name", "Next-Hop", "Estimated Delay"])
        self.clientSessionTime = datadir+'/PARClientSession.csv'
        with open(self.clientSessionTime, 'w') as sesstime:
            writer = csv.writer(sesstime, delimiter='|')
            writer.writerow(["Time", "Prefix"])


        #'/home/ubuntu/perf.sock'
        os.mkfifo(self.unixsock)

    def __str__(self):
        return "Performance-Aware Module(type: %s)" % (self.name)

    def run(self):
        libc = cdll.LoadLibrary("libc.so.6")
        buff = create_string_buffer(len(self.name)+5)
        buff.value = ("foo " + self.name).encode()
        libc.prctl(15, byref(buff), 0, 0, 0)

        callbacks = []

        try:
            perfpipe = os.open(self.unixsock, os.O_RDONLY | os.O_NONBLOCK)
            try:
                poll = select.poll()
                poll.register(perfpipe, select.POLLIN)
                try:
                    while True:
                        #curr_time = time.time()
                        #if self.last_performed != 0:
                        #    time_diff = curr_time - self.last_performed
                        #    if time_diff > 120:
                        #        best_routes = self._send_latest_best_route()
                        #        self.command_queue.put(("par-update", {
                        #            "routes": best_routes,
                        #            "type": self.name,
                        #        }))
                        if (perfpipe, select.POLLIN) in poll.poll(100):
                            self.log.info("PARMetricsModule %s received message from IPMininet!!!" % self.name)
                            msg_size_bytes = os.read(perfpipe, 4)
                            msg_size = decode_msg_size(msg_size_bytes)
                            msg_content = os.read(perfpipe, msg_size)
                            #perfnode = perfmsg.ExitNode()
                            #exitnode = perfnode.FromString(msg_content)
                            #node = exitnode.name
                            #nexthop = exitnode.address
                            # Compare paths and make decision to switch here:
                            msmMsg = perfmsg.DstMsmMsgs()
                            msms = msmMsg.FromString(msg_content)
                            #if len(self.clients) == 0:
                            #    self.client_dst_msm['time'] = time.monotonic()
                            for dstPerfMsg in msms.dstMsm:
                                dstAddr = dstPerfMsg.DstAddr
                                #delay_l = []
                                nodes_m = []
                                for exitnode in dstPerfMsg.node:
                                    node = exitnode.name
                                    nexthop = exitnode.address
                                    #delay = round(exitnode.delay, 4)
                                    #delay_l.append(delay)
                                    estDelay = round(exitnode.estDelay, 4)
                                    devDelay = round(exitnode.devDelay, 4)
                                    nodes_m.append((node, nexthop, estDelay, devDelay))
                                if dstAddr not in self.clients:
                                    with open(self.clientSessionTime, 'a') as sesstime:
                                        row = [time.time(), dstAddr]
                                        writer = csv.writer(sesstime, delimiter='|')
                                        writer.writerow(row)
                                    self.clients.add(dstAddr)
                                    self.client_dst_msm[dstAddr] = {}
                                    self.client_dst_msm[dstAddr]['msm_sample'] = 1
                                    self.client_dst_msm[dstAddr]['time'] = time.monotonic()
                                    self.log.info("PARMetricsModule ROUTING PERIOD for %s begins" %dstAddr)
                                    for n in nodes_m:
                                        name, nh, estD, devD = n
                                        self.client_dst_msm[dstAddr][name] = {}
                                        self.client_dst_msm[dstAddr][name]['estDelay'] = estD
                                        self.client_dst_msm[dstAddr][name]['PrvEstDelay'] = estD
                                        self.client_dst_msm[dstAddr][name]['devDelay'] = devD
                                        #self.client_dst_msm[dstAddr][name]['delay'] = [d]
                                        self.client_dst_msm[dstAddr][name]['nexthop'] = nh
                                    #self.log.info("PARMetricsModule self.client_dst_msm: %s" % self.client_dst_msm)
                                else:
                                    self.client_dst_msm[dstAddr]['msm_sample'] += 1
                                    for n in nodes_m:
                                        name, nh, estD, devD = n
                                        self.client_dst_msm[dstAddr][name]['PrvEstDelay'] = self.client_dst_msm[dstAddr][name]['estDelay']
                                        self.client_dst_msm[dstAddr][name]['estDelay'] = estD
                                        self.client_dst_msm[dstAddr][name]['devDelay'] = devD

                                #self.log.info("PARMetricsModule received measurements for DST:%s from nodes: %s" % (dstAddr, nodes_m))
                                pname, pnextop, pestDelay, pdevDelay = nodes_m[0]
                                #self.log.info("PARMetricsModule number of measurements stored for DST:%s for %s is %s" %(dstAddr, pname, self.client_dst_msm[dstAddr][pname]['estDelay']))

                            #self.log.info("PARMetricsModule Routing Period Cycle for is: %s" %self.period)
                            for dstAddr in self.clients:
                            #if (time.monotonic() - self.client_dst_msm['time']) >= self.period:
                                #self.log.info("PARMetricsModule Routing Period Cycle is: %s" %self.period)
                                ## Full algorithm here:
                                ## Get current path
                                #for dstAddr in self.clients:
                                #if (self.client_dst_msm[dstAddr]['msm_sample'] * self.mperiod) >= self.period:
                                if (time.monotonic() - self.client_dst_msm[dstAddr]['time']) >= self.period:
                                
                                    self.log.info("PARMetricsModule Routing Period Cycle, Measurement Period Cycle and Samples collected for DST:%s is: %s, %s, %s" % (dstAddr, self.period, self.mperiod, self.client_dst_msm[dstAddr]['msm_sample']))
                                    if Prefix(dstAddr) not in self.preferred_routes:
                                        curr_route, current_node = self.current_routes[Prefix(dstAddr)]
                                        self.log.info("PARMetricsModule PICKING ROUTE via %s with NEXTHOP: %s for DST:%s from self.current_routes"
                                                      %(current_node, curr_route.nexthop, dstAddr))
                                        self.preferred_routes[Prefix(dstAddr)] = self.current_routes[Prefix(dstAddr)]
                                        self.flag = True
                                    else:
                                        curr_route, current_node = self.preferred_routes[Prefix(dstAddr)]
                                        
                                    lower_th_node = []
                                    lower_th_node_d = []
                                    #good_nodes = []
                                    #good_nodes_d = []
                                    best_route = {}
                                    nodes = []
                                    delay_l = []

                                    for e_node in self.client_dst_msm[dstAddr].keys():
                                        if (e_node == 'msm_sample') or  (e_node == 'time'):
                                            continue
                                        estDelay = self.client_dst_msm[dstAddr][e_node]['estDelay']
                                        PrvEstDelay = self.client_dst_msm[dstAddr][e_node]['PrvEstDelay']
                                        nh = self.client_dst_msm[dstAddr][e_node]['nexthop']
                                        devDelay = self.client_dst_msm[dstAddr][e_node]['devDelay']
                                        delay_l.append(estDelay)
                                        nodes.append((e_node, nh, estDelay, PrvEstDelay, devDelay))
                                        # Handle link and path failure 2023-05-23
                                        if (estDelay < (self.thresholds['gaming'])) and (estDelay != 0.0):
                                            lower_th_node.append((e_node, nh, estDelay, devDelay))
                                            lower_th_node_d.append(estDelay)

                                    for e_node in self.client_dst_msm[dstAddr].keys():
                                        if (e_node == 'msm_sample') or (e_node == 'time'):
                                            continue
                                        estDelay = self.client_dst_msm[dstAddr][e_node]['estDelay']
                                        prevDelay = self.client_dst_msm[dstAddr][e_node]['PrvEstDelay']
                                        devDelay = self.client_dst_msm[dstAddr][e_node]['devDelay']
                                        n_delay = estDelay + (2.5 * devDelay)
                                        if e_node == current_node:
                                            #if (n_delay >= (self.thresholds['gaming'] - 0.05)) or (n_delay == 0.0):
                                            #if (n_delay >= (self.thresholds['gaming'] - 0.5)) or (n_delay == 0.0):
                                            if  (n_delay >= (self.thresholds['gaming'] - (5.0 *  devDelay))) or (estDelay == 0.0):
                                                self.log.info("PARMetricsModule REPORTING n_delay on current path for  DST:%s as %sms using a devRTT of %s" % (dstAddr, n_delay, devDelay))

                                                if len(lower_th_node) != 0:
                                                    min_best = min(lower_th_node_d)
                                                    for lth_node in lower_th_node:
                                                        lt_name, lt_nh, lt_delay, lt_devDelay = lth_node
                                                        if lt_delay == min_best:
                                                            self.log.info("PARMetricsModule should update path for DST:%s to a better one" % dstAddr)
                                                            best_route = self._fetch_route_for_prefix(lt_name, lt_nh, dstAddr)
                                                            self.preferred_routes[Prefix(dstAddr)] = best_route[Prefix(dstAddr)][0]
                                                            # XXX 2023-08-16 self.preferred_routes is set here based on measurements
                                                            #if Prefix(dstAddr) in self.preferred_routes:
                                                            #    self.preferred_routes[Prefix(dstAddr)] = best_route[Prefix(dstAddr)][0]
                                                            #else:
                                                            #    self.log.info("PARMetricsModule NO_CURRENT_ROUTE for %s" % dstAddr)

                            
                                    if len(best_route) != 0:
                                        self.command_queue.put(("par-update", {
                                            "routes": best_route,
                                            "type": self.name,
                                        }))
                                        with open(self.decision_report_file, 'a') as reporting:
                                            route_val = list(best_route.values())[0]
                                            route, exitNodeName = route_val[0]
                                            row = [time.time(), dstAddr, exitNodeName, route.nexthop, min(lower_th_node_d)]
                                            writer = csv.writer(reporting, delimiter='|')
                                            writer.writerow(row)
                                        self.log.info("PARMetricsModule RUN RECEIVED PERFOMANCE UPDATE for PREFIX %s AND NOTIFIED CONTROLLER TO UPDATE DATAPLANE WITH: %s" % (dstAddr, best_route))
                                    self.client_dst_msm[dstAddr]['msm_sample'] = 0
                                    self.client_dst_msm[dstAddr]['time'] = time.monotonic()
                                ###### 2023-03-06 Disabled this
                                #min_d = min(delay_l)
                                #max_d = max(delay_l)
                                #pct_change = ((max_d - min_d)/min_d) * 100
                                #self.log.info("PARMetricsModule percentage difference in paths for DST:%s is %s" %(dstAddr, pct_change))
                                #if pct_change > 10:
                                #    for e_node in nodes:
                                #        n_name, n_nh, n_delay = e_node
                                #        if n_delay == min_d:
                                #            self.log.info("PARMetricsModule should update path for DST:%s to a better one" % dstAddr)
                                #            #self.best_routes = self._fetch_route(n_name, n_nh)
                                #            best_route = self._fetch_route_for_prefix(n_name, n_nh, dstAddr)
                                #            break
                                #else:
                                #    best_route = {}
                                #self.log.info("PARMetricsModule DISABLED _fetch_route function, show self.best_routes: %s" %self.best_routes)
                                #if len(best_route) != 0:
                                #    self.command_queue.put(("par-update", {
                                #        "routes": best_route,
                                #        "type": self.name,
                                #    }))
                                #    self.log.info("PARMetricsModule RUN RECEIVED PERFOMANCE UPDATE for PREFIX %s AND NOTIFIED CONTROLLER TO UPDATE DATAPLANE WITH: %s" %(dstAddr,best_route))
                            
            
                            ###### 2023-03-03
                            #nodes = []
                            #delay_l = []
                            #perf_msg = perfmsg.PerformanceMsg()
                            #perf = perf_msg.FromString(msg_content)
                            #for exitnode in perf.node:
                            #    node= exitnode.name
                            #    nexthop = exitnode.address 
                            #    delay = exitnode.delay
                            #    delay_l.append(delay)
                            #    nodes.append((node, nexthop, delay))
                            #self.log.info("PARMetricsModule received nodes: %s" %nodes)
                            #min_d = min(delay_l)
                            #max_d = max(delay_l)
                            #pct_change = ((max_d - min_d)/min_d) * 100
                            #self.log.info("PARMetricsModule percentage difference in paths is %s" %pct_change)
                            #if pct_change > 10: 
                            #    for e_node in nodes: 
                            #        n_name, n_nh, n_delay = e_node
                            #        if n_delay == min_d:
                            #            self.best_routes = self._fetch_route(n_name, n_nh)
                            #            break
                            ##### 2023-03-03
                            #self.best_routes = self._fetch_route(node, nexthop)

                            ###### 2023-03-04
                            #if len(self.best_routes) != 0: 
                            #    self.command_queue.put(("par-update", {
                            #        "routes": self.best_routes,
                            #        "type": self.name,
                            #    }))
                            #    self.log.info("PARMetricsModule RUN RECEIVED PERFOMANCE UPDATE AND NOTIFIED CONTROLLER TO UPDATE DATAPLANE WITH: %s" %self.best_routes)
                            ##### 2023-03-04 
                        else:
                            pass

                        try:
                            msgtype, message = self.mailbox.get(block=True, timeout=0.2)
                        except Empty:
                            for callback, timeout in callbacks:
                                self.log.debug("No recent messages, callback %s triggereed" %
                                        callback)
                                callback()
                            callbacks.clear()
                            continue

                        # if it's been too long since we added a callback, deal with it
                        # now before continuing to process messages
                        while len(callbacks) > 0 and callbacks[0][1] < time.time():
                            self.log.debug("Triggering overdue callback %s" % callback)
                            callback, timeout = callbacks.pop(0)
                            callback()

                        if msgtype in self.actions:
                            # actions may trigger a callback (e.g. advertising routes) but
                            # we don't want to repeatedly perform these actions, so delay
                            # briefly in case we get more messages
                            callback = self.actions[msgtype](message)
                            if callback and not any(callback == x for x, y in callbacks):
                                callbacks.append((callback, time.time() + 10))
                        else:
                            self.log.warning("Ignoring unknown message type %s" % msgtype)
                        del message
                finally:
                    poll.unregister(perfpipe) 
            finally:
                os.close(perfpipe)
        finally:
            os.remove(self.unixsock)

    def _process_add_route(self, message):
        for route_tup in message["routes"]:
            route, pref = route_tup
            self.log.info("BANDWIDTH_DIMEJI_BBBBBBB _process_add_route: %s" %route)
            self.log.info("BANDWIDTH_DIMEJI_FBDSDBFDSD _process_add_route: prefix type is %s" % type(route))
            pfx = route.prefix
            self.log.info("BANDWIDTH_DIMEJI_CHECKING PFX is %s" %pfx)
            self.log.info("BANDWIDTH_DIMEJI_CHECKING PFX TYPE is %s" %type(pfx))
            addr_family = get_address_family(str(pfx))
            if addr_family == AF_INET6:
                for dest in self.prefixes:
                    if ipv6_addr_is_subset(str(dest),str(pfx)):
                        self.routes[dest].add((route, message["from"]))

            if addr_family == AF_INET:
                for dest in self.prefixes:
                    if ipv4_addr_is_subset(str(dest),str(pfx)):
                        self.routes[dest].add((route, message["from"]))
            #for route in message["routes"][prefix]:
            #    self.routes[prefix].add((route, message["from"]))
        self.log.info("BANDWIDTH_DIMEJI_BBBBB _process_add_route: %s" %self.routes)
        return

    def _process_remove_route(self, message):
        for dest in self.prefixes:
            pfx = str(message["prefix"])
            addr_family = get_address_family(str(pfx))
            if addr_family == AF_INET6:
                if ipv6_addr_is_subset(str(dest), pfx):
                    self.log.info("BANDWIDTH_DIMEJI _process_remove_route Prefix: %s and for Route %s\n\n\n" %(message["prefix"], message["route"]))
                    self.routes[dest].remove((message["route"],message["from"]))

                if ipv4_addr_is_subset(str(dest), pfx):
                    self.log.info("BANDWIDTH_DIMEJI _process_remove_route Prefix: %s and for Route %s\n\n\n" %(message["prefix"], message["route"]))
                    self.routes[dest].remove((message["route"],message["from"]))
                self.counter = 0

    # Initialise current routes with routes selected by Peer process
    def _process_initial_route(self, message):
        sender = message["from"]
        prefixes = message["prefixes"]
        for prefixDict in prefixes:
            pfx = list(prefixDict.keys())[0]
            route, exitnode = prefixDict[pfx] 
            self.log.info("PARModule processing initial BGP best and current route to %s received by %s" %(pfx, sender))
            addr_family = get_address_family(str(pfx))
            if addr_family == AF_INET6:
                for dest in self.prefixes:
                    if ipv6_addr_is_subset(str(dest), str(pfx)):
                        self.current_routes[dest] = (route, exitnode)
                        if (dest not in self.preferred_routes) and self.flag is False:
                            best_route = self._fetch_route_for_prefix(exitnode,
                                                                      route.nexthop,
                                                                      str(dest))
                            if len(best_route) != 0:
                                self.command_queue.put(("par-update", {
                                                        "routes": best_route,
                                                        "type": self.name,
                                                        }))

                        #if dest not in self.preferred_routes:
                        #    self.preferred_routes[dest] = (route, exitnode)
                        #else:
                        #    pref_route, pref_exitnode = self.preferred_routes[dest]
                        #    if pref_exitnode != exitnode:
                        #        self.preferred_routes[dest] = (route, exitnode)


            if addr_family == AF_INET:
                for dest in self.prefixes:
                    if ipv4_addr_is_subset(str(dest), str(pfx)):
                        self.current_routes[dest] = (route, exitnode)
                        if (dest not in self.preferred_routes) and self.flag is False:
                            best_route = self._fetch_route_for_prefix(exitnode,
                                                                      route.nexthop,
                                                                      dest)
                            if len(best_route) != 0:
                                self.command_queue.put(("par-update", {
                                                        "routes": best_route,
                                                        "type": self.name,
                                                        }))
                        #if dest not in self.preferred_routes:
                        #    self.preferred_routes[dest] = (route, exitnode)
                        #else:
                        #    pref_route, pref_exitnode = self.preferred_routes[dest]
                        #    if pref_exitnode != exitnode:
                        #        self.preferred_routes[dest] = (route, exitnode)

        for dest, route in self.current_routes.items():
            self.log.info("PARModule will use %s initially for %s" %(route, dest))


    def _evaluate_rtt_trend(self, actual_rtt, estimated_rtt):
        if isinstance(actual_rtt, float) and isinstance(estimated_rtt, float):
            diff = actual_rtt - estimated_rtt

            if diff <= 0.5:
                return "STABLE"

            if diff > 1.0:
                return "UP"

        if isinstance(actual_rtt, list) and isinstance(estimated_rtt, list):
            rtt_diff = [actual - estimated for actual, estimated in zip(actual_rtt, estimated_rtt)]

            if all(diff > 1.0 for diff in rtt_diff):
                return "UP"
            elif all(diff <= 0.5 for diff in rtt_diff):
                return "STABLE"
            else:
                return "UNSTABLE"


    @abstractmethod
    def _send_latest_best_route(self):
        pass
    
    @abstractmethod
    def _fetch_route(self, exitpeer, nexthop):
        pass

    @abstractmethod
    def _fetch_route_for_prefix(self, exitpeer, nexthop, prefix):
        pass

    @abstractmethod
    def _process_send_best_route(self, message):
        self.log.info("PARMetricsModule_DIMEJI_BBB _process_send_best_route print before pass!!!!!!!")
        pass


class Bandwidth(BasePARModule):
    def __init__(self, name, command_queue, prefixes, peer_addrs, period, m_period, datadir):
        super(Bandwidth, self).__init__(name, command_queue, flows, peer_addrs, period, m_period, datadir)
        self.log = logging.getLogger("BANDWIDTH")
        #self.actions = {
        #    "get": self._process_send_best_route,
        #}
        self.command_queue = command_queue


    def _fetch_route(self, exitpeer, nexthop): 
        best_routes  = {}
        for prefix, routes_desc in self.routes.items():
            for desc in routes_desc:
                route, exitnode = desc
                if (exitnode == exitpeer) and (nexthop == route.nexthop): 
                    best_routes[prefix] = [desc]
        self.log.info("PARMetricsModule_DIMEJI_VALIDATION _FETCH_ROUTE returning: %s" %best_routes)
        return best_routes


    def _fetch_route_for_prefix(self, exitpeer, nexthop, pfx):
        pfx_route = {}
        for prefix, routes_desc in self.routes.items():
            #self.log.info("PARMetricsModul _fetch_route_for_prefix Prefix:%s, pfx:%s" %(prefix, pfx))
            if Prefix(pfx) == prefix:
                for desc in routes_desc:
                    route, exitnode = desc
                    if (exitnode == exitpeer) and (nexthop == route.nexthop):
                        self.best_routes[prefix] = [desc]
                        pfx_route[prefix] = [desc]
                break
        self.log.info("PARMetricsModule Individual PFX FETCH_ROUTE returning: %s" %pfx_route)
        return pfx_route

    def _send_latest_best_route(self):
        self.last_performed = time.time()

        ### Sending current_routes instead
        #for pfx, routes_desc in self.current_routes.items():
        #    best_routes[pfx] = [routes_desc]

        ### 2023-03-28 Send empty dict instead. Default route should
        # initially handle traffic
        best_routes = {}


        ### 2023-03-06 Send current_routes instead
        #for prefix, routes in self.routes.items():
        #    max_index = len(routes) - 1
        #    if (len(routes) != 0) and (self.counter <= max_index):
        #        #self.counter += 1
        #        lroutes = list(routes)
        #        self.log.info("BANDWIDTH_DIMEJI _send_latest_best_route length of available routes for PAR is %s" %len(routes))
        #        self.log.info("BANDWIDTH_DIMEJI _send_latest_best_route send route %s for counter %s\n\n" %(lroutes[self.counter], self.counter))
        #        best_routes[prefix] = [lroutes[self.counter]]
        #        self.counter += 1
        #        if self.counter > max_index:
        #            self.log.info("BANDWDITH_DIMEJI _send_latest_best_route self.counter is %s to be set to 0\n\n" %self.counter)
        #            self.counter = 0
        #    elif len(routes) == 1:
        #        self.counter = 0
        #        lroutes = list(routes)
        #        self.log.info("BANDWIDTH_DIMEJI _send_latest_best_route length of available routes for PAR is %s" %len(routes))
        #        self.log.info("BANDWIDTH_DIMEJI _send_latest_best_route send route %s for counter %s\n\n" %(lroutes[self.counter], self.counter))
        #        best_routes[prefix] = [lroutes[self.counter]]
        #        self.counter += 1
        #        best_routes[prefix] = [random.choice(list(routes))]
        #    else:
        #        best_routes[prefix] = []

        self.log.info("BANDWITH_DIMEJI _send_latest_best_route: %s" % best_routes)
        return best_routes


    def _process_send_best_route(self, message):
        if message["from"] not in self.enabled_peers:
            return
        ### 2023-03-28 No need sending best_routes anymore.
        # Default route should initially forwarding
        best_routes = {}
        self.command_queue.put(("par-update", {
            "routes": best_routes,
            "type": self.name,
        }))

        #if len(self.best_routes) == 0:
        #    best_routes = self._send_latest_best_route()
        #    self.command_queue.put(("par-update", {
        #        "routes": best_routes,
        #        "type": self.name,
        #    }))
        #else:
        #    self.command_queue.put(("par-update", {
        #        "routes": self.best_routes,
        #        "type": self.name,
        #    }))
        self.log.info("BANDWIDTH_DIMEJI_FJDDHGDJDH^&*^SDHFKDHDH _Process_send_best_route message sent !!!")
        return

class TrafficModule(BasePARModule):
    def __init__(self, name, command_queue, flows, peer_addrs, period, m_period, datadir):
        super(TrafficModule, self).__init__(name, command_queue, flows, peer_addrs, period, m_period, datadir)
        self.log = logging.getLogger(self.name)
        #self.actions = {
        #    "get": self._process_send_best_route,
        #}
        self.command_queue = command_queue


    def _fetch_route(self, exitpeer, nexthop): 
        best_routes  = {}
        for prefix, routes_desc in self.routes.items():
            for desc in routes_desc:
                route, exitnode = desc
                if (exitnode == exitpeer) and (nexthop == route.nexthop): 
                    best_routes[prefix] = [desc]
        self.log.info("PARMetricsModule_DIMEJI_VALIDATION _FETCH_ROUTE returning: %s" %best_routes)
        return best_routes


    def _fetch_route_for_prefix(self, exitpeer, nexthop, pfx):
        pfx_route = {}
        for prefix, routes_desc in self.routes.items():
            #self.log.info("PARMetricsModul _fetch_route_for_prefix Prefix:%s, pfx:%s" %(prefix, pfx))
            if Prefix(pfx) == prefix:
                for desc in routes_desc:
                    route, exitnode = desc
                    if (exitnode == exitpeer) and (nexthop == route.nexthop):
                        self.best_routes[prefix] = [desc]
                        pfx_route[prefix] = [desc]
                break
        #self.log.info("PARMetricsModule Individual PFX FETCH_ROUTE returning: %s" %pfx_route)
        return pfx_route


    def _send_latest_best_route(self):
        self.last_performed = time.time()
        best_routes = {}
        
        ### 2023-03-06 Just send current_routes instead
        #for pfx, routes_desc in self.current_routes.items():
        #    best_routes[pfx] = [routes_desc]

        ### 2023-03-28 Send empty dict instead
        


        self.log.info("BANDWITH_DIMEJI _send_latest_best_route: %s" % best_routes)
        return best_routes

    def _process_send_best_route(self, message):

        if message["from"] not in self.enabled_peers:
            return

        ### 2023-03-28 No need sending best_routes anymore.
        # Default route should initially forwarding
        best_routes = {}
        self.command_queue.put(("par-update", {
            "routes": best_routes,
            "type": self.name,
        }))

        #if len(self.best_routes) == 0:
        #    best_routes = self._send_latest_best_route()
        #    self.command_queue.put(("par-update", {
        #        "routes": best_routes,
        #        "type": self.name,
        #    }))
        #else:
        #    self.command_queue.put(("par-update", {
        #        "routes": self.best_routes,
        #        "type": self.name,
        #    }))
        self.log.info("BANDWIDTH_DIMEJI_FJDDHGDJDH^&*^SDHFKDHDH _Process_send_best_route message sent !!!")
        return

    
