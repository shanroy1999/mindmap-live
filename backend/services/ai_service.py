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


async def auto_layout(
    nodes: list[dict],
    existing_edges: list[dict],
) -> dict:
    """Compute a hierarchical layout via two focused Claude calls.

    Call 1 — hierarchy + positions:
        Ask Claude to assign each node a level (0 = root, 1 = children, …)
        and compute x/y coordinates:
        - root at x=600, y=50
        - each level adds 150 px to y
        - siblings spread 200 px apart horizontally, centred under their parent

    Call 2 — edge suggestions:
        Ask Claude to suggest up to 4 new edges that improve the graph.

    Args:
        nodes:          List of dicts with ``id``, ``label``, and ``node_type``.
        existing_edges: List of dicts with ``source_id`` and ``target_id``.

    Returns:
        A dict with two keys:
        ``nodes``         — list of ``{"id", "x", "y", "level"}`` dicts.
        ``edges_to_add``  — list of ``{"source_id", "target_id", "reason"}`` dicts.
        ``clusters``      — empty list (clusters handled separately via /clusters).

    Raises:
        anthropic.APIError: On network or API-level failures.
        ValueError:         If the model returns unparseable JSON, with the raw
                            response included in the message for debugging.
    """
    if not nodes:
        return {"nodes": [], "edges_to_add": [], "clusters": []}

    node_lines = "\n".join(
        f'{n["id"]} | {n["label"]}'
        for n in nodes
    )
    edge_lines = (
        "\n".join(f'{e["source_id"]} -> {e["target_id"]}' for e in existing_edges)
        if existing_edges
        else "(none)"
    )

    client = _client()

    # ── Call 1: hierarchy and positions ───────────────────────────────────────
    layout_prompt = (
        "You are a graph layout tool. Return ONLY a raw JSON array. "
        "No explanation. No markdown. No code blocks. Just the JSON array.\n\n"
        "NODES (id | label):\n"
        f"{node_lines}\n\n"
        "EDGES (source_id -> target_id):\n"
        f"{edge_lines}\n\n"
        "Task: Assign each node a level and x/y position for a top-down tree layout.\n"
        "Rules:\n"
        "- Pick one root node (level 0). Place it at x=600, y=50.\n"
        "- Direct children of root are level 1, at y=200.\n"
        "- Their children are level 2, at y=350. And so on (add 150 per level).\n"
        "- Spread siblings horizontally 200px apart, centred under their parent.\n"
        "- Every node must appear exactly once.\n\n"
        "Return a JSON array where each element has exactly these fields:\n"
        '{"id": "the-node-id", "x": 600, "y": 50, "level": 0}\n\n'
        "Example output:\n"
        '[{"id":"abc","x":600,"y":50,"level":0},{"id":"def","x":500,"y":200,"level":1}]'
    )

    msg1 = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": layout_prompt}],
    )
    raw_layout: str = msg1.content[0].text if msg1.content else "[]"
    try:
        layout_nodes = _extract_json(raw_layout)
    except Exception as exc:
        raise ValueError(
            f"Layout call returned unparseable JSON. "
            f"Raw response: {raw_layout!r}. Parse error: {exc}"
        ) from exc

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
