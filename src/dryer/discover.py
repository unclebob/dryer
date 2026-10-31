"""Find source files and decide which language each one is written in.

The extensions and the skipped directories match crapper and mutator, with
`.cljd` added because dry4clj reads it. Ruby adds `.rb` and `.rake`, and Rails
migrations are left out of a walk unless they are asked for: they repeat by
design and are never edited.
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
    ".rb": "ruby",
    ".rake": "ruby",
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
    ".bundle",
}

TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__"}

RUBY_TEST_HELPERS = {"spec_helper.rb", "rails_helper.rb", "test_helper.rb"}


def language_of(path: str | Path) -> str | None:
    file_path = Path(path)
    name = file_path.name
    if name.endswith(".d.ts"):
        return None
    return EXTENSIONS.get(file_path.suffix)


def is_test_file(path: str | Path) -> bool:
    file_path = Path(path)
    name = file_path.name
    if name.endswith("_test.go"):
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
    if name in RUBY_TEST_HELPERS or name.endswith(("_test.rb", "_spec.rb")):
        return True
    if name.startswith("test_") and name.endswith(".rb"):
        return True
    return any(part in TEST_DIRS for part in file_path.parts)


def is_migration(path: str | Path) -> bool:
    """A Rails migration under `db/migrate`, or the generated `db/schema.rb`."""

    parts = Path(path).parts
    if parts[-2:] == ("db", "schema.rb"):
        return True
    return any(parts[index : index + 2] == ("db", "migrate") for index in range(len(parts) - 2))


def walked_part(path: Path, root: Path) -> Path:
    """`path` from the walk root, starting at the root's own name.

    A root named on the command line counts as asked for, so a walk of
    `db/migrate` compares its migrations and a walk of `db` does not.
    """

    return Path(root.name) / path.relative_to(root)


def _skipped_dir(name: str) -> bool:
    return name in SKIP_DIRS or name in TEST_DIRS


def _walk(root: Path, include_migrations: bool, skipped: list[Path] | None) -> list[Path]:
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
            if not include_migrations and is_migration(walked_part(path, root)):
                if skipped is not None:
                    skipped.append(path.resolve())
                continue
            found.append(path)
    return found


def iter_source_files(
    roots: list[Path], include_migrations: bool = False, skipped: list[Path] | None = None
) -> list[Path]:
    """Source files under `roots`. Migrations left out are added to `skipped`."""

    files: set[Path] = set()
    for root in roots:
        for path in _walk(root, include_migrations, skipped):
            files.add(path.resolve())
    return sorted(files, key=lambda path: path.as_posix())
