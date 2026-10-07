"""Reusable helpers to compute DAPT2020-style network statistics from a pcap.

All definitions follow the task's background exactly. No instance values are
hardcoded; everything is derived from the pcap passed in at runtime.
"""
import math
from collections import Counter, defaultdict


def shannon_entropy(counter):
    """Base-2 Shannon entropy over a Counter/dict of value->count."""
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counter.values():
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log2(p)
    return h


def compute_metrics(pcap_path, thresholds):
    """Single streaming pass over the pcap; returns dict of metric->value.

    Requires scapy. Raises ImportError if scapy is unavailable.
    """
    from scapy.all import PcapReader, IP, TCP, UDP, ICMP, ARP

    # counters
    c_tcp = c_udp = c_icmp = c_arp = c_ip = 0
    lengths = []
    times = []

    src_ip_ctr = Counter()
    dst_ip_ctr = Counter()
    src_port_ctr = Counter()
    dst_port_ctr = Counter()

    nodes = set()
    edges = set()
    out_map = defaultdict(set)
    in_map = defaultdict(set)

    bytes_sent = defaultdict(int)
    bytes_recv = defaultdict(int)

    flows = set()

    # per-source scan evidence
    src_dstports = defaultdict(set)       # src_ip -> set(dst_port)
    src_dstport_ctr = defaultdict(Counter)  # src_ip -> Counter(dst_port)
    src_syn_only = defaultdict(int)       # src_ip -> syn-only tcp pkts
    src_tcp_total = defaultdict(int)      # src_ip -> tcp pkts

    with PcapReader(pcap_path) as pr:
        for pkt in pr:
            try:
                length = len(pkt)
                lengths.append(length)
                try:
                    times.append(float(pkt.time))
                except Exception:
                    pass

                has_ip = IP in pkt
                has_tcp = TCP in pkt
                has_udp = UDP in pkt
                has_icmp = ICMP in pkt
                has_arp = ARP in pkt

                if has_tcp:
                    c_tcp += 1
                if has_udp:
                    c_udp += 1
                if has_icmp:
                    c_icmp += 1
                if has_arp:
                    c_arp += 1

                src_ip = dst_ip = None
                if has_ip:
                    c_ip += 1
                    src_ip = pkt[IP].src
                    dst_ip = pkt[IP].dst
                    src_ip_ctr[src_ip] += 1
                    dst_ip_ctr[dst_ip] += 1
                    nodes.add(src_ip)
                    nodes.add(dst_ip)
                    edges.add((src_ip, dst_ip))
                    out_map[src_ip].add(dst_ip)
                    in_map[dst_ip].add(src_ip)
                    bytes_sent[src_ip] += length
                    bytes_recv[dst_ip] += length

                # ports from transport layers (pooled over TCP+UDP)
                if has_tcp:
                    sp = int(pkt[TCP].sport)
                    dp = int(pkt[TCP].dport)
                    src_port_ctr[sp] += 1
                    dst_port_ctr[dp] += 1
                    if has_ip:
                        flows.add((src_ip, dst_ip, sp, dp, 'TCP'))
                        src_dstports[src_ip].add(dp)
                        src_dstport_ctr[src_ip][dp] += 1
                        src_tcp_total[src_ip] += 1
                        try:
                            fl = int(pkt[TCP].flags)
                        except Exception:
                            fl = 0
                        syn = bool(fl & 0x02)
                        ack = bool(fl & 0x10)
                        if syn and not ack:
                            src_syn_only[src_ip] += 1
                elif has_udp:
                    sp = int(pkt[UDP].sport)
                    dp = int(pkt[UDP].dport)
                    src_port_ctr[sp] += 1
                    dst_port_ctr[dp] += 1
                    if has_ip:
                        flows.add((src_ip, dst_ip, sp, dp, 'UDP'))
            except Exception:
                # skip malformed packet but keep going
                continue

    m = {}
    m['protocol_tcp'] = c_tcp
    m['protocol_udp'] = c_udp
    m['protocol_icmp'] = c_icmp
    m['protocol_arp'] = c_arp
    m['protocol_ip_total'] = c_ip

    # time / rate
    if times:
        start = min(times)
        end = max(times)
        m['duration_seconds'] = end - start
        buckets = Counter()
        for t in times:
            idx = int(math.floor((t - start) / 60.0))
            buckets[idx] += 1
        counts = list(buckets.values())
        if counts:
            m['packets_per_minute_avg'] = sum(counts) / len(counts)
            m['packets_per_minute_max'] = max(counts)
            m['packets_per_minute_min'] = min(counts)
        else:
            m['packets_per_minute_avg'] = 0.0
            m['packets_per_minute_max'] = 0
            m['packets_per_minute_min'] = 0
    else:
        m['duration_seconds'] = 0.0
        m['packets_per_minute_avg'] = 0.0
        m['packets_per_minute_max'] = 0
        m['packets_per_minute_min'] = 0

    # sizes
    if lengths:
        m['total_bytes'] = sum(lengths)
        m['avg_packet_size'] = sum(lengths) / len(lengths)
        m['min_packet_size'] = min(lengths)
        m['max_packet_size'] = max(lengths)
    else:
        m['total_bytes'] = 0
        m['avg_packet_size'] = 0.0
        m['min_packet_size'] = 0
        m['max_packet_size'] = 0

    # entropy
    m['src_ip_entropy'] = shannon_entropy(src_ip_ctr)
    m['dst_ip_entropy'] = shannon_entropy(dst_ip_ctr)
    m['src_port_entropy'] = shannon_entropy(src_port_ctr)
    m['dst_port_entropy'] = shannon_entropy(dst_port_ctr)
    m['unique_src_ports'] = len(src_port_ctr)
    m['unique_dst_ports'] = len(dst_port_ctr)

    # graph
    n = len(nodes)
    m['num_nodes'] = n
    m['num_edges'] = len(edges)
    if n < 2:
        m['network_density'] = 0.0
    else:
        m['network_density'] = len(edges) / (n * (n - 1))
    m['max_outdegree'] = max((len(s) for s in out_map.values()), default=0)
    m['max_indegree'] = max((len(s) for s in in_map.values()), default=0)

    # IAT
    if len(times) >= 2:
        st = sorted(times)
        gaps = [st[i + 1] - st[i] for i in range(len(st) - 1)]
        cnt = len(gaps)
        mean = sum(gaps) / cnt
        var = sum((x - mean) ** 2 for x in gaps) / cnt
        m['iat_mean'] = mean
        m['iat_variance'] = var
        m['iat_cv'] = (math.sqrt(var) / mean) if mean != 0 else 0.0
    else:
        m['iat_mean'] = 0.0
        m['iat_variance'] = 0.0
        m['iat_cv'] = 0.0

    # PCR
    producers = consumers = 0
    for ip in set(bytes_sent) | set(bytes_recv):
        s = bytes_sent.get(ip, 0)
        r = bytes_recv.get(ip, 0)
        if s + r == 0:
            continue
        pcr = (s - r) / (s + r)
        if pcr > 0.2:
            producers += 1
        elif pcr < -0.2:
            consumers += 1
    m['num_producers'] = producers
    m['num_consumers'] = consumers

    # flows
    m['unique_flows'] = len(flows)
    m['tcp_flows'] = sum(1 for f in flows if f[4] == 'TCP')
    m['udp_flows'] = sum(1 for f in flows if f[4] == 'UDP')
    bidir = 0
    for (si, di, sp, dp, pr) in flows:
        if (di, si, dp, sp, pr) in flows:
            bidir += 1
    m['bidirectional_flows'] = bidir // 2

    # classification flags
    th = thresholds
    port_scan = False
    for ip, ports in src_dstports.items():
        if len(ports) < th['scan_min_unique_ports']:
            continue
        ent = shannon_entropy(src_dstport_ctr[ip])
        tot = src_tcp_total.get(ip, 0)
        syn_ratio = (src_syn_only.get(ip, 0) / tot) if tot > 0 else 0.0
        if ent >= th['scan_min_port_entropy'] and syn_ratio >= th['scan_min_syn_ratio']:
            port_scan = True
            break
    m['has_port_scan'] = port_scan

    avg_ppm = m['packets_per_minute_avg']
    max_ppm = m['packets_per_minute_max']
    dos = (avg_ppm > 0 and (max_ppm / avg_ppm) >= th['dos_ratio']
           and max_ppm >= th['dos_min_max_ppm'])
    m['has_dos_pattern'] = bool(dos)

    cv = m['iat_cv']
    m['has_beaconing'] = bool(cv > 0 and cv < th['beacon_max_cv'])

    m['is_traffic_benign'] = not (m['has_port_scan'] or m['has_dos_pattern']
                                  or m['has_beaconing'])
    return m
