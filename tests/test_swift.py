from pathlib import Path

from dryer.scan import find_duplicates, scan_files


def write_source(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def pairs(root: Path):
    files = sorted(path for path in root.rglob("*") if path.is_file())
    entries, warnings = scan_files(files, root, min_lines=1, min_nodes=1)
    assert warnings == []
    return find_duplicates(entries, threshold=0.99)


SWIFT_LEFT = """\
func alpha(xs: [Int]) -> [Int] {
    let ys = filter(xs, odd)
    return map(ys, inc)
}
"""

SWIFT_RIGHT = """\
func beta(items: [Int]) -> [Int] {
    let kept = filter(items, even)
    return map(kept, dec)
}
"""


def test_renamed_locals_in_swift_functions_match(tmp_path):
    write_source(tmp_path, "left.swift", SWIFT_LEFT)
    write_source(tmp_path, "right.swift", SWIFT_RIGHT)
    found = pairs(tmp_path)
    assert [(item.language, item.left.file, item.right.file, item.score) for item in found] == [
        ("swift", "left.swift", "right.swift", 1.0)
    ]


def test_a_different_swift_callee_is_not_the_same_structure(tmp_path):
    write_source(tmp_path, "left.swift", SWIFT_LEFT)
    write_source(
        tmp_path,
        "right.swift",
        """\
func beta(items: [Int]) -> [Int] {
    let kept = select(items, even)
    return collect(kept, dec)
}
""",
    )
    files = sorted(tmp_path.glob("*.swift"))
    entries, warnings = scan_files(files, tmp_path, min_lines=1, min_nodes=1)
    assert warnings == []
    found = find_duplicates(entries, threshold=0.0)
    assert len(found) == 1
    assert found[0].score < 1.0
