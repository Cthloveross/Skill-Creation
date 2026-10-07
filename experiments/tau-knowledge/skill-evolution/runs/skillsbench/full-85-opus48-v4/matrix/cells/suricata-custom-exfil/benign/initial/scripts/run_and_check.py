#!/usr/bin/env python3
"""Replay pcaps through Suricata and summarize alerts per pcap by sid.

Stdin JSON schema (all optional, with sensible defaults):
  {
    "config": "/root/suricata.yaml",
    "rules": "/root/local.rules",
    "pcap_dir": "/root/pcaps",
    "suricata_bin": "suricata",
    "target_sid": 1000001          # optional; adds per-pcap boolean
  }

For each *.pcap/*.pcapng file it runs:
  suricata -c <config> -S <rules> -r <pcap> -l <tmp> -k none
then parses <tmp>/eve.json for alert events, collecting the set of sids fired.

Stdout JSON:
  {
    "suricata_version_rc": <int>,
    "results": {
      "<pcap filename>": {"sids": [..], "target_fired": bool|null,
                           "returncode": <int>, "stderr_tail": "..."}
    },
    "errors": [..]
  }
"""
import glob
import json
import os
import subprocess
import sys
import tempfile


def run_one(bin_, config, rules, pcap, target_sid):
    tmp = tempfile.mkdtemp(prefix='sur_')
    cmd = [bin_, '-c', config, '-S', rules, '-r', pcap, '-l', tmp, '-k', 'none']
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sids = set()
    eve = os.path.join(tmp, 'eve.json')
    if os.path.exists(eve):
        with open(eve, 'r', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get('event_type') == 'alert':
                    sid = ev.get('alert', {}).get('signature_id')
                    if sid is not None:
                        sids.add(int(sid))
    tfired = None
    if target_sid is not None:
        tfired = int(target_sid) in sids
    stderr_tail = proc.stderr.decode('utf-8', 'replace')[-800:]
    return {
        'sids': sorted(sids),
        'target_fired': tfired,
        'returncode': proc.returncode,
        'stderr_tail': stderr_tail,
    }


def main():
    data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    config = data.get('config', '/root/suricata.yaml')
    rules = data.get('rules', '/root/local.rules')
    pcap_dir = data.get('pcap_dir', '/root/pcaps')
    bin_ = data.get('suricata_bin', 'suricata')
    target_sid = data.get('target_sid')

    errors = []
    try:
        ver = subprocess.run([bin_, '-V'], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        ver_rc = ver.returncode
    except Exception as exc:  # pragma: no cover
        ver_rc = -1
        errors.append('suricata not runnable: %s' % exc)

    pcaps = []
    for pat in ('*.pcap', '*.pcapng'):
        pcaps.extend(glob.glob(os.path.join(pcap_dir, pat)))
    pcaps.sort()
    if not pcaps:
        errors.append('no pcaps found in %s' % pcap_dir)

    results = {}
    for p in pcaps:
        try:
            results[os.path.basename(p)] = run_one(bin_, config, rules, p,
                                                   target_sid)
        except Exception as exc:
            errors.append('run failed for %s: %s' % (p, exc))

    json.dump({'suricata_version_rc': ver_rc, 'results': results,
               'errors': errors}, sys.stdout, indent=2)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
