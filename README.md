# OvW-Sys-Research

Source code for the BGP EPE controller and network emulation from the CoNEXT '26 paper
[Bring 'em on! Pragmatic Egress Routing for Interactive Multiplayer Games](<INSERT_DOI_OR_URL>).

Overwatch is a latency-aware routing control system that uses BGP Egress Peer Engineering
to steer game client traffic across multiple AS paths, switching paths when RTT exceeds
configurable thresholds — without changes to the Internet core.

---

## Repository structure

```
OvW-Sys-Research/
├── bgpcontroller/       # Overwatch controller, BGP peer logic, metrics, gRPC stubs
├── bgpspeaker/          # ExaBGP process scripts (sender.py, receiver.py)
├── ExperimentTools/     # Game emulation clients/server, log utilities, cleanup scripts
├── EvaluationTools/     # MRT data conversion tool
├── TopoEmulation/       # IPMininet topology scripts, config files, experiment runners
├── Measurement-Results/ # RIPE Atlas RTT measurements used for TC netem configuration
├── gRPC/                # Proto definitions and generated Python stubs
├── srv6-controller/     # SRv6 dataplane manager (see srv6-controller/README.md)
├── setup.py             # Builds Prefix and RouteEntry C extensions
└── requirements.txt
```

`bgpcontroller/multiprocessing36/` is a vendored copy of the Python 3.6 standard library
`multiprocessing` module included for compatibility. Do not install it separately.

For detailed design notes see `DOCUMENTATION.md`. For observation logs from experiments
see `OBSERVATIONS.md`.

---

## Installation

### System requirements

| Requirement | Minimum |
|-------------|---------|
| OS          | Ubuntu 18.04 |
| Memory      | 12 GB |
| CPU cores   | 8 |
| Python      | 3.6.9 |

### Dependencies

Install system dependencies for IPMininet (see https://ipmininet.readthedocs.io/en/latest/).

Install Python packages:

```bash
pip install -r requirements.txt
```

Key dependencies:

- **IPMininet** — https://ipmininet.readthedocs.io/en/latest/
- **ExaBGP** — https://github.com/Exa-Networks/exabgp

### Building Overwatch

```bash
cd OvW-Sys-Research/
python setup.py build
python setup.py install
```

This compiles two C extensions: `Prefix` and `RouteEntry`. After installation, copy the
generated `.so` files into `bgpcontroller/`:

```bash
cp ~/PAR-EMULATOR/lib64/python3.6/site-packages/Overwatch-1.0.0-py3.6-linux-x86_64.egg/Prefix.cpython-36m-x86_64-linux-gnu.so \
   ~/OvW-Sys-Research/bgpcontroller/

cp ~/PAR-EMULATOR/lib64/python3.6/site-packages/Overwatch-1.0.0-py3.6-linux-x86_64.egg/RouteEntry.cpython-36m-x86_64-linux-gnu.so \
   ~/OvW-Sys-Research/bgpcontroller/
```

The files are also available in `build/lib.linux-x86_64-3.6/` if you prefer to copy from
the build directory directly.

---

## Configuration

### ExaBGP

After installing ExaBGP, create its working directories:

```bash
mkdir -p ~/.exabgp/etc
mkdir -p ~/.exabgp/scripts
```

Copy the following into `~/.exabgp/etc/exabgp.env`:

```ini
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

Create named pipes for the ExaBGP CLI:

```bash
mkdir /home/ubuntu/run
mkfifo /home/ubuntu/run/exabgp.{in,out}
chmod 600 /home/ubuntu/run/exabgp.{in,out}
```

In some environments it is better to place the pipes in `/var/run`:

```bash
mkfifo /var/run/exabgp.{in,out}
chmod 666 /var/run/exabgp.{in,out}
```

Run ExaBGP:

```bash
env exabgp.daemon.daemonize=false exabgp ~/.exabgp/etc/exabgp.conf \
    --env ~/.exabgp/etc/exabgp.env
```

### Mako template for ExaBGP

Replace the default IPMininet ExaBGP Mako template with the one below so that IPMininet
generates the correct ExaBGP configuration for the Overwatch controller.

Back up the original first:

```bash
cp /usr/local/lib/python3.6/dist-packages/ipmininet/router/config/templates/exabgp.mako \
   /usr/local/lib/python3.6/dist-packages/ipmininet/router/config/templates/exabgp.mako-original
```

Template:

```mako
process announce-routes {
    run /home/ubuntu/PAR-EMULATOR/bin/python /OvW-Sys-Research/bgpspeaker/sender.py;
    encoder json;
}

process receive-routes {
    run /home/ubuntu/PAR-EMULATOR/bin/python /OvW-Sys-Research/bgpspeaker/receiver.py;
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

### SRv6 support

Enable SRv6 on the host running IPMininet and Overwatch:

```bash
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

---

## Measurement analysis pipeline

The topology TC delay parameters are derived from RIPE Atlas RTT measurements using
the following pipeline. All scripts are in the project root or `ExperimentTools/`.

### Step 1 — Proximity group identification

`game-server-probe-analysis.py` clusters RIPE Atlas probes by AS, country, and geographic
proximity (50 km radius) and identifies groups with path diversity to three game server
targets (Blizzard AS57976, Ubisoft AS49544, Valve AS32590). Outputs:

- `diverse_path_groups.csv` — one row per proximity group
- `probe_details.csv` — one row per probe with RTT and path data

### Step 2 — Per-group RTT characterisation

`probe-group-analyzer-updated2.py` and `analyze_neighbor_probes.py` analyse the RTT
measurements for each proximity group, identify the best, median, and worst probes on
each AS path, and produce `detailed_results.json`.

### Step 3 — RTT distribution and stability analysis

`rtt_distribution_analyser_with_correlation.py` fits statistical distributions to each
path's RTT time series, detects multi-modal behaviour, and generates:

- `distribution_analysis_results.json`
- `enhanced_tc_distribution_config.json` — TC netem commands per path, including
  multi-modal switching schedules

### Step 4 — Topology config generation

`as_json_config_gen.py` (with classification variant `as_json_config_gen_with_classification.py`)
combines the above outputs to produce `as_topology_config_with_variation.json`, which both
topology scripts consume at runtime.

---

## Running experiments

All topology scripts and experiment runners live in `TopoEmulation/`. The topology scripts
load `as_topology_config_with_variation.json` and `enhanced_tc_distribution_config.json`
to configure TC netem delays on each link.

```bash
cd TopoEmulation/
```

### Without Overwatch (baseline)

The baseline topology uses Pareto-distributed TC netem delays derived from real
measurements. The multimode variant adds scheduled mode switches during the experiment
to emulate real path variability.

```bash
# Standard variation baseline
./testEvalRuns.sh -s GameServerTopo-Custom-With-Variation-Updated.py \
    -n 5 -b <base-results-dir> -p 10

# Multi-modal baseline (path switching during experiment)
./testEvalRuns.sh -s GameServerTopo-Custom-With-Multimode.py \
    -n 5 -b <base-results-dir> -p 10
```

### With Overwatch

`-r` sets the routing period (seconds), `-m` sets the measurement period (seconds).
Use only measurement period values that divide evenly into the routing period to avoid
phase misalignment (e.g., MP ∈ {1, 2, 5, 10} s for RP ∈ {10, 20, 30, 40, 50} s).

```bash
./eval_experiment_runs_scale.sh \
    -s EvalTopoWithOvWRunInGS-CUSTOM-ASES-WITH-VARIATION.py \
    -n 5 -b <base-results-dir> -r 20 -m 1 -p 10
```

The `-n` parameter maps each run number to a timer offset (2 s steps) to sweep
phase alignment across runs. For a full phase sweep with RP=40 s, use `-n 22`.

### Configuration files

Modify these files in `TopoEmulation/` before running:

- `as_topology_config_with_variation.json` — AS topology, path delays, multi-modal
  switching parameters, and AS group mapping to real-world AS groups and targets
- `enhanced_tc_distribution_config.json` — TC netem commands per path
- `config-Tp1AS.yaml` / `config-Tp1AS-Three.yaml` — BGP topology configuration
- `internal-Tp1AS.csv` — internal AS peer table
- `topology-eval.csv` / `topology-eval-three.csv` — client topology mapping

Create or modify the output directories that the scripts write results to before running.

### Cleanup

After experiments, clean up Mininet state:

```bash
cd ExperimentTools/
./ipmininetcleanup.sh
```

Dump Mininet namespace state for debugging:

```bash
./mininet_namespaces_dump.sh
```

---

## ExperimentTools

`ExperimentTools/` contains the game traffic emulation and log processing scripts.

| Script | Purpose |
|--------|---------|
| `GameEmulation/gameClientP1.py`, `gameClientP2.py` | Game client emulators for path 1 and path 2 |
| `GameEmulation/gameMsmOrchestrator.py` | Orchestrates multi-path game measurement sessions |
| `GameEmulation/gameMsmOrchestrator-Three.py` | Three-path variant of the orchestrator |
| `GameEmulation/gameMsmPath1/2/3.py` | Per-path measurement processes |
| `GameEmulation/gameServer.py` | Game server emulator |
| `GameEmulation/simpleGameClient.py` | Lightweight client for quick tests |
| `decode-logs.py` | Decodes binary experiment logs |
| `log-to-csv.py` | Converts decoded logs to CSV |
| `readlogdev.py` | Reads log files during development |
| `experiment_runs.sh` | Wrapper for running experiment batches |
| `upload.py` | Uploads results to remote storage |

---

## EvaluationTools

`EvaluationTools/mrt2json.py` converts MRT-format routing table dumps to JSON for
path analysis.

---

## Measurement-Results

`Measurement-Results/` contains RIPE Atlas RTT measurements used to derive the
TC netem delay distributions for network emulation.

Results are organised by source AS and game server target (Blizzard, Ubisoft, Valve).
Each subdirectory contains:

- One or more RIPE Atlas measurement JSON files
- Per-probe RTT CSVs (one file per probe per AS path)
- Combined RTT CSVs aggregated across probes per AS path

These measurements informed the TC netem Pareto distribution parameters in the
IPMininet topologies.

---

## gRPC

`gRPC/proto/` contains Protocol Buffer definitions for:

- `gobgpapi/` — gobgp, ExaBGP API, attribute, and capability messages
- `SRv6/` — SRv6 explicit path messages
- `messages.proto`, `perfmon.proto` — controller messaging and performance monitoring

Generated Python stubs are in `gRPC/python_grpc/`. The copies in `bgpcontroller/` and
`bgpspeaker/` are the ones used at runtime.

---

## SRv6 controller

`srv6-controller/` is the SRv6 dataplane manager, supporting gRPC, NETCONF, REST,
and SSH southbound interfaces. See `srv6-controller/README.md` for details.

---

## Citation

If you use this code, please cite:

```
@inproceedings{overwatch-conext24,
  title     = {Bring 'em on! Pragmatic Egress Routing for Interactive Multiplayer Games},
  booktitle = {Proceedings of CoNEXT '26},
  year      = {2026}
}
```

_Update the BibTeX entry with the full author list, pages, and DOI once available._
