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
        self.routes = {}
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
                        if (perfpipe, select.POLLIN) in poll.poll(100):
                            msg_size_bytes = os.read(perfpipe, 4)
                            msg_size = decode_msg_size(msg_size_bytes)
                            msg_content = os.read(perfpipe, msg_size)
                            # Compare paths and make decision to switch here:
                            msmMsg = perfmsg.DstMsmMsgs()
                            msms = msmMsg.FromString(msg_content)
                            for dstPerfMsg in msms.dstMsm:
                                dstAddr = dstPerfMsg.DstAddr
                                nodes_m = []
                                for exitnode in dstPerfMsg.node:
                                    node = exitnode.name
                                    nexthop = exitnode.address
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
                                    self.client_dst_msm[dstAddr]['time'] = time.perf_counter()
                                    self.log.info("PARMetricsModule ROUTING PERIOD for %s begins" %dstAddr)
                                    for n in nodes_m:
                                        name, nh, estD, devD = n
                                        self.client_dst_msm[dstAddr][name] = {}
                                        self.client_dst_msm[dstAddr][name]['estDelay'] = estD
                                        self.client_dst_msm[dstAddr][name]['PrvEstDelay'] = estD
                                        self.client_dst_msm[dstAddr][name]['devDelay'] = devD
                                        self.client_dst_msm[dstAddr][name]['nexthop'] = nh
                                else:
                                    self.client_dst_msm[dstAddr]['msm_sample'] += 1
                                    if self.client_dst_msm[dstAddr]['time'] == 0:
                                        self.client_dst_msm[dstAddr]['time'] = time.perf_counter()
                                    for n in nodes_m:
                                        name, nh, estD, devD = n
                                        self.client_dst_msm[dstAddr][name]['PrvEstDelay'] = self.client_dst_msm[dstAddr][name]['estDelay']
                                        self.client_dst_msm[dstAddr][name]['estDelay'] = estD
                                        self.client_dst_msm[dstAddr][name]['devDelay'] = devD

                                pname, pnextop, pestDelay, pdevDelay = nodes_m[0]

                            for dstAddr in self.clients:
                                if (time.perf_counter() - self.client_dst_msm[dstAddr]['time']) >= (self.period - 1):
                                
                                    self.log.info("PARMetricsModule Routing Period Cycle, Measurement Period Cycle and Samples collected for DST:%s is: %s, %s, %s" % (dstAddr, self.period, self.mperiod, self.client_dst_msm[dstAddr]['msm_sample']))
                                    if Prefix(dstAddr) not in self.preferred_routes:
                                        curr_route, current_node = self._fetch_current_route(Prefix(dstAddr))
                                        self.log.info("PARMetricsModule PICKING ROUTE via %s with NEXTHOP: %s for DST:%s from self.current_routes"
                                                      %(current_node, curr_route.nexthop, dstAddr))
                                        self.preferred_routes[Prefix(dstAddr)] = self._fetch_current_route(Prefix(dstAddr))
                                        init_route = {}
                                        init_route[Prefix(dstAddr)] = [(curr_route, current_node)]
                                        self.command_queue.put(("par-update", {
                                            "routes": init_route,
                                            "type": self.name,
                                        }))
                                        self.flag = True
                                    else:
                                        curr_route, current_node = self.preferred_routes[Prefix(dstAddr)]
                                        
                                    lower_th_node = []
                                    lower_th_node_d = []
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
                                        n_delay = estDelay + (4.0 * devDelay)
                                        if e_node == current_node:
                                            if  (n_delay >= self.thresholds['gaming']) or (estDelay == 0.0):
                                                self.log.info("PARMetricsModule REPORTING n_delay on current path for  DST:%s as %sms using a devRTT of %s" % (dstAddr, n_delay, devDelay))

                                                if len(lower_th_node) != 0:
                                                    min_best = min(lower_th_node_d)
                                                    for lth_node in lower_th_node:
                                                        lt_name, lt_nh, lt_delay, lt_devDelay = lth_node
                                                        if lt_delay == min_best:
                                                            self.log.info("PARMetricsModule should update path for DST:%s to a better one" % dstAddr)
                                                            best_route = self._fetch_route_for_prefix(lt_name, lt_nh, dstAddr)
                                                            self.preferred_routes[Prefix(dstAddr)] = best_route[Prefix(dstAddr)][0]

                            
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
                                    self.client_dst_msm[dstAddr]['time'] = 0
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

                        while len(callbacks) > 0 and callbacks[0][1] < time.time():
                            self.log.debug("Triggering overdue callback %s" % callback)
                            callback, timeout = callbacks.pop(0)
                            callback()

                        if msgtype in self.actions:
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
            pfx = route.prefix
            self.log.info("BANDWIDTH_CHECKING PFX is %s" %pfx)
            self.log.info("BANDWIDTH__CHECKING PFX TYPE is %s" %type(pfx))
            if pfx not in self.routes:
                self.routes[pfx] = set()
            self.routes[pfx].add((route, message["from"]))
        self.log.info("BANDWIDTH _process_add_route: %s" %self.routes)
        return

    def _process_remove_route(self, message):
        for route_tup in message["routes"]:
            route, pref = route_tup
            pfx = route.prefix
            if pfx in self.routes:
                self.routes[pfx].remove((route, message["from"]))


    # Initialise current routes with routes selected by Peer process
    def _process_initial_route(self, message):
        sender = message["from"]
        prefixes = message["prefixes"]
        for prefixDict in prefixes:
            pfx = list(prefixDict.keys())[0]
            route, exitnode = prefixDict[pfx] 
            self.log.info("PARModule processing initial BGP best and current route to %s received by %s" %(pfx, sender))
            best_route = self._fetch_route_for_prefix(exitnode,
                                                      route.nexthop,
                                                      str(pfx))
            self.current_routes[pfx] = (route, exitnode)
            if len(best_route) != 0:
                self.command_queue.put(("par-update", {
                                        "routes": best_route,
                                        "type": self.name,
                                       }))
            

        for dest, route in self.current_routes.items():
            self.log.info("PARModule will use %s initially for %s" %(route, dest))


    def _fetch_current_route(self, dest):
        addr_family = get_address_family(str(dest))
        for pfx, route_tup in self.current_routes.items():
            if addr_family == AF_INET6:
                if ipv6_addr_is_subset(str(dest), str(pfx)):
                    route, exitnode = route_tup
                    return route, exitnode
        return None, None

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
        self.log.info("PARMetricsModule _process_send_best_route print before pass!!!!!!!")
        pass


class Bandwidth(BasePARModule):
    def __init__(self, name, command_queue, prefixes, peer_addrs, period, m_period, datadir):
        super(Bandwidth, self).__init__(name, command_queue, flows, peer_addrs, period, m_period, datadir)
        self.log = logging.getLogger("BANDWIDTH")
        self.command_queue = command_queue


    def _fetch_route(self, exitpeer, nexthop): 
        best_routes  = {}
        for prefix, routes_desc in self.routes.items():
            for desc in routes_desc:
                route, exitnode = desc
                if (exitnode == exitpeer) and (nexthop == route.nexthop): 
                    best_routes[prefix] = [desc]
        self.log.info("PARMetricsModule _FETCH_ROUTE returning: %s" %best_routes)
        return best_routes


    def _fetch_route_for_prefix(self, exitpeer, nexthop, pfx):
        pfx_route = {}
        for prefix, routes_desc in self.routes.items():

            if (Prefix(pfx) == prefix) or (ipv6_addr_is_subset(pfx, str(prefix))):
                for desc in routes_desc:
                    route, exitnode = desc
                    if (exitnode == exitpeer) and (nexthop == route.nexthop):
                        self.best_routes[Prefix(pfx)] = [desc]
                        pfx_route[Prefix(pfx)] = [desc]
                break
        self.log.info("PARMetricsModule Individual PFX FETCH_ROUTE returning: %s" %pfx_route)
        return pfx_route

    def _send_latest_best_route(self):
        self.last_performed = time.time()

        best_routes = {}



        self.log.info("BANDWITH _send_latest_best_route: %s" % best_routes)
        return best_routes


    def _process_send_best_route(self, message):
        if message["from"] not in self.enabled_peers:
            return
        best_routes = {}
        self.command_queue.put(("par-update", {
            "routes": best_routes,
            "type": self.name,
        }))

        self.log.info("BANDWIDTH _Process_send_best_route message sent !!!")
        return

class TrafficModule(BasePARModule):
    def __init__(self, name, command_queue, flows, peer_addrs, period, m_period, datadir):
        super(TrafficModule, self).__init__(name, command_queue, flows, peer_addrs, period, m_period, datadir)
        self.log = logging.getLogger(self.name)
        self.command_queue = command_queue


    def _fetch_route(self, exitpeer, nexthop): 
        best_routes  = {}
        for prefix, routes_desc in self.routes.items():
            for desc in routes_desc:
                route, exitnode = desc
                if (exitnode == exitpeer) and (nexthop == route.nexthop): 
                    best_routes[prefix] = [desc]
        self.log.info("PARMetricsModule _FETCH_ROUTE returning: %s" %best_routes)
        return best_routes


    def _fetch_route_for_prefix(self, exitpeer, nexthop, pfx):
        pfx_route = {}
        for prefix, routes_desc in self.routes.items():
            if (Prefix(pfx) == prefix) or (ipv6_addr_is_subset(pfx, str(prefix))):
                for desc in routes_desc:
                    route, exitnode = desc
                    if (exitnode == exitpeer) and (nexthop == route.nexthop):
                        self.best_routes[Prefix(pfx)] = [desc]
                        pfx_route[Prefix(pfx)] = [desc]
                break
        return pfx_route


    def _send_latest_best_route(self):
        self.last_performed = time.time()
        best_routes = {}
        


        self.log.info("BANDWITH _send_latest_best_route: %s" % best_routes)
        return best_routes

    def _process_send_best_route(self, message):

        if message["from"] not in self.enabled_peers:
            return

        best_routes = {}
        self.command_queue.put(("par-update", {
            "routes": best_routes,
            "type": self.name,
        }))

        self.log.info("BANDWIDTH _Process_send_best_route message sent !!!")
        return
