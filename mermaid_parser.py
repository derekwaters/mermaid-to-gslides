"""
Parse Mermaid flowchart/graph definitions into nodes and edges.
Supports: graph TD/LR/BT/RL, flowchart, node shapes, arrow styles.
"""
import re
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Node:
    """A diagram node with id, label, and shape type."""
    id: str
    label: str
    shape: Literal["rect", "round", "circle", "diamond", "hexagon", "trapezoid", "parallelogram"] = "rect"


@dataclass
class Edge:
    """A directed edge between two nodes, with optional label."""
    from_id: str
    to_id: str
    label: str = ""
    style: Literal["arrow", "line", "dotted", "thick"] = "arrow"


@dataclass
class MermaidDiagram:
    """Parsed Mermaid diagram: direction, nodes, edges."""
    direction: Literal["TD", "LR", "BT", "RL"]
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def get_node(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None


# Mermaid node shape patterns (id may be in brackets/parens with label)
# id or id[text] or id(text) or id((text)) or id{text} or id{{text}} or id[/text\] or id[\text/] or id[/text/]
NODE_PATTERNS = [
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*([^\]\\]*?)\s*\]"), "rect"),       # [text]
    (re.compile(r"([a-zA-Z0-9_]+)\s*\(\s*\(\s*([^)]*?)\s*\)\s*\)"), "circle"),  # ((text)) - before round
    (re.compile(r"([a-zA-Z0-9_]+)\s*\(\s*(?!\()([^)]*?)\s*\)"), "round"),    # (text) - round, not ((
    (re.compile(r"([a-zA-Z0-9_]+)\s*\{\s*\{\s*([^}]*?)\s*\}\s*\}"), "hexagon"), # {{text}} - before diamond
    (re.compile(r"([a-zA-Z0-9_]+)\s*\{\s*(?!\{)([^}]*?)\s*\}"), "diamond"), # {text} - diamond, not {{
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*/\s*([^\\]+)\s*\\\s*\]"), "trapezoid"),  # [/text\]
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*\\\\s*([^/]+)\s*/\s*\]"), "trapezoid"),  # [\text/] (backslash)
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*/\s*([^/]+)\s*/\s*\]"), "parallelogram"), # [/text/]
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*\\\\s*([^\\]+)\s*\\\s*\]"), "parallelogram"), # [\text\]
]

# Edge patterns: --> --- -.-> ==> and with optional |label|
EDGE_ARROW = re.compile(
    r"([a-zA-Z0-9_]+)\s*"
    r"(-{2,3}|-\.-|-={2})\s*"
    r"(?:>\s*)?"
    r"(?:\|\s*([^|]*?)\s*\|)?\s*"
    r"([a-zA-Z0-9_]+)"
)
# Simpler: just match A-->B or A---B (no label)
EDGE_SIMPLE = re.compile(r"([a-zA-Z0-9_]+)\s*(-{2,3}|-\.-|-={2})\s*>?\s*([a-zA-Z0-9_]+)")


def _normalize_id(s: str) -> str:
    """Ensure node id is valid for Slides (alphanumeric, underscore, 5-50 chars)."""
    s = re.sub(r"[^a-zA-Z0-9_]", "_", s.strip())
    if len(s) < 5:
        s = (s + "_____")[:5]
    return s[:50]


def _parse_direction(line: str) -> Literal["TD", "LR", "BT", "RL"] | None:
    """Extract flowchart direction from first line."""
    line = line.strip().upper()
    if "LR" in line:
        return "LR"
    if "RL" in line:
        return "RL"
    if "BT" in line:
        return "BT"
    return "TD"  # default and TD


def _ensure_node(diagram: MermaidDiagram, node_id: str, label: str | None = None) -> Node:
    """Get existing node or create a default one."""
    existing = diagram.get_node(node_id)
    if existing:
        return existing
    n = Node(id=node_id, label=label or node_id, shape="rect")
    diagram.nodes.append(n)
    return n


def _parse_node_def(diagram: MermaidDiagram, token: str) -> str | None:
    """
    Parse a single node definition token. Add node to diagram, return node id.
    """
    token = token.strip()
    if not token or token in ("-->", "---", "->", "graph", "flowchart", "TD", "LR", "BT", "RL", "end"):
        return None

    # Check each node shape pattern
    for pat, shape in NODE_PATTERNS:
        m = pat.search(token)
        if m:
            nid = _normalize_id(m.group(1))
            label = m.group(2).strip() if m.lastindex >= 2 else nid
            node = diagram.get_node(nid)
            if node:
                node.label = label
                node.shape = shape
            else:
                diagram.nodes.append(Node(id=nid, label=label, shape=shape))
            return nid

    # Plain id (word)
    if re.match(r"^[a-zA-Z0-9_]+$", token):
        nid = _normalize_id(token)
        _ensure_node(diagram, nid, token)
        return nid
    return None


def _parse_edge(diagram: MermaidDiagram, from_id: str, connector: str, to_id: str, label: str = "") -> None:
    if connector in ("-->", "->"):
        style = "arrow"
    elif connector == "---":
        style = "line"
    elif "-.-" in connector or "-.->" in connector:
        style = "dotted"
    elif "==" in connector:
        style = "thick"
    else:
        style = "arrow"
    from_norm = _normalize_id(from_id)
    to_norm = _normalize_id(to_id)
    _ensure_node(diagram, from_norm, from_id)
    _ensure_node(diagram, to_norm, to_id)
    diagram.edges.append(Edge(from_id=from_norm, to_id=to_norm, label=label.strip(), style=style))


def parse_mermaid(source: str) -> MermaidDiagram:
    """
    Parse Mermaid flowchart/graph source into MermaidDiagram.
    """
    direction: Literal["TD", "LR", "BT", "RL"] = "TD"
    diagram = MermaidDiagram(direction=direction)

    # Normalize: single line or multi-line, strip comments
    lines = []
    for line in source.split("\n"):
        line = line.strip()
        if line.startswith("%%"):
            continue
        lines.append(line)
    text = " ".join(lines)

    # First token: graph or flowchart + direction
    if re.match(r"^\s*(?:flowchart|graph)\s", text, re.IGNORECASE):
        dir_match = re.search(r"(?:flowchart|graph)\s+(\w+)", text, re.IGNORECASE)
        if dir_match:
            d = dir_match.group(1).upper()
            if d in ("TD", "LR", "BT", "RL"):
                direction = d
                diagram.direction = direction

    # Split by semicolon and comma to get statements
    parts = re.split(r"[;,]", text)
    for part in parts:
        part = part.strip()
        if not part or re.match(r"^(?:graph|flowchart)\s+\w+$", part, re.IGNORECASE):
            continue

        # Find connectors (--> or --- etc); from_id/to_id may have trailing [text] or {text}
        connector_re = re.compile(r"(-\.->|-{2,}>|-{2,}|-={2,}>?)\s*(?:\|\s*([^|]*?)\s*\|)?\s*")
        pos = 0
        last_to_id = None
        while True:
            m = connector_re.search(part, pos)
            if not m:
                break
            conn = m.group(1)
            label = m.group(2) if m.lastindex >= 2 else ""
            # Text before connector: may be "A[Start]" or "A" or "B{Decision}"
            left = part[pos : m.start()].strip()
            # Text after connector (until next connector or end): "B{Decision}" or "B"
            right_start = m.end()
            next_conn = connector_re.search(part, right_start)
            right_end = next_conn.start() if next_conn else len(part)
            right = part[right_start:right_end].strip()
            m_from = re.search(r"([a-zA-Z0-9_]+)(?:\s*(?:\[[^\]]*\]|\(+[^)]*\)+|\{+[^}]*\}+))?\s*$", left)
            from_id = m_from.group(1) if m_from else None
            to_id = re.match(r"([a-zA-Z0-9_]+)", right).group(1) if right else None
            if from_id and to_id:
                _parse_node_def(diagram, from_id)
                _parse_node_def(diagram, to_id)
                _parse_edge(diagram, from_id, conn, to_id, label or "")
                last_to_id = to_id
            pos = m.end()
        if last_to_id is not None:
            # Also parse any node shape definitions in this part (e.g. B{Decision})
            for pat, shape in NODE_PATTERNS:
                for m in pat.finditer(part):
                    nid = _normalize_id(m.group(1))
                    label = m.group(2).strip() if m.lastindex >= 2 else nid
                    node = diagram.get_node(nid)
                    if node is not None:
                        node.label = label
                        node.shape = shape
                    else:
                        diagram.nodes.append(Node(id=nid, label=label, shape=shape))
            continue

        # Single node definition (no edges in this part)
        _parse_node_def(diagram, part)

    # Deduplicate edges (keep first)
    seen_edges = set()
    unique_edges = []
    for e in diagram.edges:
        key = (e.from_id, e.to_id, e.label)
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)
    diagram.edges = unique_edges

    return diagram
