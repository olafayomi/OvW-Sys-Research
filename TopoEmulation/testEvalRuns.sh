#!/bin/bash
DATE=`date "+%Y%m%d"`

helpFunction()
{
  echo ""
  echo "Usage: $0 -s script -n num_run -b basedir -p hosts"
  echo -e "\t-s IPMininet topology script to run"
  echo -e "\t-n Number of times to run the IPMininet script for an experiment"
  echo -e "\t-b Base directory to store experiment data"
  echo -e "\t-p Number of hosts in each network"
  exit 1 # Exit script after printing help 
}

cleanup()
{
  echo "Clean ipmininet artefacts ...."
  /usr/bin/python -m ipmininet.clean
  echo "Done!!!"

  echo "Deleting config files in /tmp"
  rm -rf /tmp/resolv_*
  rm -rf /tmp/ospf*
  rm -rf /tmp/bgpd*
  rm -rf /tmp/hosts*
  rm -rf /tmp/exabgp*
  rm -rf /tmp/quagga*
  rm -rf /tmp/tmp*
  rm -rf /tmp/zebra_*
  echo "Done!!!, config files deleted"

  echo "Deleting sock files in /home/ubuntu"
  rm  -rf /home/ubuntu/bandwidth.sock
  rm  -rf /home/ubuntu/differentiated.sock
  rm  -rf /home/ubuntu/latency.sock
  rm  -rf /home/ubuntu/loss.sock
  rm  -rf /home/ubuntu/perf.sock
  rm  -rf /home/ubuntu/path1.sock
  rm  -rf /home/ubuntu/path2.sock
  rm  -rf /home/ubuntu/path3.sock
  echo "Done!!!, Sock files deleted"

  echo "Delete links"
  /sbin/ip link del dev as3sw1
  /sbin/ip link del dev s1
  /sbin/ip link del dev s2
  /sbin/ip link del dev s3
  /sbin/ip link del dev as6sw1
  /sbin/ip link del dev as6sw2
  /sbin/ip link del dev Sw1Tp1
  /sbin/ip link del dev Sw2Tp2
  /sbin/ip link del dev Sw2Tp3
  for i in {1..32}
  do
     /sbin/ip link del Sw1AS$i
  done

  echo "Done!!!, Links deleted"

  echo "Remove clients.txt"
  rm -rf /home/ubuntu/clients.txt
  echo "Done !!!, clients.txt deleted"
}

while getopts "s:n:b:p:" opt
do
   case "$opt" in 
      s ) script="$OPTARG" ;;
      n ) num_run="$OPTARG" ;;
      b ) base_dir="$OPTARG" ;;
      p ) hosts="$OPTARG" ;;
      ? ) helpFunction ;;
   esac
done

# Print helpFunction in case parameters are empty
if [ -z "$script" ] || [ -z "$num_run" ] || [ -z "$base_dir" ] || [ -z "$hosts" ]
then
   echo "Some or all of the parameters are empty";
   helpFunction
fi

re='^[0-9]+$' 
#re='^(?:[0-9]|[1-9][0-9]{1,2}|1000)$'

if ! [[ $hosts =~ $re ]] ; then 
   echo "ERROR: Number of hosts supplied is not a number"  >&2;  exit 1
fi


if ! [[ $num_run =~ $re ]] ; then 
   echo "ERROR: Number of run supplied is not a number"  >&2;  exit 1
fi

if [ ! -f "$script" ]; then
   echo "IPMininet script cannot be found!!!" >&2; exit 1
fi

for i in $(seq 1 $num_run); do
  echo -e "Experiment run $i on $DATE for $base_dir"
  client_dir="/home/ubuntu/gClient-control-logs/No-Overwatch/${base_dir}/${DATE}-${i}"
  if [ ! -d "$client_dir" ]; then
    mkdir -p "$client_dir"
    echo "Directory created: $client_dir"
  else
    echo "Directory already exists: $client_dir"
  fi

  dplane_dir="/home/ubuntu/BGP-FIB-Data/${base_dir}/${DATE}-${i}"
  if [ ! -d "$dplane_dir" ]; then
    mkdir -p "$dplane_dir"
    echo "Directory created: $dplane_dir"
  else
    echo "Directory already exists: $dplane_dir"
  fi

  /usr/bin/python $script -d $DATE -i $i -b $base_dir -n $hosts
  mv /home/ubuntu/Tp1ASr2-pref-change.log  $dplane_dir/
  mv /home/ubuntu/Tp3ASr1-pref-change.log  $dplane_dir/
  mv /home/ubuntu/Tp5ASr1-pref-change.log  $dplane_dir/
  cleanup
  source /home/ubuntu/PAR-EMULATOR/bin/activate
  /home/ubuntu/PAR-EMULATOR/bin/python process-multi-hosts.py -i $client_dir -p 90 -o ~/Ovw-Eval-Results/AS34410/Sensitivity-Analysis/BGP-Preference-Change/expt-summary-${base_dir}-$DATE-$i
  deactivate
  cleanup
  sleep 30
done
  #sleep 60

