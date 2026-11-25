from pathlib import Path

from dryer.extract import entries_in_source
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


def _scored(tmp_path, left: str, right: str) -> float:
    write_source(tmp_path, "left.swift", left)
    write_source(tmp_path, "right.swift", right)
    files = sorted(tmp_path.glob("*.swift"))
    entries, warnings = scan_files(files, tmp_path, min_lines=1, min_nodes=1)
    assert warnings == []
    found = find_duplicates(entries, threshold=0.0)
    assert len(found) == 1
    return found[0].score


def test_a_swift_method_name_stays_and_the_field_name_does_not(tmp_path):
    assert _scored(
        tmp_path,
        "func alpha(xs: Order) -> Int {\n    return xs.total\n}\n",
        "func beta(items: Order) -> Int {\n    return items.count\n}\n",
    ) == 1.0
    assert _scored(
        tmp_path,
        "func alpha(xs: Order) -> [Int] {\n    return xs.filter(odd)\n}\n",
        "func beta(items: Order) -> [Int] {\n    return items.select(even)\n}\n",
    ) < 1.0
    assert _scored(
        tmp_path,
        "func alpha(pair: (Int, Int)) -> Int {\n    return pair.0\n}\n",
        "func beta(pair: (Int, Int)) -> Int {\n    return pair.1\n}\n",
    ) == 1.0


def test_a_different_swift_operator_lowers_the_score(tmp_path):
    assert _scored(
        tmp_path,
        "func alpha(xs: Int) -> Bool {\n    return xs >= 1\n}\n",
        "func beta(items: Int) -> Bool {\n    return items >= 2\n}\n",
    ) == 1.0
    assert _scored(
        tmp_path,
        "func alpha(xs: Int) -> Bool {\n    return xs >= 1\n}\n",
        "func beta(items: Int) -> Bool {\n    return items != 1\n}\n",
    ) < 1.0


def test_a_swift_argument_label_is_part_of_the_call(tmp_path):
    assert _scored(
        tmp_path,
        "func alpha(xs: [Int]) -> [Int] {\n    return move(from: xs, to: xs)\n}\n",
        "func beta(items: [Int]) -> [Int] {\n    return move(from: items, to: items)\n}\n",
    ) == 1.0
    assert _scored(
        tmp_path,
        "func alpha(xs: [Int]) -> [Int] {\n    return move(from: xs, to: xs)\n}\n",
        "func beta(items: [Int]) -> [Int] {\n    return move(start: items, end: items)\n}\n",
    ) < 1.0


def test_swift_literals_normalize_and_interpolation_does_not(tmp_path):
    assert _scored(
        tmp_path,
        'func alpha() -> String {\n    return "Save"\n}\n',
        "func beta() -> Int {\n    return 1\n}\n",
    ) == 1.0
    assert _scored(
        tmp_path,
        "func alpha() -> Int {\n    return nil\n}\n",
        "func beta() -> Double {\n    return 1.5\n}\n",
    ) == 1.0
    assert _scored(
        tmp_path,
        'func alpha() -> String {\n    return """\n    hello\n    """\n}\n',
        "func beta() -> Int {\n    return 0\n}\n",
    ) == 1.0
    assert _scored(
        tmp_path,
        'func alpha(name: String) -> String {\n    return "Hello \\(name)"\n}\n',
        'func beta() -> String {\n    return "Hello"\n}\n',
    ) < 1.0


def test_a_swift_comment_is_not_part_of_the_structure(tmp_path):
    commented = """\
func alpha(xs: [Int]) -> [Int] {
    // keep the odds
    /* and this */
    let ys = filter(xs, odd)
    return map(ys, inc)
}
"""
    assert _scored(tmp_path, commented, SWIFT_RIGHT) == 1.0


APP = """\
import SwiftUI

struct InvoiceView: View {
    var title: String

    var body: some View {
        func hidden() -> Int {
            return count()
        }
        VStack {
            Text(title)
            Button(action: { save() }) {
                Text("Save")
            }
        }
    }

    func refresh(xs: [Int]) -> [Int] {
        let ys = filter(xs, odd)
        return map(ys, inc)
    }
}

class Panel {
    init(xs: [Int]) {
        self.items = filter(xs, odd)
        self.kept = map(xs, inc)
    }

    func beta(items: [Int]) -> [Int] {
        let kept = filter(items, even)
        return map(kept, dec)
    }
}

extension Board {
    func gamma(xs: [Int]) -> [Int] {
        let ys = filter(xs, odd)
        return map(ys, inc)
    }
}

enum Status {
    case open
    case closed

    func label(xs: [Int]) -> [Int] {
        let ys = filter(xs, odd)
        return map(ys, inc)
    }
}

protocol Saving {
    func save(order: Order)

    func load(id: Int) -> Order {
        return cache(id)
    }
}

func outer(xs: [Int]) -> [Int] {
    func inner(ys: [Int]) -> [Int] {
        let kept = filter(ys, odd)
        return map(kept, inc)
    }
    let closure = { (zs: [Int]) -> [Int] in
        let kept = filter(zs, even)
        return map(kept, dec)
    }
    return inner(xs)
}

let alpha = { (xs: [Int]) -> [Int] in
    func inner(ys: [Int]) -> [Int] {
        let kept = filter(ys, odd)
        return map(kept, inc)
    }
    return inner(xs)
}
"""

INVOICE = """\
struct InvoiceView: View {
    var title: String
    var body: some View {
        VStack {
            Text(title)
            Button(action: { save() }) {
                Text("Save")
            }
        }
    }
}
"""

RECEIPT = """\
struct ReceiptView: View {
    var heading: String
    var body: some View {
        VStack {
            Text(heading)
            Button(action: { save() }) {
                Text("Done")
            }
        }
    }
}
"""

LABEL_VIEW = """\
struct LabelView: View {
    var heading: String
    var body: some View {
        VStack {
            Label(heading)
            Button(action: { save() }) {
                Text("Done")
            }
        }
    }
}
"""


def test_swift_keeps_methods_bodies_and_top_level_closures_only():
    entries, warning = entries_in_source("swift", APP, "App.swift", "App.swift")
    assert warning is None
    assert [(entry.start_line, entry.end_line) for entry in entries] == [
        (6, 16),
        (18, 21),
        (30, 33),
        (37, 40),
        (47, 50),
        (56, 58),
        (61, 71),
        (73, 79),
    ]


def test_swiftui_views_match_when_only_the_data_changes(tmp_path):
    assert _scored(tmp_path, INVOICE, RECEIPT) == 1.0
    assert _scored(tmp_path, RECEIPT, LABEL_VIEW) < 1.0


def test_a_top_level_swift_closure_matches_its_renamed_copy(tmp_path):
    left = """\
let alpha = { (xs: [Int]) -> [Int] in
    let ys = filter(xs, odd)
    return map(ys, inc)
}
"""
    right = """\
let beta = { (items: [Int]) -> [Int] in
    let kept = filter(items, even)
    return map(kept, dec)
}
"""
    assert _scored(tmp_path, left, right) == 1.0
