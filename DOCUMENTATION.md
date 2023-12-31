# DOCUMENTATION #

This file documents the commands and configurations required to use different
tools for my research and emulating PAR with overwatch in IPMininet or GNS3. 



## Exabgp
After installing exabgp with pip, create a directory in the home directory 
of the user where you will be running exabgp
```
mdkir -p ~/.exabgp/etc
mkdir -p ~/.exabgp/scripts
```
Copy the config below into ~/.exabgp/etc/exabgp.env
```

[exabgp.api]
ack = true
chunk = 1
cli = true
compact = false
encoder = json
pipename = 'exabgp'
respawn = true
terminate = false

[exabgp.bgp]
openwait = 60

[exabgp.cache]
attributes = true
nexthops = true

[exabgp.daemon]
daemonize = false
drop = true
pid = ''
umask = '0o137'
user = 'nobody'

[exabgp.log]
all = true 
configuration = true
daemon = true
destination = 'stdout'
enable = true
level = INFO
message = true
network = true
packets = false
parser = true
processes = true
reactor = true
rib = false
routes = true
short = false
timers = false

[exabgp.pdb]
enable = false

[exabgp.profile]
enable = false
file = ''

[exabgp.reactor]
speed = 1.0

[exabgp.tcp]
acl = false
bind = ''
delay = 0
once = false
port = 179
```
Create named pipes for exabgp cli 

```
mkdir /home/ubuntu/run
mkfifo /home/ubuntu/run/exabgp.{in,out}
chmod 600 /home/ubuntu/run/exabgp.{in,out}
```
In some cases it might be better to create the named pipes in /var/run
```
mkfifo /var/run/exabgp.{in,out}
chmod 666 /var/run/exabgp.{in,out}
```
to run exabgp with configs

```
env exabgp.daemon.deamonize=false exabgp ~/.exabgp/etc/exabgp.conf --env ~/.exabgp/etc/exabgp.env
```

#### Mako template for exabgp daemon.
I replaced the default exabgp Mako template with a template that enables IPMininet to
generate the right exabgp configs for the controller based on the topology. This way,
I didn't have to change IPMininet code that much.
See template below:
```
process announce-routes {
    run /home/ubuntu/PAR-EMULATOR/bin/python /home/ubuntu/git-repos/overwatch/bgpspeaker/sender.py;
    encoder json;
}

process receive-routes { 
    run /home/ubuntu/PAR-EMULATOR/bin/python /home/ubuntu/git-repos/overwatch/bgpspeaker/receiver.py;
    encoder json;
}

template {
    neighbor edge_peers {
       capability {
          graceful-restart 120;
          add-path send/receive;
          route-refresh;
       }
       api send {
          processes [announce-routes];
       }
       api receive {
          processes [receive-routes];
          neighbor-changes;
          receive {
             notification;
             open;
             refresh;
             operational;
             keepalive;
             update;
             parsed;
          }
       }
    }
}

%for n in node.exabgp.neighbors:

neighbor ${n.peer} {
    inherit edge_peers;
    description ${n.description};
    router-id ${node.exabgp.routerid};
    local-address ${n.local_addr};
    local-as ${node.exabgp.asn};
    peer-as ${n.asn};
    listen ${node.exabgp.port};
    connect ${n.port};

    %if node.exabgp.passive:
    passive;
    %endif

    family {
    %for af in node.exabgp.address_families:
        %if n.family == af.name :
        ${af.name} unicast;
        %endif
    %endfor
    }
}
%endfor
```
to use this template instead of the default exabgp template shipped with IPMininet, do
* Backup the original/default exabgp template
```
cp /usr/local/lib/python3.6/dist-packages/ipmininet/router/config/templates/exabgp.mako > /usr/local/lib/python3.6/dist-packages/ipmininet/router/config/templates/exabgp.mako-original
```
* Replace the exabgp template with the one above.

## FRR BGPD configs

* Until I fix the code, overwatch includes the ASN of the transit AS in the BGP updates it sends to other BGP routers in the AS. As a result, those routers reject those updates so as a workaround, the routers have an ```allowas-in``` config included in their to enable them accept and receive routes from overwatch. The ```bgpd.mako``` template in IPMininet has been modified to add the ```allowas-in``` command, see section below(This is only necessary if we're using the ```AS prepend OUT filter``` export in the tables or peers, I have disabled it):

```
% for af in node.bgpd.address_families:
    address-family ${af.name}
    % for rm in node.bgpd.route_maps:
        % if rm.family == af.name:
        neighbor ${rm.neighbor.peer} route-map ${rm.name} ${rm.direction}
        % endif
    % endfor
    % for net in af.networks:
        network ${net.with_prefixlen}
    % endfor
    % for r in af.redistribute:
        redistribute ${r}
    % endfor
    % for n in af.neighbors:
        % if n.family == af.name:
        neighbor ${n.peer} activate
            % if n.nh_self:
        neighbor ${n.peer} ${n.nh_self}
            % endif
            % if node.bgpd.rr and n.asn == node.bgpd.asn:
        neighbor ${n.peer} route-reflector-client
            % endif
	neighbor ${n.peer} allowas-in 1
        % endif
    % endfor
    % if node.bgpd.rr:
    bgp cluster-id ${node.bgpd.routerid}
    % endif
    exit-address-family
    !
% endfor
```

## Overwatch
### We're using Cpython bytecode with overwatch.
To install and generate the cpython bytecode, cd into the overwatch directory
```
cd ~/git-repos/overwatch
```
Install overwatch in the python virtualenv with
```
source  PAR-EMULATOR/bin/activate
python setup.py build
python setup.py install
```
Copy ```Prefix.cpython-36m-x86_64-linux-gnu.so``` and ```RouteEntry.cpython-36m-x86_64-linux-gnu.so``` from the lib directory of the virtualenv to the bgpcontroller directory of the overwatch code 
```
cp ~/PAR-EMULATOR/lib64/python3.6/site-packages/Overwatch-1.0.0-py3.6-linux-x86_64.egg/Prefix.cpython-36m-x86_64-linux-gnu.so  ~/git-repos/overwatch/bgpcontroller

cp ~/PAR-EMULATOR/lib64/python3.6/site-packages/Overwatch-1.0.0-py3.6-linux-x86_64.egg/RouteEntry.cpython-36m-x86_64-linux-gnu.so ~/git-repos/overwatch/bgpcontroller 
```

### Other modules and packages needed
pip install mako (to generate special exabgp config for our controller).

## Running experiments
### iperf commands
* On server
```
iperf3 -p 465 -s -6
```

* On client 
```
iperf3 -6 -c  2001:4521::2 -p 465 -b 1000M -t 20 -M 1280
```

* Manually add SRv6 segment routes to test
```
ip -6 route add 2001:4521::/48 encap seg6 mode encap segs 2001:df40::9,2001:df34::4,2001:df31::3,2001:df23::32 dev as3r2-eth1 metric 10
```

### Setting networks and nodes with IPMininet

* On ingress nodes/routers in the transit AS doing PAR, there needs to be a separate routing table that will be used for performance-aware traffic. A separate ```par.out``` routing table is created for PAR routes. This can be done on the ingress nodes with ipmininet ```cmd``` function in the scripts as below or manually applying the commands to the ingress node from the xterm terminal:

```
net["as3r2"].cmd("grep  -qxF '201 par.out' /etc/iproute2/rt_tables || echo '201 par.out' >> /etc/iproute2/rt_tables")
```

* After the routing table is created, the next thing that should be done is to add an IP rule to steer traffic into that routing table on the ingress nodes. This can also be done with ipmininet ```cmd``` function  or the manually applying the commands:

```
net["as3r2"].cmd("ip -6 rule add fwmark 2 table par.out")
```

* Ensure that SRv6 is enabled  on the host machine running IPMininet in the various network namespaces for the hosts by setting these kernel parameters:

```
sysctl -w net.ipv6.conf.all.seg6_require_hmac=-1
sysctl -w net.ipv6.conf.all.seg6_enabled=1
sysctl -w net.ipv6.conf.default.seg6_enabled=1
sysctl -w net.ipv6.conf.default.seg6_require_hmac=-1
sysctl -w net.ipv6.conf.eth0.seg6_require_hmac=-1
sysctl -w net.ipv6.conf.eth0.seg6_enabled=1
sysctl -w net.ipv6.conf.eth1.seg6_require_hmac=-1
sysctl -w net.ipv6.conf.eth1.seg6_enabled=1
sysctl -w net.ipv6.conf.eth2.seg6_enabled=1
sysctl -w net.ipv6.conf.eth2.seg6_require_hmac=-1
```

* IP tables rules to steer packet into SRv6 route. See good explanation of iptables in case of next time,[iptables explanation](https://danielmiessler.com/study/iptables/)

```
ip6tables -t mangle -A PREROUTING -i as3r2-eth0 -p tcp  --dport 465 -j MARK --set-mark 2
```
Apply ip6tables rules to the inbound interface on the ingress router to mark packets with
a particular destination port so that it can be steered. then create a separate rule

* Flushing IP tables rules

```
ip6tables -t mangle -F
```

* Show packets and byte counts for IP tables rules

```
ip6tables -t mangle -n -v -L
```

* Command to generate python bindings from proto files

```
python -m grpc\_tools.protoc --proto\_path=. --python\_out=../../python\_grpc/ --grpc_python_out=../../python_grpc/ \*.proto
```

* Dump BGP RIB for evaluation. Add this to  frr config

```
dump bgp routes-mrt dump-%Y-%m-%dT%H:%M:%S 120
```

* Python script to process MRT dump to analyse the RIB of routers

```
 python mrt2json.py -P 2001:df8:: -O test.csv -I dump-as6r1\*
```

* command to add constant delay to egress scheduler for an interface

```
tc qdisc add dev as4r1-eth2 root netem delay 0.200ms
```

* Install owamp on server to perform one way latency measurements. Download from git repo https://github.com/perfsonar/owamp
```
 git clone https://github.com/perfsonar/owamp.git
 cd owamp 
 # Change directory again into owamp sub-directory in the owamp repo
 cd owamp
 git submodule update --init 
 ./bootstrap
 ./configure
 make
```

* Owamp configuration files 
```
# owamp-server.conf file
authmode 0
vardir /home/ubuntu/git-repos/owamp/owampd
testports 8760-9960
diskfudge 3.0

```
```
# owamp-server.limit-bak file
limit root with disk=0,\
                bandwidth=0,\
                delete_on_fetch=on

limit open with parent=root, \
                bandwidth=900m, \
                disk=2g, \
                allow_open_mode=on

assign default regular
```

* Starting owampd on one server. command that has worked

```
./owampd -v -f -a O
```

* Starting owping on another server

```
./owping fc00:0:15::1 
```

* Debug python code with gdb

```
gdb python <pid of running process> 

```

* Using D-ITG to measure latency and metrics between AS2R1 and AS6H1

```
# On Sender AS2R1
./tools/D-ITG-2.8.1-r1023/bin/ITGSend -T TCP -a 2001:4521::2 -c 100 -C 10 -t 15000 -rp 465 -l send_log_file -x recv_log_file &> /dev/null & 

# On receiver 
./tools/D-ITG-2.8.1-r1023/bin/ITGRecv -l recv_log_file  
```

* Remove old version of ovs
```
apt-get remove  openvswitch-testcontroller openvswitch-common openvswitch-pki openswitch-switch
```

* Exporting CSV to Google sheets using python. [link](https://medium.com/craftsmenltd/from-csv-to-google-sheet-using-python-ef097cb014f9) 

* Use library called ```gspread``` with pip in your virtual env. 

* Go to google developers console and enable the Google drive and google sheet APIs. [link](https://console.developers.google.com) 

* Create Credentials

* Download credentials in json file.

* Create new spreadsheet and share the spreadsheet with edit permission with the ```client_email``` in the credentials file.

* Run scripts to upload CSV files to google spreadsheet.

* Connect to vtysh
```
telnet localhost bgpd
telnet localhost ospf6d
```

* Ways to add loss and delay with tc and netem to an interface at the same time

```
tc qdisc change dev s3-eth2 root netem delay 30ms loss 5% 
# Or this approach

tc qdisc add dev eth0 root
tc qdisc add dev eth0 root handle 1: netem delay 30ms
tc qdisc add dev eth0 root handle 2: netem loss 5%
```

* Show tc and netem statistics on an interfae 
```
tc -s qdisc show dev s1-eth2
```

* Delete qdisc on interface with tc

```
tc qdisc del dev as4r2-eth2 root
```

* Add or change HTB bandwidth on interface

```
tc qdisc add dev as4r2-eth2 root handle 5:1 htb default 1
tc class add dev as4r2-eth2 parent 5:1 classid 5:1 htb rate 500Mbit ceil 500Mbit burst 15250b cburst 1500b
tc class change dev as4r2-eth2 parent 5:1 classid 5:1 htb rate 500Mbit ceil 500Mbit burst 15250b cburst 1500b
```

* Add or change TBF bandwidth on interface 

```
tc qdisc change dev as4r1-eth2 root tbf 150mbit burst 50mbit limit 2000
```
