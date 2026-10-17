#!/bin/sh
# iperf3 server in the background, snmpd in the foreground (container lifetime).
iperf3 -s -D
exec snmpd -f -Lo -C -c /etc/snmp/snmpd.conf
