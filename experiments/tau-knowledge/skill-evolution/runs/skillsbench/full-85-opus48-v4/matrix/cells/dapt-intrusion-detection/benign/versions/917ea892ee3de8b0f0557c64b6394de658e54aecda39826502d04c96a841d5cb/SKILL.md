---
name: pcap-network-stats
description: >
  Compute network-traffic statistics and intrusion-detection flags from a PCAP
  capture and fill the `value` column of a provided CSV template (e.g. the
  DAPT2020 intrusion-detection task). Use this Skill whenever you are given a
  .pcap file plus a network_stats CSV template and must produce protocol counts,
  rate/time stats, size stats, Shannon entropies, directed-IP-graph metrics,
  inter-arrival-time stats, producer/consumer ratios, 5-tuple flow counts, and
  boolean traffic-classification flags.
---

# PCAP Network Statistics & Intrusion-Detection Flags

## When to use

The public task gives:
- a packet capture (default `/root/packets.pcap`), and
- a CSV template (default `/root/network_stats.csv`) whose non-comment rows name
  one metric each and have an empty `value` column.

You must fill **only** the `value` column, leaving comment lines (`#...`) and any
header/blank lines unchanged. This Skill parses the pcap with **scapy** and
computes every metric using the exact definitions below, then rewrites the CSV
in place.

## Method (exact definitions — follow precisely)

Parse the pcap with scapy (`PcapReader`) so VLAN tags / tunnels / nested
encapsulations are dissected correctly. Fixed-offset parsers miss such packets.

**Protocol counts** — use *independent* top-level layer checks:
`TCP in pkt`, `UDP in pkt`, `ICMP in pkt`, `ARP in pkt`. Do **not** nest the
transport checks inside an `IP in pkt` guard. `protocol_ip_total` is the only
counter that uses `IP in pkt` (IPv4 only; IPv6/ARP are not IPv4). A packet may
match several counters (counting is not mutually exclusive).

**Packet length** = `len(pkt)` (full captured frame). Size stats
(`total_bytes`, `avg_packet_size`, `min_packet_size`, `max_packet_size`) and PCR
byte sums use this full frame length over **all** packets.

**Time / rate** — `duration_seconds = max(ts) - min(ts)`. Bucket each packet by
`floor((ts - start)/60)`; accumulate per-bucket counts in a dict; compute
avg/max/min over the counts of buckets that actually received packets.

**Shannon entropy** (base 2): `H = -sum(p*log2(p))` over observed values with
`p>0`. IP entropies use src/dst IPs of **IP-layer** packets. Port entropies use
src/dst ports pooled over **all TCP and UDP** packets together. `unique_src_ports`
/`unique_dst_ports` are the counts of distinct ports in those pooled counters.

**Directed IP graph** — nodes = every IP seen as src or dst in IP packets;
edges = distinct `(src,dst)` pairs. `network_density = edges/(n*(n-1))`, 0 if
`n<2`. `max_outdegree` = max distinct destinations for any source;
`max_indegree` = max distinct sources for any destination.

**IAT** — sort all packets by timestamp; intervals are the N-1 consecutive gaps.
`iat_mean = sum/count`; `iat_variance = sum((x-mean)^2)/count` (population,
divide by count, NOT Bessel); `iat_cv = sqrt(variance)/mean` (0 if mean=0).

**PCR** — over IP packets, `bytes_sent[ip]` sums frame length where ip is src,
`bytes_recv[ip]` where ip is dst. `PCR=(sent-recv)/(sent+recv)`, skip ip with
sent+recv=0. `num_producers`=count(PCR>0.2); `num_consumers`=count(PCR<-0.2).

**Flows** — 5-tuple `(src_ip,dst_ip,src_port,dst_port,proto)` only for TCP/UDP
packets that also have an IP layer. `unique_flows`=distinct keys; `tcp_flows`/
`udp_flows`=subset by proto; `bidirectional_flows`=number of flow keys whose
reverse `(dst,src,dst_port,src_port,proto)` is also present (iterate all flows,
count matches, divide by 2).

**Classification flags** (booleans, printed lowercase `true`/`false`) are derived
from the computed metrics using converging evidence, not the dataset name:
- `has_port_scan`: some single source IP shows high destination-port fan-out AND
  high per-source dst-port entropy AND a high SYN-only ratio (half-open probing).
- `has_dos_pattern`: `packets_per_minute_max / packets_per_minute_avg` is
  extraordinarily large (flood dwarfing baseline).
- `has_beaconing`: global `iat_cv` is low (regular, metronomic arrivals).
- `is_traffic_benign`: none of the above fired.
The thresholds live in `scripts/compute_stats.py` (`THRESHOLDS`). They are a
starting heuristic; adjust them there if evidence requires, keeping each flag's
scope independent.

## How to run

```
echo '{}' | python3 scripts/compute_stats.py
```

Input JSON on stdin (all optional):
```
{"pcap_path": "/root/packets.pcap", "csv_path": "/root/network_stats.csv"}
```
Defaults are the task's `/root/packets.pcap` and `/root/network_stats.csv`.

The script writes the filled CSV in place and emits a JSON object on stdout:
```
{"ok": true, "metrics": {<metric_name>: <value>, ...},
 "filled": <int rows updated>, "unknown_rows": [<metric names in CSV not computed>]}
```
If scapy or the pcap is missing it prints `{"ok": false, "error": "..."}` and
exits non-zero — install scapy (`pip install scapy`) and re-run; internet is
allowed in this environment.

## Executor workflow

1. `python3 -c "import scapy"`; if it fails, `pip install scapy`.
2. Run the entrypoint as above.
3. Confirm `ok:true`, `unknown_rows` is empty (every CSV metric was recognized),
   and open `/root/network_stats.csv` to verify the `value` column is populated
   and comment lines are untouched.
4. Sanity-check with `scripts/validate_output.py` (reads the CSV, re-asserts
   formatting invariants). See `references/metrics.md` for the full definition
   list and the invariants used for review.

Do not hardcode any computed numbers into the Skill; always recompute from the
actual supplied pcap at run time.
