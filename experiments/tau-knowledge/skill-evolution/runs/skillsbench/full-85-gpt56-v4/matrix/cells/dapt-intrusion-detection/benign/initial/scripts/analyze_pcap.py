#!/usr/bin/env python3
"""Compute requested PCAP statistics and update the value column of a CSV template.

Input (stdin): {"pcap_path": str, "csv_path": str, optional classification thresholds}
Output (stdout): {"ok": true, "pcap_path": str, "csv_path": str, "metrics": object}
"""
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict

try:
    from scapy.all import ARP, ICMP, IP, TCP, UDP
    from scapy.utils import PcapReader
except Exception as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit("Scapy is required to analyze PCAP files: %s" % exc)

REQUIRED = {
    "protocol_tcp", "protocol_udp", "protocol_icmp", "protocol_arp", "protocol_ip_total",
    "duration_seconds", "packets_per_minute_avg", "packets_per_minute_max", "packets_per_minute_min",
    "total_bytes", "avg_packet_size", "min_packet_size", "max_packet_size",
    "src_ip_entropy", "dst_ip_entropy", "src_port_entropy", "dst_port_entropy",
    "unique_src_ports", "unique_dst_ports", "num_nodes", "num_edges", "network_density",
    "max_outdegree", "max_indegree", "iat_mean", "iat_variance", "iat_cv",
    "num_producers", "num_consumers", "unique_flows", "tcp_flows", "udp_flows",
    "bidirectional_flows", "is_traffic_benign", "has_port_scan", "has_dos_pattern", "has_beaconing",
}


def entropy(counter):
    """Base-2 Shannon entropy of a Counter, returning zero for no observations."""
    total = sum(counter.values())
    if not total:
        return 0.0
    return -sum((count / total) * math.log2(count / total) for count in counter.values() if count)


def mean_variance(values):
    """Return arithmetic mean and population variance, or (0, 0) for no values."""
    if not values:
        return 0.0, 0.0
    avg = sum(values) / len(values)
    return avg, sum((item - avg) ** 2 for item in values) / len(values)


def safe_layer(packet, layer):
    """Layer lookup after a membership test; keeps malformed packets from being misread."""
    try:
        return packet[layer]
    except Exception:
        return None


def compute(pcap_path, scan_min_ports=20, scan_min_syn=20, dos_rate_ratio=10.0):
    tcp_count = udp_count = icmp_count = arp_count = ip_count = 0
    lengths, timestamps = [], []
    src_ips, dst_ips = Counter(), Counter()
    src_ports, dst_ports = Counter(), Counter()
    nodes, edges = set(), set()
    out_neighbors, in_neighbors = defaultdict(set), defaultdict(set)
    sent, received = Counter(), Counter()
    flows = set()
    # Per-source scan indicators are intentionally based on IPv4 TCP packets.
    scan_ports = defaultdict(Counter)
    scan_tcp_total = Counter()
    scan_syn_only = Counter()

    try:
        reader = PcapReader(pcap_path)
    except Exception as exc:
        raise RuntimeError("cannot open PCAP %r: %s" % (pcap_path, exc))
    try:
        for packet in reader:
            try:
                timestamp = float(packet.time)
                frame_len = len(packet)
            except Exception as exc:
                raise RuntimeError("encountered packet without usable timestamp/frame length: %s" % exc)
            timestamps.append(timestamp)
            lengths.append(frame_len)

            # These are deliberately independent tests, rather than nested in IP.
            has_tcp = TCP in packet
            has_udp = UDP in packet
            if has_tcp:
                tcp_count += 1
                layer = safe_layer(packet, TCP)
                if layer is not None:
                    try:
                        src_ports[layer.sport] += 1
                        dst_ports[layer.dport] += 1
                    except Exception:
                        pass
            if has_udp:
                udp_count += 1
                layer = safe_layer(packet, UDP)
                if layer is not None:
                    try:
                        src_ports[layer.sport] += 1
                        dst_ports[layer.dport] += 1
                    except Exception:
                        pass
            if ICMP in packet:
                icmp_count += 1
            if ARP in packet:
                arp_count += 1

            if IP not in packet:
                continue
            ip = safe_layer(packet, IP)
            if ip is None:
                continue
            try:
                src, dst = str(ip.src), str(ip.dst)
            except Exception:
                continue
            ip_count += 1
            src_ips[src] += 1
            dst_ips[dst] += 1
            nodes.update((src, dst))
            # Graph density is defined for a directed graph with self-loops excluded.
            if src != dst:
                edges.add((src, dst))
                out_neighbors[src].add(dst)
                in_neighbors[dst].add(src)
            sent[src] += frame_len
            received[dst] += frame_len

            if has_tcp:
                tcp = safe_layer(packet, TCP)
                if tcp is not None:
                    try:
                        flow = (src, dst, int(tcp.sport), int(tcp.dport), "TCP")
                        flows.add(flow)
                        scan_tcp_total[src] += 1
                        scan_ports[src][int(tcp.dport)] += 1
                        flags = int(tcp.flags)
                        if (flags & 0x02) and not (flags & 0x10):  # SYN present, ACK absent
                            scan_syn_only[src] += 1
                    except Exception:
                        pass
            if has_udp:
                udp = safe_layer(packet, UDP)
                if udp is not None:
                    try:
                        flows.add((src, dst, int(udp.sport), int(udp.dport), "UDP"))
                    except Exception:
                        pass
    finally:
        reader.close()

    count = len(lengths)
    if count:
        first_time, last_time = min(timestamps), max(timestamps)
        duration = last_time - first_time
        buckets = Counter(int(math.floor((stamp - first_time) / 60.0)) for stamp in timestamps)
        bucket_values = list(buckets.values())
        ppm_avg = sum(bucket_values) / len(bucket_values)
        ppm_max, ppm_min = max(bucket_values), min(bucket_values)
    else:
        duration = ppm_avg = ppm_max = ppm_min = 0.0

    ordered = sorted(timestamps)
    intervals = [ordered[index] - ordered[index - 1] for index in range(1, len(ordered))]
    iat_mean, iat_variance = mean_variance(intervals)
    iat_cv = math.sqrt(iat_variance) / iat_mean if iat_mean else 0.0

    density = len(edges) / (len(nodes) * (len(nodes) - 1)) if len(nodes) >= 2 else 0.0
    max_out = max((len(values) for values in out_neighbors.values()), default=0)
    max_in = max((len(values) for values in in_neighbors.values()), default=0)
    all_pcr_ips = set(sent) | set(received)
    producers = consumers = 0
    for address in all_pcr_ips:
        total = sent[address] + received[address]
        if not total:
            continue
        pcr = (sent[address] - received[address]) / total
        if pcr > 0.2:
            producers += 1
        elif pcr < -0.2:
            consumers += 1

    tcp_flows = sum(1 for flow in flows if flow[4] == "TCP")
    udp_flows = sum(1 for flow in flows if flow[4] == "UDP")
    directional_matches = sum(
        1 for src, dst, sport, dport, proto in flows
        if (dst, src, dport, sport, proto) in flows
    )
    bidirectional = directional_matches // 2

    # Require all three scan signals from the same source, avoiding a global ephemeral-port false positive.
    has_port_scan = False
    for source, ports in scan_ports.items():
        attempts = scan_tcp_total[source]
        syn_ratio = scan_syn_only[source] / attempts if attempts else 0.0
        if (len(ports) >= scan_min_ports and scan_syn_only[source] >= scan_min_syn
                and entropy(ports) >= math.log2(scan_min_ports) * 0.75 and syn_ratio >= 0.70):
            has_port_scan = True
            break
    # A partial minute is retained in rate statistics, so require both a very large ratio and volume.
    has_dos = bool(ppm_avg and ppm_max >= 100 and (ppm_max / ppm_avg) >= dos_rate_ratio)
    # CV is defined over all traffic; ten intervals prevents tiny captures from being labelled periodic.
    has_beaconing = len(intervals) >= 10 and iat_mean > 0 and iat_cv < 0.5

    return {
        "protocol_tcp": tcp_count, "protocol_udp": udp_count, "protocol_icmp": icmp_count,
        "protocol_arp": arp_count, "protocol_ip_total": ip_count,
        "duration_seconds": duration, "packets_per_minute_avg": ppm_avg,
        "packets_per_minute_max": ppm_max, "packets_per_minute_min": ppm_min,
        "total_bytes": sum(lengths), "avg_packet_size": (sum(lengths) / count if count else 0.0),
        "min_packet_size": min(lengths) if lengths else 0,
        "max_packet_size": max(lengths) if lengths else 0,
        "src_ip_entropy": entropy(src_ips), "dst_ip_entropy": entropy(dst_ips),
        "src_port_entropy": entropy(src_ports), "dst_port_entropy": entropy(dst_ports),
        "unique_src_ports": len(src_ports), "unique_dst_ports": len(dst_ports),
        "num_nodes": len(nodes), "num_edges": len(edges), "network_density": density,
        "max_outdegree": max_out, "max_indegree": max_in,
        "iat_mean": iat_mean, "iat_variance": iat_variance, "iat_cv": iat_cv,
        "num_producers": producers, "num_consumers": consumers,
        "unique_flows": len(flows), "tcp_flows": tcp_flows, "udp_flows": udp_flows,
        "bidirectional_flows": bidirectional,
        "is_traffic_benign": not (has_port_scan or has_dos or has_beaconing),
        "has_port_scan": has_port_scan, "has_dos_pattern": has_dos, "has_beaconing": has_beaconing,
    }


def value_text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite metric value")
        return repr(value)
    return str(value)


def update_csv(path, metrics):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        lines = handle.readlines()
    found = set()
    output = []
    for line in lines:
        if line.lstrip().startswith("#") or not line.strip():
            output.append(line)
            continue
        try:
            row = next(csv.reader([line]))
        except Exception as exc:
            raise RuntimeError("invalid CSV row %r: %s" % (line.rstrip(), exc))
        if row and row[0] in metrics:
            if len(row) < 2:
                raise RuntimeError("metric row has no value column: %s" % row[0])
            row[1] = value_text(metrics[row[0]])
            # Keep any extra columns intact while changing just the logical value field.
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            from io import StringIO
            buffer = StringIO()
            csv.writer(buffer, lineterminator=newline).writerow(row)
            output.append(buffer.getvalue())
            found.add(row[0])
        else:
            output.append(line)
    missing = REQUIRED - found
    if missing:
        raise RuntimeError("CSV template is missing required metric rows: " + ", ".join(sorted(missing)))
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        handle.writelines(output)
    os.replace(temporary, path)


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin JSON must be an object")
        pcap_path, csv_path = request.get("pcap_path"), request.get("csv_path")
        if not isinstance(pcap_path, str) or not isinstance(csv_path, str):
            raise ValueError("pcap_path and csv_path must be strings")
        metrics = compute(
            pcap_path,
            int(request.get("port_scan_min_ports", 20)),
            int(request.get("port_scan_min_syn", 20)),
            float(request.get("dos_rate_ratio", 10.0)),
        )
        update_csv(csv_path, metrics)
        print(json.dumps({"ok": True, "pcap_path": pcap_path, "csv_path": csv_path, "metrics": metrics}, sort_keys=True))
    except Exception as exc:
        print("analyze_pcap failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
