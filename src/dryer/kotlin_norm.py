"""Kotlin facts the normalizer needs, as pure functions of tree-sitter nodes.

Only Kotlin node types are named here, except where a Kotlin node type is
also a node type of another grammar (`modifiers` is Java's too); astnorm
asks these functions only for Kotlin trees.
"""

from __future__ import annotations

# Declaration noise: modifiers and annotations are not structure.
NOISE = {
    "modifiers",
    "annotation",
    "file_annotation",
    "parameter_modifiers",
    "type_modifiers",
}


def is_noise(node) -> bool:
    return node.type in NOISE

# Nodes that only wrap one expression: an argument, with or without a label.
WRAPPERS = {"value_argument"}


def wrapped(node):
    """The expression a pure wrapper stands for (a label and `=` are dropped), else None."""

    if node.type not in WRAPPERS:
        return None
    named = node.named_children
    return named[-1] if named else None
