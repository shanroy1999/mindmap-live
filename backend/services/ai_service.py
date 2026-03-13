"""AI-powered features using the Anthropic Claude API."""

import json
import os

import anthropic


def _get_client() -> anthropic.Anthropic:
    """Return an authenticated Anthropic client using ANTHROPIC_API_KEY."""
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def suggest_connections(node_labels: list[str]) -> list[dict[str, str]]:
    """Use Claude to suggest relationships between a list of node labels.

    Args:
        node_labels: Labels of existing nodes in the knowledge graph.

    Returns:
        A list of suggested edges, each as a dict with 'source', 'target',
        and 'reason' keys.
    """
    client = _get_client()
    prompt = (
        "You are a knowledge graph assistant. Given the following node labels, "
        "suggest meaningful directed relationships between them.\n"
        "Respond with a JSON array of objects, each with keys: "
        "'source' (node label), 'target' (node label), 'reason' (one sentence).\n\n"
        f"Nodes: {', '.join(node_labels)}"
    )
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text if message.content else "[]"
    return json.loads(raw)
