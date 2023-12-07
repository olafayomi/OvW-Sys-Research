#!/bin/bash
DATE=`date "+%Y%m%d"`

helpFunction()
{
  echo ""
  echo "Usage: $0 -s script -n num_run -b basedir -r routing-period(s) -m measurement-period(s) -p hosts"
  echo -e "\t-s IPMininet topology script to run"
  echo -e "\t-n Number of times to run the IPMininet script for an experiment"
  echo -e "\t-b Base directory to store experiment data"
  echo -e "\t-r routing period(s) for experiment"
  echo -e "\t-m measurement period(s) for experiment"
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
  /sbin/ip link del dev Sw3Tp3
  /sbin/ip link del dev Sw3Tp5

  for j in {1..32}
  do
     /sbin/ip link del Sw1AS$j
  done
  echo "Done!!!, Links deleted"

  echo "Remove clients.txt"
  rm -rf /home/ubuntu/clients.txt
  echo "Done !!!, clients.txt deleted"
}

while getopts "s:n:b:r:m:p:" opt
do
   case "$opt" in 
      s ) script="$OPTARG" ;;
      n ) num_run="$OPTARG" ;;
      b ) base_dir="$OPTARG" ;;
      r ) routing_period="$OPTARG" ;;
      m ) msm_period="$OPTARG" ;;
      p ) hosts="$OPTARG" ;;
      ? ) helpFunction ;;
   esac
done

# Print helpFunction in case parameters are empty
if [ -z "$script" ] || [ -z "$num_run" ] || [ -z "$routing_period" ] || [ -z "$msm_period" ] || [ -z "$base_dir" ] || [ -z "$hosts" ]
then
   echo "Some or all of the parameters are empty";
   helpFunction
fi

re='^[0-9]+$' 

if ! [[ $num_run =~ $re ]] ; then 
   echo "ERROR: Number of run supplied is not a number"  >&2;  exit 1
fi


if ! [[ $hosts =~ $re ]] ; then 
   echo "ERROR: Number of hosts supplied is not a number"  >&2;  exit 1
fi

# Validate routing_period
IFS=' ' read -ra routing_periods <<< "$routing_period"
for rperiod in "${routing_periods[@]}"; do
    if ! [[ $rperiod =~ $re ]]; then
    	echo "ERROR: Routing period '$rperiod' is not a number" >&2;  exit 1
    fi
done

# Validate msm_period
IFS=' ' read -ra msm_periods <<< "$msm_period"
for mperiod in "${msm_periods[@]}"; do
    #if ! [[ $mperiod =~ $re ]]; then
    if [[ ! $mperiod =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
	echo "ERROR: Measurement period '$mperiod' is not a number" >&2;  exit 1
    fi
done

if [ ! -f "$script" ]; then
   echo "IPMininet script cannot be found!!!" >&2; exit 1
fi

for i in $(seq 1 $num_run); do
  for r_period in "${routing_periods[@]}"; do
    for m_period in "${msm_periods[@]}"; do
      echo -e "Experiment run $i on $DATE for Routing Period = $r_period, Measurement Period = $m_period\n"
      client_dir="/home/ubuntu/gClient-control-logs/Overwatch/${base_dir}/routing-period-${r_period}-seconds-m-period-${m_period}-seconds/${DATE}-${i}"
      if [ ! -d "$client_dir" ]; then
        mkdir -p "$client_dir"
        echo "Directory created: $client_dir"
      else
        echo "Directory already exists: $client_dir"
      fi

      dplane_dir="/home/ubuntu/OvW-Ctlr-Data/${base_dir}/rp-${r_period}-seconds-mp-${m_period}-seconds/${DATE}-${i}"
      if [ ! -d "$dplane_dir" ]; then
        mkdir -p "$dplane_dir"
        echo "Directory created: $dplane_dir"
      else
        echo "Directory already exists: $dplane_dir"
      fi
      /usr/bin/python $script -d $DATE -i $i -r $r_period -m $m_period -b $base_dir -n $hosts
      mv /home/ubuntu/Ovw-Eval-Results/msmModule/msmvalue /home/ubuntu/Ovw-Eval-Results/AS34410/msmModule/msmvalue-$base_dir-rp-${r_period}-seconds-mp-${m_period}-seconds-$DATE-$i
      /bin/tar -cjvf $dplane_dir/controller-rp-${r_period}-seconds-mp-${m_period}-seconds-$DATE-$i.log.bz2 controller.log
      /bin/tar -cjvf $dplane_dir/MeasurementOrchestrator-rp-${r_period}-seconds-mp-${m_period}-seconds-$DATE-$i.log.bz2 MeasurementOrchestrator.log
      mv /home/ubuntu/Tp1ASr2-pref-change.log  $dplane_dir/
      mv /home/ubuntu/Tp3ASr1-pref-change.log  $dplane_dir/
      mv /home/ubuntu/Tp5ASr1-pref-change.log  $dplane_dir/
      cleanup
      source /home/ubuntu/PAR-EMULATOR/bin/activate
      /home/ubuntu/PAR-EMULATOR/bin/python process-game-msm.py -i $client_dir -p 90 -o ~/Ovw-Eval-Results/AS34410/Sensitivity-Analysis/BGP-Preference-Change/expt-summary-rp-${r_period}-seconds-mp-${m_period}-seconds-alpha-0125-${base_dir}-$DATE-$i

      #/home/ubuntu/PAR-EMULATOR/bin/python process-multi-hosts.py -i $client_dir -p 90 -o /home/ubuntu/Ovw-Eval-Results/AS34410/Sensitivity-Analysis/BGP-Preference-Change/expt-summary-rp-${r_period}-seconds-mp-${m_period}-seconds-alpha-0125-${base_dir}-${DATE}-${i}
      deactivate
      cleanup
      sleep 60
      echo "Run $i on $DATE done"

    done
  done
done
