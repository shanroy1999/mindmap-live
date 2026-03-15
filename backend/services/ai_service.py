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
