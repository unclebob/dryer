import random

import dryer.scan as scan
from dryer.model import Duplicate, Entry, Span


def _entry(index: int, language: str, fingerprints: set[str]) -> Entry:
    return Entry(
        language=language,
        file=f"src/{index}.py",
        start_line=index + 1,
        end_line=index + 4,
        nodes=len(fingerprints),
        fingerprints=frozenset(fingerprints),
    )


def _brute_force(entries: list[Entry], threshold: float) -> list[Duplicate]:
    found = []
    for index, left in enumerate(entries):
        for right in entries[index + 1 :]:
            if left.language != right.language:
                continue
            union = left.fingerprints | right.fingerprints
            score = (
                len(left.fingerprints & right.fingerprints) / len(union)
                if union
                else 0.0
            )
            if score < threshold:
                continue
            found.append(
                Duplicate(
                    score=score,
                    language=left.language,
                    left=Span(left.file, left.start_line, left.end_line),
                    right=Span(right.file, right.start_line, right.end_line),
                    left_nodes=left.nodes,
                    right_nodes=right.nodes,
                )
            )
    found.sort(key=scan._duplicate_key)
    return found


def test_similarity_join_matches_the_brute_force_result():
    randomizer = random.Random(20261102)
    vocabulary = [f"fingerprint-{index}" for index in range(40)]
    entries = []
    for index in range(80):
        size = randomizer.randint(0, len(vocabulary))
        fingerprints = set(randomizer.sample(vocabulary, size))
        language = "python" if index % 3 else "haskell"
        entries.append(_entry(index, language, fingerprints))

    for threshold in (0.0, 0.2, 0.5, 0.82, 1.0):
        assert scan.find_duplicates(entries, threshold) == _brute_force(
            entries, threshold
        )


def test_similarity_join_keeps_pairs_exactly_on_fractional_size_boundaries():
    entries = [
        _entry(index, "python", {f"shared-{token}" for token in range(index)})
        for index in range(1, 25)
    ]
    thresholds = {
        numerator / denominator
        for denominator in range(1, 25)
        for numerator in range(denominator + 1)
    }

    for threshold in thresholds:
        assert scan.find_duplicates(entries, threshold) == _brute_force(
            entries, threshold
        )


def test_similarity_join_does_not_score_pairs_that_cannot_reach_the_threshold(
    monkeypatch,
):
    real_jaccard = scan.jaccard
    entries = [
        _entry(1, "python", {"a"}),
        _entry(2, "python", {f"b-{index}" for index in range(10)}),
        _entry(3, "python", {f"c-{index}" for index in range(100)}),
    ]

    def guarded(left, right):
        assert min(len(left), len(right)) / max(len(left), len(right)) >= 0.8
        return real_jaccard(left, right)

    monkeypatch.setattr(scan, "jaccard", guarded)
    assert scan.find_duplicates(entries, 0.8) == []
