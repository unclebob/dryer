"""Jaccard similarity over structural fingerprints.

This is the dry4clj score. A normalized form is a tree of keywords, names, and
vectors. The fingerprint set contains the printed form of every subtree. The
score is the size of the shared set divided by the size of the union.
"""

from __future__ import annotations


class K:
    """A keyword in the normalized tree. Prints the way Clojure prints keywords."""

    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return ":" + self.name


def _pr_atom(node) -> str:
    if isinstance(node, K):
        return ":" + node.name
    if isinstance(node, str):
        escaped = node.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise TypeError(f"cannot print {node!r}")


def _print_list(current: list, done: dict[int, str], atoms: set[str]) -> str:
    pieces = []
    for child in current:
        if isinstance(child, list):
            pieces.append(done[id(child)])
        else:
            printed = _pr_atom(child)
            atoms.add(printed)
            pieces.append(printed)
    return "[" + " ".join(pieces) + "]"


def _queue_lists(stack: list, current: list) -> None:
    for child in reversed(current):
        if isinstance(child, list):
            stack.append((child, False))


def _printed(node: list) -> tuple[dict[int, str], set[str]]:
    # Post-order. A 1,200-deep tree must not raise RecursionError.
    done: dict[int, str] = {}
    atoms: set[str] = set()
    stack: list[tuple[list, bool]] = [(node, False)]
    while stack:
        current, expanded = stack.pop()
        key = id(current)
        if expanded:
            done[key] = _print_list(current, done, atoms)
            continue
        if key in done:
            continue
        stack.append((current, True))
        _queue_lists(stack, current)
    return done, atoms


def pr(node) -> str:
    """Print a normalized node the way Clojure `pr-str` prints it."""

    if not isinstance(node, list):
        return _pr_atom(node)
    done, _atoms = _printed(node)
    return done[id(node)]


def node_count(node) -> int:
    """One plus the count of every nested node. Atoms count as one."""

    if not isinstance(node, list):
        return 1
    total = 0
    stack: list = [node]
    while stack:
        current = stack.pop()
        total += 1
        if isinstance(current, list):
            stack.extend(current)
    return total


def fingerprints(node) -> frozenset[str]:
    """Return printed forms of every subtree and atom in `node`."""

    if not isinstance(node, list):
        return frozenset({_pr_atom(node)})
    done, atoms = _printed(node)
    atoms.update(done.values())
    return frozenset(atoms)


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)
