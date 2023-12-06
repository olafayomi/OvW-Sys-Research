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
        Tp1ASr4 = self.bgp('Tp1ASr4')
        
        Tp2ASr1 = self.bgp('Tp2ASr1')
        Tp2ASr2 = self.bgp('Tp2ASr2')
        Tp3ASr1 = self.bgp('Tp3ASr1')
        Tp3ASr2 = self.bgp('Tp3ASr2')
        Tp4ASr1 = self.bgp('Tp4ASr1')
        Tp5ASr1 = self.bgp('Tp5ASr1')
        Tp5ASr2 = self.bgp('Tp5ASr2')

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
        Sw4Tp5 = self.addSwitch('Sw3Tp5')

        Tp1ASr1Sw1 = self.addLink(Tp1ASr1, Sw1Tp1)
        Tp1ASr1Sw1[Tp1ASr1].addParams(ip=("100::1/48",))
        Tp1ASr2Sw1 = self.addLink(Tp1ASr2, Sw1Tp1)
        Tp1ASr2Sw1[Tp1ASr2].addParams(ip=("100::2/48",))
        Tp1ASr3Sw1 = self.addLink(Tp1ASr3, Sw1Tp1)
        Tp1ASr3Sw1[Tp1ASr3].addParams(ip=("100::3/48",))
        Tp1ASr4Sw1 = self.addLink(Tp1ASr4, Sw1Tp1)
        Tp1ASr4Sw1[Tp1ASr4].addParams(ip=("100::6/48",))

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

        lTp1Tp5 = self.addLink(Tp1ASr4, Tp5ASr1)
        lTp1Tp5[Tp1ASr4].addParams(ip=("1005::100/48",))
        lTp1Tp5[Tp5ASr1].addParams(ip=("1005::200/48",))

        Tp5ASr1Sw4 = self.addLink(Tp5ASr1, Sw4Tp5)
        Tp5ASr1Sw4[Tp5ASr1].addParams(ip=("500::1/48",))
        Tp5ASr2Sw4 = self.addLink(Tp5ASr2, Sw4Tp5)
        Tp5ASr2Sw4[Tp5ASr2].addParams(ip=("500::2/48",))

        
        # Add Game server host to topology
        gameServer = self.addHost('gameServer')
        GsRtrLink = self.addLink(gameServer, Tp1ASr1)
        GsRtrLink[gameServer].addParams(ip=("55::1/48",))
        GsRtrLink[Tp1ASr1].addParams(ip=("55::2/48",))



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

        self.addLinks((Tp2ASr2, Tp4ASr1), (Tp3ASr2, Tp4ASr1),
                      (Tp5ASr2, Tp4ASr1))


        for i in range(1, 31):
            link = self.addLink(Tp4ASr1, eval("AS{}R1".format(i)))
            

        #self.addAS(55, (GsASr1,))
        self.addAS(100, (Tp1ASr1, Tp1ASr2, Tp1ASr3, Tp1ASr4))
        self.addAS(200, (Tp2ASr1, Tp2ASr2))
        self.addAS(300, (Tp3ASr1, Tp3ASr2))
        self.addAS(500, (Tp5ASr1, Tp5ASr2))
        self.addAS(400, (Tp4ASr1,))

        for i in range(1, 31):
            exec(f"self.addAS(i, (AS{i}R1,))")

        bgp_peering(self, Tp1ASr1, Tp1ASr2)
        bgp_peering(self, Tp1ASr1, Tp1ASr3)
        bgp_peering(self, Tp1ASr1, Tp1ASr4)

        bgp_peering(self, Tp2ASr1, Tp2ASr2)
        bgp_peering(self, Tp3ASr1, Tp3ASr2)
        bgp_peering(self, Tp5ASr1, Tp5ASr2)
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

        #prefer path via Tp3 or Tp2
        Tp1ASr4.get_config(BGP).set_local_pref(500, from_peer=Tp5ASr1,
                                               matching=(loc_prefC,))

        Tp1ASr3.get_config(BGP).set_local_pref(500, from_peer=Tp3ASr1,
                                               matching=(loc_prefB,))

        Tp1ASr2.get_config(BGP).set_local_pref(500, from_peer=Tp2ASr1,
                                               matching=(loc_prefA,))

        Tp2ASr1.get_config(BGP).set_community('2:500', to_peer=Tp1ASr2,
                                              matching=(acl4, aclA))

        Tp3ASr1.get_config(BGP).set_community('3:500', to_peer=Tp1ASr3,
                                              matching=(acl4, aclB))

        Tp5ASr1.get_config(BGP).set_community('5:500', to_peer=Tp1ASr4,
                                              matching=(acl4, aclC))

        ebgp_session(self, Tp1ASr2, Tp2ASr1)
        ebgp_session(self, Tp1ASr3, Tp3ASr1)
        ebgp_session(self, Tp1ASr4, Tp5ASr1)

        # Prefer return path from clients via Tp3 or Tp2
        Tp4ASr1.get_config(BGP).set_local_pref(100, from_peer=Tp2ASr2,
                                               matching=(acl4,acl))
        Tp4ASr1.get_config(BGP).set_local_pref(300, from_peer=Tp3ASr2,
                                               matching=(acl4,acl))
        Tp4ASr1.get_config(BGP).set_local_pref(200, from_peer=Tp5ASr2,
                                               matching=(acl4,acl))
        ebgp_session(self, Tp4ASr1, Tp2ASr2) #, link_type=CLIENT_PROVIDER)
        ebgp_session(self, Tp4ASr1, Tp3ASr2) #, link_type=CLIENT_PROVIDER)
        ebgp_session(self, Tp4ASr1, Tp5ASr2)

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
                            default='Path-via-Tp2-Spread-Out-Latency-Stable-30ms')

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
        tp2_delay = 45.5

        tp3_delay = 45
        tp3_delay_f = 40.5
        tp3_delay_r = 4.5

        tp5_delay = 35.5

        net.modifyLink(net["Tp2ASr1"], net["Tp2ASr2"],
                       params1={"delay": "{}ms".format(tp2_delay)},
                       params2={"delay": "{}ms".format(tp2_delay)})
        net.modifyLink(net["Tp3ASr1"], net["Tp3ASr2"],
                       params1={"delay": "{}ms".format(tp3_delay_f)},
                       params2={"delay": "{}ms".format(tp3_delay_r)})

        net.modifyLink(net["Tp5ASr1"], net["Tp5ASr2"],
                       params1={"delay": "{}ms".format(tp5_delay)},
                       params2={"delay": "{}ms".format(tp5_delay)})

        print(f'Delay set on Tp2 link is {tp2_delay}ms and RTT should be above {tp2_delay+tp3_delay_r}ms')
        print(f'Delay set on Tp3 link is {tp3_delay}ms and RTT should be less than {tp3_delay_f+tp3_delay_r}ms')
        print(f'Delay set on Tp5 link is {tp5_delay}ms and RTT should be less than {tp5_delay+tp3_delay_r}ms')

        net["Tp2ASr1"].cmd("/sbin/tc qdisc change dev Tp2ASr1-eth1 root netem delay {}ms".format(tp2_delay))
        net["Tp2ASr2"].cmd("/sbin/tc qdisc change dev Tp2ASr2-eth0 root netem delay {}ms".format(tp2_delay))

        net["Tp3ASr1"].cmd("/sbin/tc qdisc change dev Tp3ASr1-eth1 root netem delay {}ms".format(tp3_delay_f))
        net["Tp3ASr2"].cmd("/sbin/tc qdisc change dev Tp3ASr2-eth0 root netem delay {}ms".format(tp3_delay_r))

        net["Tp5ASr1"].cmd("/sbin/tc qdisc change dev Tp5ASr1-eth1 root netem delay {}ms".format(tp5_delay))
        net["Tp5ASr2"].cmd("/sbin/tc qdisc change dev Tp5ASr2-eth0 root netem delay {}ms".format(tp5_delay))

        net["Tp1ASr2"].cmd("./login_update_route_map_Tp1ASr2.sh localhost bgpd zebra &> ~/Tp1ASr2-route-map-update.log")
        net["Tp2ASr1"].cmd("./login_update_route_map_Tp2.sh localhost bgpd zebra &> ~/Tp2ASr1-route-map-update.log")

        net["Tp1ASr3"].cmd("./login_update_route_map_Tp1ASr3.sh localhost bgpd zebra &> ~/Tp1ASr3-route-map-update.log")
        net["Tp3ASr1"].cmd("./login_update_route_map_Tp3.sh localhost bgpd zebra &> ~/Tp3ASr1-route-map-update.log")

        net["Tp1ASr4"].cmd("./login_update_route_map_Tp1ASr4.sh localhost bgpd zebra &> ~/Tp1ASr4-route-map-update.log")
        net["Tp5ASr1"].cmd("./login_update_route_map_Tp5.sh localhost bgpd zebra &> ~/Tp5ASr1-route-map-update.log")

        fibFullPath = f'{fib_data_dir}/{args.date}-{str(args.expt_no)}'
        net["Tp1ASr1"].cmd("source /home/ubuntu/PAR-EMULATOR/bin/activate")
        net["Tp1ASr1"].cmd("/home/ubuntu/PAR-EMULATOR/bin/python /home/ubuntu/RouteMonitor.py -d {}  &> Tp1ASr1-Route-Monitor.log &".format(fibFullPath))

        net["gameServer"].cmd("python gameServer.py &> /dev/null &")
        time.sleep(260)
        start_time = time.time()
        print("%s: Started adding hosts" % (str(datetime.now())))


        client_names = [f"gCl{i}_{j}" for i in range(1, 31) for j in range(1, args.nhost + 1)]

        iat_list = generate_iat_list(200, len(client_names))
        random.shuffle(client_names)
        for idx, host_name in enumerate(client_names):
            exec_time = time.perf_counter()
            iat = iat_list[idx]
            net[host_name].cmd(f"python simpleGameClient.py  -n {host_name} -d 900 -c {cl_data_dir}/{args.date}-{str(args.expt_no)}/{host_name}.csv &> /dev/null &")
            print(f'Started game client on host {host_name} at {str(datetime.now())}')
            exec_delta = time.perf_counter() - exec_time
        
            if exec_delta < iat:
                exec_iat = iat - exec_delta
                print(f'Sleeping for {exec_iat} seconds')
                time.sleep(exec_iat)
            #print(f'Would have slept for {iat_list[idx]} seconds')
                
        print("%s: All hosts added" % (str(datetime.now())))
        time.sleep(150)
        fail_count = 0
        while (time.time() - start_time) < 860:
            if fail_count < 1:
                # Increase link delay on path A 
                print("Increasing link delay on path Tp2 to %sms at %s" %(tp2_delay+20.0,
                                                                          str(datetime.now())))
                net["Tp2ASr1"].cmd("/sbin/tc qdisc change dev Tp2ASr1-eth1 root netem delay {}ms".format(tp2_delay+20.0))
                net["Tp2ASr1"].cmd("/bin/echo `date '+%Y-%m-%d %H:%M:%S'` >> ~/Tp1ASr2-pref-change.log")
                time.sleep(70)
                fail_count += 1

            if fail_count < 2:
                # Restoring link delay on path A 
                print("Restoring link delay on path Tp2 to %sms at %s" %(tp2_delay, str(datetime.now())))
                net["Tp2ASr1"].cmd("/sbin/tc qdisc change dev Tp2ASr1-eth1 root netem delay {}ms".format(tp2_delay))
                net["Tp2ASr1"].cmd("/bin/echo `date '+%Y-%m-%d %H:%M:%S'` >> ~/Tp1ASr2-pref-change.log")
                time.sleep(70)
                fail_count += 1

            if fail_count < 3:
                # Increase link delay on path B & C
                print("Increasing link delay on paths Tp3 and Tp5 to %sms and %sms at %s" %(tp3_delay_f+25.0, tp5_delay+30.0, str(datetime.now())))
                net["Tp3ASr1"].cmd("/sbin/tc qdisc change dev Tp3ASr1-eth1 root netem delay {}ms".format(tp3_delay_f+25.0))
                net["Tp5ASr1"].cmd("/sbin/tc qdisc change dev Tp5ASr1-eth1 root netem delay {}ms".format(tp5_delay+30.0))
                net["Tp3ASr1"].cmd("/bin/echo `date '+%Y-%m-%d %H:%M:%S'` >> ~/Tp3ASr1-pref-change.log")
                net["Tp5ASr1"].cmd("/bin/echo `date '+%Y-%m-%d %H:%M:%S'` >> ~/Tp5ASr1-pref-change.log")
                time.sleep(70)
                fail_count += 1

            if fail_count < 4:
                # Increase link delay on path B & C
                print("Restoring link delay on paths Tp3 and Tp5 to %sms and %sms at %s" %(tp3_delay_f, tp5_delay, str(datetime.now())))
                net["Tp3ASr1"].cmd("/sbin/tc qdisc change dev Tp3ASr1-eth1 root netem delay {}ms".format(tp3_delay_f))
                net["Tp5ASr1"].cmd("/sbin/tc qdisc change dev Tp5ASr1-eth1 root netem delay {}ms".format(tp5_delay))
                net["Tp3ASr1"].cmd("/bin/echo `date '+%Y-%m-%d %H:%M:%S'` >> ~/Tp3ASr1-pref-change.log")
                net["Tp5ASr1"].cmd("/bin/echo `date '+%Y-%m-%d %H:%M:%S'` >> ~/Tp5ASr1-pref-change.log")
                time.sleep(70)
                fail_count += 1

        print("%s: End Experiment" % (str(datetime.now())))
    finally:
        net.stop()
