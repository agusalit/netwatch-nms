# One image, three nodes: each runs a real net-snmp agent and an iperf3 server,
# so NetWatch polls genuine IF-MIB counters and traffic between nodes is real.
FROM ubuntu:24.04

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        snmpd iperf3 iproute2 iputils-ping \
 && rm -rf /var/lib/apt/lists/*

COPY snmpd.conf /etc/snmp/snmpd.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
