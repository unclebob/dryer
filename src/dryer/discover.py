"""Find source files and decide which language each one is written in.

The extensions and the skipped directories match crapper and mutator, with
`.cljd` added because dry4clj reads it.
"""

import os
from pathlib import Path

EXTENSIONS = {
    ".clj": "clojure",
    ".cljc": "clojure",
    ".cljs": "clojure",
    ".cljd": "clojure",
    ".bb": "clojure",
    ".java": "java",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".rs": "rust",
    ".py": "python",
    ".dart": "dart",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "target",
    "dist",
    "build",
    "out",
    "coverage",
    ".metrics",
    "testdata",
    "__pycache__",
    ".clj-kondo",
    ".dart_tool",
}

TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__"}
# Dart tests only: a Go or Python folder with these names is still source.
DART_TEST_DIRS = {"integration_test", "test_driver"}

DART_GENERATED_SUFFIXES = (
    ".g.dart",
    ".freezed.dart",
    ".mocks.dart",
    ".gr.dart",
    ".config.dart",
    ".pb.dart",
    ".pbenum.dart",
    ".pbjson.dart",
    ".pbserver.dart",
)


def language_of(path: str | Path) -> str | None:
    file_path = Path(path)
    name = file_path.name
    if name.endswith(".d.ts") or name.endswith(DART_GENERATED_SUFFIXES):
        return None
    return EXTENSIONS.get(file_path.suffix)


def _test_dirs(file_path: Path) -> set[str]:
    if file_path.suffix == ".dart":
        return TEST_DIRS | DART_TEST_DIRS
    return TEST_DIRS


def is_test_file(path: str | Path) -> bool:
    file_path = Path(path)
    name = file_path.name
    if name.endswith(("_test.go", "_test.dart")):
        return True
    if name.endswith(("_test.clj", "_test.cljc", "_test.cljs", "_test.cljd", "_test.bb")):
        return True
    if name.endswith(
        (
            ".test.ts",
            ".spec.ts",
            ".test.tsx",
            ".spec.tsx",
            ".test.mts",
            ".spec.mts",
            ".test.cts",
            ".spec.cts",
        )
    ):
        return True
    if name == "conftest.py":
        return True
    if name.endswith("_test.py") or (name.startswith("test_") and name.endswith(".py")):
        return True
    return any(part in _test_dirs(file_path) for part in file_path.parts)


def _skipped_dir(name: str) -> bool:
    return name in SKIP_DIRS or name in TEST_DIRS


def _walk(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not _skipped_dir(name)]
        for name in filenames:
            path = Path(dirpath) / name
            if language_of(path) is None or is_test_file(path):
                continue
            found.append(path)
    return found


def iter_source_files(roots: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        for path in _walk(root):
            files.add(path.resolve())
    return sorted(files, key=lambda path: path.as_posix())
