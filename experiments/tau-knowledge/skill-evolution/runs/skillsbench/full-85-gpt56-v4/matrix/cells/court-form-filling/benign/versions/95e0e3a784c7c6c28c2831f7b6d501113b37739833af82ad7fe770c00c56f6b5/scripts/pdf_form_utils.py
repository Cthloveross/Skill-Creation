"""Small dependency-free helpers for AcroForm and XFA packet inspection."""
from xml.etree import ElementTree as ET


def deref(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


def local_name(element):
    return element.tag.rsplit("}", 1)[-1]


def xfa_packets(acroform):
    """Return {packet_name: stream_object} for an XFA packet array, or {}."""
    xfa = acroform.get("/XFA")
    if not xfa:
        return {}
    xfa = deref(xfa)
    if not isinstance(xfa, (list, tuple)):
        raise ValueError("unsupported XFA representation (expected packet array)")
    packets = {}
    for index in range(0, len(xfa) - 1, 2):
        packets[str(xfa[index])] = deref(xfa[index + 1])
    return packets


def xfa_dataset_root(packets):
    stream = packets.get("datasets")
    if stream is None:
        raise ValueError("XFA form has no datasets packet")
    try:
        return stream, ET.fromstring(stream.get_data())
    except ET.ParseError as exc:
        raise ValueError("XFA datasets packet is not parseable XML") from exc


def xfa_data_instance(dataset_root):
    data = next((e for e in dataset_root.iter() if local_name(e) == "data"), None)
    if data is None:
        raise ValueError("XFA datasets packet has no xfa:data element")
    children = list(data)
    if not children:
        raise ValueError("XFA datasets packet has no form data instance")
    return children[0]


def segment_name(element, siblings):
    """A stable, copyable path segment; indexes only repeated same-name siblings."""
    name = local_name(element)
    same = [x for x in siblings if local_name(x) == name]
    if len(same) > 1:
        return "%s[%d]" % (name, same.index(element))
    return name


def node_path(node, root):
    nodes = []
    # ElementTree has no parent links; this function is intentionally unused externally.
    raise NotImplementedError


def enumerate_xfa_data(instance):
    """List editable leaf nodes as exact slash paths relative to the data instance."""
    result = []

    def walk(element, path):
        children = list(element)
        if not children:
            # Nodes explicitly declared groups are structural even if currently empty.
            is_group = any(key.rsplit("}", 1)[-1] == "dataNode" and value == "dataGroup"
                           for key, value in element.attrib.items())
            if not is_group:
                result.append({"path": path, "value": element.text or ""})
            return
        for child in children:
            walk(child, path + "/" + segment_name(child, children))

    walk(instance, local_name(instance))
    return result


def parse_path_segment(segment):
    if segment.endswith("]") and "[" in segment:
        base, possible_index = segment.rsplit("[", 1)
        if possible_index[:-1].isdigit():
            return base, int(possible_index[:-1])
    return segment, 0


def find_xfa_data_node(instance, path):
    """Resolve a path emitted by enumerate_xfa_data; reject malformed/nonexistent paths."""
    pieces = [p for p in str(path).split("/") if p]
    if not pieces:
        raise KeyError(path)
    first, first_index = parse_path_segment(pieces[0])
    if first != local_name(instance) or first_index != 0:
        raise KeyError(path)
    current = instance
    for piece in pieces[1:]:
        wanted, occurrence = parse_path_segment(piece)
        candidates = [child for child in list(current) if local_name(child) == wanted]
        if occurrence >= len(candidates):
            raise KeyError(path)
        current = candidates[occurrence]
    return current


def text_content(element):
    return " ".join("".join(element.itertext()).split())


def enumerate_xfa_template(packets, data_paths):
    """Provide labels and legal check values from a template packet when present."""
    stream = packets.get("template")
    if stream is None:
        return []
    try:
        root = ET.fromstring(stream.get_data())
    except ET.ParseError:
        return []
    names_to_paths = {}
    for path in data_paths:
        leaf = parse_path_segment(path.split("/")[-1])[0]
        names_to_paths.setdefault(leaf, []).append(path)
    result = []

    def walk(element, path):
        name = element.attrib.get("name")
        current = path + ("/" + name if name else "")
        if local_name(element) in ("field", "exclGroup") and name:
            caption = " ".join(text_content(c) for c in element if local_name(c) == "caption").strip()
            ui = []
            item_values = []
            for descendant in element.iter():
                if descendant is element:
                    continue
                tag = local_name(descendant)
                if tag in ("textEdit", "numericEdit", "dateTimeEdit", "checkButton", "choiceList"):
                    ui.append(tag)
                if local_name(descendant) in ("items",):
                    item_values.extend(text_content(c) for c in descendant)
            result.append({
                "path": current,
                "name": name,
                "caption": caption,
                "ui": sorted(set(ui)),
                "item_values": item_values,
                "matching_data_paths": names_to_paths.get(name, []),
            })
        for child in element:
            walk(child, current)

    walk(root, "")
    return result
