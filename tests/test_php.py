from pathlib import Path

from dryer.discover import is_test_file, language_of
from dryer.extract import entries_in_source
from dryer.model import Entry
from dryer.scan import find_duplicates, scan_files


def write_source(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def forms(source: str, file: str = "a.php") -> list[Entry]:
    entries, warning = entries_in_source("php", source, file, file)
    assert warning is None
    return entries


def score(left: str, right: str) -> float:
    found = find_duplicates(forms(left, "a.php") + forms(right, "b.php"), threshold=0.0)
    assert len(found) == 1
    return found[0].score


def body(text: str) -> str:
    return f"<?php\nfunction subject($xs, $ys)\n{{\n{text}\n}}\n"


def test_php_files_and_tests_are_found(tmp_path):
    assert language_of("app/Survey/Board.php") == "php"
    assert is_test_file("app/Survey/BoardTest.php") is True
    assert is_test_file("app/Survey/Board.php") is False
    write_source(
        tmp_path,
        "app/Left.php",
        """\
<?php
class Left
{
    public function alpha(array $xs): array
    {
        $ys = array_filter($xs, $odd);
        return array_map($inc, $ys);
    }
}
""",
    )
    write_source(
        tmp_path,
        "app/Right.php",
        """\
<?php
class Right
{
    public function beta(array $items): array
    {
        $kept = array_filter($items, $even);
        return array_map($dec, $kept);
    }
}
""",
    )
    files = sorted(path for path in tmp_path.rglob("*") if path.is_file())
    entries, warnings = scan_files(files, tmp_path, min_lines=1, min_nodes=1)
    assert warnings == []
    found = find_duplicates(entries, threshold=0.99)
    assert [(item.language, item.left.file, item.right.file, item.score) for item in found] == [
        ("php", "app/Left.php", "app/Right.php", 1.0)
    ]


def test_called_names_stay_and_locals_fields_and_literals_do_not():
    left = body(
        """\
    $a = $this->repo->find($xs->id, 'x');
    $b = Board::make(new Panel(1), self::LIMIT, static::$count);
    return \\strlen($a?->label) . $b?->total() . "plain";"""
    )
    right = body(
        """\
    $row = $this->store->find($ys->key, 2.5);
    $out = Board::make(new Panel(true), self::MAX, static::$seen);
    return \\strlen($row?->title) . $out?->total() . 'plain';"""
    )
    assert score(left, right) == 1.0
    names = " ".join(forms(left)[0].fingerprints)
    for called in ("find", "make", "Panel", "strlen", "total"):
        assert called in names
    for dropped in ("repo", "LIMIT", "count", "label"):
        assert dropped not in names


def test_a_different_called_name_lowers_the_score():
    assert score(body("    return $xs->filter($ys);"), body("    return $xs->select($ys);")) < 1.0
    assert score(body("    return strlen($xs);"), body("    return count($xs);")) < 1.0
    assert score(body("    return Board::make($xs);"), body("    return Board::build($xs);")) < 1.0


def test_an_interpolated_string_is_not_a_plain_literal():
    assert score(body('    return "plain";'), body("    return 'plain';")) == 1.0
    assert score(body('    return "plain";'), body('    return "x {$xs}";')) < 1.0


def test_methods_and_top_level_functions_are_candidates():
    source = """\
<?php
interface Shape { public function area(): float; }

abstract class Base
{
    abstract protected function hook(): void;

    public function run($xs)
    {
        $keep = fn($x) => $x > 0;
        $map = function ($x) { return $x; };
        $anon = new class { public function hidden() { return 1; } };
        return array_map($map, $xs);
    }
}

function helper($xs)
{
    function inner() { return 1; }
    return $xs;
}
"""
    assert [(entry.start_line, entry.end_line) for entry in forms(source)] == [(8, 14), (17, 21)]


def test_a_method_with_an_empty_body_is_not_a_candidate():
    source = """\
<?php
final class SurveyInput
{
    public function __construct(
        public readonly string $name,
        public readonly array $values,
    ) {
        // Promoted properties only.
    }

    public function noop(): void {}

    public function name(): string
    {
        return $this->name;
    }
}
"""
    assert [(entry.start_line, entry.end_line) for entry in forms(source)] == [(13, 16)]
