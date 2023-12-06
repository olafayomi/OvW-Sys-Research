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
import random
import numpy as np


class TestTopo(IPTopo):

    def __init__(self, nhosts=1, *args, **kwargs):
        self.nhosts = nhosts
        super(TestTopo, self).__init__(*args,  **kwargs)


    def build(self, *args, **kwargs):
        # Add all routers

        Tp1ASr1 = self.bgp('Tp1ASr1')
        Tp1ASr2 = self.bgp('Tp1ASr2')
        Tp1ASr3 = self.bgp('Tp1ASr3')

        Tp2ASr1 = self.bgp('Tp2ASr1')
        Tp2ASr2 = self.bgp('Tp2ASr2')
        Tp3ASr1 = self.bgp('Tp3ASr1')
        Tp3ASr2 = self.bgp('Tp3ASr2')
        Tp4ASr1 = self.bgp('Tp4ASr1')
        Tp5ASr1 = self.bgp('Tp5ASr1')

        AS1R1 = self.bgp('AS1R1')
        AS2R1 = self.bgp('AS2R1')
        AS3R1 = self.bgp('AS3R1')
        AS4R1 = self.bgp('AS4R1')
        AS5R1 = self.bgp('AS5R1')
        AS6R1 = self.bgp('AS6R1')
        AS7R1 = self.bgp('AS7R1')
        AS8R1 = self.bgp('AS8R1')
        AS9R1 = self.bgp('AS9R1')
        AS10R1 = self.bgp('AS10R1')
        AS11R1 = self.bgp('AS11R1')
        AS12R1 = self.bgp('AS12R1')
        AS13R1 = self.bgp('AS13R1')
        AS14R1 = self.bgp('AS14R1')
        AS15R1 = self.bgp('AS15R1')
        AS16R1 = self.bgp('AS16R1')
        AS17R1 = self.bgp('AS17R1')
        AS18R1 = self.bgp('AS18R1')
        AS19R1 = self.bgp('AS19R1')
        AS20R1 = self.bgp('AS20R1')
        AS21R1 = self.bgp('AS21R1')
        AS22R1 = self.bgp('AS22R1')
        AS23R1 = self.bgp('AS23R1')
        AS24R1 = self.bgp('AS24R1')
        AS25R1 = self.bgp('AS25R1')
        AS26R1 = self.bgp('AS26R1')
        AS27R1 = self.bgp('AS27R1')
        AS28R1 = self.bgp('AS28R1')
        AS29R1 = self.bgp('AS29R1')
        AS30R1 = self.bgp('AS30R1')

        Sw1Tp1 = self.addSwitch('Sw1Tp1')
        Sw2Tp2 = self.addSwitch('Sw2Tp2')
        Sw3Tp3 = self.addSwitch('Sw3Tp3')

        Tp1ASr1Sw1 = self.addLink(Tp1ASr1, Sw1Tp1)
        Tp1ASr1Sw1[Tp1ASr1].addParams(ip=("100::1/48",))
        Tp1ASr2Sw1 = self.addLink(Tp1ASr2, Sw1Tp1)
        Tp1ASr2Sw1[Tp1ASr2].addParams(ip=("100::2/48",))
        Tp1ASr3Sw1 = self.addLink(Tp1ASr3, Sw1Tp1)
        Tp1ASr3Sw1[Tp1ASr3].addParams(ip=("100::3/48",))

        lTp1Tp2 = self.addLink(Tp1ASr2, Tp2ASr1)
        lTp1Tp2[Tp1ASr2].addParams(ip=("1002::100/48",))
        lTp1Tp2[Tp2ASr1].addParams(ip=("1002::200/48",))

        Tp2ASr1Sw2 = self.addLink(Tp2ASr1, Sw2Tp2)
        Tp2ASr1Sw2[Tp2ASr1].addParams(ip=("200::1/48",))
        Tp2ASr2Sw2 = self.addLink(Tp2ASr2, Sw2Tp2)
        Tp2ASr2Sw2[Tp2ASr2].addParams(ip=("200::2/48",))

        lTp1Tp3 = self.addLink(Tp1ASr3, Tp3ASr1)
        lTp1Tp3[Tp1ASr3].addParams(ip=("1003::100/48",))
        lTp1Tp3[Tp3ASr1].addParams(ip=("1003::300/48",))

        Tp3ASr1Sw3 = self.addLink(Tp3ASr1, Sw3Tp3)
        Tp3ASr1Sw3[Tp3ASr1].addParams(ip=("300::1/48",))
        Tp3ASr2Sw3 = self.addLink(Tp3ASr2, Sw3Tp3)
        Tp3ASr2Sw3[Tp3ASr2].addParams(ip=("300::2/48",))

        # Add Game server host to topology
        gameServer = self.addHost('gameServer')
        GsRtrLink = self.addLink(gameServer, Tp1ASr1)
        GsRtrLink[gameServer].addParams(ip=("55::1/48",))
        GsRtrLink[Tp1ASr1].addParams(ip=("55::2/48",))


        # Add game client hosts to user network, nhosts per networt!!!
        for i in range(1, 31):
            Sw1AS = self.addSwitch(f'Sw1AS{i}')
            rtrlink = self.addLink(eval(f"AS{i}R1"), Sw1AS)
            ip_as = f"2001:df{str(i).zfill(2)}::{self.nhosts+i}/48"
            rtrlink[eval(f"AS{i}R1")].addParams(ip=(ip_as,))
            for j in range(1, self.nhosts + 1): 
                host_name = f"gCl{i}_{j}"
                link_name = f"gClink{i}_{j}"
                host = self.addHost(host_name)
                link = self.addLink(Sw1AS, host)
                ip_host = f"2001:df{str(i).zfill(2)}::{j}/48"
                link[host].addParams(ip=(ip_host,))

        self.addLinks((Tp2ASr2, Tp4ASr1), (Tp3ASr2, Tp4ASr1))

        link_delay = 0.5

        for i in range(1, 31):
            if (i == 10) or (i == 20):
                link_d = link_delay - 0.375
                link = self.addLink(Tp4ASr1, eval("AS{}R1".format(i)),
                                    delay="{}ms".format(link_d/2))
            elif i == 11:
                link_d = link_delay + 0.4
                link = self.addLink(Tp4ASr1, eval("AS{}R1".format(i)),
                                    delay="{}ms".format(link_d/2))
            else:
                link = self.addLink(Tp4ASr1, eval("AS{}R1".format(i)),
                                    delay="{}ms".format(link_delay/2))
            link_delay += 0.5

        self.addAS(100, (Tp1ASr1, Tp1ASr2, Tp1ASr3))
        self.addAS(200, (Tp2ASr1, Tp2ASr2))
        self.addAS(300, (Tp3ASr1, Tp3ASr2))
        self.addAS(400, (Tp4ASr1,))

        for i in range(1, 31):
            exec(f"self.addAS(i, (AS{i}R1,))")

        bgp_peering(self, Tp1ASr1, Tp1ASr2)
        bgp_peering(self, Tp1ASr1, Tp1ASr3)

        bgp_peering(self, Tp2ASr1, Tp2ASr2)
        bgp_peering(self, Tp3ASr1, Tp3ASr2)
        
        # Set ACL and prefer one path over the other
        acl4 = AccessList(name='all', entries=('any',), family='ipv4')

        acl = AccessList(name='all6', entries=('any',), family='ipv6')

        #prefer path via Tp3 or Tp2
        Tp1ASr3.get_config(BGP).set_local_pref(300, from_peer=Tp3ASr1,
                                               matching=(acl4, acl))

        Tp1ASr2.get_config(BGP).set_local_pref(200, from_peer=Tp2ASr1,
                                               matching=(acl4,acl))


        ebgp_session(self, Tp1ASr2, Tp2ASr1)
        ebgp_session(self, Tp1ASr3, Tp3ASr1)

        # Prefer return path from clients via Tp3 or Tp2
        Tp4ASr1.get_config(BGP).set_local_pref(100, from_peer=Tp2ASr2,
                                               matching=(acl4,acl))
        Tp4ASr1.get_config(BGP).set_local_pref(200, from_peer=Tp3ASr2,
                                               matching=(acl4,acl))
        ebgp_session(self, Tp4ASr1, Tp2ASr2) #, link_type=CLIENT_PROVIDER)
        ebgp_session(self, Tp4ASr1, Tp3ASr2) #, link_type=CLIENT_PROVIDER)

        for i in range(1, 31):
            exec(f"ebgp_session(self, AS{i}R1, Tp4ASr1, link_type=CLIENT_PROVIDER)")

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
    

    def modifyLink(self, node1, node2, delay="2ms", bw=None, max_queue_size=None, **opts):

        src_params = opts.get("params1", {})
        dst_params = opts.get("params2", {})        
        src_delay = src_params.get("delay")
        src_loss = src_params.get("loss")
        src_max_queue = src_params.get("max_queue_size")
        
        dst_delay = dst_params.get("delay")
        dst_loss = dst_params.get("loss")
        dst_max_queue = dst_params.get("max_queue_size")
        
        for sw in self.switches:
            src_link = node2.connectionsTo(sw)
            dst_link = node1.connectionsTo(sw)
            if src_link and dst_link:
                break

        src_int, _ = src_link[0]
        dst_int, _ = dst_link[0]

        src_delay = src_delay or delay
        src_loss = src_loss or 0
        
        src_int.config(delay=src_delay, max_queue_size=src_max_queue, loss=src_loss)
        dst_int.config(delay=dst_delay, max_queue_size= src_max_queue, loss=dst_loss)


async def sleep(duration):
    await asyncio.sleep(duration)


def generate_iat_list(total_time, num_clients, init_iat=200.0, min_iat=1.0):
    exp_rate = np.log(init_iat / min_iat) / (num_clients - 1)
    iat_list = [init_iat]
    for i in range(1, num_clients):
        iat = np.clip(init_iat * np.exp(-exp_rate * i), a_min=min_iat, a_max=None)
        iat_list.append(iat)
    
    iat_sum = np.sum(iat_list)
    if iat_sum > total_time:
        iat_list = [iat * total_time / iat_sum for iat in iat_list]
    return iat_list


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser(
            description='IPMininet script for Evaluation without OvW',
            usage='%(prog)s [ -d date -i experiment-number -b basedirname]')
    arg_parser.add_argument('-d', dest='date',
                            help='Date of experiment run',
                            type=str,
                            default=datetime.now().strftime("%Y%m%d"))

    arg_parser.add_argument('-i', dest='expt_no',
                            help='Experiment run number',
                            type=int,
                            default=None)

    arg_parser.add_argument('-b', dest='basedirname',
                            help='Name of base directory folder to store experiment files',
                            type=str,
                            default='BGP-Preference-Change-30ms')

    arg_parser.add_argument('-n', dest='nhost',
                            help='Number of hosts per network',
                            type=int,
                            default=1)

    args = arg_parser.parse_args()
    cl_data_dir = '/home/ubuntu/gClient-control-logs/No-Overwatch/'+args.basedirname
    fib_data_dir = '/home/ubuntu/BGP-FIB-Data/'+args.basedirname
    if not pathlib.Path(cl_data_dir).exists():
        raise SystemExit("Directory for the game client logs does not exist")

    if not pathlib.Path(fib_data_dir).exists():
        raise SystemExit("Directory for the controller data does not exist")

    net = PARNet(topo=TestTopo(nhosts=args.nhost), use_v4=False)
    random.seed(12345)

    try:
        net.start()
        tp2_delay = 49
        
        tp3_delay = 50
        tp3_delay_f = 44.250
        tp3_delay_r = 4.250
        net.modifyLink(net["Tp2ASr1"], net["Tp2ASr2"],
                       params1={"delay": "{}ms".format(tp2_delay)},
                       params2={"delay": "{}ms".format(tp2_delay)})
        net.modifyLink(net["Tp3ASr1"], net["Tp3ASr2"],
                       params1={"delay": "{}ms".format(tp3_delay_f)},
                       params2={"delay": "{}ms".format(tp3_delay_r)})
        net["Tp2ASr1"].cmd("/sbin/tc qdisc change dev Tp2ASr1-eth1 root netem delay {}ms".format(tp2_delay))
        net["Tp2ASr2"].cmd("/sbin/tc qdisc change dev Tp2ASr2-eth0 root netem delay {}ms".format(tp2_delay))


        net["Tp3ASr1"].cmd("/sbin/tc qdisc change dev Tp3ASr1-eth1 root netem delay {}ms".format(tp3_delay_f))
        net["Tp3ASr2"].cmd("/sbin/tc qdisc change dev Tp3ASr2-eth0 root netem delay {}ms".format(tp3_delay_r))
        
        fibFullPath = f'{fib_data_dir}/{args.date}-{str(args.expt_no)}'
        net["Tp1ASr1"].cmd("source /home/ubuntu/PAR-EMULATOR/bin/activate")
        net["Tp1ASr1"].cmd("/home/ubuntu/PAR-EMULATOR/bin/python /home/ubuntu/RouteMonitor.py -d {}  &> Tp1ASr1-Route-Monitor.log &".format(fibFullPath))

        #IPCLI(net)
        net["gameServer"].cmd("python gameServer.py &> /dev/null &")
        time.sleep(260)
        start_time = time.time()
        print("%s: Started adding hosts" %(str(datetime.now())))


        client_names = [f"gCl{i}_{j}" for i in range(1, 31) for j in range(1, args.nhost + 1)]

        iat_list = generate_iat_list(200, len(client_names))
        random.shuffle(client_names)

        for idx, host_name in enumerate(client_names):
            exec_time = time.perf_counter()
            iat = iat_list[idx]
            net[host_name].cmd(f"python simpleGameClient.py  -n {host_name} -d 600 -c {cl_data_dir}/{args.date}-{str(args.expt_no)}/{host_name}.csv &> /dev/null &")
            print(f'Started game client on host {host_name} at {str(datetime.now())}')
            exec_delta = time.perf_counter() - exec_time
        
            if exec_delta < iat:
                exec_iat = iat - exec_delta
                print(f'Sleeping for {exec_iat} seconds')
                time.sleep(exec_iat)

        print("%s: All hosts added" %(str(datetime.now())))
        time.sleep(60)
        fail_count = 0
        while (time.time() - start_time) < 860:
            # 165 + 60 + 75 gives us exactly 5 minutes after clients are in
            # There are 30 clients now and 60 seconds IAT
            time.sleep(140)
            if fail_count  < 1:
                print("Changed config at %s" %(str(datetime.now())))
                net["Tp1ASr2"].cmd("./login_update_pref.sh localhost bgpd zebra &> ~/Tp1ASr2-pref-change.log")
                net["Tp1ASr2"].cmd("/bin/echo `date '+%Y-%m-%d %H:%M:%S'` >> ~/Tp1ASr2-pref-change.log")

            fail_count += 1
        print("%s: End Experiment" %(str(datetime.now())))
    finally:
        net.stop()
