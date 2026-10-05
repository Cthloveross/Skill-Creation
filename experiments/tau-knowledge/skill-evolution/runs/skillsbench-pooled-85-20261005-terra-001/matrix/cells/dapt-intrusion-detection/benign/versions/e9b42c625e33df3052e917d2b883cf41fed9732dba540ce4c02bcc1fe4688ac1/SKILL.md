---
name: pcap-network-statistics-csv
description: Compute IPv4-oriented traffic statistics, flow/graph/PCR metrics, and conservative intrusion-pattern flags from a PCAP, then populate the value column of a supplied network-statistics CSV template. Use for packet-capture analysis tasks that provide a PCAP and a metric,value CSV while requiring comments and metric ordering to be preserved.
---

# PCAP network-statistics CSV

Use `scripts/analyze_pcap.py` to analyze a PCAP with Scapy's protocol dissection and write values into an existing CSV template. It streams packets rather than loading the full capture at once.

## Runtime requirements

- Python 3
- Scapy, including `scapy.utils.PcapReader`
- Read access to the input PCAP and template CSV; write access to the output CSV

Scapy is required because it can identify IPv4 and transport layers through VLAN and other nested encapsulations. The script fails explicitly if Scapy or a requested input is unavailable.

## Input and output schema

The script reads one JSON object from standard input:

```json
{
  "pcap_path": "/root/packets.pcap",
  "template_path": "/root/network_stats.csv",
  "output_path": "/root/network_stats.csv"
}
```

All fields are optional only when the public task uses the standard paths shown above. `template_path` may equal `output_path`; the template is completely read before the output is written.

On success it emits JSON containing `ok: true`, the output path, and the computed metric values. On an input/runtime failure it emits `ok: false` and an error message, and exits nonzero.

Run it, for example:

```sh
python3 scripts/analyze_pcap.py <<'JSON'
{"pcap_path":"/root/packets.pcap","template_path":"/root/network_stats.csv","output_path":"/root/network_stats.csv"}
JSON
```

## Computation rules implemented

- Packet length is `len(packet)`, the complete captured frame. Size and IAT metrics include every packet.
- `protocol_ip_total` and all IP-address, graph, PCR, and flow metrics use IPv4 (`IP`) only. IPv6 and ARP therefore do not enter those IP metrics.
- TCP, UDP, ICMP, and ARP counters are independent Scapy layer checks, rather than being nested under an IPv4 check.
- Port distributions and 5-tuples use IPv4 TCP/UDP packets. Entropy is base 2 and is zero for an empty population.
- Packet-rate bucket zero begins at the earliest packet timestamp. The rate sequence includes every relative 60-second bucket through the latest packet, including empty buckets between packets and partial first/last buckets.
- Graph self-loops are excluded, consistent with the directed density denominator `N*(N-1)`. Nodes still include every IPv4 source or destination address.
- IAT values are computed after sorting all packet timestamps; variance is population variance. Empty IAT populations have zero-valued timing statistics.
- PCR uses full-frame bytes of IPv4 packets. An address is a producer only when PCR is strictly greater than 0.2 and a consumer only when strictly less than -0.2.
- A bidirectional flow pair is counted once, not once per direction.

## Analysis flag policy

The task does not prescribe numerical attack thresholds, so the script uses transparent, conservative combined signals rather than a dataset-name assumption:

- Port scan: at least 20 distinct TCP destination ports from one source, destination-port entropy at least 80% of that source's theoretical maximum, and at least 50% SYN-without-ACK TCP attempts.
- DoS pattern: at least 100 packets in the busiest minute and that minute has at least ten times the all-bucket average rate.
- Beaconing: at least 10 IAT intervals, positive mean IAT, and IAT CV at most 0.20.
- `is_traffic_benign` is true only when none of those three patterns is indicated.

These are heuristic flags; the numerical packet-derived metrics remain the primary output. If a task supplies explicit detection thresholds, adapt the policy rather than inferring labels from the capture or dataset name.

## Validation performed before success

The script verifies that the template has a non-comment header with a `value` column, that it contains every required metric name, that every required metric was populated, and that all original comment lines are byte-for-byte unchanged. It retains row order and leaves any non-required template rows untouched.
