#!/usr/bin/env python3
"""Compute PCAP metrics and populate a metric,value CSV template.

JSON stdin schema:
  {"pcap_path": str, "template_path": str, "output_path": str}
Defaults are the standard public task paths. JSON stdout is a success/error object.
"""
import csv
import io
import json
import math
import os
import sys
from collections import Counter, defaultdict

try:
    from scapy.all import ARP, ICMP, IP, TCP, UDP
    from scapy.utils import PcapReader
except Exception as exc:  # reported by main in a JSON-safe fashion
    SCAPY_ERROR = exc
else:
    SCAPY_ERROR = None

REQUIRED_METRICS = {
    "protocol_tcp", "protocol_udp", "protocol_icmp", "protocol_arp", "protocol_ip_total",
    "duration_seconds", "packets_per_minute_avg", "packets_per_minute_max", "packets_per_minute_min",
    "total_bytes", "avg_packet_size", "min_packet_size", "max_packet_size",
    "src_ip_entropy", "dst_ip_entropy", "src_port_entropy", "dst_port_entropy",
    "unique_src_ports", "unique_dst_ports", "num_nodes", "num_edges", "network_density",
    "max_outdegree", "max_indegree", "iat_mean", "iat_variance", "iat_cv",
    "num_producers", "num_consumers", "unique_flows", "tcp_flows", "udp_flows",
    "bidirectional_flows", "is_traffic_benign", "has_port_scan", "has_dos_pattern",
    "has_beaconing",
}


def entropy(counter):
    """Base-2 Shannon entropy for a Counter, with an empty result of 0."""
    total = sum(counter.values())
    if not total:
        return 0.0
    return -math.fsum((n / total) * math.log2(n / total) for n in counter.values() if n)


def as_number_text(value):
    """Format numeric CSV values without lossy fixed decimal rounding."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if value == 0:
        return "0"
    return repr(float(value))


def update_template(template_path, output_path, values):
    """Replace only metric value fields while preserving comments and row ordering."""
    with open(template_path, "r", encoding="utf-8", newline="") as handle:
        original_lines = handle.readlines()

    header_index = None
    header = None
    for index, raw in enumerate(original_lines):
        if raw.startswith("#") or not raw.strip():
            continue
        parsed = next(csv.reader([raw]))
        header_index = index
        header = parsed
        break
    if header is None or "value" not in header:
        raise ValueError("template must contain a non-comment header with a 'value' column")
    value_index = header.index("value")
    metric_index = 0
    if "metric" in header:
        metric_index = header.index("metric")

    seen = set()
    rendered = list(original_lines)
    for index in range(header_index + 1, len(original_lines)):
        raw = original_lines[index]
        if raw.startswith("#") or not raw.strip():
            continue
        row = next(csv.reader([raw]))
        if len(row) <= max(metric_index, value_index):
            raise ValueError("malformed template row %d" % (index + 1))
        metric = row[metric_index]
        if metric not in values:
            continue
        row[value_index] = as_number_text(values[metric])
        seen.add(metric)
        line_ending = "\r\n" if raw.endswith("\r\n") else "\n" if raw.endswith("\n") else ""
        output = io.StringIO()
        csv.writer(output, lineterminator="").writerow(row)
        rendered[index] = output.getvalue() + line_ending

    missing = REQUIRED_METRICS - seen
    if missing:
        raise ValueError("template is missing required metric rows: " + ", ".join(sorted(missing)))

    # Comments must remain exactly as supplied, including comment text and line ending.
    for before, after in zip(original_lines, rendered):
        if before.startswith("#") and before != after:
            raise AssertionError("comment preservation validation failed")

    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        handle.writelines(rendered)


def compute_metrics(pcap_path):
    if SCAPY_ERROR is not None:
        raise RuntimeError("Scapy could not be imported: %s" % SCAPY_ERROR)
    if not os.path.isfile(pcap_path):
        raise FileNotFoundError("PCAP does not exist: " + pcap_path)

    protocol = Counter()
    sizes = []
    timestamps = []
    src_ips, dst_ips = Counter(), Counter()
    src_ports, dst_ports = Counter(), Counter()
    nodes, edges = set(), set()
    out_neighbors, in_neighbors = defaultdict(set), defaultdict(set)
    sent, received = Counter(), Counter()
    flows = set()
    tcp_dest_ports_by_source = defaultdict(Counter)
    tcp_attempts, tcp_syn_only = Counter(), Counter()

    with PcapReader(pcap_path) as reader:
        for packet in reader:
            packet_length = len(packet)
            sizes.append(packet_length)
            timestamps.append(float(packet.time))

            # These checks deliberately remain independent of the IPv4 test.
            if TCP in packet:
                protocol["tcp"] += 1
            if UDP in packet:
                protocol["udp"] += 1
            if ICMP in packet:
                protocol["icmp"] += 1
            if ARP in packet:
                protocol["arp"] += 1
            if IP not in packet:
                continue

            protocol["ip_total"] += 1
            ip = packet[IP]
            source, destination = str(ip.src), str(ip.dst)
            src_ips[source] += 1
            dst_ips[destination] += 1
            nodes.update((source, destination))
            sent[source] += packet_length
            received[destination] += packet_length

            # The density definition excludes self-loop graph edges.
            if source != destination:
                edges.add((source, destination))
                out_neighbors[source].add(destination)
                in_neighbors[destination].add(source)

            if TCP in packet:
                tcp = packet[TCP]
                sport, dport = int(tcp.sport), int(tcp.dport)
                src_ports[sport] += 1
                dst_ports[dport] += 1
                flows.add((source, destination, sport, dport, "TCP"))
                tcp_dest_ports_by_source[source][dport] += 1
                tcp_attempts[source] += 1
                flags = int(tcp.flags)
                if (flags & 0x02) and not (flags & 0x10):  # SYN set, ACK clear
                    tcp_syn_only[source] += 1
            if UDP in packet:
                udp = packet[UDP]
                sport, dport = int(udp.sport), int(udp.dport)
                src_ports[sport] += 1
                dst_ports[dport] += 1
                flows.add((source, destination, sport, dport, "UDP"))

    count = len(sizes)
    if count:
        first_time, last_time = min(timestamps), max(timestamps)
        duration = last_time - first_time
        # Include every temporal bucket from capture start to final packet, even empty gaps.
        bucket_counts = [0] * (int(math.floor(duration / 60.0)) + 1)
        for timestamp in timestamps:
            bucket_counts[int(math.floor((timestamp - first_time) / 60.0))] += 1
        ppm_avg = math.fsum(bucket_counts) / len(bucket_counts)
        ppm_max, ppm_min = max(bucket_counts), min(bucket_counts)
    else:
        duration = ppm_avg = ppm_max = ppm_min = 0
        bucket_counts = []

    sorted_times = sorted(timestamps)
    iats = [right - left for left, right in zip(sorted_times, sorted_times[1:])]
    if iats:
        iat_mean = math.fsum(iats) / len(iats)
        iat_variance = math.fsum((gap - iat_mean) ** 2 for gap in iats) / len(iats)
        iat_cv = math.sqrt(iat_variance) / iat_mean if iat_mean else 0.0
    else:
        iat_mean = iat_variance = iat_cv = 0.0

    bidirectional = 0
    for flow in flows:
        reverse = (flow[1], flow[0], flow[3], flow[2], flow[4])
        # Ordering counts a two-direction pair once; a self-reversing key is not a pair.
        if reverse in flows and flow != reverse and flow < reverse:
            bidirectional += 1

    producer_count = consumer_count = 0
    for address in nodes:
        total = sent[address] + received[address]
        if not total:
            continue
        pcr = (sent[address] - received[address]) / total
        if pcr > 0.2:
            producer_count += 1
        elif pcr < -0.2:
            consumer_count += 1

    port_scan = False
    for source, distribution in tcp_dest_ports_by_source.items():
        distinct = len(distribution)
        attempts = tcp_attempts[source]
        entropy_ratio = entropy(distribution) / math.log2(distinct) if distinct > 1 else 0.0
        syn_ratio = tcp_syn_only[source] / attempts if attempts else 0.0
        if distinct >= 20 and entropy_ratio >= 0.80 and syn_ratio >= 0.50:
            port_scan = True
            break
    dos_pattern = bool(bucket_counts and max(bucket_counts) >= 100 and ppm_avg > 0 and max(bucket_counts) / ppm_avg >= 10.0)
    beaconing = len(iats) >= 10 and iat_mean > 0 and iat_cv <= 0.20

    values = {
        "protocol_tcp": protocol["tcp"], "protocol_udp": protocol["udp"],
        "protocol_icmp": protocol["icmp"], "protocol_arp": protocol["arp"],
        "protocol_ip_total": protocol["ip_total"], "duration_seconds": duration,
        "packets_per_minute_avg": ppm_avg, "packets_per_minute_max": ppm_max,
        "packets_per_minute_min": ppm_min, "total_bytes": sum(sizes),
        "avg_packet_size": (math.fsum(sizes) / count) if count else 0,
        "min_packet_size": min(sizes) if sizes else 0, "max_packet_size": max(sizes) if sizes else 0,
        "src_ip_entropy": entropy(src_ips), "dst_ip_entropy": entropy(dst_ips),
        "src_port_entropy": entropy(src_ports), "dst_port_entropy": entropy(dst_ports),
        "unique_src_ports": len(src_ports), "unique_dst_ports": len(dst_ports),
        "num_nodes": len(nodes), "num_edges": len(edges),
        "network_density": len(edges) / (len(nodes) * (len(nodes) - 1)) if len(nodes) >= 2 else 0,
        "max_outdegree": max((len(v) for v in out_neighbors.values()), default=0),
        "max_indegree": max((len(v) for v in in_neighbors.values()), default=0),
        "iat_mean": iat_mean, "iat_variance": iat_variance, "iat_cv": iat_cv,
        "num_producers": producer_count, "num_consumers": consumer_count,
        "unique_flows": len(flows), "tcp_flows": sum(1 for flow in flows if flow[4] == "TCP"),
        "udp_flows": sum(1 for flow in flows if flow[4] == "UDP"),
        "bidirectional_flows": bidirectional, "has_port_scan": port_scan,
        "has_dos_pattern": dos_pattern, "has_beaconing": beaconing,
        "is_traffic_benign": not (port_scan or dos_pattern or beaconing),
    }
    if set(values) != REQUIRED_METRICS:
        raise AssertionError("internal metric-set validation failed")
    return values


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin JSON must be an object")
        pcap_path = request.get("pcap_path", "/root/packets.pcap")
        template_path = request.get("template_path", "/root/network_stats.csv")
        output_path = request.get("output_path", "/root/network_stats.csv")
        if not all(isinstance(p, str) and p for p in (pcap_path, template_path, output_path)):
            raise ValueError("pcap_path, template_path, and output_path must be nonempty strings")
        values = compute_metrics(pcap_path)
        update_template(template_path, output_path, values)
        print(json.dumps({"ok": True, "output_path": output_path, "values": values}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
