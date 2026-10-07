#!/usr/bin/env python3
"""Validate the filled CSV against structural invariants (no network needed).

Stdin JSON (optional): {"csv_path": "/root/network_stats.csv"}
Stdout JSON: {"ok": bool, "problems": [...], "values": {name: raw_str}}

Checks (derived from the public request, not from any expected answer):
  - every non-comment, non-header metric row has a non-empty value field;
  - boolean flag rows are exactly 'true' or 'false';
  - numeric rows parse as a number;
  - comment lines preserved (presence check only).
This does NOT recompute metrics; run compute_stats.py for that.
"""
import json
import sys

DEFAULT_CSV = "/root/network_stats.csv"
BOOL_METRICS = {'is_traffic_benign', 'has_port_scan', 'has_dos_pattern',
                'has_beaconing'}
KNOWN = {
    'protocol_tcp', 'protocol_udp', 'protocol_icmp', 'protocol_arp',
    'protocol_ip_total', 'duration_seconds', 'packets_per_minute_avg',
    'packets_per_minute_max', 'packets_per_minute_min', 'total_bytes',
    'avg_packet_size', 'min_packet_size', 'max_packet_size', 'src_ip_entropy',
    'dst_ip_entropy', 'src_port_entropy', 'dst_port_entropy', 'unique_src_ports',
    'unique_dst_ports', 'num_nodes', 'num_edges', 'network_density',
    'max_outdegree', 'max_indegree', 'iat_mean', 'iat_variance', 'iat_cv',
    'num_producers', 'num_consumers', 'unique_flows', 'tcp_flows', 'udp_flows',
    'bidirectional_flows',
} | BOOL_METRICS


def main():
    try:
        raw = sys.stdin.read()
        cfg = json.loads(raw) if raw.strip() else {}
    except Exception:
        cfg = {}
    path = cfg.get('csv_path', DEFAULT_CSV)
    problems = []
    values = {}
    try:
        with open(path) as f:
            lines = f.readlines()
    except Exception as e:
        print(json.dumps({"ok": False, "problems": ["cannot read: %s" % e],
                          "values": {}}))
        return 1

    seen = set()
    for line in lines:
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        parts = s.split(',')
        key = parts[0].strip()
        if key not in KNOWN:
            continue  # header or other
        seen.add(key)
        val = parts[1].strip() if len(parts) >= 2 else ''
        values[key] = val
        if val == '':
            problems.append("%s: empty value" % key)
            continue
        if key in BOOL_METRICS:
            if val not in ('true', 'false'):
                problems.append("%s: not boolean (%r)" % (key, val))
        else:
            try:
                float(val)
            except Exception:
                problems.append("%s: not numeric (%r)" % (key, val))

    missing = sorted(KNOWN - seen)
    if missing:
        problems.append("missing metric rows: %s" % missing)

    ok = not problems
    print(json.dumps({"ok": ok, "problems": problems, "values": values}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
