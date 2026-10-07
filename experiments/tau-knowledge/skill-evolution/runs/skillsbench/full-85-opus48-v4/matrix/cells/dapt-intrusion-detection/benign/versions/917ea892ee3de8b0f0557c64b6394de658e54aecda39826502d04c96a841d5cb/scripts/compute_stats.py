#!/usr/bin/env python3
"""Entrypoint: compute network stats from a pcap and fill a CSV template.

Stdin JSON (all optional):
  {"pcap_path": "/root/packets.pcap", "csv_path": "/root/network_stats.csv"}

Stdout JSON:
  {"ok": true, "metrics": {...}, "filled": N, "unknown_rows": [...]}
  or {"ok": false, "error": "..."} on failure (non-zero exit).

The CSV is edited in place: for every non-comment data row whose first column is
a known metric name, the second (value) column is set to the computed value.
Comment lines (starting with #), blank lines, and unknown rows are left intact.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcap_metrics import compute_metrics  # noqa: E402

DEFAULT_PCAP = "/root/packets.pcap"
DEFAULT_CSV = "/root/network_stats.csv"

# Heuristic thresholds for classification flags. Tune here if evidence requires;
# keep each flag's scope independent.
THRESHOLDS = {
    "scan_min_unique_ports": 100,
    "scan_min_port_entropy": 5.0,
    "scan_min_syn_ratio": 0.5,
    "dos_ratio": 10.0,
    "dos_min_max_ppm": 1000,
    "beacon_max_cv": 0.5,
}

INT_METRICS = {
    'protocol_tcp', 'protocol_udp', 'protocol_icmp', 'protocol_arp',
    'protocol_ip_total', 'packets_per_minute_max', 'packets_per_minute_min',
    'total_bytes', 'min_packet_size', 'max_packet_size', 'unique_src_ports',
    'unique_dst_ports', 'num_nodes', 'num_edges', 'max_outdegree',
    'max_indegree', 'num_producers', 'num_consumers', 'unique_flows',
    'tcp_flows', 'udp_flows', 'bidirectional_flows',
}
BOOL_METRICS = {
    'is_traffic_benign', 'has_port_scan', 'has_dos_pattern', 'has_beaconing',
}


def fmt(name, value):
    if name in BOOL_METRICS or isinstance(value, bool):
        return 'true' if value else 'false'
    if name in INT_METRICS or isinstance(value, int):
        return str(int(value))
    return repr(float(value))


def main():
    try:
        raw = sys.stdin.read()
        cfg = json.loads(raw) if raw.strip() else {}
    except Exception:
        cfg = {}
    pcap_path = cfg.get('pcap_path', DEFAULT_PCAP)
    csv_path = cfg.get('csv_path', DEFAULT_CSV)

    if not os.path.exists(pcap_path):
        print(json.dumps({"ok": False, "error": "pcap not found: " + pcap_path}))
        return 1
    if not os.path.exists(csv_path):
        print(json.dumps({"ok": False, "error": "csv not found: " + csv_path}))
        return 1

    try:
        metrics = compute_metrics(pcap_path, THRESHOLDS)
    except ImportError as e:
        print(json.dumps({"ok": False,
                          "error": "scapy required: %s (pip install scapy)" % e}))
        return 1
    except Exception as e:
        print(json.dumps({"ok": False, "error": "compute failed: %s" % e}))
        return 1

    with open(csv_path, 'r') as f:
        lines = f.readlines()

    out_lines = []
    filled = 0
    unknown = []
    for line in lines:
        nl = '\n' if line.endswith('\n') else ''
        stripped = line.rstrip('\n')
        s = stripped.strip()
        if not s or s.startswith('#'):
            out_lines.append(line)
            continue
        parts = stripped.split(',')
        key = parts[0].strip()
        if key in metrics:
            val = fmt(key, metrics[key])
            if len(parts) >= 2:
                parts[1] = val
                new = ','.join(parts)
            else:
                new = parts[0] + ',' + val
            out_lines.append(new + nl)
            filled += 1
        else:
            # not a computed metric (likely a header row); leave unchanged
            unknown.append(key)
            out_lines.append(line)

    with open(csv_path, 'w') as f:
        f.writelines(out_lines)

    # unknown rows that look like metrics (lowercase_with_underscores) are worth
    # surfacing; a header such as 'metric'/'name'/'value' is expected and benign.
    print(json.dumps({"ok": True, "metrics": metrics, "filled": filled,
                       "unknown_rows": unknown}, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
