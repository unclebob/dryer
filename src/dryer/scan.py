"""Read source files and pair the forms that clear the similarity threshold."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path

from dryer.discover import language_of
from dryer.extract import entries_in_source
from dryer.model import Duplicate, Entry, Span
from dryer.shape import jaccard

# Prevent IEEE-754 rounding from dropping boundary pairs on threshold * m.
_SLACK = 1e-9


def _display_path(resolved_path: Path, resolved_root: Path) -> str:
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def display_path(path: Path, root: Path) -> str:
    """Return `path` relative to `root` using POSIX separators when possible."""

    return _display_path(path.resolve(), root.resolve())


def _keep(entry: Entry, min_lines: int, min_nodes: int) -> bool:
    lines = entry.end_line - entry.start_line + 1
    return lines >= min_lines and entry.nodes >= min_nodes


def scan_files(
    files: list[Path], root: Path, min_lines: int, min_nodes: int
) -> tuple[list[Entry], list[str]]:
    resolved_root = root.resolve()
    entries: list[Entry] = []
    warnings: list[str] = []
    for path in files:
        language = language_of(path)
        if language is None:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        file = _display_path(path.resolve(), resolved_root)
        found, warning = entries_in_source(language, source, path.as_posix(), file)
        if warning:
            warnings.append(f"{file}:{warning}")
        entries.extend(entry for entry in found if _keep(entry, min_lines, min_nodes))
    return entries, warnings


def _same_span(left: Entry, right: Entry) -> bool:
    if left.file != right.file:
        return False
    if left.start_line != right.start_line:
        return False
    return left.end_line == right.end_line


def _duplicate_key(item: Duplicate):
    score = -item.score
    return (
        score,
        item.language,
        item.left.file,
        item.left.start_line,
        item.right.file,
        item.right.start_line,
    )


def _make_duplicate(
    language: str, left: Entry, right: Entry, score: float
) -> Duplicate:
    return Duplicate(
        score=score,
        language=language,
        left=Span(left.file, left.start_line, left.end_line),
        right=Span(right.file, right.start_line, right.end_line),
        left_nodes=left.nodes,
        right_nodes=right.nodes,
    )


def _all_pairs_duplicates(
    language: str, group: list[Entry], threshold: float, found: list[Duplicate]
) -> None:
    for index, left in enumerate(group):
        for right in group[index + 1 :]:
            if _same_span(left, right):
                continue
            score = jaccard(left.fingerprints, right.fingerprints)
            if score >= threshold:
                found.append(_make_duplicate(language, left, right, score))


def _intern_tokens(non_empty: list[tuple[int, Entry]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for _, entry in non_empty:
        counts.update(entry.fingerprints)
    ordered = sorted(counts, key=lambda token: (counts[token], token))
    return {token: token_id for token_id, token in enumerate(ordered)}


class _GroupIndex:
    """Frequency-ordered prefix-filtered inverted index for one language group."""

    def __init__(self, group: list[Entry], non_empty: list[tuple[int, Entry]]) -> None:
        token_ids = _intern_tokens(non_empty)
        encoded = [
            (idx, sorted(token_ids[tok] for tok in entry.fingerprints))
            for idx, entry in non_empty
        ]
        encoded.sort(key=lambda item: len(item[1]))
        self.group = group
        self.orig_indices: list[int] = []
        self.token_lists: list[list[int]] = []
        self.int_sets: list[set[int]] = []
        self.sizes: list[int] = []
        for idx, tokens in encoded:
            self.orig_indices.append(idx)
            self.token_lists.append(tokens)
            self.int_sets.append(set(tokens))
            self.sizes.append(len(tokens))
        self.inverted: dict[int, list[int]] = defaultdict(list)
        self.seen_mark = [-1] * len(encoded)
        self.matches: list[tuple[int, int, float]] = []

    def candidates_for(self, cur_pos: int, prefix: list[int], min_other: int) -> list[int]:
        sizes = self.sizes
        inverted = self.inverted
        seen_mark = self.seen_mark
        candidates: list[int] = []
        for tok in prefix:
            for other_pos in reversed(inverted[tok]):
                if sizes[other_pos] < min_other:
                    break
                if seen_mark[other_pos] == cur_pos:
                    continue
                seen_mark[other_pos] = cur_pos
                candidates.append(other_pos)
        return candidates

    def score_candidates(
        self, cur_pos: int, candidates: list[int], threshold: float
    ) -> None:
        group = self.group
        orig_indices = self.orig_indices
        int_sets = self.int_sets
        sizes = self.sizes
        cur_idx = orig_indices[cur_pos]
        cur_set = int_sets[cur_pos]
        cur_size = sizes[cur_pos]
        for other_pos in candidates:
            other_idx = orig_indices[other_pos]
            left_idx, right_idx = (
                (cur_idx, other_idx) if cur_idx < other_idx else (other_idx, cur_idx)
            )
            if _same_span(group[left_idx], group[right_idx]):
                continue
            inter = len(int_sets[other_pos] & cur_set)
            score = inter / (cur_size + sizes[other_pos] - inter)
            if score >= threshold:
                self.matches.append((left_idx, right_idx, score))

    def index_entry(self, cur_pos: int, prefix: list[int]) -> None:
        inverted = self.inverted
        for tok in prefix:
            inverted[tok].append(cur_pos)


def _indexed_group_duplicates(
    language: str, group: list[Entry], threshold: float, found: list[Duplicate]
) -> None:
    non_empty = [(idx, entry) for idx, entry in enumerate(group) if entry.fingerprints]
    if len(non_empty) < 2:
        return
    index = _GroupIndex(group, non_empty)
    for cur_pos, tokens in enumerate(index.token_lists):
        m = len(tokens)
        min_other = math.ceil(threshold * m - _SLACK)
        prefix_len = max(1, min(m, m - min_other + 1))
        prefix = tokens[:prefix_len]
        candidates = index.candidates_for(cur_pos, prefix, min_other)
        if candidates:
            index.score_candidates(cur_pos, candidates, threshold)
        index.index_entry(cur_pos, prefix)
    index.matches.sort()
    for left_idx, right_idx, score in index.matches:
        found.append(_make_duplicate(language, group[left_idx], group[right_idx], score))


def find_duplicates(entries: list[Entry], threshold: float) -> list[Duplicate]:
    """Pair forms of the same language. Each unordered pair is reported once."""

    if threshold > 1.0:
        return []

    by_language: dict[str, list[Entry]] = {}
    for entry in entries:
        by_language.setdefault(entry.language, []).append(entry)

    found: list[Duplicate] = []
    for language, group in by_language.items():
        if threshold <= 0.0:
            _all_pairs_duplicates(language, group, threshold, found)
        else:
            _indexed_group_duplicates(language, group, threshold, found)
    found.sort(key=_duplicate_key)
    return found
