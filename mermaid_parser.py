"""
Parse Mermaid flowchart/graph definitions into nodes and edges.
Supports: graph TD/LR/BT/RL, flowchart, node shapes, arrow styles, subgraphs.
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
    style: Literal["arrow", "line", "dotted", "thick", "bidirectional"] = "arrow"


@dataclass
class Subgraph:
    """A named group of nodes (cluster)."""
    id: str
    label: str
    node_ids: list[str] = field(default_factory=list)


@dataclass
class MermaidDiagram:
    """Parsed Mermaid diagram: direction, nodes, edges, subgraphs."""
    direction: Literal["TD", "LR", "BT", "RL"]
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    subgraphs: list[Subgraph] = field(default_factory=list)

    def get_node(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None


# Mermaid node shape patterns
NODE_PATTERNS = [
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*([^\]\\]*?)\s*\]"), "rect"),
    (re.compile(r"([a-zA-Z0-9_]+)\s*\(\s*\(\s*([^)]*?)\s*\)\s*\)"), "circle"),   # ((text)) before round
    (re.compile(r"([a-zA-Z0-9_]+)\s*\(\s*(?!\()([^)]*?)\s*\)"), "round"),         # (text) not ((
    (re.compile(r"([a-zA-Z0-9_]+)\s*\{\s*\{\s*([^}]*?)\s*\}\s*\}"), "hexagon"),  # {{text}} before diamond
    (re.compile(r"([a-zA-Z0-9_]+)\s*\{\s*(?!\{)([^}]*?)\s*\}"), "diamond"),       # {text} not {{
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*/\s*([^\\]+)\s*\\\s*\]"), "trapezoid"),
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*\\\\s*([^/]+)\s*/\s*\]"), "trapezoid"),
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*/\s*([^/]+)\s*/\s*\]"), "parallelogram"),
    (re.compile(r"([a-zA-Z0-9_]+)\s*\[\s*\\\\s*([^\\]+)\s*\\\s*\]"), "parallelogram"),
]


def _normalize_id(s: str) -> str:
    """Ensure node id is valid for Slides (alphanumeric, underscore, 5-50 chars)."""
    s = re.sub(r"[^a-zA-Z0-9_]", "_", s.strip())
    if len(s) < 5:
        s = (s + "_____")[:5]
    return s[:50]


def _clean_label(label: str) -> str:
    """Replace HTML line breaks with newlines and strip whitespace."""
    return label.replace("<br/>", "\n").replace("<br>", "\n").strip()


def _ensure_node(diagram: MermaidDiagram, node_id: str, label: str | None = None) -> Node:
    existing = diagram.get_node(node_id)
    if existing:
        return existing
    n = Node(id=node_id, label=_clean_label(label or node_id), shape="rect")
    diagram.nodes.append(n)
    return n


def _parse_node_def(diagram: MermaidDiagram, token: str) -> str | None:
    token = token.strip()
    if not token or token in (
        "-->", "---", "->", "graph", "flowchart", "TD", "LR", "BT", "RL", "end", "style"
    ):
        return None

    for pat, shape in NODE_PATTERNS:
        m = pat.search(token)
        if m:
            nid = _normalize_id(m.group(1))
            label = _clean_label(m.group(2).strip()) if m.lastindex >= 2 else nid
            node = diagram.get_node(nid)
            if node:
                node.label = label
                node.shape = shape
            else:
                diagram.nodes.append(Node(id=nid, label=label, shape=shape))
            return nid

    if re.match(r"^[a-zA-Z0-9_]+$", token):
        nid = _normalize_id(token)
        _ensure_node(diagram, nid, token)
        return nid
    return None


def _parse_edge(
    diagram: MermaidDiagram, from_id: str, connector: str, to_id: str, label: str = ""
) -> None:
    if connector in ("-->", "->"):
        style: Literal["arrow", "line", "dotted", "thick", "bidirectional"] = "arrow"
    elif connector == "<-->":
        style = "bidirectional"
    elif connector == "---":
        style = "line"
    elif "-.-" in connector:
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


def _preprocess_subgraphs(
    lines: list[str],
) -> tuple[list[str], list[tuple[str, str, list[str]]]]:
    """
    Strip subgraph/end/internal-direction lines and collect subgraph membership.

    Returns:
        cleaned_lines: source lines without subgraph structural keywords
        raw_subgraphs: list of (raw_id, label, [raw_member_node_ids])
    """
    _SKIP_IDS = {"end", "graph", "flowchart", "subgraph", "direction", "style",
                 "TD", "LR", "BT", "RL", "TB"}
    raw_subgraphs: list[dict] = []
    sg_stack: list[dict] = []
    cleaned: list[str] = []

    for line in lines:
        stripped = line.strip()

        m_sg = re.match(r"subgraph\s+(\w+)(?:\s*\[\s*([^\]]*)\s*\])?\s*$", stripped, re.IGNORECASE)
        if m_sg:
            raw_id = m_sg.group(1)
            label = m_sg.group(2).strip() if m_sg.group(2) is not None else raw_id
            entry: dict = {"id": raw_id, "label": label, "raw_ids": []}
            raw_subgraphs.append(entry)
            sg_stack.append(entry)
            continue

        if stripped.lower() == "end" and sg_stack:
            sg_stack.pop()
            continue

        if re.match(r"direction\s+\w+\s*$", stripped, re.IGNORECASE) and sg_stack:
            continue

        cleaned.append(line)

        if sg_stack:
            # Collect node IDs via shape patterns
            for pat, _ in NODE_PATTERNS:
                for m2 in pat.finditer(stripped):
                    raw_id = m2.group(1)
                    for entry in sg_stack:
                        if raw_id not in entry["raw_ids"]:
                            entry["raw_ids"].append(raw_id)
            # Also collect bare IDs from edge lines (strip bracket content first)
            bare = re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}", "", stripped)
            for raw_id in re.findall(r"\b([a-zA-Z][a-zA-Z0-9_]*)\b", bare):
                if raw_id not in _SKIP_IDS:
                    for entry in sg_stack:
                        if raw_id not in entry["raw_ids"]:
                            entry["raw_ids"].append(raw_id)

    return cleaned, [(e["id"], e["label"], e["raw_ids"]) for e in raw_subgraphs]


def parse_mermaid(source: str) -> MermaidDiagram:
    """Parse Mermaid flowchart/graph source into MermaidDiagram."""
    direction: Literal["TD", "LR", "BT", "RL"] = "TD"
    diagram = MermaidDiagram(direction=direction)

    raw_lines = [ln.strip() for ln in source.split("\n") if not ln.strip().startswith("%%")]

    cleaned_lines, raw_subgraphs = _preprocess_subgraphs(raw_lines)
    sg_raw_ids: set[str] = {raw_id for raw_id, _, _ in raw_subgraphs}
    sg_norm_ids: set[str] = {_normalize_id(rid) for rid in sg_raw_ids}

    text = " ".join(cleaned_lines)

    if re.match(r"^\s*(?:flowchart|graph)\s", text, re.IGNORECASE):
        dir_match = re.search(r"(?:flowchart|graph)\s+(\w+)", text, re.IGNORECASE)
        if dir_match:
            d = dir_match.group(1).upper()
            if d in ("TD", "LR", "BT", "RL"):
                direction = d
                diagram.direction = direction

    parts = re.split(r"[;,]", text)
    # <--> and <-- must precede -- patterns in the alternation
    connector_re = re.compile(
        r"(<-->|<--|-\.->|-{2,}>|-{2,}|-={2,}>?)\s*(?:\|\s*([^|]*?)\s*\|)?\s*"
    )

    for part in parts:
        part = part.strip()
        if not part or re.match(r"^(?:graph|flowchart)\s+\w+$", part, re.IGNORECASE):
            continue

        pos = 0
        last_to_id = None
        while True:
            m = connector_re.search(part, pos)
            if not m:
                break
            conn = m.group(1)
            label = m.group(2) if m.lastindex >= 2 else ""

            left = part[pos : m.start()].strip()
            right_start = m.end()
            next_conn = connector_re.search(part, right_start)
            right_end = next_conn.start() if next_conn else len(part)
            right = part[right_start:right_end].strip()

            m_from = re.search(
                r"([a-zA-Z0-9_]+)(?:\s*(?:\[[^\]]*\]|\(+[^)]*\)+|\{+[^}]*\}+))?\s*$", left
            )
            from_id = m_from.group(1) if m_from else None
            to_id = re.match(r"([a-zA-Z0-9_]+)", right).group(1) if right else None

            # Reverse arrow: swap so edge always goes source → target
            if conn == "<--" and from_id and to_id:
                from_id, to_id = to_id, from_id
                conn = "-->"

            if from_id and to_id:
                if (
                    _normalize_id(from_id) not in sg_norm_ids
                    and _normalize_id(to_id) not in sg_norm_ids
                ):
                    _parse_node_def(diagram, from_id)
                    _parse_node_def(diagram, to_id)
                    _parse_edge(diagram, from_id, conn, to_id, label or "")
                last_to_id = to_id

            pos = m.end()

        if last_to_id is not None:
            for pat, shape in NODE_PATTERNS:
                for m2 in pat.finditer(part):
                    nid = _normalize_id(m2.group(1))
                    if nid in sg_norm_ids:
                        continue
                    label_text = _clean_label(m2.group(2).strip()) if m2.lastindex >= 2 else nid
                    node = diagram.get_node(nid)
                    if node is not None:
                        node.label = label_text
                        node.shape = shape
                    else:
                        diagram.nodes.append(Node(id=nid, label=label_text, shape=shape))
            continue

        _parse_node_def(diagram, part)

    # Remove any phantom nodes/edges whose IDs are subgraph container IDs
    diagram.nodes = [n for n in diagram.nodes if n.id not in sg_norm_ids]
    diagram.edges = [
        e for e in diagram.edges
        if e.from_id not in sg_norm_ids and e.to_id not in sg_norm_ids
    ]

    # Build Subgraph objects with normalized, deduplicated member IDs
    for raw_id, label, raw_member_ids in raw_subgraphs:
        member_ids: list[str] = []
        seen_m: set[str] = set()
        for rid in raw_member_ids:
            if rid in sg_raw_ids:
                continue  # skip nested subgraph IDs
            nid = _normalize_id(rid)
            if nid not in seen_m:
                seen_m.add(nid)
                member_ids.append(nid)
        diagram.subgraphs.append(Subgraph(id=_normalize_id(raw_id), label=label, node_ids=member_ids))

    # Deduplicate edges (keep first occurrence)
    seen_edges: set[tuple[str, str, str]] = set()
    unique_edges: list[Edge] = []
    for e in diagram.edges:
        key = (e.from_id, e.to_id, e.label)
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)
    diagram.edges = unique_edges

    return diagram
