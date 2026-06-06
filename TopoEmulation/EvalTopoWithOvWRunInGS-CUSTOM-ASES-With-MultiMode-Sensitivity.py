from ipmininet.iptopo import IPTopo
from ipmininet.cli import IPCLI
from ipmininet.ipnet import IPNet
from ipmininet.router.config.ospf import OSPFRedistributedRoute
from ipmininet.srv6 import enable_srv6
from ipmininet.router.config import BGP, ebgp_session, set_rr, AccessList, \
     AF_INET6, AF_INET, BorderRouterConfig, RouterConfig, OSPF, OSPF6, \
     bgp_peering, ExaBGPDaemon, STATIC, StaticRoute, CLIENT_PROVIDER, SHARE, CommunityList
from ipmininet.link import IPLink
import argparse
import pathlib
import csv
import statistics as stat
import time
from datetime import datetime
import asyncio
import threading
from collections import OrderedDict
import socket
import perfmon_pb2 as perfmsg
import struct
import os
import sys
import random
import numpy as np
import json
import os

def encode_msg_size(size: int) -> bytes:
    return struct.pack("<I", size)


def create_msg(content: bytes) -> bytes:
    size = len(content)
    return encode_msg_size(size) + content


class TestTopo(IPTopo):
    """The topology is composed of 55 ASes. One of the ASes is the
    game server network and it hosts the game serve (AS1). Four of these ASes
    are transit providers while the rest are stub ASes that host the game
    clients. Transit AS2 is the transit provider for the game server network
    and the network running Overwatch. Transit AS3 and AS4 are peers of AS2
    and they provide transit for AS5 which is the ISPs for AS6 to AS55.
    The peerings AS2<->AS3 and AS2<->AS4 provide multiple paths to reach
    AS6 to AS55. """

    def __init__(self, as_config, nhosts=1, *args, **kwargs):
        self.nhosts = nhosts
        self.as_config = as_config
        super(TestTopo, self).__init__(*args,  **kwargs)


    def build(self, *args, **kwargs):
        # Add all routers

        max_paths = max(config[0] for config in self.as_config.values())

        # Add transit routers
        transit_routers = []
        transit_router_dict = {}
        for i in range(1, max_paths + 2):
            router_name = f'Tp1ASr{i}'
            router = self.bgp(router_name)
            #router_id = f"192.168.1.{i}"
            #router.get_config(BGP).router_id = router_id
            transit_routers.append(router)
            transit_router_dict[router_name] = router
            print(f"Transit router in AS100: {router_name}")

        # Create transit switch
        Sw1Tp1 = self.addSwitch('Sw1Tp1')
        for i, router in enumerate(transit_routers, 1):
            link = self.addLink(router, Sw1Tp1)
            # Skip IP 100::4 which is reserved for Tp1ASctlr
            ip_addr = i if i < 4 else i + 2
            link[router].addParams(ip=(f"100::{ip_addr}/48",))
        
        # Add controller and ExaBGP speaker node
        Tp1ASctlr = self.addRouter("Tp1ASctlr", config=RouterConfig)

        # Add controller to transit switch
        Tp1ASctlrSw1 = self.addLink(Tp1ASctlr, Sw1Tp1)
        Tp1ASctlrSw1[Tp1ASctlr].addParams(ip=("100::4/48",))

        # Add controller and ExaBGP speaker node
        Tp1ASctlr.addDaemon(ExaBGPDaemon, env = { 'api' : {'cli':'true', 'encoder':'json',
                                                       'ack':'true', 'pipename':'\'exabgp\'',
                                                       'respawn':'true','chunk':1,
                                                       'terminate':'false'},
                                              'bgp' : {'openwait' : 60},
                                              'cache': {'attributes':'true', 'nexthops':'true'},
                                              'daemon': {'daemonize':'false', 'drop':'true', 
                                                         'pid': '\'\'', 'umask':'\'0o137\'', 
                                                         'user':'nobody'},
                                              'log': {'all':'true','configuration':'true','daemon':'true',
                                                      'message':'true','destination':'stdout',
                                                      'enable':'true','level':'INFO','network':'true',
                                                      'packets':'false','parser':'true',
                                                      'processes':'true','reactor':'true',
                                                      'rib':'false','routes':'true','short':'false',
                                                      'timers':'false'},
                                              'pdb': {'enable':'false'},
                                              'profile': { 'enable':'false', 'file':'\'\''},
                                              'reactor': {'speed':'1.0'},
                                              'tcp': {'acl':'false', 'bind':'', 'delay':0,
                                                      'once':'false', 'port': 179}
                                            }, passive=False )
        
        # Create all AS routers dynamically
        as_routers = {}

        for as_num, (num_routers, transit_connections, delays) in self.as_config.items():
            as_routers[as_num] = {}
            
            # Create border routers
            for i in range(1, num_routers + 1):
                router = self.bgp(f'AS{as_num}R{i}')
                as_routers[as_num][f'R{i}'] = router
                print(f"Border router for AS{as_num}: AS{as_num}R{i}")
            # Create internal router
            internal_router = self.bgp(f'AS{as_num}i')
            as_routers[as_num]['i'] = internal_router
            print(f"Internal router for AS{as_num}: AS{as_num}i")
            
            # Connect to transit providers
            for i in range(num_routers):
                as_router = as_routers[as_num][f'R{i+1}']
                if i == 0:
                    transit_router_name = 'Tp1ASr2'
                elif i == 1:
                    transit_router_name = 'Tp1ASr3'
                elif i == 2:
                    transit_router_name = 'Tp1ASr4'
                else:
                    transit_router_name = f'Tp1ASr{i+2}'

                transit_router = transit_router_dict[transit_router_name]
                link = self.addLink(transit_router, as_router)
                print(f"Adding link between {transit_router_name} and AS{as_num}R{i+1}")
                subnet_base = i * 4
                transit_offset = subnet_base + 1
                as_offset = subnet_base + 2
                base_ip = 1000 + as_num
                link[transit_router].addParams(ip=(f"{base_ip}::{transit_offset:x}/126",))
                link[as_router].addParams(ip=(f"{base_ip}::{as_offset:x}/126",))

            for i in range(1, min(3, num_routers +1)):
                sw = self.addSwitch(f'Sw{i}AS{as_num}')
                self.addLink(as_routers[as_num]['i'], sw)
                self.addLink(as_routers[as_num][f'R{i}'], sw)

            # For 3+ router ASes, add Sw4 for R3 (note: Sw3 is reserved for hosts)
            if num_routers >= 3:
                sw4 = self.addSwitch(f'Sw4AS{as_num}')
                self.addLink(as_routers[as_num]['i'], sw4)
                self.addLink(as_routers[as_num]['R3'], sw4)
            
            # For 4+ router ASes, continue with Sw5, Sw6, etc.
            for i in range(4, num_routers + 1):
                sw = self.addSwitch(f'Sw{i+1}AS{as_num}')  # Skip Sw3
                self.addLink(as_routers[as_num]['i'], sw)
                self.addLink(as_routers[as_num][f'R{i}'], sw)
            
            # Add host network
            sw_host = self.addSwitch(f'Sw3AS{as_num}')
            link = self.addLink(as_routers[as_num]['i'], sw_host)
            ip_as = f"2001:df{str(as_num).zfill(2)}::{self.nhosts + as_num}/48"
            link[as_routers[as_num]['i']].addParams(ip=(ip_as,))
            
            # Add hosts
            for j in range(1, self.nhosts + 1):
                host_name = f"gCl{as_num}_{j}"
                host = self.addHost(host_name)
                link = self.addLink(sw_host, host)
                ip_host = f"2001:df{str(as_num).zfill(2)}::{j}/48"
                link[host].addParams(ip=(ip_host,))

        # Add Game server host to topology
        gameServer = self.addHost('gameServer')
        GsRtrLink = self.addLink(gameServer, transit_routers[0])
        GsRtrLink[gameServer].addParams(ip=("55::1/48",))
        GsRtrLink[transit_routers[0]].addParams(ip=("55::2/48",))

        # Add all ASes
        self.addAS(100, transit_routers + [Tp1ASctlr])
        for as_num, routers in as_routers.items():
            self.addAS(as_num, list(routers.values()))

        # Set up BGP peerings
        # Transit peerings - Hub and spoke with Tp1ASr1 as the hub connecting to Tp1ASctlr
        bgp_peering(self, transit_routers[0], Tp1ASctlr)  # Tp1ASr1 connects to Tp1ASctlr
        
        # Other transit routers connect to Tp1ASctlr (not Tp1ASr1)
        for i in range(1, len(transit_routers)):
            bgp_peering(self, Tp1ASctlr, transit_routers[i])

        # AS internal peerings
        for as_num, routers in as_routers.items():
            internal = routers['i']
            for key, router in routers.items():
                if key != 'i':
                    bgp_peering(self, router, internal)

        # Set ACL and prefer one path over the other
        acl4 = AccessList(name='all', entries=('any',), family='ipv4')
        acl = AccessList(name='all6', entries=('any',), family='ipv6')

        aclA = AccessList(name='split6', entries=('2001:df01::/48',
                                                  '2001:df04::/48',
                                                  '2001:df07::/48',
                                                  '2001:df10::/48',
                                                  '2001:df13::/48',
                                                  '2001:df16::/48',
                                                  '2001:df19::/48',
                                                  '2001:df22::/48',
                                                  '2001:df25::/48',
                                                  '2001:df28::/48',),
                          family='ipv6')

        aclB = AccessList(name='split6', entries=('2001:df02::/48',
                                                  '2001:df05::/48',
                                                  '2001:df08::/48',
                                                  '2001:df11::/48',
                                                  '2001:df14::/48',
                                                  '2001:df17::/48',
                                                  '2001:df20::/48',
                                                  '2001:df23::/48',
                                                  '2001:df26::/48',
                                                  '2001:df29::/48',),
                          family='ipv6')

        aclC = AccessList(name='split6', entries=('2001:df03::/48',
                                                  '2001:df06::/48',
                                                  '2001:df09::/48',
                                                  '2001:df12::/48',
                                                  '2001:df15::/48',
                                                  '2001:df18::/48',
                                                  '2001:df21::/48',
                                                  '2001:df24::/48',
                                                  '2001:df27::/48',
                                                  '2001:df30::/48',),
                          family='ipv6')
        
        loc_prefA = CommunityList('loc-pref', community='2:500')
        loc_prefB = CommunityList('loc-pref', community='3:500')
        loc_prefC = CommunityList('loc-pref', community='5:500')

        # Set local preferences
        for as_num in self.as_config.keys():
            if f'R1' in as_routers[as_num]:
                peer = as_routers[as_num]['R1']
                transit_routers[1].get_config(BGP).set_local_pref(200, from_peer=peer,
                                                                   matching=(acl4, acl))
        
            if f'R2' in as_routers[as_num]:
                peer = as_routers[as_num]['R2']
                router = as_routers[as_num]['R2']
                transit_routers[2].get_config(BGP).set_local_pref(100, from_peer=peer,
                                                                  matching=(acl4, acl))

                router.get_config(BGP).set_local_pref(200, from_peer=transit_routers[2],
                                                      matching=(acl4, acl))

            if f'R3' in as_routers[as_num]:
                peer_name = f'AS{as_num}R3'
                peer = as_routers[as_num]['R3']
                transit_routers[3].get_config(BGP).set_local_pref(100, from_peer=peer,
                                                                   matching=(acl4, acl))

        # eBGP sessions
        for as_num, (num_routers, transit_connections, _) in self.as_config.items():
            for i in range(num_routers):
                if i == 0:
                    transit_router_name = 'Tp1ASr2'
                elif i == 1:
                    transit_router_name = 'Tp1ASr3'
                elif i == 2:
                    transit_router_name = 'Tp1ASr4'
                else:
                    transit_router_name = f'Tp1ASr{i+2}'

                transit_router = transit_router_dict[transit_router_name]
                as_router = as_routers[as_num][f'R{i+1}']
                ebgp_session(self, transit_router, as_router)

        super().build(*args, **kwargs)

    def post_build(self, net):
        for n in net.hosts + net.routers:
            enable_srv6(n)
        super().post_build(net)

    def bgp(self, name):
        r = self.addRouter(name, config=RouterConfig)
        r.addDaemon(BGP,  address_families=(
            AF_INET(redistribute=('connected',)),
            AF_INET6(redistribute=('connected',))))
        return r

class PARNet(IPNet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._as_group_mapping = {}
        self._tc_config = {}
        self._multimodal_timeline = {}

    def load_tc_config(self, tc_config_file, as_group_mapping):
        """Load enhanced TC distribution configuration with multimodal support"""
        self._as_group_mapping = as_group_mapping
        
        if tc_config_file and os.path.exists(tc_config_file):
            with open(tc_config_file, 'r') as f:
                self._tc_config = json.load(f)
            print(f"Loaded enhanced TC configuration from {tc_config_file}")
            
            # Analyze multimodal paths
            self._analyze_multimodal_paths()
        else:
            print("No TC configuration file found, using fallback delays")

    def _analyze_multimodal_paths(self):
        """Analyze and prepare multimodal switching timeline"""
        multimodal_paths = {}
        
        for target, target_config in self._tc_config.items():
            for group_id, group_config in target_config.items():
                topology_as = None
                for emulated_as_str, group_info in self._as_group_mapping.items():
                    if (group_info.get('group_id') == group_id and 
                        group_info.get('target') == target):
                        topology_as = int(emulated_as_str)
                        path_names = group_info.get('path_names', [])
                        break
                                            
                if topology_as is None:
                    continue
                    
                for path_name, path_config in group_config.items():
                    if path_config.get('type') == 'multimodal':
                        # Find router number for this path
                        router_num = None
                        if path_name in path_names:
                            router_num = path_names.index(path_name) + 1
                    
                        if router_num:
                            path_key = f"{target}::{group_id}_{path_name}"
                            modes = path_config.get('modes', {})
                        
                            if len(modes) > 1:
                                multimodal_paths[path_key] = {
                                    'target': target,
                                    'group_id': group_id,
                                    'path_name': path_name,
                                    'topology_as': topology_as,        # Store topology AS
                                    'router_num': router_num,          # Store router number
                                    'modes': modes,
                                    'current_mode_index': 0,
                                    'mode_names': list(modes.keys())
                                }
        
        self._multimodal_timeline = multimodal_paths
        
        print(f"\n🎯 MULTIMODAL PATHS DETECTED: {len(multimodal_paths)}")
        for path_key, path_info in multimodal_paths.items():
            print(f" TARGET-{path_info['target']} Topology Router AS{path_info['topology_as']}R{path_info['router_num']} {path_key}: {len(path_info['modes'])} modes")
            for mode_name, mode_config in path_info['modes'].items():
                weight = mode_config.get('weight_percentage', 0)
                tc_cmd = mode_config.get('tc_command', '')
                print(f"    {mode_name}: {weight:.1f}% - {tc_cmd}")


    def find_multimodal_path_info(self, as_num, router_num):
        """Find multimodal configuration for a specific AS and router"""
        # Get group information for this AS
        group_info = self._as_group_mapping.get(str(as_num), {})
        group_id = group_info.get('group_id', f'AS{as_num}')
        path_names = group_info.get('path_names', [])
        
        # Determine path name for this router
        if router_num <= len(path_names):
            path_name = path_names[router_num - 1]
        else:
            path_name = f'Path{router_num}'
        
        path_key = f"{group_id}_{path_name}"
        
        return self._multimodal_timeline.get(path_key)


    def modifyLink(self, node1, node2, delay="0.1ms", bw=None, max_queue_size=None, **opts):
        """Modified to properly handle netem parameters"""
        src_params = opts.get("params1", {})
        dst_params = opts.get("params2", {})        
        src_delay = src_params.get("delay")
        src_loss = src_params.get("loss")
        src_max_queue = src_params.get("max_queue_size")
        
        dst_delay = dst_params.get("delay")
        dst_loss = dst_params.get("loss")
        dst_max_queue = dst_params.get("max_queue_size")
        
        # Find the link between the two nodes
        for sw in self.switches:
            src_link = node2.connectionsTo(sw)
            dst_link = node1.connectionsTo(sw)
            if src_link and dst_link:
                break

        src_int, _ = src_link[0]
        dst_int, _ = dst_link[0]

        src_delay = src_delay or delay
        src_loss = src_loss or 0
        
        # Configure source interface
        if src_delay:
            src_int.config(delay=src_delay, max_queue_size=src_max_queue, loss=src_loss)
        
        # Configure destination interface with proper netem handling
        if dst_delay:
            # Check if dst_delay contains netem parameters
            if isinstance(dst_delay, str) and ('distribution' in dst_delay or ' ' in dst_delay):
                # This is a complex netem command - use direct tc command
                try:
                    # Execute tc command directly to avoid string formatting issues
                    tc_cmd = f"tc qdisc replace dev {dst_int.name} root netem delay {dst_delay}"
                    dst_int.node.cmd(tc_cmd)
                    print(f"Applied netem command: {tc_cmd}")
                except Exception as e:
                    print(f"Error applying netem command: {e}")
                    # Fallback to simple delay
                    simple_delay = dst_delay.split()[0] if ' ' in dst_delay else dst_delay
                    dst_int.config(delay=simple_delay, max_queue_size=dst_max_queue, loss=dst_loss)
            else:
                # Simple delay value
                dst_int.config(delay=dst_delay, max_queue_size=dst_max_queue, loss=dst_loss)

    def parse_tc_command(self, tc_command):
        """Parse TC command and extract netem parameters"""
        try:
            # Example: "tc qdisc add dev ethX root netem delay 27.4ms 0.2ms 25% distribution normal"
            parts = tc_command.split()
            if tc_command.startswith('tc qdisc'):
                if 'delay' not in parts:
                    return None
            
                delay_idx = parts.index('delay')
            elif tc_command.startswith('delay'):
                delay_idx = 0
            else:
                return None
            
            params = []
            i = delay_idx + 1
            
            # Extract delay parameters
            while i < len(parts) and not parts[i].startswith('distribution'):
                params.append(parts[i])
                i += 1
            
            # Find distribution type
            distribution = 'normal'
            if 'distribution' in parts:
                dist_idx = parts.index('distribution')
                if dist_idx + 1 < len(parts):
                    distribution = parts[dist_idx + 1]
            
            # Build netem command - escape any % signs that might cause formatting issues
            if len(params) >= 2:
                netem_cmd = f"{params[0]} {params[1]}"
                
                # Add correlation if present
                if len(params) >= 3 and params[2].endswith('%'):
                    netem_cmd += f" {params[2]}"
                
                # Add distribution
                netem_cmd += f" distribution {distribution}"
                
                return netem_cmd
            
        except (ValueError, IndexError) as e:
            print(f"Error parsing TC command: {e}")
            return None
        
        return None
    
    def _find_as_router_for_path(self, target, group_id, path_name):
        """Find AS number and router number for a given group and path"""
        try:
            # New approach: Use AS_GROUP_MAPPING to find the correct emulated AS
            # group_id format: "AS3320-1", path_name format: "AS3356"
            
            # First, search through AS_GROUP_MAPPING to find which emulated AS 
            # corresponds to this group_id
            for emulated_as_str, group_info in self._as_group_mapping.items():
                emulated_as_num = int(emulated_as_str)
                
                # Check if this group matches
                mapped_group_id = group_info.get('group_id', '')
                if mapped_group_id == group_id:
                    # Found the emulated AS number!
                    path_names = group_info.get('path_names', [])
                    
                    # Find router number based on path name
                    if path_name in path_names:
                        router_num = path_names.index(path_name) + 1
                        return emulated_as_num, router_num
                    elif path_name.startswith('Path') and path_name[4:].isdigit():
                        router_num = int(path_name[4:])
                        return emulated_as_num, router_num
                    elif path_name.startswith('AS') and path_name[2:].isdigit():
                        # Try to map AS number in path_name to router position
                        # This is a fallback - you might need to adjust this logic
                        # based on your specific path naming convention
                        
                        # For now, assume first path = router 1, second = router 2, etc.
                        if len(path_names) > 0:
                            router_num = 1  # Default to first router
                            return emulated_as_num, router_num
                            
            # Fallback: Try the old method if AS_GROUP_MAPPING lookup failed
            print(f"Warning: Could not find group_id '{group_id}' in AS_GROUP_MAPPING, trying fallback")
            
            # Extract AS number from group_id (format: AS{num}-{router})
            if group_id.startswith('AS') and '-' in group_id:
                as_num_str = group_id.split('-')[0][2:]  # Remove 'AS' and get number before '-'
                router_suffix = group_id.split('-')[1]   # Get router identifier after '-'
                
                # Check if this AS exists in our topology
                try:
                    as_num = int(as_num_str)
                    if as_num in self._as_config:  # Check if this AS exists in topology
                        # Try to determine router number from group_id suffix
                        if router_suffix.isdigit():
                            router_num = int(router_suffix)
                        else:
                            router_num = 1  # Default
                        
                        # Validate router exists
                        num_routers = self._as_config[as_num][0]  # First element is num_routers
                        if router_num <= num_routers:
                            return as_num, router_num
                            
                except ValueError:
                    pass
                    
        except Exception as e:
            print(f"Error in _find_as_router_for_path for group_id '{group_id}', path_name '{path_name}': {e}")
        
        return None, None


    def configure_delays(self, as_config, baseline_delay_ms=0.6):
        """Configure delays with enhanced multimodal distribution analysis integration"""
        print("\n" + "="*80)
        print("CONFIGURING NETWORK DELAYS WITH ENHANCED MULTIMODAL ANALYSIS")
        print(f"Baseline delay correction: {baseline_delay_ms}ms")
        print("="*80)
        
        configured_count = 0
        fallback_count = 0
        multimodal_count = 0
        
        # Store reference to as_config for _find_as_router_for_path
        self._as_config = as_config
        
        for as_num, (num_routers, _, delays) in as_config.items():
            # Get group information
            group_info = self._as_group_mapping.get(str(as_num), {})
            group_id = group_info.get('group_id', f'AS{as_num}')
            target = group_info.get('target', 'Unknown')
            path_names = group_info.get('path_names', [])
            classification = group_info.get('classification', 'unknown')
            scenario = group_info.get('scenario', 'unknown')
            
            print(f"\nAS{as_num} ({group_id} -> {target}):")
            print(f"  Classification: {classification}, Scenario: {scenario}")
            print(f"  Available paths: {path_names}")
            
            print(f"  AS{as_num} mapped to group_id='{group_id}', target='{target}'")
            print(f"  Looking up: self._tc_config['{target}']['{group_id}']")

            if target in self._tc_config and group_id in self._tc_config[target]:
                print(f"  FOUND config for {target}::{group_id}")
                print(f"  Available paths: {list(self._tc_config[target][group_id].keys())}")
            else:
                print(f"  NOT FOUND - checking what's actually available...")
                print(f"  Available targets: {list(self._tc_config.keys())}")
                for t in self._tc_config.keys():
                    if 'AS34984-1' in self._tc_config[t]:
                        print(f"  Found AS34984-1 in target: {t}")

            for i in range(1, num_routers + 1):
                if i <= len(delays):
                    # Determine path name
                    path_name = path_names[i-1] if i-1 < len(path_names) else f'Path{i}'
                    
                    print(f"  DEBUG: Looking for target='{target}', group_id='{group_id}', path_name='{path_name}'")
                    print(f"  DEBUG: Available targets in TC config: {list(self._tc_config.keys())}")
                    if target in self._tc_config:
                        print(f"  DEBUG: Available groups for {target}: {list(self._tc_config[target].keys())}")
                    # Always start with tc_applied = False
                    tc_applied = False
                    
                    # Try to get optimized TC configuration with TARGET AWARENESS
                    if (self._tc_config and 
                        target in self._tc_config and 
                        group_id in self._tc_config[target] and 
                        path_name in self._tc_config[target][group_id]):
                        
                        path_config = self._tc_config[target][group_id][path_name]
                        config_type = path_config.get('type', 'single_mode')
                        
                        print(f"  Found TC config for {target}::{group_id}::{path_name}")
                        
                        if config_type == 'multimodal':
                            # Configure first mode for multimodal paths
                            modes = path_config.get('modes', {})
                            if modes:
                                first_mode = list(modes.keys())[0]
                                mode_config = modes[first_mode]
                                tc_command = mode_config.get('tc_command', '')
                                weight = mode_config.get('weight_percentage', 0)
                                confidence = mode_config.get('confidence', 'low')
                                
                                # Parse and apply TC command for first mode
                                netem_params = self.parse_tc_command(tc_command)
                                
                                if netem_params:
                                    print(f"  R{i} via {path_name}: {netem_params} (multimodal - {first_mode}, {weight:.1f}%, confidence: {confidence})")
                                    
                                    try:
                                        delay_params = {
                                            "params1": {"delay": "0.1ms"},
                                            "params2": {"delay": netem_params}
                                        }
                                        self.apply_delay_with_baseline_correction(
                                            f"AS{as_num}R{i}", f"AS{as_num}i", 
                                            delay_params, baseline_delay_ms
                                        )
                                        tc_applied = True
                                        multimodal_count += 1
                                    except Exception as e:
                                        print(f"    Error applying multimodal TC to AS{as_num}R{i}: {e}")
                                        tc_applied = False
                        
                        else:
                            # Single mode configuration
                            tc_command = path_config.get('tc_command', '')
                            confidence = path_config.get('confidence', 'low')
                            
                            # Parse and apply TC command
                            netem_params = self.parse_tc_command(tc_command)
                            
                            if netem_params:
                                print(f"  R{i} via {path_name}: {netem_params} (single-mode, confidence: {confidence})")
                                
                                try:
                                    delay_params = {
                                        "params1": {"delay": "0.1ms"},
                                        "params2": {"delay": netem_params}
                                    }
                                    self.apply_delay_with_baseline_correction(
                                        f"AS{as_num}R{i}", f"AS{as_num}i", 
                                        delay_params, baseline_delay_ms
                                    )
                                    tc_applied = True
                                    configured_count += 1
                                except Exception as e:
                                    print(f"    Error applying single-mode TC to AS{as_num}R{i}: {e}")
                                    tc_applied = False
                    else:
                        print(f"  No TC config found for {target}::{group_id}::{path_name}")
                    
                    # ALWAYS use fallback if TC was not successfully applied
                    if not tc_applied:
                        delay_median, delay_stddev = delays[i-1]
                        adjusted_median = delay_median - baseline_delay_ms  # Apply baseline correction here too
                        fallback_cmd = f"{adjusted_median}ms {delay_stddev}ms distribution normal"
                        
                        print(f"  R{i} via {path_name}: {fallback_cmd} (fallback with baseline correction)")
                        
                        try:
                            delay_params = {
                                "params1": {"delay": "0.1ms"},
                                "params2": {"delay": fallback_cmd}
                            }
                            self.apply_delay_with_baseline_correction(
                                f"AS{as_num}R{i}", f"AS{as_num}i", 
                                delay_params, baseline_delay_ms
                            )
                            fallback_count += 1
                        except Exception as e:
                            print(f"    Error applying fallback delay to AS{as_num}R{i}: {e}")
        
        print(f"\n{'='*80}")
        print(f"CONFIGURATION COMPLETE")
        print(f"Links configured with single-mode TC: {configured_count}")
        print(f"Links configured with multimodal TC: {multimodal_count}")
        print(f"Links using fallback configuration: {fallback_count}")
        print(f"{'='*80}")


    def extract_delay_value(self, delay_string):
        """Extract the main delay value in ms from a delay string"""
        try:
            if isinstance(delay_string, str):
                # Handle various formats like "27.5ms", "27.5ms 2.1ms distribution normal", etc.
                # The first value before 'ms' is always the main delay
                import re
                match = re.search(r'(\d+\.?\d*)ms', delay_string)
                if match:
                    return float(match.group(1))
            elif isinstance(delay_string, (int, float)):
                return float(delay_string)
        except (ValueError, AttributeError):
            pass
        
        return 0.0

    def apply_delay_with_baseline_correction(self, router1_name, router2_name, delay_params, baseline_delay_ms=0.6):
        """Apply delay with baseline correction for accurate end-to-end delays"""
        
        # Extract the target delay from params2
        dst_delay = delay_params.get("params2", {}).get("delay", "0ms")
        target_delay_ms = self.extract_delay_value(dst_delay)
        
        # Calculate corrected delay (subtract baseline topology delay)
        corrected_delay_ms = max(0.1, target_delay_ms - baseline_delay_ms)  # Minimum 0.1ms
        
        # Reconstruct the delay string with corrected value
        if isinstance(dst_delay, str) and ' ' in dst_delay:
            # Complex netem command like "27.5ms 2.1ms distribution normal"
            parts = dst_delay.split()
            if len(parts) > 0:
                # Replace the first delay value
                parts[0] = f"{corrected_delay_ms:.1f}ms"
                corrected_delay_str = ' '.join(parts)
            else:
                corrected_delay_str = f"{corrected_delay_ms:.1f}ms"
        else:
            # Simple delay value
            corrected_delay_str = f"{corrected_delay_ms:.1f}ms"
        
        # Update the delay parameters
        corrected_params = delay_params.copy()
        corrected_params["params2"] = corrected_params.get("params2", {}).copy()
        corrected_params["params2"]["delay"] = corrected_delay_str
        
        print(f"    Delay correction: {target_delay_ms:.1f}ms → {corrected_delay_ms:.1f}ms (baseline: {baseline_delay_ms}ms)")
        
        # Apply the corrected delay
        self.modifyLink(self[router1_name], self[router2_name], **corrected_params)
        
        return corrected_delay_ms

    def apply_multimodal_mode(self, as_num, router_num, mode_name, mode_config, baseline_delay_ms=0.6):
        """Apply a specific mode configuration to a multimodal path"""
        try:
            tc_command = mode_config.get('tc_command', '')
            weight = mode_config.get('weight_percentage', 0)
            confidence = mode_config.get('confidence', 'unknown')
            
            # Parse TC command
            netem_params = self.parse_tc_command(tc_command)
            
            if netem_params:
                print(f"    Applied {mode_name} to AS{as_num}R{router_num}: {netem_params} ({weight:.1f}%, {confidence})")
                
                # Use modifyLink just like in configure_delays
                delay_params = {
                                "params1": {"delay": "0.1ms"},
                                "params2": {"delay": netem_params}
                               }
                self.apply_delay_with_baseline_correction(
                            f"AS{as_num}R{router_num}", f"AS{as_num}i", 
                                delay_params, baseline_delay_ms
                                )
                #self.modifyLink(self[f"AS{as_num}R{router_num}"], self[f"AS{as_num}i"],
                #            params1={"delay": "0.1ms"},
                #            params2={"delay": netem_params})
                
                # Log the change
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log_cmd = f"echo '{timestamp}: {mode_name} - {netem_params}' >> ~/AS{as_num}R{router_num}-multimodal-changes.log"
                self[f"AS{as_num}R{router_num}"].cmd(log_cmd)
                
                return True
            else:
                print(f"    Error: Could not parse TC command for {mode_name}: {tc_command}")
                return False
                
        except Exception as e:
            print(f"    Error applying {mode_name} to AS{as_num}R{router_num}: {e}")
            return False


    # Fix for execute_multimodal_timeline to switch at t=400s instead of t=600s
    # Replace the execute_multimodal_timeline method in your script

    def execute_multimodal_timeline(self, start_time, game_duration=901, mode_duration=150):
        """Execute multimodal switching timeline during the experiment"""
        print(f"\n🎯 STARTING MULTIMODAL TIMELINE EXECUTION")
        print(f"Game duration: {game_duration}s, Mode switch interval: {mode_duration}s")
        
        if not self._multimodal_timeline:
            print("No multimodal paths configured - skipping timeline execution")
            return
        
        # Create a mapping table for debugging and track completion status
        print(f"\n📋 MULTIMODAL PATH MAPPING:")
        valid_paths = 0
        for path_key, path_info in self._multimodal_timeline.items():
            target = path_info['target']
            group_id = path_info['group_id']
            path_name = path_info['path_name']
            as_num = path_info['topology_as']
            router_num = path_info['router_num']
            
            if as_num and router_num:
                print(f"  ✅ {path_key} -> AS{as_num}R{router_num} ({len(path_info['modes'])} modes)")
                valid_paths += 1
                # Add completion tracking
                path_info['completed'] = False
                path_info['switches_remaining'] = len(path_info['modes']) - 1  # -1 because first mode already set
            else:
                print(f"  ❌ {path_key} -> NOT FOUND")
                # Mark invalid paths as completed so they don't interfere
                path_info['completed'] = True
                path_info['switches_remaining'] = 0
        
        print(f"Valid multimodal paths: {valid_paths}/{len(self._multimodal_timeline)}")
        
        if valid_paths == 0:
            print("No valid multimodal paths found - check AS_GROUP_MAPPING configuration")
            return
        
        # Calculate total experiment duration
        # FIXED: This should be relative to when this function is called, not absolute
        total_duration = game_duration  # Just the game duration, not including arrival/settle
        mode_switches = total_duration // mode_duration
        
        print(f"Remaining experiment duration: {total_duration}s")
        print(f"Expected mode switches: {mode_switches}")
        
        switch_count = 0
        
        # FIXED: Changed loop logic to switch FIRST, then sleep
        while (time.time() - start_time) < (90 + 110 + 200 + total_duration):
            # Apply next mode switch
            print(f"\n--- Mode Switch {switch_count} at {datetime.now()} ---")
            
            successful_switches = 0
            failed_switches = 0
            completed_paths = 0
            
            # Apply next mode for each multimodal path that hasn't completed
            for path_key, path_info in self._multimodal_timeline.items():
                
                # Skip if this path has completed all its mode switches
                if path_info.get('completed', False):
                    completed_paths += 1
                    continue
                
                modes = path_info['modes']
                mode_names = path_info['mode_names']
                current_index = path_info['current_mode_index']
                switches_remaining = path_info.get('switches_remaining', 0)
                
                # Check if this path has more switches to do
                if switches_remaining <= 0:
                    path_info['completed'] = True
                    completed_paths += 1
                    print(f"  ✅ {path_key}: All modes completed")
                    continue
                
                # Calculate next mode index (linear progression, not cycling)
                next_index = current_index + 1
                if next_index >= len(mode_names):
                    # This shouldn't happen with proper switches_remaining tracking, but safety check
                    path_info['completed'] = True
                    completed_paths += 1
                    print(f"  ✅ {path_key}: All modes completed")
                    continue
                
                next_mode_name = mode_names[next_index]
                next_mode_config = modes[next_mode_name]
                
                # Extract AS and router information from path_info
                as_num = path_info['topology_as']
                router_num = path_info['router_num']
                
                if as_num and router_num:
                    print(f"  🔄 {path_key}: {next_mode_name} (switch {len(mode_names) - switches_remaining}/{len(mode_names) - 1})")
                    success = self.apply_multimodal_mode(as_num, router_num, next_mode_name, next_mode_config, baseline_delay_ms=0.6)
                    
                    if success:
                        # Update current mode index and decrement switches remaining
                        path_info['current_mode_index'] = next_index
                        path_info['switches_remaining'] -= 1
                        
                        # Mark as completed if no more switches remaining
                        if path_info['switches_remaining'] <= 0:
                            path_info['completed'] = True
                        
                        successful_switches += 1
                    else:
                        print(f"    ❌ Failed to apply {next_mode_name}")
                        failed_switches += 1
                else:
                    target = path_info['target']
                    group_id = path_info['group_id']
                    path_name = path_info['path_name']
                    print(f"    ⚠️ Could not find AS/router for {path_key} (target: {target}, group: {group_id}, path: {path_name})")
                    failed_switches += 1
            
            print(f"  Mode switch summary: {successful_switches} successful, {failed_switches} failed, {completed_paths} completed")
            
            # Log completion status
            active_paths = sum(1 for path_info in self._multimodal_timeline.values() 
                            if not path_info.get('completed', False) and path_info.get('switches_remaining', 0) > 0)
            completed_paths_total = sum(1 for path_info in self._multimodal_timeline.values()
                                    if path_info.get('completed', False))

            print(f"  Active paths with switches remaining: {active_paths}")
            print(f"  Completed paths: {completed_paths_total}")

            if active_paths == 0:
                print(f"\n🎊 All multimodal paths have completed their mode sequences after {switch_count + 1} switches")
                break
            
            switch_count += 1
            
            if switch_count >= mode_switches:
                print(f"\n🎊 Multimodal timeline complete after {switch_count} switches")
                break
            
            # Sleep for mode duration AFTER switching
            print(f"    Sleeping for {mode_duration} seconds until next switch...")
            time.sleep(mode_duration)



async def sleep(duration):
    await asyncio.sleep(duration)


def generate_iat_list(total_time, num_clients, init_iat=200.0, min_iat=1.0):
    exp_rate = np.log(init_iat / min_iat) / (num_clients - 1)
    iat_list = [init_iat]
    for i in range(1, num_clients):
        #iat = 1.0 if i >= 35 else np.clip(init_iat * np.exp(-exp_rate * i), a_min=1.0, a_max=None)
        iat = np.clip(init_iat * np.exp(-exp_rate * i), a_min=min_iat, a_max=None)
        iat_list.append(iat)
    
    iat_sum = np.sum(iat_list)
    if iat_sum > total_time:
        iat_list = [iat * total_time / iat_sum for iat in iat_list]
    return iat_list


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(
            description='IPMininet script for Evaluation',
            usage='%(prog)s [ -d date -i experiment-number -r routing-period -m measurement-period]')
    arg_parser.add_argument('-d', dest='date',
                            help='Date of experiment run',
                            type=str,
                            default=datetime.now().strftime("%Y%m%d"))
    arg_parser.add_argument('-i', dest='expt_no',
                            help='Experiment run number',
                            type=int,
                            default=None)
    arg_parser.add_argument('-r', dest='routing_period',
                            help='Routing period of Overwatch in experiment',
                            type=int,
                            default=20)
    arg_parser.add_argument('-m', dest='msm_period',
                            help='Measurement period of Overwatch in experiment',
                            type=float,
                            default=1)
    arg_parser.add_argument('-b', dest='basedirname',
                            help='Name of base directory folder to store experiment files',
                            type=str,
                            default='PATH-Tp2-ALL-CLIENTS')

    arg_parser.add_argument('-n', dest='nhost',
                            help='Number of hosts per network',
                            type=int,
                            default=1)

    arg_parser.add_argument('--tc-config', dest='tc_config',
                            help='Path to enhanced TC distribution config file',
                            type=str,
                            default='enhanced_tc_distribution_config.json')

    arg_parser.add_argument('--mode-duration', dest='mode_duration',
                            help='Duration for each multimodal mode in seconds',
                            type=int,
                            default=200)

    args = arg_parser.parse_args()

    cl_data_dir = '/home/ubuntu/gClient-control-logs/Overwatch/'+args.basedirname
    ctlr_data_dir = '/home/ubuntu/OvW-Ctlr-Data/'+args.basedirname
    if not pathlib.Path(cl_data_dir).exists():
        raise SystemExit("Directory for the game client logs does not exist")

    if not pathlib.Path(ctlr_data_dir).exists():
        raise SystemExit("Directory for the controller data does not exist")

    if args.msm_period.is_integer():
        args.msm_period = int(args.msm_period)

    with open('as_topology_config_with_variation.json', 'r') as f:
        config_data = json.load(f)
        AS_CONFIG = {int(k): v for k, v in config_data['AS_CONFIG'].items()}
        AS_GROUP_MAPPING = config_data.get('AS_GROUP_MAPPING', {})

    net = PARNet(topo=TestTopo(as_config=AS_CONFIG, nhosts=args.nhost), use_v4=False)


    bwidthsock = '/home/ubuntu/bandwidth.sock'
    latsock = '/home/ubuntu/latency.sock'
    lossock = '/home/ubuntu/loss.sock'
    diffsock = '/home/ubuntu/differentiated.sock'
    #parsocks = [ bwidthsock, latsock, lossock, diffsock]
    parsocks = [ latsock ]
    random.seed(12345)
    # Load enhanced TC configuration with multimodal support
    net.load_tc_config(args.tc_config, AS_GROUP_MAPPING)

    try:
        net.start()
        # set tp2_delay to the same value as tp3_delay to test failure
        print("\n" + "="*80)
        print("STARTING ENHANCED MULTIMODAL NETWORK EMULATION")
        print("="*80)
        

        net.configure_delays(AS_CONFIG)

        #time.sleep(120)
        #print(f'Wait for hosts and link set up to be completed')
        # divide rtt by 2 
        #tp2_delay =  min(tp2_rtt)
        tp2_delay = 45.5
        tp2_delay_delta = [x - min(tp2_rtt) for x in tp2_rtt]
        tp2_delay_delta_avg =  np.mean(tp2_delay_delta)
        # set tp3 delay to 5ms (to make  10ms rtt) to catch any odd behaviour
        tp3_delay = 45
        tp3_delay_f = 40.5
        tp3_delay_r = 4.5
        tp3_delay_delta = [x - min(tp3_rtt) for x in tp3_rtt]
        tp3_delay_delta_avg = np.mean(tp3_delay_delta)

        tp5_delay = 35.5
        tp5_delay_delta = [x - tp3_delay for x in tp3_rtt] 
        tp5_delay_delta_avg = np.mean(tp5_delay_delta)

        net["gameServer"].cmd("python gameServer.py &> /dev/null &")
        net["gameServer"].cmd("/usr/sbin/tcpdump -i any -nnnnttttvvvleXXXSS host 100::4 and port 50055 -w /home/ubuntu/dptrace.pcap &")
        net["gameServer"].cmd("source /home/ubuntu/PAR-EMULATOR/bin/activate")
        net["gameServer"].cmd(f'/home/ubuntu/PAR-EMULATOR/bin/python /home/ubuntu/git-repos/srv6-controller/grpc/dataplane-manager.py -e /home/ubuntu/git-repos/srv6-controller/grpc/dataplane_manager.env -c {ctlr_data_dir}/rp-{str(args.routing_period)}-seconds-mp-{str(args.msm_period)}-seconds/{args.date}-{str(args.expt_no)}/dataplane-gameServer-Inst.csv &> dataplane-gameServer.log &')

        #time.sleep(1)
        net["Tp1ASr1"].cmd('ping -c 10 100::4 > Tp1ASr1_out &')
        net["Tp1ASr2"].cmd('ping -c 10 100::4 > Tp1ASr2_out &')
        net["Tp1ASr3"].cmd('ping -c 10 100::4 > Tp1ASr3_out &')
        net["Tp1ASr4"].cmd('ping -c 10 100::4 > Tp1ASr4_out &')

        ctlrFullPath = f'{ctlr_data_dir}/rp-{str(args.routing_period)}-seconds-mp-{str(args.msm_period)}-seconds/{args.date}-{str(args.expt_no)}'
        net["Tp1ASctlr"].cmd("ip -6 route add 55::/48 via 100::1 dev Tp1ASctlr-eth0")
        net["gameServer"].cmd('ping -c 10 100::4 > gameServer_out &')
        #time.sleep(3)
        #time.sleep(10)

        #net["Tp1ASr1"].cmd("./login_update_reset_bgp_session.sh localhost bgpd zebra &> ~/Tp1ASr1-reset-session.log")
        #net["Tp1ASr2"].cmd("./login_update_reset_bgp_session.sh localhost bgpd zebra &> ~/Tp1ASr2-reset-session.log")
        #net["Tp1ASr3"].cmd("./login_update_reset_bgp_session.sh localhost bgpd zebra &> ~/Tp1ASr3-reset-session.log")
        #net["Tp1ASr4"].cmd("./login_update_reset_bgp_session.sh localhost bgpd zebra &> ~/Tp1ASr4-reset-session.log")
        #net["Tp1ASr2"].cmd("./login_update_reset_bgp_session.sh localhost bgpd zebra &> ~/Tp1ASr2-reset-session.log")

        net["Tp1ASctlr"].cmd("source /home/ubuntu/PAR-EMULATOR/bin/activate")
        #net["Tp1ASctlr"].cmd("/home/ubuntu/PAR-EMULATOR/bin/python /home/ubuntu/git-repos/overwatch/bgpcontroller/Controller.py -r {} -m {} -d {} /home/ubuntu/config-Tp1AS-Three.yaml &> controller.log &".format(args.routing_period, args.msm_period, ctlrFullPath))
        net["Tp1ASctlr"].cmd("/home/ubuntu/PAR-EMULATOR/bin/python /home/ubuntu/git-repos/overwatch/bgpcontroller/Controller.py -r {} -m {} -d {} /home/ubuntu/config-Tp1AS-Three-Run-in-GS.yaml &> controller.log &".format(args.routing_period, args.msm_period, ctlrFullPath))

        time.sleep(20)
        #net["Tp1ASr1"].cmd("./login_update_reset_bgp_session.sh localhost bgpd zebra &> ~/Tp1ASr1-reset-session.log")
        #net["Tp1ASr2"].cmd("./login_update_reset_bgp_session.sh localhost bgpd zebra &> ~/Tp1ASr2-reset-session.log")
        #net["Tp1ASr3"].cmd("./login_update_reset_bgp_session.sh localhost bgpd zebra &> ~/Tp1ASr3-reset-session.log")
        #net["Tp1ASr4"].cmd("./login_update_reset_bgp_session.sh localhost bgpd zebra &> ~/Tp1ASr4-reset-session.log")

        ## Add monitoring configuration
        net["gameServer"].cmd('ip -6 addr add 55::4/48 dev gameServer-eth0')
        net["gameServer"].cmd('ip -6 addr add 55::5/48 dev gameServer-eth0')
        net["gameServer"].cmd('ip -6 addr add 55::6/48 dev gameServer-eth0')

        net["gameServer"].cmd('ip6tables -t mangle -A OUTPUT -o gameServer-eth0 -p ipv6-icmp -s 55::4 -j MARK --set-mark 40')
        net["gameServer"].cmd('ip6tables -t mangle -A OUTPUT -o gameServer-eth0 -p udp -s 55::4 --dport 12346 -j MARK --set-mark 40')
        net["gameServer"].cmd('ip6tables -t mangle -A OUTPUT -o gameServer-eth0 -p udp -s 55::4 --sport 12346 -j MARK --set-mark 40')
        net["gameServer"].cmd('ip -6 rule add fwmark 40 table 40')
        net["gameServer"].cmd('ip -6 route add 2001::/16 encap seg6 mode encap segs 100::2 dev gameServer-eth0 metric 10 table 40')

        net["gameServer"].cmd('ip6tables -t mangle -A OUTPUT -o gameServer-eth0 -p ipv6-icmp -s 55::5 -j MARK --set-mark 50')
        net["gameServer"].cmd('ip6tables -t mangle -A OUTPUT -o gameServer-eth0 -p udp -s 55::5 --dport 12347 -j MARK --set-mark 50')
        net["gameServer"].cmd('ip6tables -t mangle -A OUTPUT -o gameServer-eth0 -p udp -s 55::5 --sport 12347 -j MARK --set-mark 50')
        net["gameServer"].cmd('ip -6 rule add fwmark 50 table 50')
        net["gameServer"].cmd('ip -6 route add 2001::/16 encap seg6 mode encap segs 100::3 dev gameServer-eth0 metric 10 table 50')

        net["gameServer"].cmd('ip6tables -t mangle -A OUTPUT -o gameServer-eth0 -p ipv6-icmp -s 55::6 -j MARK --set-mark 60')
        net["gameServer"].cmd('ip6tables -t mangle -A OUTPUT -o gameServer-eth0 -p udp -s 55::6 --dport 12348 -j MARK --set-mark 60')
        net["gameServer"].cmd('ip6tables -t mangle -A OUTPUT -o gameServer-eth0 -p udp -s 55::6 --sport 12348 -j MARK --set-mark 60')
        net["gameServer"].cmd('ip -6 rule add fwmark 60 table 60')
        net["gameServer"].cmd('ip -6 route add 2001::/16 encap seg6 mode encap segs 100::6 dev gameServer-eth0 metric 10 table 60')

        IPCLI(net)
        time.sleep(300)
        net["gameServer"].cmd("python /home/ubuntu/gameMsmOrchestrator-Three-Variable.py -m {} &> /home/ubuntu/MeasurementOrchestrator.log &".format(args.msm_period))
        #net["gameServer"].cmd("python /home/ubuntu/gameMsmOrchestrator.py &> /dev/null &")
        time.sleep(10)
        net["gameServer"].cmd("source /home/ubuntu/gufo-ping-updated/bin/activate")
        #net["gameServer"].cmd("/home/ubuntu/gufo-ping-updated/bin/python /home/ubuntu/gameMsmPath1.py &> /dev/null &")
        net["gameServer"].cmd("/home/ubuntu/gufo-ping-updated/bin/python /home/ubuntu/gameMsmPath1.py -m {} &> /home/ubuntu/gClient-logs/Msm-logs/gameMsmPath1.log &".format(args.msm_period))

        net["gameServer"].cmd("source /home/ubuntu/gufo-ping-updated/bin/activate")
        #net["gameServer"].cmd("/home/ubuntu/gufo-ping-updated/bin/python /home/ubuntu/gameMsmPath2.py &> /dev/null &")
        net["gameServer"].cmd("/home/ubuntu/gufo-ping-updated/bin/python /home/ubuntu/gameMsmPath2.py -m {} &> /home/ubuntu/gClient-logs/Msm-logs/gameMsmPath2.log &".format(args.msm_period))

        net["gameServer"].cmd("source /home/ubuntu/gufo-ping-updated/bin/activate")
        #net["gameServer"].cmd("/home/ubuntu/gufo-ping-updated/bin/python /home/ubuntu/gameMsmPath2.py &> /dev/null &")
        net["gameServer"].cmd("/home/ubuntu/gufo-ping-updated/bin/python /home/ubuntu/gameMsmPath3.py -m {} &> /home/ubuntu/gClient-logs/Msm-logs/gameMsmPath3.log &".format(args.msm_period))
        
        #IPCLI(net)

        time.sleep(30)
        start_time = time.time()
        experiment_start = datetime.now()
        print(f"\n🚀 EXPERIMENT START: {experiment_start}")
        print("="*60)

        client_names = [f"gCl{i}_{j}" for i in range(1, len(AS_CONFIG)+1) for j in range(1, args.nhost + 1)]
        hosts_nums = list(range(1, 31))
        # remember to change to 75
        iat_list = generate_iat_list(90, len(client_names))
        if 'gCl49_1' in client_names:
            client_names.remove('gCl49_1')
            random.shuffle(client_names)
            client_names.insert(0, 'gCl49_1')
            print(f"📌 Client gCl49_1 set to arrive first for synchronized analysis")
        else:
            random.shuffle(client_names)
            print(f"⚠️ Warning: gCl49_1 not found, using default ordering")

        # Define three-path networks based on AS_CONFIG
        three_path_networks = [as_num for as_num, (num_routers, _, _) in AS_CONFIG.items() if num_routers >= 3]
        print(f"Three-path networks (ASes with 3+ routers): {three_path_networks}")

        print(f"📈 Starting {len(client_names)} game clients with IAT over 90 seconds")

        # Start multimodal timeline in background thread
        import threading
        
        def multimodal_thread():
            # Wait until clients are settled (90s + 60s)
            # time.sleep(210)
            arrival_time = 90
            settle_time = 110
            initial_wait = arrival_time + settle_time

            time.sleep(initial_wait)
            # Sleep additional 200s to reach t=400s for first mode switch
            if args.routing_period == 30:
                mode_wait = 200
                mode_dur = args.mode_duration
                #mode_wait = 210
                #mode_dur = args.mode_duration
            else:
                mode_wait = 200
                mode_dur = args.mode_duration

            print(f"\n{'='*80}")
            print(f"SYNCHRONIZED MODE SWITCHING AT T=400s")
            print(f"{'='*80}")
            print(f"Experiment timeline:")
            print(f"  t=0-{arrival_time}s: Client arrivals (gCl43_1 first)")
            print(f"  t={arrival_time}-{initial_wait}s: Settlement period")
            print(f"  t={initial_wait}-{initial_wait + mode_wait}s: Pre-switching wait")
            print(f"  t={initial_wait + mode_wait}s: FIRST MODE SWITCH")
            print(f"  Subsequent switches every 200s: 400s, 600s, 800s, 1000s...")
            print(f"")
            print(f"Routing Period: {args.routing_period}s")
            print(f"Measurement Period: {args.msm_period}s")
            print(f"First switch at: t={initial_wait + mode_wait}s")
            print(f"Mode duration: {mode_dur}s")
            print(f"Mode Switch Interval: 200s")
            print(f"")
            if args.routing_period == 30:
                print(f"30s RP Configuration:")
                print(f"  390/30 = 13 ✓ ALIGNED")
                print(f"  Switch times: 390s, 570s, 750s, 930s")
            else:
                print(f"Standard Configuration:")
                print(f"  400/{args.routing_period} = {400//args.routing_period} ✓ ALIGNED")
                print(f"  Switch times: 400s, 600s, 800s, 1000s")
            print(f"{'='*80}\n")
    
            # Sleep the additional 200s
            time.sleep(mode_wait)
            net.execute_multimodal_timeline(start_time, game_duration=901, mode_duration=mode_dur)
        
        if net._multimodal_timeline:
            threading.Thread(target=multimodal_thread, daemon=True).start()
            print(f"🎯 Multimodal timeline thread started (mode switches every {args.mode_duration}s)")


        for idx, host_name in enumerate(client_names):
            exec_time = time.perf_counter()
            iat = iat_list[idx]
            
            # Extract network number from host name (i from gCl{i}_{j})
            network_num = int(host_name.split('_')[0][3:])  # Gets i from gCli_j

            net[host_name].cmd(f"python simpleGameClient.py -n {host_name} -d 901 -c {cl_data_dir}/routing-period-{str(args.routing_period)}-seconds-m-period-{str(args.msm_period)}-seconds/{args.date}-{str(args.expt_no)}/{host_name}.csv &> /dev/null &")
            net[host_name].cmd(f"python gameClientP1.py -d 901 -n {host_name} -s 55::4 -p 12346  &> /home/ubuntu/gClient-logs/Msm-logs/{host_name}-P1.log &")
            net[host_name].cmd(f"python gameClientP1.py -d 901 -n {host_name} -s 55::5 -p 12347  &> /home/ubuntu/gClient-logs/Msm-logs/{host_name}-P2.log &")

            if network_num in three_path_networks:
                net[host_name].cmd(f"python gameClientP1.py -d 901 -n {host_name} -s 55::6 -p 12348  &> /home/ubuntu/gClient-logs/Msm-logs/{host_name}-P3.log &")
            print(f'🎮 Started game client on host {host_name} at {datetime.now()}')

            exec_delta = time.perf_counter() - exec_time
            if exec_delta < iat:
                exec_iat = iat - exec_delta
                print(f'Sleeping for {exec_iat} seconds')
                time.sleep(exec_iat)

        clients_added_time = datetime.now()
        print(f"\n✅ ALL CLIENTS ADDED: {clients_added_time}")
        print(f"📊 Settling for 120 seconds before multimodal switching begins...")
        # time.sleep(120)
        #IPCLI(net)

        # Main experiment loop with enhanced multimodal handling
        settle_complete_time = datetime.now()
        print(f"\n🔄 MULTIMODAL SWITCHING PHASE: {settle_complete_time}")
        print("="*60)

        # The multimodal timeline is now handled by the background thread
        # This main loop can handle other experiment control or monitoring
        # total_experiment_duration = 1125  # Original experiment duration\
        total_experiment_duration = 90 + 110 + 200 + 901

        while (time.time() - start_time) < total_experiment_duration:
            time.sleep(30)  # Check every 30 seconds
            elapsed = time.time() - start_time
            remaining = total_experiment_duration - elapsed
            
            if remaining > 0:
                print(f"⏱️  Experiment progress: {elapsed:.0f}s/{total_experiment_duration}s (remaining: {remaining:.0f}s)")
            else:
                break

        experiment_end_time = datetime.now()
        print(f"\n🏁 EXPERIMENT COMPLETE: {experiment_end_time}")
        print(f"📈 Total duration: {experiment_end_time - experiment_start}")
        
        # Generate experiment summary
        print("\n" + "="*80)
        print("EXPERIMENT SUMMARY")
        print("="*80)
        print(f"🕐 Start time: {experiment_start}")
        print(f"🕐 Clients added: {clients_added_time}")
        print(f"🕐 Settling complete: {settle_complete_time}")
        print(f"🕐 End time: {experiment_end_time}")
        print(f"🎮 Total clients: {len(client_names)}")
        print(f"🎯 Multimodal paths: {len(net._multimodal_timeline)}")
        print(f"⏱️  Mode switch interval: {args.mode_duration}s")
        
        if net._multimodal_timeline:
            expected_switches = (total_experiment_duration - 210) // args.mode_duration
            print(f"🔄 Expected mode switches: {expected_switches}")
            
            print("\nMultimodal paths configured:")
            for path_key, path_info in net._multimodal_timeline.items():
                current_mode = path_info['mode_names'][path_info['current_mode_index']]
                print(f"  {path_key}: {len(path_info['modes'])} modes (current: {current_mode})")

        print("="*80)
    finally:
        net.stop()
