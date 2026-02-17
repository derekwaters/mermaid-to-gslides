"""
Simple hierarchical layout for flowchart nodes.
Assigns (x, y) positions in EMU (English Metric Units) for Google Slides.
1 inch = 914400 EMU, 1 pt = 12700 EMU.
"""
from collections import defaultdict, deque

from mermaid_parser import MermaidDiagram, Node

# Google Slides default slide size (10" x 7.5" in 4:3) in EMU
INCH_EMU = 914_400
SLIDE_WIDTH_EMU = 10 * INCH_EMU
SLIDE_HEIGHT_EMU = 7.5 * INCH_EMU

# Node box size and spacing
NODE_WIDTH_EMU = int(1.2 * INCH_EMU)
NODE_HEIGHT_EMU = int(0.5 * INCH_EMU)
H_SPACING_EMU = int(0.4 * INCH_EMU)
V_SPACING_EMU = int(0.3 * INCH_EMU)


def _build_adjacency(diagram: MermaidDiagram) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Build successors and predecessors per node."""
    succ: dict[str, list[str]] = defaultdict(list)
    pred: dict[str, list[str]] = defaultdict(list)
    for e in diagram.edges:
        succ[e.from_id].append(e.to_id)
        pred[e.to_id].append(e.from_id)
    for n in diagram.nodes:
        if n.id not in succ:
            succ[n.id] = []
        if n.id not in pred:
            pred[n.id] = []
    return dict(succ), dict(pred)


def _assign_layers(
    diagram: MermaidDiagram,
    succ: dict[str, list[str]],
    pred: dict[str, list[str]],
) -> dict[str, int]:
    """
    Assign each node to a layer (0, 1, 2, ...) for topological order.
    TD/LR: layer = distance from sources; BT/RL: layer = distance from sinks.
    """
    node_ids = {n.id for n in diagram.nodes}
    if not node_ids:
        return {}

    if diagram.direction in ("BT", "RL"):
        # Reverse: layers from sinks
        succ, pred = pred, succ

    # BFS from all sources (in-degree 0)
    in_degree = {nid: len(pred[nid]) for nid in node_ids}
    layers: dict[str, int] = {}
    q: deque[tuple[str, int]] = deque((nid, 0) for nid in node_ids if in_degree[nid] == 0)
    for nid in node_ids:
        if in_degree[nid] == 0 and nid not in layers:
            q.append((nid, 0))
    while q:
        nid, layer = q.popleft()
        if nid in layers:
            continue
        layers[nid] = layer
        for next_id in succ[nid]:
            in_degree[next_id] -= 1
            if in_degree[next_id] == 0:
                q.append((next_id, layer + 1))
    # Nodes not reached (cycles): put at max layer + 1
    max_layer = max(layers.values()) if layers else 0
    for nid in node_ids:
        if nid not in layers:
            layers[nid] = max_layer + 1
    return layers


def _layer_groups(layers: dict[str, int]) -> dict[int, list[str]]:
    """Group node ids by layer index."""
    groups: dict[int, list[str]] = defaultdict(list)
    for nid, layer in layers.items():
        groups[layer].append(nid)
    for k in groups:
        groups[k].sort()
    return dict(groups)


def layout_diagram(diagram: MermaidDiagram) -> dict[str, tuple[int, int]]:
    """
    Compute (x_emu, y_emu) for each node. Origin top-left; x right, y down.
    Returns map node_id -> (center_x_emu, center_y_emu).
    """
    if not diagram.nodes:
        return {}

    succ, pred = _build_adjacency(diagram)
    layers = _assign_layers(diagram, succ, pred)
    layer_groups = _layer_groups(layers)
    n_layers = len(layer_groups)
    if n_layers == 0:
        return {}

    # Margins
    margin_x = int(0.5 * INCH_EMU)
    margin_y = int(0.5 * INCH_EMU)
    content_width = SLIDE_WIDTH_EMU - 2 * margin_x
    content_height = SLIDE_HEIGHT_EMU - 2 * margin_y

    positions: dict[str, tuple[int, int]] = {}

    if diagram.direction in ("TD", "BT"):
        # Vertical flow: layers are rows
        max_nodes_in_layer = max(len(nodes) for nodes in layer_groups.values())
        row_height = NODE_HEIGHT_EMU + V_SPACING_EMU
        total_height = n_layers * row_height
        start_y = margin_y + (content_height - total_height) // 2 if total_height < content_height else margin_y
        for layer_idx in range(n_layers):
            nodes_in_layer = layer_groups.get(layer_idx, [])
            n_nodes = len(nodes_in_layer)
            row_width = n_nodes * NODE_WIDTH_EMU + (n_nodes - 1) * H_SPACING_EMU if n_nodes else 0
            start_x = margin_x + (content_width - row_width) // 2 if row_width < content_width else margin_x
            for i, nid in enumerate(nodes_in_layer):
                x = start_x + i * (NODE_WIDTH_EMU + H_SPACING_EMU) + NODE_WIDTH_EMU // 2
                if diagram.direction == "BT":
                    row_idx = n_layers - 1 - layer_idx
                    y = margin_y + row_idx * row_height + NODE_HEIGHT_EMU // 2
                else:
                    y = start_y + layer_idx * row_height + NODE_HEIGHT_EMU // 2
                positions[nid] = (x, y)
    else:
        # LR or RL: layers are columns
        max_nodes_in_layer = max(len(nodes) for nodes in layer_groups.values())
        col_width = NODE_WIDTH_EMU + H_SPACING_EMU
        total_width = n_layers * col_width
        start_x = margin_x + (content_width - total_width) // 2 if total_width < content_width else margin_x
        for layer_idx in range(n_layers):
            nodes_in_layer = layer_groups.get(layer_idx, [])
            n_nodes = len(nodes_in_layer)
            col_height = n_nodes * NODE_HEIGHT_EMU + (n_nodes - 1) * V_SPACING_EMU if n_nodes else 0
            start_y = margin_y + (content_height - col_height) // 2 if col_height < content_height else margin_y
            for i, nid in enumerate(nodes_in_layer):
                if diagram.direction == "RL":
                    col_idx = n_layers - 1 - layer_idx
                    x = start_x + col_idx * col_width + NODE_WIDTH_EMU // 2
                else:
                    x = start_x + layer_idx * col_width + NODE_WIDTH_EMU // 2
                y = start_y + i * (NODE_HEIGHT_EMU + V_SPACING_EMU) + NODE_HEIGHT_EMU // 2
                positions[nid] = (x, y)

    return positions


def get_node_size_emu() -> tuple[int, int]:
    """Return (width, height) in EMU for node shapes."""
    return NODE_WIDTH_EMU, NODE_HEIGHT_EMU
