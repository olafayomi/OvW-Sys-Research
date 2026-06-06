#!/bin/bash
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
rm  -rf /home/ubuntu/path4.sock
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

for i in {1..60}
do
   /sbin/ip link del Sw1AS$i
   /sbin/ip link del Sw2AS$i
   /sbin/ip link del Sw3AS$i
   /sbin/ip link del Sw4AS$i
done
echo "Done!!!, Links deleted"

echo "Remove clients.txt"
rm -rf /home/ubuntu/clients.txt
echo "Done !!!, clients.txt deleted"
