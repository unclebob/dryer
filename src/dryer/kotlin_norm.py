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
