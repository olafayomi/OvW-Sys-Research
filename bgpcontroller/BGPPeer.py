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
#

import logging

from Peer import Peer
from PolicyObject import ACCEPT
from Prefix import Prefix
from RouteEntry import RouteEntry, DEFAULT_LOCAL_PREF, ORIGIN_EGP

class BGPPeer(Peer):
    def __init__(self, name, asn, address, outgoing_queue, control_queue,
            internal_command_queue,
            datadir,
            #preference,
            preference=DEFAULT_LOCAL_PREF,
            default_import=ACCEPT,
            default_export=ACCEPT,par=False):

        super(BGPPeer, self).__init__(name, asn, address, control_queue,
                internal_command_queue, datadir, preference, default_import,
                default_export,par)

        self.log = logging.getLogger("BGPPeer")
        self.out_queue = outgoing_queue
        self.command_queue = internal_command_queue

        self.seen_eor = False
        self.actions.update({
            "bgp": self._process_bgp_message,
        })

        # Do not export or process anything until we know the peers
        # capabilities. We should not receive an exaBGP route update before
        # the negotiated message. The negotiated message will cause us to
        # send a request to our tables to reload their routes to us.
        self.afi_safi = []

    def __cmp__(self, other):
        if self.asn > other.asn:
            return 1
        if self.asn < other.asn:
            return -1
        if self.address > other.address:
            return 1
        if self.address < other.address:
            return -1
        return 0

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

    def _do_announce(self, prefix, route, locPref):
        # TODO origin, aggregator/atomic-aggregate attributes
        # TODO use attributes/nlri announce many routes with same attributes
        #    "announce attribute next-hop self community [] nlri 1.2.3.4/32"
        self.log.debug("Peer %s announce %s" %(self.name, prefix))
        announce = "neighbor %s announce route %s next-hop %s %s %s" % (
                    self.address,
                    prefix, route.nexthop, route.get_announce_as_path_string(),
                    route.get_announce_communities_string())
        # this queue is just raw bytes, not packed inside a protobuf message
        self.command_queue.put(("encode", {
            "peer": self.address,
            "asn": self.asn,
            "route": {
                "nlri": prefix,
                "nexthop": route.nexthop,
                "origin": route.origin,
                "aspath": route.as_path(),
                "communities": route.communities(),
                "local-preference": locPref,
            },
            "type": "advertise",
        }))


    def _do_withdraw(self, prefix, route, locPref):
        self.log.debug("Peer process %s withdrawing %s with nexthop %s and local preference %s", 
                       self.name, prefix, route.nexthop, locPref)
        withdraw = "neighbor %s withdraw route %s next-hop %s" % (
                    self.address, prefix, route.nexthop)
        self.command_queue.put(("encode", {
            "peer": self.address,
            "asn": self.asn,
            "route": {
                "nlri": prefix,
                "nexthop": route.nexthop,
            },
            "type": "withdraw",
        }))

    def _process_bgp_message(self, message):
        #assert(message["neighbor"]["address"]["peer"] == self.address)
        #assert(message["neighbor"]["asn"]["peer"] == self.asn)
        assert(message["peer"]["address"] == self.address)
        assert(message["peer"]["asn"] == self.asn)

        if message["type"] == "state":
            callback = self._process_state_message(message)
        elif message["type"] == "notification":
            callback = self._process_notification_message(message)
        elif message["type"] == "update":
            callback = self._process_update_message(message)
        elif message["type"] == "open":
            callback = self._process_open_message(message)
        elif message["type"] == "refresh":
            self.log.error("\n\nREFRESH\n\n")
            callback = self._process_refresh_message(message)
        elif message["type"] == "negotiated":
            callback = self._process_negotiated_message(message)
        else:
            self.log.warning("Unknown BGP message type: %s" % message["type"])
            callback = None
        return callback

    def _process_state_message(self, message):
        """
            Process and handle bgp state messages.
        """
        #self.log.debug("Peer %s state change: %s", self.name,
        #        message["neighbor"]["state"])
        self.log.debug("Peer %s state change: %s", self.name,
                message["state"])
        # TODO deal with graceful restart
        if message["state"] == "up":
            self._state_change(True)
        elif message["state"] == "down":
            self._state_change(False)
        return None

    def _process_notification_message(self, message):
        """
            Process and handle bgp notification messages
        """
        self.log.debug("Peer %s notification: %s", self.name, message)
        return None

    def _process_withdraw_prefixes(self, family, update):
        """
            Process the withdraw BGP prefixes for a specified family. Please
            note that this method doesn't validate if the family exists
            as the caller should have already done this. Return true if
            prefix changes occurred.
        """
        #prefixes = update["withdraw"][family]
        prefixes = update["withdraw"]["nlri"]

        empty = []
        for withdrawn in prefixes:
            withdrawn_prefix = Prefix(withdrawn)
            # a peer can remove supernets that don't explicitly exist, so we
            # need to check if a prefix is contained within the withdrawn one
            for prefix in self.received.keys():
                if withdrawn_prefix.contains(Prefix(prefix)):
                    # remove any routes that fall within the prefix
                    empty.append(prefix)

        # remove prefixes that no longer have routes
        for prefix in empty:
            #del self.received[prefix]
            pfx = Prefix(prefix)
            if pfx in self.PAR_prefixes:
                route, pref = self.received[prefix]
                message = (("remove", {
                            "route": route,
                            "prefix": pfx,
                            "from": self.name,
                          }))
                for parmodule in self.PARModules:
                    self.log.debug("BGPPEER DEBUG par route delete XXXXCXCSCSJSDSJD Peer %s removing routes: %s in _process_withdraw_prefixes\n\n\n\n" %(self.name, route))
                    parmodule.mailbox.put(message)
            del self.received[prefix]    
                

        return len(prefixes) > 0

    def _process_announce_prefixes(self, family, update):
        """
            Process the announced BGP prefixes for a specified family. Please
            note that this method doesn't validate if the family exists
            as the caller should have already done this. Return true if
            prefix changes occurred.
        """
        #announce = update["announce"][family]
        announce = update["announce"]

        if "null" in announce and \
            "eor" in announce["null"]:
            # TODO see also restart flags that say not to wait for EOR
            self.seen_eor = True
            return True

        #if "attribute" not in update:
        if "attribute" not in announce:
            return False
        

     
        as_path = announce["attribute"].get("as-path", [])
        as_set = announce["attribute"].get("as-set", [])
        communities = announce["attribute"].get("community", [])
        origin = announce["attribute"].get("origin", ORIGIN_EGP)
        prefixes = announce["nlri"]
        nexthop = announce["nexthop"]
        preference = announce["attribute"].get("local-preference", self.preference)
        #preference = int(self.preference)
        self.log.info("debug_bgppeer _process_announce_prefixes local preference for %s  is %s" % (self.name, preference))
        self.log.info("debug_bgppeer DEFAULT_LOCAL_PREF is type: %s" %type(DEFAULT_LOCAL_PREF))

        for pfx in prefixes:
            route = RouteEntry(origin, self.asn,
                    str(pfx), str(nexthop), as_path, as_set,
                    communities, int(preference))
            if self.filter_import_route(route):
                self.received[str(pfx)] = (route, preference)
        self.log.info("DEBUG_BGPPeer _process_announce_prefixes self.received is %s" % self.received)
        return len(prefixes) > 0

    def _process_bgp_update_section(self, update, section_name, func):
        """
            Process a BGP update specific for specific AFI SAFI prefix
            families as defined by the peer. This method returns True if
            an update occurred, false otherwise. If the update section
            doesn't exist in the update message false is returned.

            For every family that exists in the update section the function
            func will be executed and the status for all families returned.
        """
        status = False


        if section_name not in update:
            return False

        # Process the message for negotiated AFI/SAFI values
        section = update[section_name]
        for family in self.afi_safi:
            # Convert the tuple to a exaBGP afi safi string value
            #family = self._afi_safi_to_str(family[0], family[1])
            if family in section["family"]:
                if func(family, update):
                    status = True
        return status

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

    def _process_update_message(self, message):
        update = message.get("update", None)
        withdrawn = False
        announced = False
        # Process EoR messages if there is no update
        # XXX: This assumes that we will not get an update and eor in message
        if update is None:
            #eor_section = message["neighbor"]["message"].get("eor", None)
            eor_section = message.get("eor", None)
            if not eor_section is None:
                self.seen_eor = True
                announced = True
                self.log.debug("%s seen eor for AFI %s and SAFI %s" % (self.name,
                        eor_section["family"][0][0], eor_section["family"][0][1]))
                        #eor_section["safi"], eor_section["afi"]))
        else:
            withdrawn = self._process_bgp_update_section(update, "withdraw",
                    self._process_withdraw_prefixes)
            announced = self._process_bgp_update_section(update, "announce",
                    self._process_announce_prefixes)

        # if anything changed then just send all the routes we have
        if self.seen_eor and (withdrawn or announced):
            # send filtered routes to the route tables
            self.log.debug("Updating %s peer tables" % self.name)
            return self._update_tables_with_routes
        return None

    def _process_open_message(self, message):
        if message["direction"] != "receive":
            return None

        self.log.debug("Received peer %s open message", self.name)

        # Check if the GR capability is advertised
        #if "64" in message["neighbor"]["open"]["capabilities"]:
        if "gracefulrestart" in message["capabilities"]:
            self.seen_eor = False
            self.log.debug("Peer %s advertised GR capability, waiting for EoR",
                    self.name)
        else:
            self.seen_eor = True
            self.log.debug("Peer %s lacks GR capability, disabling EoR wait",
                    self.name)

        if "multiprotocol" in message["capabilities"]:
            self.afi_safi = message["capabilities"]["multiprotocol"]
            # reload tables for family
            self._reload_from_tables()
            self.log.debug("Peer supports the following protocol families: %s",
                           self.afi_safi)

        # TODO: Do capability processing once GR support is implemented
        # If capability 64 is advertised but no AFI or SAFI is present then
        # peer will send us EoR but is not GR capable.
        return None

    def _process_negotiated_message(self, message):
        # Parse the peers negotiated AFI SAFI from the message
        negotiated = message["neighbor"].get("negotiated", None)
        if negotiated:
            if "families" in negotiated:
                self.afi_safi = []
                for family in negotiated["families"]:
                    self.afi_safi.append(self._str_to_afi_safi(family))
                self.log.debug("%s negotiated msg received, AFI SAFI %s",
                        self.name, self.afi_safi)

                # Ask the tables that are exporting to us to resend their routes
                # XXX can we remove the need for this if they haven't sent us
                # anything useful yet?
                self._reload_from_tables()
        return None

    def _process_refresh_message(self, message):
        # TODO check that AFI/SAFI are valid?
        # TODO do enhanced route refresh (RFC 7313) if peer is capable
        self._do_export_routes(refresh=True)
        # TODO does this need to be delayed? if so make a new function to do it
        # cause we can't pass arguments around
        return None
