"""AI-powered graph features using the Anthropic Claude API."""

import json
import os
import re
from typing import Optional

import anthropic


def _client() -> anthropic.AsyncAnthropic:
    """Return an async Anthropic client using ANTHROPIC_API_KEY."""
    return anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _extract_json(text: str) -> list[dict]:
    """Pull a JSON array out of *text*, stripping any markdown code fences."""
    # Strip ```json ... ``` or ``` ... ``` wrappers if present.
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    raw = match.group(1) if match else text.strip()
    result = json.loads(raw)
    if not isinstance(result, list):
        raise ValueError("Expected a JSON array from the model")
    return result


def _extract_json_object(text: str) -> dict:
    """Pull a JSON object out of *text*, stripping any markdown code fences."""
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    raw = match.group(1) if match else text.strip()
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object from the model")
    return result


async def suggest_relationships(
    nodes: list[dict],
    existing_edges: Optional[list[dict]] = None,
) -> list[dict]:
    """Ask Claude to suggest up to 5 new relationships between the given nodes.

    Each element of *nodes* must have at least ``id`` and ``label`` keys.
    Elements of *existing_edges* (optional) must have ``source_id`` and
    ``target_id`` keys; Claude will be instructed to avoid re-suggesting them.

    Args:
        nodes:          List of node dicts, each with ``id`` and ``label``.
        existing_edges: Optional list of edge dicts already present in the map.

    Returns:
        A list of up to 5 dicts, each containing:
        ``source_id`` (str), ``target_id`` (str), ``reason`` (str).

    Raises:
        anthropic.APIError: On network or API-level failures.
        ValueError:         If the model returns unparseable JSON.
    """
    if not nodes:
        return []

    node_lines = "\n".join(f'- id={n["id"]}  label="{n["label"]}"' for n in nodes)

    existing_pairs = ""
    if existing_edges:
        pairs = [f'({e["source_id"]} → {e["target_id"]})' for e in existing_edges]
        existing_pairs = (
            "\n\nExisting edges (do NOT suggest these again):\n"
            + ", ".join(pairs)
        )

    prompt = (
        "You are a knowledge graph assistant.\n\n"
        "Below is a list of nodes in a mind map, each with a unique ID and a label:\n\n"
        f"{node_lines}"
        f"{existing_pairs}\n\n"
        "Suggest up to 5 meaningful directed relationships between pairs of nodes "
        "that do not already have an edge. Focus on semantic connections that would "
        "genuinely help someone understand how these concepts relate.\n\n"
        "Respond with ONLY a JSON array — no explanation, no markdown prose. "
        "Each element must have exactly three string fields:\n"
        '  "source_id"  — the id of the source node\n'
        '  "target_id"  — the id of the target node\n'
        '  "reason"     — one sentence explaining the relationship\n\n'
        "Example:\n"
        '[{"source_id": "abc", "target_id": "def", "reason": "abc influences def."}]'
    )

    client = _client()
    message = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text: str = message.content[0].text if message.content else "[]"
    return _extract_json(raw_text)


async def cluster_nodes(nodes: list[dict]) -> list[dict]:
    """Ask Claude to group *nodes* into semantic clusters based on their labels.

    Each element of *nodes* must have at least ``id`` and ``label`` keys.

    Args:
        nodes: List of node dicts, each with ``id`` and ``label``.

    Returns:
        A list of cluster dicts, each containing:
        ``cluster_name`` (str) and ``node_ids`` (list[str]).

    Raises:
        anthropic.APIError: On network or API-level failures.
        ValueError:         If the model returns unparseable JSON.
    """
    if not nodes:
        return []

    node_lines = "\n".join(f'- id={n["id"]}  label="{n["label"]}"' for n in nodes)

    prompt = (
        "You are a knowledge graph assistant.\n\n"
        "Below is a list of nodes in a mind map, each with a unique ID and a label:\n\n"
        f"{node_lines}\n\n"
        "Group these nodes into semantic clusters based on how their concepts relate. "
        "Give each cluster a concise, descriptive name. Every node must appear in "
        "exactly one cluster.\n\n"
        "Respond with ONLY a JSON array — no explanation, no markdown prose. "
        "Each element must have exactly two fields:\n"
        '  "cluster_name"  — a short descriptive name for the group (string)\n'
        '  "node_ids"      — list of node id strings belonging to this cluster\n\n'
        "Example:\n"
        '[{"cluster_name": "Infrastructure", "node_ids": ["abc", "def"]}]'
    )

    client = _client()
    message = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text: str = message.content[0].text if message.content else "[]"
    return _extract_json(raw_text)


def _compute_tree_layout(
    hierarchy: list[dict],
    all_node_ids: list[str],
    canvas_center: int = 600,
    x_spacing: int = 200,
    y_spacing: int = 150,
    y_start: int = 50,
) -> list[dict]:
    """Compute x/y positions from a parent-child hierarchy.

    Uses a bottom-up subtree-width calculation so siblings are centred cleanly
    under their parent at any depth, with no overlap.

    Args:
        hierarchy:     List of ``{"node_id": str, "parent_id": str | None}``.
        all_node_ids:  Complete list of IDs (orphan-detection guard).
        canvas_center: Horizontal centre of the canvas in pixels.
        x_spacing:     Horizontal space allocated per leaf node.
        y_spacing:     Vertical gap between levels in pixels.
        y_start:       Y coordinate of the root level.

    Returns:
        List of ``{"id": str, "x": int, "y": int, "level": int}`` dicts,
        one per entry in *all_node_ids*.
    """
    node_set = set(all_node_ids)

    # Build parent → children map, ignoring invalid parent refs.
    children: dict[str | None, list[str]] = {None: []}
    for item in hierarchy:
        nid = item.get("node_id", "")
        if not nid or nid not in node_set:
            continue
        children.setdefault(nid, [])
        pid: str | None = item.get("parent_id") or None
        if pid and pid not in node_set:
            pid = None
        if nid not in children[pid if pid is not None else None]:
            children.setdefault(pid, []).append(nid)

    # Any node not mentioned in the hierarchy becomes an extra root.
    mentioned = {item.get("node_id") for item in hierarchy}
    for nid in all_node_ids:
        if nid not in mentioned:
            children[None].append(nid)
            children.setdefault(nid, [])

    roots = children.get(None, [])
    if not roots:
        roots = all_node_ids[:1]

    # Count leaves in each subtree to determine horizontal space allocation.
    def _leaf_count(nid: str, seen: set[str]) -> int:
        if nid in seen:
            return 1
        seen.add(nid)
        kids = [k for k in children.get(nid, []) if k not in seen]
        if not kids:
            return 1
        return sum(_leaf_count(k, seen) for k in kids)

    positions: dict[str, dict[str, int]] = {}

    def _place(nid: str, level: int, x_left: float, seen: set[str]) -> float:
        """Recursively place *nid* and its subtree; return the right boundary x."""
        if nid in seen:
            # Cycle guard — treat as a leaf at current cursor.
            if nid not in positions:
                positions[nid] = {
                    "x": round(x_left + x_spacing / 2),
                    "y": y_start + level * y_spacing,
                    "level": level,
                }
            return x_left + x_spacing
        seen.add(nid)

        kids = [k for k in children.get(nid, []) if k not in seen]
        if not kids:
            x = x_left + x_spacing / 2
            positions[nid] = {
                "x": round(x),
                "y": y_start + level * y_spacing,
                "level": level,
            }
            return x_left + x_spacing

        x_cursor = x_left
        child_centers: list[float] = []
        for kid in kids:
            x_right = _place(kid, level + 1, x_cursor, seen)
            child_centers.append(positions[kid]["x"])
            x_cursor = x_right

        positions[nid] = {
            "x": round((child_centers[0] + child_centers[-1]) / 2),
            "y": y_start + level * y_spacing,
            "level": level,
        }
        return x_cursor

    total_leaves = sum(_leaf_count(r, set()) for r in roots)
    x_cursor: float = canvas_center - total_leaves * x_spacing / 2
    seen: set[str] = set()
    for root in roots:
        x_cursor = _place(root, 0, x_cursor, seen)

    # Fallback: place any still-unpositioned nodes in a row below the tree.
    unpositioned = [nid for nid in all_node_ids if nid not in positions]
    if unpositioned:
        max_level = max((p["level"] for p in positions.values()), default=0)
        total = len(unpositioned)
        for i, nid in enumerate(unpositioned):
            positions[nid] = {
                "x": round(canvas_center + (i - (total - 1) / 2) * x_spacing),
                "y": y_start + (max_level + 2) * y_spacing,
                "level": max_level + 2,
            }

    return [
        {"id": nid, "x": pos["x"], "y": pos["y"], "level": pos["level"]}
        for nid, pos in positions.items()
    ]


async def auto_layout(
    nodes: list[dict],
    existing_edges: list[dict],
) -> dict:
    """Compute a hierarchical layout: Claude decides structure, Python computes positions.

    Claude is only asked for the parent-child hierarchy (a simple, compact
    response that scales to 40+ nodes without truncation).  All x/y coordinate
    math is performed in ``_compute_tree_layout``.

    Call 1 — hierarchy:
        Returns ``[{"node_id": str, "parent_id": str | null}]`` — one entry per node.

    Call 2 — edge suggestions:
        Returns ``[{"source_id", "target_id", "reason"}]`` — up to 4 new edges.

    Args:
        nodes:          List of dicts with ``id``, ``label``, and ``node_type``.
        existing_edges: List of dicts with ``source_id`` and ``target_id``.

    Returns:
        A dict with keys:
        ``nodes``        — list of ``{"id", "x", "y", "level"}`` dicts.
        ``edges_to_add`` — list of ``{"source_id", "target_id", "reason"}`` dicts.
        ``clusters``     — empty list (handled separately via /clusters).

    Raises:
        anthropic.APIError: On network or API-level failures.
        ValueError:         If the model returns unparseable JSON; the raw
                            response is included in the error message.
    """
    if not nodes:
        return {"nodes": [], "edges_to_add": [], "clusters": []}

    all_node_ids = [n["id"] for n in nodes]
    node_lines = "\n".join(f'{n["id"]} | {n["label"]}' for n in nodes)
    edge_lines = (
        "\n".join(f'{e["source_id"]} -> {e["target_id"]}' for e in existing_edges)
        if existing_edges
        else "(none)"
    )

    client = _client()

    # ── Call 1: hierarchy only ─────────────────────────────────────────────────
    hierarchy_prompt = (
        "You are a graph analysis tool. Return ONLY a raw JSON array. "
        "No explanation. No markdown. No code blocks. Just the JSON array.\n\n"
        "NODES (id | label):\n"
        f"{node_lines}\n\n"
        "EDGES (source_id -> target_id):\n"
        f"{edge_lines}\n\n"
        "Task: Decide the parent-child hierarchy for a top-down tree layout.\n"
        "Rules:\n"
        "- Pick one root node. Set its parent_id to null.\n"
        "- Assign every other node a parent_id (must be one of the node ids above).\n"
        "- Every node must appear exactly once.\n"
        "- Use existing edges to guide relationships where possible.\n\n"
        "Return a JSON array where each element has exactly these two fields:\n"
        '{"node_id": "the-node-id", "parent_id": "parent-node-id-or-null"}\n\n'
        "Example output:\n"
        '[{"node_id":"abc","parent_id":null},{"node_id":"def","parent_id":"abc"}]'
    )

    msg1 = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": hierarchy_prompt}],
    )
    raw_hierarchy: str = msg1.content[0].text if msg1.content else "[]"
    try:
        hierarchy = _extract_json(raw_hierarchy)
    except Exception as exc:
        raise ValueError(
            f"Hierarchy call returned unparseable JSON. "
            f"Raw response: {raw_hierarchy!r}. Parse error: {exc}"
        ) from exc

    # Compute x/y coordinates entirely in Python.
    layout_nodes = _compute_tree_layout(hierarchy, all_node_ids)

    # ── Call 2: edge suggestions ───────────────────────────────────────────────
    edge_prompt = (
        "You are a knowledge graph assistant. Return ONLY a raw JSON array. "
        "No explanation. No markdown. No code blocks. Just the JSON array.\n\n"
        "NODES (id | label):\n"
        f"{node_lines}\n\n"
        "EXISTING EDGES (source_id -> target_id):\n"
        f"{edge_lines}\n\n"
        "Task: Suggest up to 4 new meaningful relationships between nodes "
        "that do NOT already have an edge.\n\n"
        "Return a JSON array where each element has exactly these fields:\n"
        '{"source_id": "id1", "target_id": "id2", "reason": "one sentence"}\n\n'
        "Example output:\n"
        '[{"source_id":"abc","target_id":"def","reason":"abc depends on def."}]'
    )

    msg2 = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": edge_prompt}],
    )
    raw_edges: str = msg2.content[0].text if msg2.content else "[]"
    try:
        edges_to_add = _extract_json(raw_edges)
    except Exception as exc:
        raise ValueError(
            f"Edge suggestion call returned unparseable JSON. "
            f"Raw response: {raw_edges!r}. Parse error: {exc}"
        ) from exc

    return {"nodes": layout_nodes, "edges_to_add": edges_to_add, "clusters": []}
