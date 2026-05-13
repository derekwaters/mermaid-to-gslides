"""
Build Google Slides from a Mermaid diagram: create shapes and connector lines.
Uses Google Slides API with OAuth2 credentials.
"""
from __future__ import annotations

from mermaid_parser import MermaidDiagram, Node, Subgraph
from layout import layout_diagram, get_node_size_emu

# Shape type mapping: Mermaid shape -> Google Slides API shape type
SHAPE_TYPE_MAP = {
    "rect": "RECTANGLE",
    "round": "ROUND_RECTANGLE",
    "circle": "ELLIPSE",
    "diamond": "DIAMOND",
    "hexagon": "HEXAGON",
    "trapezoid": "TRAPEZOID",
    "parallelogram": "PARALLELOGRAM",
}

_INCH_EMU = 914_400
_LABEL_W_EMU = int(0.8 * _INCH_EMU)
_LABEL_H_EMU = int(0.25 * _INCH_EMU)
_SG_PADDING_EMU = int(0.25 * _INCH_EMU)  # padding around subgraph node cluster


def _make_object_id(prefix: str, suffix: str) -> str:
    """Slides object IDs: alphanumeric/underscore, 5-50 chars."""
    s = f"{prefix}_{suffix}".replace("-", "_")[:50]
    return (s + "_____")[:5] if len(s) < 5 else s


def _size_emu(w_emu: int, h_emu: int) -> dict:
    return {
        "width": {"magnitude": w_emu, "unit": "EMU"},
        "height": {"magnitude": h_emu, "unit": "EMU"},
    }


def _transform_emu(cx_emu: int, cy_emu: int, w_emu: int, h_emu: int) -> dict:
    """AffineTransform placing the shape's center at (cx, cy)."""
    tx = cx_emu - w_emu // 2
    ty = cy_emu - h_emu // 2
    return {
        "scaleX": 1,
        "scaleY": 1,
        "translateX": tx,
        "translateY": ty,
        "unit": "EMU",
    }


def _connection_sites(direction: str) -> tuple[int, int]:
    """Return (from_site, to_site) connection site indices for the diagram direction.
    Site indices: 0=top, 1=right, 2=bottom, 3=left."""
    if direction == "TD":
        return 2, 0  # bottom of source → top of destination
    elif direction == "BT":
        return 0, 2  # top → bottom
    elif direction == "RL":
        return 3, 1  # left → right
    else:  # LR
        return 1, 3  # right → left


def _line_properties(style: str, from_site: int, to_site: int, from_obj: str, to_obj: str) -> dict:
    dash = "DOT" if style == "dotted" else "SOLID"
    weight = 3 * 12700 if style == "thick" else 12700  # ~2.25pt vs ~1pt in EMU
    end_arrow = "NONE" if style == "line" else "OPEN_ARROW"
    start_arrow = "OPEN_ARROW" if style == "bidirectional" else "NONE"
    return {
        "startConnection": {"connectedObjectId": from_obj, "connectionSiteIndex": from_site},
        "endConnection": {"connectedObjectId": to_obj, "connectionSiteIndex": to_site},
        "dashStyle": dash,
        "weight": {"magnitude": weight, "unit": "EMU"},
        "endArrow": end_arrow,
        "startArrow": start_arrow,
    }


def _subgraph_requests(
    page_id: str,
    sg: Subgraph,
    positions: dict[str, tuple[int, int]],
    node_w: int,
    node_h: int,
) -> list[dict]:
    """Create a background rectangle with label for a subgraph cluster."""
    sg_positions = [positions[nid] for nid in sg.node_ids if nid in positions]
    if not sg_positions:
        return []

    min_cx = min(cx for cx, _ in sg_positions)
    max_cx = max(cx for cx, _ in sg_positions)
    min_cy = min(cy for _, cy in sg_positions)
    max_cy = max(cy for _, cy in sg_positions)

    box_x = min_cx - node_w // 2 - _SG_PADDING_EMU
    box_y = min_cy - node_h // 2 - _SG_PADDING_EMU
    box_w = (max_cx + node_w // 2 + _SG_PADDING_EMU) - box_x
    box_h = (max_cy + node_h // 2 + _SG_PADDING_EMU) - box_y

    box_id = _make_object_id("sg", sg.id)
    reqs: list[dict] = [
        {
            "createShape": {
                "objectId": box_id,
                "shapeType": "RECTANGLE",
                "elementProperties": {
                    "pageObjectId": page_id,
                    "size": _size_emu(box_w, box_h),
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": box_x,
                        "translateY": box_y,
                        "unit": "EMU",
                    },
                },
            },
        },
        {
            "updateShapeProperties": {
                "objectId": box_id,
                "shapeProperties": {
                    "shapeBackgroundFill": {
                        "solidFill": {
                            "color": {"rgbColor": {"red": 0.96, "green": 0.96, "blue": 0.98}},
                            "alpha": 0.9,
                        },
                    },
                    "outline": {
                        "outlineFill": {
                            "solidFill": {
                                "color": {"rgbColor": {"red": 0.2, "green": 0.2, "blue": 0.2}},
                            },
                        },
                        "weight": {"magnitude": 12700, "unit": "EMU"},
                        "dashStyle": "SOLID",
                    },
                    "contentAlignment": "TOP",
                },
                "fields": "shapeBackgroundFill,outline,contentAlignment",
            },
        },
    ]
    if sg.label:
        reqs.append({
            "insertText": {
                "objectId": box_id,
                "text": sg.label,
                "insertionIndex": 0,
            },
        })
    return reqs


def build_requests(
    diagram: MermaidDiagram,
    page_object_id: str,
) -> list[dict]:
    """
    Build list of Slides API batchUpdate requests to create the diagram on the given page.
    Returns list of request objects for presentations().batchUpdate(body={'requests': [...]}).
    """
    positions = layout_diagram(diagram)
    w_emu, h_emu = get_node_size_emu()
    from_site, to_site = _connection_sites(diagram.direction)

    # Subgraph background boxes come first so they render behind node shapes
    bg_requests: list[dict] = []
    for sg in diagram.subgraphs:
        bg_requests.extend(_subgraph_requests(page_object_id, sg, positions, w_emu, h_emu))

    node_requests: list[dict] = []
    for node in diagram.nodes:
        pos = positions.get(node.id)
        if not pos:
            continue
        cx, cy = pos
        object_id = _make_object_id("node", node.id)
        shape_type = SHAPE_TYPE_MAP.get(node.shape, "RECTANGLE")
        node_requests.append({
            "createShape": {
                "objectId": object_id,
                "shapeType": shape_type,
                "elementProperties": {
                    "pageObjectId": page_object_id,
                    "size": _size_emu(w_emu, h_emu),
                    "transform": _transform_emu(cx, cy, w_emu, h_emu),
                },
            },
        })
        node_requests.append({
            "insertText": {
                "objectId": object_id,
                "text": node.label[:100],
                "insertionIndex": 0,
            },
        })

    edge_requests: list[dict] = []
    line_counter = [0]

    def next_line_id() -> str:
        line_counter[0] += 1
        return _make_object_id("line", str(line_counter[0]))

    for edge in diagram.edges:
        from_obj = _make_object_id("node", edge.from_id)
        to_obj = _make_object_id("node", edge.to_id)
        line_id = next_line_id()
        edge_requests.append({
            "createLine": {
                "objectId": line_id,
                "lineCategory": "STRAIGHT",
                "elementProperties": {
                    "pageObjectId": page_object_id,
                    "size": _size_emu(1, 1),
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": 0,
                        "translateY": 0,
                        "unit": "EMU",
                    },
                },
            },
        })
        edge_requests.append({
            "updateLineProperties": {
                "objectId": line_id,
                "lineProperties": _line_properties(edge.style, from_site, to_site, from_obj, to_obj),
                "fields": "startConnection,endConnection,dashStyle,weight,endArrow,startArrow",
            },
        })

        if edge.label:
            from_pos = positions.get(edge.from_id)
            to_pos = positions.get(edge.to_id)
            if from_pos and to_pos:
                mx = (from_pos[0] + to_pos[0]) // 2
                my = (from_pos[1] + to_pos[1]) // 2
                lbl_id = _make_object_id("lbl", str(line_counter[0]))
                edge_requests.append({
                    "createShape": {
                        "objectId": lbl_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": page_object_id,
                            "size": _size_emu(_LABEL_W_EMU, _LABEL_H_EMU),
                            "transform": _transform_emu(mx, my, _LABEL_W_EMU, _LABEL_H_EMU),
                        },
                    },
                })
                edge_requests.append({
                    "insertText": {
                        "objectId": lbl_id,
                        "text": edge.label[:50],
                        "insertionIndex": 0,
                    },
                })

    return bg_requests + node_requests + edge_requests


def create_diagram_slide(service, presentation_id: str, diagram: MermaidDiagram) -> str | None:
    """
    Create a new blank slide, add the diagram to it, and return the new slide's object ID.
    """
    resp = service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": [{"createSlide": {"slideLayoutReference": {"predefinedLayout": "BLANK"}}}]},
    ).execute()
    create_reply = next(
        (r for r in resp.get("replies", []) if "createSlide" in r),
        None,
    )
    if not create_reply:
        return None
    page_id = create_reply["createSlide"]["objectId"]

    requests = build_requests(diagram, page_id)
    if not requests:
        return page_id
    service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": requests},
    ).execute()
    return page_id
