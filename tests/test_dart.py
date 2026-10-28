import hashlib
from pathlib import Path

from dryer.cli import run
from dryer.discover import iter_source_files, language_of
from dryer.extract import entries_in_source
from dryer.model import Entry
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


def forms(source: str, file: str) -> list[Entry]:
    entries, warning = entries_in_source("dart", source, file, file)
    assert warning is None
    return entries


def _function(body: str, name: str = "alpha") -> str:
    return f"Object {name}(List<int> xs, String? a) {{\n{body}\n}}\n"


def _score(left: str, right: str) -> float:
    found = find_duplicates(forms(left, "a.dart") + forms(right, "b.dart"), threshold=0.0)
    assert len(found) == 1
    return found[0].score


def test_dart_matches_renamed_locals(tmp_path):
    write_source(
        tmp_path,
        "lib/left.dart",
        "List<int> alpha(List<int> xs) {\n  var ys = filter(xs, odd);\n  return map(ys, inc);\n}\n",
    )
    write_source(
        tmp_path,
        "lib/right.dart",
        "List<int> beta(List<int> items) {\n  var kept = filter(items, even);\n  return map(kept, dec);\n}\n",
    )
    found = pairs(tmp_path)
    assert len(found) == 1
    assert found[0].language == "dart"
    assert found[0].score == 1.0


def test_dart_member_calls_keep_their_names():
    filtered = _function("  return xs.where((x) => x > 0).length;")
    mapped = _function("  return xs.map((x) => x > 0).length;", "beta")
    counted = _function("  return ys.where((y) => y > 1).size;", "beta")
    assert _score(filtered, mapped) < 0.99
    assert _score(filtered, counted) == 1.0


def test_dart_operators_keep_their_spelling():
    plus = _function("  return xs.length + 1;")
    minus = _function("  return xs.length - 1;", "beta")
    assert _score(plus, minus) < 1.0


def test_dart_null_aware_access_is_part_of_the_shape():
    safe = _function("  return a?.length;")
    plain = _function("  return a.length;", "beta")
    assert _score(safe, plain) < 1.0


def test_dart_interpolated_string_is_not_a_plain_literal():
    template = _function("  return 'n ${xs.length}';")
    plain = _function("  return 'n';", "beta")
    other = _function("  return 'other';", "beta")
    assert _score(template, plain) < 1.0
    assert _score(plain, other) == 1.0


def test_dart_candidates_match_crapper():
    source = """int top(int a) {
  return a;
}

class Board {
  Board(int s) {
    print(s);
  }
  factory Board.fromJson(Map<String, dynamic> j) {
    return Board(j['s']);
  }
  int get size => 1;
  set size(int v) {
    print(v);
  }
  Board operator +(Board o) => this;
  @override
  // a comment
  String toString() {
    int local() => 1;
    var f = (int y) => y;
    return 'b';
  }
  external int ext();
}

abstract class Shape {
  void abs();
}
"""
    entries = forms(source, "lib/board.dart")
    assert [(e.start_line, e.end_line) for e in entries] == [
        (1, 3),
        (9, 11),
        (12, 12),
        (13, 15),
        (16, 16),
        (19, 23),
    ]


def test_dart_flutter_build_methods_pair(tmp_path):
    widget = """class {name} extends StatelessWidget {{
  final String {field};
  const {name}(this.{field});

  @override
  Widget build(BuildContext context) {{
    return Padding(
      padding: const EdgeInsets.all({pad}),
      child: Text({field}, style: Theme.of(context).textTheme.titleLarge),
    );
  }}
}}
"""
    write_source(tmp_path, "lib/a.dart", widget.format(name="Title", field="title", pad=8))
    write_source(tmp_path, "lib/b.dart", widget.format(name="Caption", field="caption", pad=4))
    found = pairs(tmp_path)
    assert len(found) == 1
    assert (found[0].left.start_line, found[0].right.start_line) == (6, 6)


def test_dart_detection(tmp_path):
    assert language_of("a.dart") == "dart"
    assert language_of("lib/a.g.dart") is None
    assert language_of("lib/a.freezed.dart") is None
    for name in ("lib/a.dart", ".dart_tool/x.dart", "integration_test/y.dart", "lib/b_test.dart", "lib/c.mocks.dart"):
        write_source(tmp_path, name, "void a() {}\n")
    assert [p.name for p in iter_source_files([tmp_path])] == ["a.dart"]


def test_dart_broken_source_does_not_raise():
    entries = forms("int a() {\n  return 1 +;\n}\n\nint b() {\n  return 2;\n}\n", "a.dart")
    assert (5, 7) in [(e.start_line, e.end_line) for e in entries]
    assert isinstance(forms("int a( {\n  return 1;\n}\n", "a.dart"), list)


SAMPLES = {
    ("java", "A.java"): "class A {\n  int f(int[] xs, String s) {\n    int n = 0;\n    for (int x : xs) { if (x > 0 && s != null) n += x * 2; }\n    return s.length() + n - 1;\n  }\n}\n",
    ("typescript", "a.ts"): "function f(xs: number[], s?: string): number {\n  const ys = xs.filter((x) => x > 0).map((x) => x * 2);\n  return `${s}`.length + (s?.length ?? 0) - ys.length;\n}\n",
    ("python", "a.py"): "def f(xs, s):\n    ys = [x * 2 for x in xs if x > 0 and s]\n    return len(s) + sum(ys) - 1\n",
}

DIGESTS = {
    "java": "dcb1e5ff90317fb0483167096aaf653af44a6c9d",
    "typescript": "abf938e18ce240fe8b3c12af7d11336f66c6d0b2",
    "python": "ac7c7686c73dbed762977d3cbbc94aa920f53699",
}


def test_other_languages_keep_their_fingerprints():
    for (language, path), source in SAMPLES.items():
        [entry] = entries_in_source(language, source, path, path)[0]
        printed = "\n".join(sorted(entry.fingerprints)).encode()
        assert hashlib.sha1(printed).hexdigest() == DIGESTS[language], language


def test_help_mentions_dart(capsys):
    assert run(["--help"]) == 0
    assert "Dart (.dart)" in capsys.readouterr().out


def test_dart_const_constructor_calls_keep_their_names():
    padding = _function("  return const Padding(padding: EdgeInsets.all(8), child: Text('a'));")
    sized = _function("  return const SizedBox(height: EdgeInsets.all(8), width: Text('a'));", "beta")
    all_ = _function("  return const EdgeInsets.all(8);")
    symmetric = _function("  return const EdgeInsets.symmetric(8);", "beta")
    assert _score(padding, sized) < 1.0
    assert _score(all_, symmetric) < 1.0


def test_dart_cascade_calls_keep_their_names():
    add = _function("  return xs..add(1)..clear();")
    remove = _function("  return xs..remove(1)..clear();", "beta")
    assert _score(add, remove) < 1.0


def test_dart_super_calls_keep_their_names():
    init = _function("  super.initState();\n  return a;")
    dispose = _function("  super.dispose();\n  return a;", "beta")
    assert _score(init, dispose) < 1.0


def test_dart_test_folders_do_not_skip_other_languages(tmp_path):
    write_source(tmp_path, "integration_test/tool.go", "package x\n")
    write_source(tmp_path, "integration_test/app.dart", "void a() {}\n")
    assert [p.name for p in iter_source_files([tmp_path])] == ["tool.go"]
