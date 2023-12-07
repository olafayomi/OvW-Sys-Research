# OvW-Sys-Research

This repo contains the source code for the BGP EPE controller and emulation discussed
in CoNEXT'24 paper [Bring 'em on! Pragmatic Egress Routing for Interactive Multiplayer Games](www.add_later).
Overwatch is a pragmatic latency-aware routing control approach which uses explicit routing to attain feasible
latency for interactive multiplayer game players without changes to the Internet core. \

The evaluation of the  system was done in IPmininet and this repo  contains the scripts used to run the topologies
that Overwatch was evaluated with.

## Installation

This section details the packages, tools and the versions required to install and operate Overwatch.

### System Requirements
- OS: Minimum Ubuntu 18.04
- Memory: Minimum 12GB
- CPU: 8

### Required packages and tools
Install these packages.
- Python version: 3.6.9
- IPMininet: https://ipmininet.readthedocs.io/en/latest/
- ExaBGP:  https://github.com/Exa-Networks/exabgp
- Required Python packages:

Install the python libraries in requirements.txt
```
pip install -r requirements.txt
```

Installing Overwatch
---------------------
- Clone the repo
- cd into the repo directory 
```
cd Ovw-Sys-Research/
```
- Install Overwatch

```
python setup.py build
python setup.py install
```
- This will generate some Cpython bytecode, copy it to the bgpcontroller directory where Overwatch will be running
- Copy ```Prefix.cpython-36m-x86_64-linux-gnu.so``` and ```RouteEntry.cpython-36m-x86_64-linux-gnu.so``` from the lib directory of the virtualenv to the bgpcontroller directory of the overwatch code 
```
cp ~/PAR-EMULATOR/lib64/python3.6/site-packages/Overwatch-1.0.0-py3.6-linux-x86_64.egg/Prefix.cpython-36m-x86_64-linux-gnu.so  ~/OvW-Sys-Research/bgpcontroller

cp ~/PAR-EMULATOR/lib64/python3.6/site-packages/Overwatch-1.0.0-py3.6-linux-x86_64.egg/RouteEntry.cpython-36m-x86_64-linux-gnu.so ~/OvW-Sys-Research/bgpcontroller 
```

### Configuration
#### Exabgp
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
We replaced the default exabgp Mako template with a template that enables IPMininet to
generate the right exabgp configs for the controller based on the topology.
See template below:
```
process announce-routes {
    run /home/ubuntu/PAR-EMULATOR/bin/python /OvW-Sys-Research/bgpspeaker/sender.py;
    encoder json;
}

process receive-routes { 
    run /home/ubuntu/PAR-EMULATOR/bin/python /OvW-Sys-Research/receiver.py;
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

#### Enable SRv6 Support on system running IPMininet and OvW
* Run these commands

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

### Running Overwatch in a Topology
* Use the bash scripts in ```TopoEmulation``` directory to run the IPMininet topology scripts with and without overwatch.
* To run the topologies without Overwatch
```
./testEvalRuns.sh -s GameServerTopo-Wide-Range-BGP-Pref-SCALE.py -n 5 -b BGP-Preference-Change-30ms -p 10
./testEvalRuns.sh -s GameServerTopoThree-SPLIT-CONFIG-SCALE.py -n 5 -b Three-PATHS-SCALED-300-CLIENTS -p 10
```
* To run the topologies with Overwatch
```
./eval_experiment_runs_scale.sh -s EvalTopoWithOvWInGS-THREE-PATHS-SPLIT-CONFIG-SCALE.py -n 1 -b TEST-SCALE -r 20 -m 1 -p 10
./eval_experiment_runs_scale.sh -s EvalTopoWithOvWInGS-Wide-Range-SPLIT-CONFIG-SCALE.py -n 5 -b SPLIT-CLIENTS-ODDS-TP2 -r 20 -m 1 -p 10
./eval_experiment_runs_scale.sh -s EvalTopoWithOvWInGS-Wide-Range-BGP-Pref-SCALE.py -n 5 -b BGP-Preference-Change-30ms -r 20 -m 1 -p 10
```

* Modify the ```config-Tp1*.yaml```, ```internal-Tp1AS.csv``` and ```topology-eval.csv``` files in the config directory as necessary
* Create and modify directories where the results will be written to as necessary.

