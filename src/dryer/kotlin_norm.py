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

# Nodes that only wrap one expression: an argument (with or without a label)
# or a trailing lambda (with or without annotation or label).
WRAPPERS = {"value_argument", "annotated_lambda"}


def wrapped(node):
    """The expression a pure wrapper stands for (a label and `=` are dropped), else None."""

    if node.type not in WRAPPERS:
        return None
    named = node.named_children
    return named[-1] if named else None


def suffix_items(node):
    """Everything a call suffix passes: parenthesised arguments, then a trailing lambda."""

    items = []
    for child in node.named_children:
        if child.type == "value_arguments":
            items.extend(child.named_children)
        else:
            items.append(child)
    return items

# Tokens that are operators wherever they stand ...
TOKENS = {"?:", "!!", "..", "..<", "::"}

# ... and keywords that mean something only under one kind of parent.
PARENT_TOKENS = {
    "check_expression": {"is", "in"},
    "range_test": {"in"},
    "type_test": {"is"},
    "as_expression": {"as", "as?"},
    "jump_expression": {"return", "return@", "throw", "break", "break@", "continue", "continue@"},
}


def is_operator(node) -> bool:
    if node.type in TOKENS:
        return True
    parent = node.parent
    return parent is not None and node.type in PARENT_TOKENS.get(parent.type, ())


def kind(node) -> str:
    """The node type, with a `?.` suffix told apart from a `.` suffix."""

    if node.type == "navigation_suffix" and node.children[0].type == "?.":
        return "safe_navigation_suffix"
    return node.type


def infix_parts(node):
    """(left, function name, right) of `a shl 2`, else None."""

    named = node.named_children
    if node.type == "infix_expression" and len(named) == 3 and named[1].type == "simple_identifier":
        return named
    return None
