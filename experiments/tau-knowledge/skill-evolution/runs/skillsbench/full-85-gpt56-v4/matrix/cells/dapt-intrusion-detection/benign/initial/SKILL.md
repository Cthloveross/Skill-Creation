---
name: pcap-network-statistics
summary: Analyze an IPv4 PCAP with Scapy and populate a metric/value CSV template with traffic, graph, timing, flow, PCR, and conservative anomaly-classification metrics.
---

# PCAP Network Statistics

Use this Skill when a task supplies a packet capture and a CSV metric template whose `value` column must be completed. It streams the PCAP with Scapy, uses full captured-frame lengths, and writes values only for recognized metric rows while preserving comment lines.

## Prerequisites

- Python 3 and Scapy must be available in the execution environment.
- The input capture must be readable by `scapy.utils.PcapReader`.
- The output template must contain a header plus metric rows in `metric,value` form. Comment lines beginning with `#` are retained unchanged.

## Run

The entrypoint accepts one JSON object on standard input and emits a JSON execution report on standard output:

```sh
python3 scripts/analyze_pcap.py <<'JSON'
{"pcap_path":"/root/packets.pcap","csv_path":"/root/network_stats.csv"}
JSON
```

Optional JSON keys:

- `pcap_path` (required): source PCAP path.
- `csv_path` (required): existing CSV template to update in place.
- `port_scan_min_ports` (default `20`), `port_scan_min_syn` (default `20`), and `dos_rate_ratio` (default `10.0`) tune the conservative classification rules.

The report has the schema:

```json
{"ok": true, "pcap_path": "...", "csv_path": "...", "metrics": {"metric_name": 0}}
```

On an invalid input, unreadable PCAP, unavailable Scapy, or missing required metric row, the script exits nonzero with a descriptive error on stderr and does not claim success.

## Computation rules

- Protocol counters test Scapy's TCP, UDP, ICMP, and ARP layers independently. `protocol_ip_total` and all IP-address graph/PCR metrics use IPv4 (`IP`) only.
- Packet length is `len(packet)`, i.e. the full captured frame. Size and IAT calculations include every packet.
- Time buckets are relative to the earliest timestamp: `floor((time - first_time) / 60)`. IATs are calculated after sorting all timestamps and use population variance.
- IP entropy, graph nodes/edges, and PCR use IPv4 packets only. TCP/UDP port entropy uses packets containing TCP or UDP. TCP/UDP flows additionally require an IPv4 source and destination because the specified five-tuple uses IP addresses.
- A bidirectional flow pair is counted once, not once per direction.
- For anomaly flags, port scanning requires convergent source-level evidence (many distinct destination ports, high destination-port entropy, and SYN-without-ACK predominance). DoS requires a large rate spike and substantial peak volume. Beaconing requires enough intervals plus low IAT CV. `is_traffic_benign` is true exactly when none of those three flags is true.

## Validation

After execution, inspect the emitted report and the CSV. Every required metric should have a nonempty `value`, booleans must be lowercase `true` or `false`, and comments/metric names must remain unchanged. The script validates that all required metric names are present before replacing the template.
