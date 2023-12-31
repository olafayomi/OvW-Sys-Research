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

import logging
import time
from collections import defaultdict

from PolicyObject import PolicyObject, ACCEPT

# what about prefixes inside aggregates where the AS set needs to be modified
# every time? or withdrawing the final prefix inside the aggregate


class RouteTable(PolicyObject):
    def __init__(self,
            name, control_queue,
            default_import=ACCEPT,
            default_export=ACCEPT):

        PolicyObject.__init__(self, name, control_queue, default_import,
                default_export)

        self.log = logging.getLogger("RouteTable")

        self.routes = {}
        # Add peer preference  #2023-05-26
        self.peerPref = {}
        self.export_peers = []
        self.update_source = None
        self.actions.update({
            "update": self._process_update_message,
            "reload": self._process_reload_message,
            "debug": self._process_debug_message,
        })

    def __str__(self):
        return "RouteTable(%s, %d import filters %d export filters)" % (
                self.name, len(self.import_filter), len(self.export_filter))

    def __repr__(self):
        return self.__str__()

    def add_export_peer(self, peers):
        if not isinstance(peers, list):
            peers = [peers]
        self.export_peers.extend(peers)

    def _process_debug_message(self, message):
        self.log.debug(self)
        return None

    def _process_reload_message(self, message):
        # Try to find the peer object from its attributes
        peer = None
        for _peer in self.export_peers:
            if _peer.name == message["from"]:
                peer = _peer
                break

        if peer:
            # If the peer exists re-send (reload) the table routes
            self._update_peer(peer)
        # TODO do we want to do this one instantly?
        return None

    def _process_update_message(self, message):
        peer = message.get("from")
        self.routes[peer] = []
        if isinstance(message["routes"], list):
            self._try_import_routes(self.routes[peer], message["routes"])
        elif isinstance(message["routes"], dict):
            # routes from a table are a dictionary of lists
            for routes in message["routes"].values():
                self._try_import_routes(self.routes[peer], routes)
        self.update_source = peer if self.update_source is None else None
        return self._update_peers

    def _try_import_routes(self, table, routes):
        # run all the routes through the filter to see which we should keep
        for route_tup in routes:
            if isinstance(route_tup, tuple):
                route, pref = route_tup
            else:
                route = route_tup
                pref = 100
            filtered = self.filter_import_route(route, copy=False)
            if filtered is not None:
                # each peer should only give us one route per prefix
                table.append((filtered, pref))

    def _update_peers(self):
        """
            Update all export peers of this table with the table routes
        """
        self.log.debug("%s sending routes to peers", self.name)
        mark = time.time()
        for peer in self.export_peers:
            # Send the update to every peer in our table that needs it
            if self.update_source != peer.name:
                self._update_peer(peer, mark=mark)
        self.update_source = None

    # XXX what if we have withdrawn all our routes...
    def _update_peer(self, peer, mark=None):
        """
            Filter and send routes to a specific peer from this table
        """
        if mark is None:
            mark = time.time()
        
        # build a set of routes to send to a specific peer
        # 2023-05-26 update combined to include local-preference of source-peer sending the routes
        combined = defaultdict(list)
        for source_peer, routes in self.routes.items():
            # exclude routes we received from this source
            if source_peer != peer.name:
                for route_tup in routes:
                    route, pref = route_tup
                    try:
                        # if a peer, exclude routes that traverse its ASN
                        if (peer.asn not in route.as_path() and
                                (route.as_set() is None or
                                 peer.asn not in route.as_set())):
                            combined[route.prefix].append((route, pref))

                    except AttributeError:
                        combined[route.prefix].append((route, pref))

        filtered_routes = self.filter_export_routes(combined)
        # get the right preference for filtered_routes

        self.log.info("Table %s filtered routes for %s in %fs" % (
                self.name, peer.name, time.time() - mark))

        mark = time.time()
        peer.mailbox.put(("update", {
                    "from": self.name,
                    "routes": filtered_routes
                    }))
        self.log.info("Table %s sent %d routes to %s in %fs" % (
                self.name, len(filtered_routes), peer.name,
                time.time() - mark))
        del filtered_routes
        del combined
