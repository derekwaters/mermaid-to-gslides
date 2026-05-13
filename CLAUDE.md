# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mermaid-to-gslides** converts Mermaid flowchart definitions into Google Slides presentations. Mermaid nodes become shapes (rectangles, circles, diamonds, etc.) and edges become connector lines, positioned automatically using a hierarchical layout algorithm.

## Common Commands

**Run the tool:**
```bash
python main.py diagram.mmd
python main.py diagram.mmd --presentation-id <ID>
echo "graph TD; A-->B; B-->C;" | python main.py -
```

**Debug: inspect parsed diagram**
```bash
python -c "from mermaid_parser import parse_mermaid; print(parse_mermaid(open('example.mmd').read()))"
```

**Debug: check layout positions**
```bash
python -c "from mermaid_parser import parse_mermaid; from layout import layout_diagram; d = parse_mermaid(open('example.mmd').read()); print(layout_diagram(d))"
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Note:** There is currently no test framework or linter configured. Tests can be run ad-hoc with `python -m pytest` if pytest is installed, but are not set up in CI.

## Architecture

The tool follows a clear pipeline from text to API requests:

```
Mermaid text → Parser → Layout → Slides API requests → Google Slides
```

### Data Flow

1. **Parser** (`mermaid_parser.py`): Converts Mermaid syntax to `MermaidDiagram` with `Node` and `Edge` dataclasses
2. **Layout** (`layout.py`): Assigns (x, y) coordinates to each node using hierarchical topological sort
3. **Slides Builder** (`slides_builder.py`): Generates Google Slides API batch requests for shapes and connectors
4. **Main** (`main.py`): Orchestrates OAuth2 auth, presentation creation, and API calls

### Key Modules

**mermaid_parser.py**
- Parses Mermaid flowchart syntax (supports `graph TD/LR/BT/RL`, `flowchart`)
- Handles 7 node shapes: `[rect]`, `(round)`, `((circle))`, `{diamond}`, `{{hexagon}}`, trapezoid, parallelogram
- Regex-based parsing; node IDs are normalized to 5-50 alphanumeric chars with underscores
- Returns `MermaidDiagram` with direction, nodes, and edges (including style: arrow/line/dotted/thick)

**layout.py**
- Computes hierarchical layout using topological sort (BFS from sources)
- Returns node positions as (center_x, center_y) in EMU (English Metric Units)
- Respects diagram direction: TD/BT place nodes in rows, LR/RL in columns
- Centers nodes within available slide space with configurable margins and spacing

**slides_builder.py**
- Maps Mermaid shapes to Google Slides shape types (RECTANGLE, ELLIPSE, DIAMOND, etc.)
- Builds batch API requests: `createShape`, `insertText`, `createLine`, `updateLineProperties`
- Positions connectors using connection site indices (0=top, 1=right, 2=bottom, 3=left)

**main.py**
- Handles OAuth2 flow: loads/refreshes credentials, persists token
- Creates or appends to presentations
- Calls parser → slides_builder → batchUpdate

## Important Design Decisions

- **EMU units**: All positions are in Google Slides EMU (914,400 EMU per inch). Constants defined in `layout.py`.
- **Node ID normalization**: IDs must be 5-50 alphanumeric/underscore chars for Slides API. Short IDs are padded, invalid chars replaced with underscores.
- **Connection sites**: Lines attach to shapes at fixed indices (0=top, 1=right, 2=bottom, 3=left). Currently hardcoded to 1→3 (right→left); can be adjusted for better routing.
- **Layer assignment**: Topological BFS handles cycles by placing unreachable nodes at max_layer + 1. This avoids infinite loops but may not produce ideal layouts for highly cyclic graphs.
- **Deduplication**: Duplicate edges (same from_id, to_id, label) are removed after parsing; last-seen style wins.

## Setup & Credentials

- `credentials.json`: OAuth2 client ID from Google Cloud Console (Desktop app type). Required for first run.
- `token.json`: Auto-generated after first login; persists refresh token for future runs. Should be in `.gitignore`.
- Both paths are configurable via `--credentials` and `--token` CLI flags.

## Debugging & Common Issues

- **"No nodes or edges parsed"**: Check Mermaid syntax. The parser is regex-based; complex syntax edge cases may not be caught.
- **Nodes off-slide**: Large diagrams may exceed slide dimensions. Adjust spacing constants in `layout.py` (H_SPACING_EMU, V_SPACING_EMU) if needed.
- **Connector routing**: The current implementation uses fixed connection sites; complex node layouts may have overlapping lines. Future improvement: dynamic site selection or curve routing.
- **OAuth2 errors**: If token expires or credentials are invalid, delete `token.json` and re-run to trigger login flow.
- **Debug print in slides_builder.py:171**: `print(requests[13])` is leftover debug code; remove if refactoring.

## Testing

No test suite is currently set up. For ad-hoc testing:
- Use `example.mmd` or create test files with various Mermaid syntax
- Verify parsed output: `parse_mermaid(source)`
- Verify positions: `layout_diagram(diagram)`
- Verify API requests: inspect `build_requests()` output before calling Google API

