"""Standalone dialogue parser, validator, DOT writer, and JSON-stdin entrypoint."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile

HEADER = re.compile(r'^\s*\[([^\[\]\r\n]+)\]\s*$')
OPTION = re.compile(r'^\s*(\d+[.)])\s+(.+)$')


def _transition(line, lineno):
    if '->' not in line:
        return line.strip(), None
    body, _, target = line.rpartition('->')
    body, target = body.strip(), target.strip()
    if target.startswith('[') and target.endswith(']'):
        target = target[1:-1].strip()
    if not body or not target or any(c in target for c in '[]\r\n'):
        raise ValueError(f'Line {lineno}: malformed transition')
    return body, target


def _speech(body):
    if ':' in body:
        speaker, text = body.split(':', 1)
        if speaker.strip():
            return speaker.strip(), text.strip()
    return '', body


def _parse_record(identifier, lines):
    has_options = any(OPTION.match(line) for _, line in lines if line.strip())
    fragments = []
    speakers = []
    edges = []
    for lineno, raw in lines:
        if not raw.strip():
            fragments.append('')
            continue
        body, target = _transition(raw, lineno)
        option = OPTION.match(body)
        if option:
            label = option.group(2).strip()
            fragments.append(body)
            if target is not None:
                edges.append({'from': identifier, 'to': target, 'text': label})
        else:
            speaker, speech = _speech(body)
            if speaker and speaker not in speakers:
                speakers.append(speaker)
            fragments.append(speech)
            if target is not None:
                edges.append({'from': identifier, 'to': target, 'text': ''})
    if len(speakers) > 1:
        raise ValueError(f'Record {identifier!r}: multiple speakers in one node are unsupported')
    while fragments and not fragments[0]:
        fragments.pop(0)
    while fragments and not fragments[-1]:
        fragments.pop()
    node = {'id': identifier, 'text': '\n'.join(fragments),
            'speaker': speakers[0] if speakers else '',
            'type': 'choice' if has_options else 'line'}
    return node, edges


def parse_script(text: str):
    """Parse declared records; graph-wide validity is checked separately."""
    if not isinstance(text, str):
        raise TypeError('parse_script expects a string')
    text = text.removeprefix('\ufeff')
    records = []
    seen = set()
    current = None
    body = []
    for lineno, line in enumerate(text.splitlines(), 1):
        match = HEADER.fullmatch(line)
        if match:
            if current is not None:
                records.append((current, body))
            current = match.group(1).strip()
            if not current or current in seen:
                raise ValueError(f'Line {lineno}: empty or duplicate record ID {current!r}')
            seen.add(current)
            body = []
        elif current is None:
            if line.strip():
                raise ValueError(f'Line {lineno}: text before the first record header')
        else:
            body.append((lineno, line))
    if current is not None:
        records.append((current, body))
    nodes, edges = [], []
    for identifier, lines in records:
        node, outgoing = _parse_record(identifier, lines)
        nodes.append(node)
        edges.extend(outgoing)
    return {'nodes': nodes, 'edges': edges}


def validate_graph(graph, terminals=('End',)):
    if not isinstance(graph, dict) or set(graph) != {'nodes', 'edges'}:
        raise ValueError('Graph must have exactly nodes and edges')
    if not isinstance(graph['nodes'], list) or not isinstance(graph['edges'], list):
        raise ValueError('nodes and edges must be arrays')
    if not isinstance(terminals, (list, tuple)) or any(
            not isinstance(t, str) or not t for t in terminals):
        raise ValueError('terminals must be an array of nonempty strings')
    if not graph['nodes']:
        raise ValueError('No declared nodes')
    ids = set()
    for node in graph['nodes']:
        if not isinstance(node, dict) or set(node) != {'id', 'text', 'speaker', 'type'}:
            raise ValueError('Invalid node fields')
        if any(not isinstance(v, str) for v in node.values()):
            raise ValueError('Node fields must be strings')
        if not node['id'] or node['id'] in ids or node['type'] not in ('line', 'choice'):
            raise ValueError(f'Invalid node ID or type: {node!r}')
        ids.add(node['id'])
    allowed = set(terminals)
    adjacency = {identifier: [] for identifier in ids}
    missing = []
    for edge in graph['edges']:
        if not isinstance(edge, dict) or set(edge) != {'from', 'to', 'text'}:
            raise ValueError('Invalid edge fields')
        if any(not isinstance(v, str) for v in edge.values()):
            raise ValueError('Edge fields must be strings')
        if edge['from'] not in ids:
            raise ValueError(f'Undeclared edge source: {edge["from"]!r}')
        if edge['to'] not in ids and edge['to'] not in allowed:
            missing.append((edge['from'], edge['to']))
        elif edge['to'] in ids:
            adjacency[edge['from']].append(edge['to'])
    if missing:
        raise ValueError(f'Unresolved nonterminal targets: {missing!r}')
    reached = set()
    pending = [graph['nodes'][0]['id']]
    while pending:
        identifier = pending.pop()
        if identifier in reached:
            continue
        reached.add(identifier)
        pending.extend(adjacency[identifier])
    unreachable = [node['id'] for node in graph['nodes'] if node['id'] not in reached]
    if unreachable:
        raise ValueError(f'Unreachable declared nodes: {unreachable!r}')
    return {'reachable_nodes': len(reached), 'external_targets': sorted(
        {edge['to'] for edge in graph['edges'] if edge['to'] not in ids})}


def _quote(value):
    # JSON double-quoted strings escape quotes, backslashes and newlines for DOT.
    return json.dumps(value, ensure_ascii=False)


def to_dot(graph):
    lines = ['digraph dialogue {', '  rankdir=LR;']
    for node in graph['nodes']:
        parts = [node['id']]
        if node['speaker']:
            parts.append(node['speaker'] + ': ' + node['text'])
        elif node['text']:
            parts.append(node['text'])
        shape = 'diamond' if node['type'] == 'choice' else 'box'
        lines.append('  ' + _quote(node['id']) + ' [shape=' + shape +
                     ', label=' + _quote('\n'.join(parts)) + '];')
    for edge in graph['edges']:
        lines.append('  ' + _quote(edge['from']) + ' -> ' + _quote(edge['to']) +
                     ' [label=' + _quote(edge['text']) + '];')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def _atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         dir=path.parent, delete=False) as stream:
            name = stream.name
            stream.write(content)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def execute(config):
    if not isinstance(config, dict):
        raise ValueError('Input must be a JSON object')
    supported = {'input_path', 'encoding', 'solution_path', 'json_path', 'dot_path', 'terminals'}
    unknown = set(config) - supported
    if unknown:
        raise ValueError(f'Unknown configuration keys: {sorted(unknown)!r}')
    defaults = {'input_path': '/app/script.txt', 'solution_path': '/app/solution.py',
                'json_path': '/app/dialogue.json', 'dot_path': '/app/dialogue.dot'}
    paths = {}
    for key, default in defaults.items():
        value = config.get(key, default)
        if not isinstance(value, str) or not value:
            raise ValueError(f'{key} must be a nonempty path string')
        paths[key] = Path(value).resolve()
    if len(set(paths.values())) != len(paths):
        raise ValueError('Input, solution, JSON and DOT paths must be distinct')
    own_path = Path(__file__).resolve()
    if any(paths[key] == own_path for key in ('input_path', 'json_path', 'dot_path')):
        raise ValueError('Input and graph artifacts must not overwrite the running module')
    encoding = config.get('encoding', 'utf-8-sig')
    if not isinstance(encoding, str) or not encoding:
        raise ValueError('encoding must be a nonempty string')
    terminals = config.get('terminals', ['End'])
    text = paths['input_path'].read_bytes().decode(encoding)
    graph = parse_script(text)
    checks = validate_graph(graph, terminals)
    dot = to_dot(graph)
    serialized = json.dumps(graph, ensure_ascii=False, indent=2) + '\n'
    if paths['solution_path'] != own_path:
        _atomic_write(paths['solution_path'], own_path.read_text(encoding='utf-8'))
    _atomic_write(paths['json_path'], serialized)
    _atomic_write(paths['dot_path'], dot)
    written = json.loads(paths['json_path'].read_text(encoding='utf-8'))
    validate_graph(written, terminals)
    fresh_text = paths['input_path'].read_bytes().decode(encoding)
    if written != parse_script(fresh_text):
        raise ValueError('Written JSON differs from a fresh source parse')
    if paths['dot_path'].read_text(encoding='utf-8') != to_dot(written):
        raise ValueError('Written DOT differs from graph rendering')
    if not paths['solution_path'].is_file():
        raise ValueError('Exported solution.py is missing')
    return {'ok': True, 'nodes': len(written['nodes']), 'edges': len(written['edges']),
            'validation': checks,
            'artifacts': {key: str(paths[key]) for key in
                          ('solution_path', 'json_path', 'dot_path')}}


def main():
    try:
        result = execute(json.load(sys.stdin))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)},
                         ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
