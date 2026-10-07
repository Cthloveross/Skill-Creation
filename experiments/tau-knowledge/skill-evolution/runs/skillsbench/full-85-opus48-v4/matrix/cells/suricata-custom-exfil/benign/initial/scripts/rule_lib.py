"""Reusable builder for an HTTP-aware Suricata exfil signature.

All concrete values (path, header, lengths, sid) must be passed in from the
current task instruction; nothing instance-specific is hardcoded here.
"""


def _esc_pcre(s):
    # Escape characters that are special inside a /.../ pcre literal.
    return s.replace('\\', '\\\\').replace('/', '\\/')


def build_rule(params):
    """Build a single Suricata rule string.

    params keys (all optional unless noted; supply from task instruction):
      action: default 'alert'
      proto: default 'http'
      msg: default 'Custom HTTP exfil detected'
      method: e.g. 'POST'
      path: exact request path string, e.g. '/telemetry/v2/report'
      path_exact: bool, default True (startswith+endswith). If False, only
                  anchors the start (allows query strings).
      header: full header line, e.g. 'X-TLM-Mode: exfil'
      header_nocase: bool, default True
      body_fields: list of dicts each describing a request-body constraint:
          {"prefix": "blob=", "charclass": "[A-Za-z0-9+/]", "min": 80}
              -> prefix[charclass]{min,}
          {"prefix": "sig=", "charclass": "[0-9a-fA-F]", "exact": 64}
              -> prefix[charclass]{64} with negative lookahead so it is not
                 longer than 64 of that class.
      sid: required int
      rev: default 1
    """
    action = params.get('action', 'alert')
    proto = params.get('proto', 'http')
    msg = params.get('msg', 'Custom HTTP exfil detected')
    opts = ['flow:established,to_server;']

    method = params.get('method')
    if method:
        opts.append('http.method; content:"%s";' % method)

    path = params.get('path')
    if path:
        if params.get('path_exact', True):
            opts.append('http.uri; content:"%s"; startswith; endswith;' % path)
        else:
            opts.append('http.uri; content:"%s"; startswith;' % path)
            opts.append('pcre:"/^%s/";' % _esc_pcre(path))

    header = params.get('header')
    if header:
        nc = ' nocase;' if params.get('header_nocase', True) else ''
        opts.append('http.header; content:"%s";%s' % (header, nc))

    body_fields = params.get('body_fields') or []
    if body_fields:
        opts.append('http.request_body;')
        for bf in body_fields:
            prefix = bf['prefix']
            cc = bf.get('charclass', '[A-Za-z0-9+/]')
            # content prefilter on the literal prefix for performance
            opts.append('content:"%s";' % prefix)
            if 'exact' in bf:
                k = int(bf['exact'])
                pcre = '%s%s{%d}(?!%s)' % (_esc_pcre(prefix), cc, k,
                                          cc.strip('[]') and cc)
                # Build negative lookahead using same class contents.
                inner = cc[1:-1] if cc.startswith('[') and cc.endswith(']') else cc
                pcre = '%s%s{%d}(?![%s])' % (_esc_pcre(prefix), cc, k, inner)
                opts.append('pcre:"/%s/";' % pcre)
            else:
                mn = int(bf.get('min', 1))
                pcre = '%s%s{%d,}' % (_esc_pcre(prefix), cc, mn)
                opts.append('pcre:"/%s/";' % pcre)

    sid = params['sid']
    rev = params.get('rev', 1)
    opts.append('sid:%d; rev:%d;' % (int(sid), int(rev)))

    body = ' '.join(opts)
    return '%s %s any any -> any any (msg:"%s"; %s)' % (action, proto, msg, body)
