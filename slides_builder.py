"""
Build Google Slides from a Mermaid diagram: create shapes and connector lines.
Uses Google Slides API with OAuth2 credentials.
"""
from __future__ import annotations

from mermaid_parser import MermaidDiagram, Node
from layout import layout_diagram, get_node_size_emu, SLIDE_WIDTH_EMU, SLIDE_HEIGHT_EMU

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
    """AffineTransform: translate so center (cx, cy) becomes top-left of element (scale 1)."""
    # Top-left of shape = center - half size
    tx = cx_emu - w_emu // 2
    ty = cy_emu - h_emu // 2
    return {
        "scaleX": 1,
        "scaleY": 1,
        "translateX": tx,
        "translateY": ty,
        "unit": "EMU",
    }


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
    requests: list[dict] = []

    # 1) Create shapes for each node
    for node in diagram.nodes:
        pos = positions.get(node.id)
        if not pos:
            continue
        cx, cy = pos
        object_id = _make_object_id("node", node.id)
        shape_type = SHAPE_TYPE_MAP.get(node.shape, "RECTANGLE")
        requests.append({
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
        # Insert text (must be separate request)
        requests.append({
            "insertText": {
                "objectId": object_id,
                "text": node.label[:100],
                "insertionIndex": 0,
            },
        })

    # 2) Create connector lines between shapes
    line_index = [0]

    def next_line_id() -> str:
        line_index[0] += 1
        return _make_object_id("line", str(line_index[0]))

    for edge in diagram.edges:
        from_obj = _make_object_id("node", edge.from_id)
        to_obj = _make_object_id("node", edge.to_id)
        line_id = next_line_id()
        # Create line with placeholder position; we'll attach with UpdateLineProperties + RerouteLine
        requests.append({
            "createLine": {
                "objectId": line_id,
                "lineCategory": "STRAIGHT",
                "lineType": "STRAIGHT_CONNECTOR_1",
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
        # Attach connector to shapes (connection site: 0=top, 1=right, 2=bottom, 3=left)
        requests.append({
            "updateLineProperties": {
                "objectId": line_id,
                "lineProperties": {
                    "startConnection": {
                        "connectedObjectId": from_obj,
                        "connectionSiteIndex": 1,
                    },
                    "endConnection": {
                        "connectedObjectId": to_obj,
                        "connectionSiteIndex": 3,
                    },
                },
                "fields": "lineProperties.startConnection,lineProperties.endConnection",
            },
        })
        requests.append({
            "rerouteLine": {
                "objectId": line_id,
            },
        })

    return requests


def create_diagram_slide(service, presentation_id: str, diagram: MermaidDiagram) -> str | None:
    """
    Create a new blank slide, add the diagram to it, and return the new slide's object ID.
    """
    # Create blank slide
    pres = service.presentations().get(presentationId=presentation_id).execute()
    slides = pres.get("slides", [])
    # Use first slide's page or create new one
    create_slide = {
        "createSlide": {
            "slideLayoutReference": {"predefinedLayout": "BLANK"},
        },
    }
    resp = service.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": [create_slide]},
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
