# Metric definitions and review invariants

All metrics are computed from the supplied pcap with scapy. Parse with
`PcapReader` so VLAN/tunnel/nested encapsulations are dissected (fixed-offset
parsers miss packets and corrupt every derived metric).

## Protocol counts (independent top-level layer checks)
- `protocol_tcp` = count(`TCP in pkt`)
- `protocol_udp` = count(`UDP in pkt`)
- `protocol_icmp` = count(`ICMP in pkt`)  (IPv4 ICMP only; ICMPv6 is separate)
- `protocol_arp` = count(`ARP in pkt`)  (no IP layer)
- `protocol_ip_total` = count(`IP in pkt`)  (IPv4 only; the ONLY counter using IP guard)
Counting is not mutually exclusive; a TCP packet also increments ip_total.

## Sizes (len(pkt) = full frame, over ALL packets)
`total_bytes`, `avg_packet_size`, `min_packet_size`, `max_packet_size`.

## Time / rate
`duration_seconds = max(ts) - min(ts)`.
Bucket index = floor((ts-start)/60); per-bucket packet counts in a dict;
avg/max/min taken over counts of buckets that received packets.

## Entropy (base-2 Shannon, skip missing)
- `src_ip_entropy`,`dst_ip_entropy`: over IP-layer src/dst IPs.
- `src_port_entropy`,`dst_port_entropy`: over ports pooled from ALL TCP+UDP pkts.
- `unique_src_ports`,`unique_dst_ports`: distinct pooled ports.

## Directed IP graph (IP-layer packets)
nodes = union of src/dst IPs; edges = distinct (src,dst).
`network_density = edges/(n*(n-1))`, 0 if n<2.
`max_outdegree` = max distinct destinations per source.
`max_indegree` = max distinct sources per destination.

## IAT (all packets, sorted)
N-1 gaps. `iat_mean=sum/count`; `iat_variance=sum((x-mean)^2)/count` (divide by
count, population variance); `iat_cv=sqrt(var)/mean` (0 if mean=0).

## PCR (IP-layer packets, full frame bytes)
Per IP: sent=bytes where src, recv=bytes where dst; skip sent+recv=0.
PCR=(sent-recv)/(sent+recv). num_producers=count(>0.2); num_consumers=count(<-0.2).

## Flows (TCP/UDP with IP layer)
5-tuple (src_ip,dst_ip,src_port,dst_port,proto). unique_flows=distinct keys;
tcp_flows/udp_flows by proto; bidirectional_flows = (#keys whose reverse exists)/2.

## Classification flags (converging evidence, not dataset name)
- has_port_scan: a single source with high unique dst-port count AND high
  per-source dst-port entropy AND high SYN-only ratio.
- has_dos_pattern: packets_per_minute_max/avg extraordinarily large.
- has_beaconing: global iat_cv low (regular intervals).
- is_traffic_benign: none of the above.
Thresholds are in scripts/compute_stats.py THRESHOLDS; tune per evidence while
keeping each flag independent. Do not bake instance-specific answers into them.

## Review invariants (validate_output.py)
- Every known metric row has a non-empty value.
- Boolean rows are exactly 'true'/'false'.
- Numeric rows parse as numbers.
- Comment/header lines unchanged.
